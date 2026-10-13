#!/usr/bin/env python3
"""Stock-firmware call graph + reachability over out/listing.asm (gp16dis.py output, stock ROM).
Usage: py -3.11 -I reach.py <stock.bin> [--cut F6A1:0106 ...] [--root F6A1:1530 ...] [--why F6A1:27DA]
 --cut  cs:ip of a call/jump instruction whose edge is removed (we patch it away)
 --root extra root (cs:ip)
Prints dead functions (reachable from the stock roots, unreachable once the cuts apply) with byte ranges."""
import sys, re, collections

B = 0xE0000
rom = open(sys.argv[1], 'rb').read()
args = sys.argv[2:]
cuts, xroots, whys, emit = set(), [], [], None
i = 0
while i < len(args):
    a = args[i]
    if a == '--cut': cuts.add(args[i + 1]); i += 2
    elif a == '--root': xroots.append(args[i + 1]); i += 2
    elif a == '--why': whys.append(args[i + 1]); i += 2
    elif a == '--emit': emit = args[i + 1]; i += 2
    else: i += 1


def phys(cs, ip): return (cs * 16 + ip) & 0xFFFFF


def csip(s):
    c, o = s.split(':'); return int(c, 16), int(o, 16)


ins = {}                      # phys -> (cs, ip, size, text)
for l in open('out/listing.asm'):
    m = re.match(r'\s+([0-9A-F]{5}) ([0-9A-F]{4}):([0-9A-F]{4})\s+([0-9a-f]+)\s+(.*)$', l)
    if not m: continue
    p = int(m.group(1), 16) + B
    ins[p] = (int(m.group(2), 16), int(m.group(3), 16), len(m.group(4)) // 2, m.group(5).strip())

# descriptor table: +14 formatter, +18 setter far ptrs
desc = []
for k in range(71):
    r = rom[0x1C396 + 22 * k:0x1C396 + 22 * k + 22]
    for o in (14, 18):
        ip = int.from_bytes(r[o:o + 2], 'little'); cs = int.from_bytes(r[o + 2:o + 4], 'little')
        if B <= phys(cs, ip) < B + len(rom): desc.append((cs, ip))


def jt_targets(p):
    """jmp word ptr cs:[bx + T] at p -> list of (cs, ip)"""
    cs, ip, sz, t = ins[p]
    tab = int(re.search(r'\+ (0x[0-9a-f]+)\]', t).group(1), 16)
    n = None
    q = p
    for _ in range(8):
        prev = [x for x in range(q - 6, q) if x in ins and x + ins[x][2] == q]
        if not prev: break
        q = prev[-1]
        c = re.search(r'cmp (bx|ax|bl|al|cx|dx), (0x[0-9a-f]+|\d+)$', ins[q][3])
        if c: n = int(c.group(2), 0) + 1; break
    n = n or 8
    out = []
    for k in range(min(n, 160)):
        o = phys(cs, tab + 2 * k) - B
        out.append((cs, int.from_bytes(rom[o:o + 2], 'little')))
    return out


def walk(fp):
    """intra-procedural walk from function entry fp -> (body set of insn phys, call edges [(site, callee phys)])"""
    body, calls, work = set(), [], [fp]
    while work:
        p = work.pop()
        while p in ins and p not in body:
            body.add(p)
            cs, ip, sz, t = ins[p]
            site = f'{cs:04X}:{ip:04X}'
            m = t.split(' ', 1)[0]
            op = t.split(' ', 1)[1] if ' ' in t else ''
            nxt = phys(cs, ip + sz)
            if m in ('ret', 'retf', 'iret', 'hlt') or 'RETRBI' in t or 'TSKSW' in t:
                break
            if m == 'call' and op.startswith('0x'):
                calls.append((site, phys(cs, int(op, 16))))
            elif m == 'lcall' and op.startswith('0x'):
                s, o = re.split(r'[:,] *', op); calls.append((site, phys(int(s, 16), int(o, 16))))
            elif m == 'lcall' and '0xa662' in op:
                for d in desc: calls.append((site, phys(*d)))
            elif m == 'ljmp' and op.startswith('0x'):
                s, o = re.split(r'[:,] *', op); calls.append((site, phys(int(s, 16), int(o, 16)))); break
            elif m == 'jmp':
                if op.startswith('0x'):
                    if site in cuts: break
                    work.append(phys(cs, int(op, 16))); break
                if 'cs:[bx +' in op:
                    for tcs, tip in jt_targets(p):
                        work.append(phys(tcs, tip))
                    break
                print('unresolved', site, t); break
            elif (m.startswith('j') or m.startswith('loop')) and op.startswith('0x'):
                if site not in cuts: work.append(phys(cs, int(op, 16)))
            elif t.startswith('BTCLR') or 'BTCLR' in t:
                pass
            p = nxt
    calls = [(s, c) for s, c in calls if s not in cuts]
    return body, calls


# roots: reset + vectors (+ param table pointers as entries) from out/entries.txt, plus the JSW OS far calls
stock_roots = [(0xE83B, 0x0088)]
for v in range(34):
    o = 0x83B0 + v * 4
    ip = int.from_bytes(rom[o:o + 2], 'little'); cs = int.from_bytes(rom[o + 2:o + 4], 'little')
    if B <= phys(cs, ip) < B + len(rom): stock_roots.append((cs, ip))
stock_roots += desc
OS_ROOTS = ['F6A1:03BC', 'F6A1:1530', 'F6A1:1DFA', 'F6A1:0382', 'F00E:0764', 'F00E:1CD2', 'EE11:17F4',
            'E93C:0238', 'E93C:0000', 'E93C:01CA', 'E83B:0626', 'E83B:0679', 'E83B:06CC', 'F2FC:0000',
            'EE11:11BA', 'E93C:00CC', 'E93C:03AE', 'E93C:0422', 'F6A1:0000']
roots = [phys(*r) for r in stock_roots] + [phys(*csip(r)) for r in OS_ROOTS + xroots]

funcs = {}
# credits / demo / init-menu / test-mode text (DS FA00:1AC7-22DA), live refs inside: only the banner's two %s formats (1E5E, 1E62)
TEXT = [(0x1A000 + 0x1AC7, 0x1A000 + 0x1E5E), (0x1A000 + 0x1E66, 0x1A000 + 0x22DB)]


def reach(rs):
    seen, parent, work = set(), {}, list(rs)
    for r in rs: parent[r] = None
    while work:
        f = work.pop()
        if f in seen: continue
        seen.add(f)
        if f not in funcs: funcs[f] = walk(f)
        for site, c in funcs[f][1]:
            if c not in seen and c not in parent: parent[c] = (f, site)
            work.append(c)
    return seen, parent


def name(p):
    cs, ip = ins[p][:2] if p in ins else (0, 0)
    return f'{cs:04X}:{ip:04X}'


if __name__ == '__main__':
    saved = cuts.copy(); cuts.clear()
    full, _ = reach(roots)
    full_body = set().union(*(funcs[f][0] for f in full))
    cuts |= saved; funcs.clear()
    live, parent = reach(roots)
    live_body = set().union(*(funcs[f][0] for f in live))
    dead = sorted(full_body - live_body)
    # jump tables owned by dead indirect jumps die with them
    jt = set()
    for p in dead:
        if 'cs:[bx +' in ins[p][3] and ins[p][3].startswith('jmp'):
            cs, ip = ins[p][:2]
            tab = int(re.search(r'\+ (0x[0-9a-f]+)\]', ins[p][3]).group(1), 16)
            for k in range(len(jt_targets(p))):
                for b in (0, 1): jt.add(phys(cs, tab + 2 * k + b) - B)
    for w in whys:
        p = phys(*csip(w)); chain = []
        while p is not None and p in parent:
            chain.append(name(p)); pr = parent[p]
            if pr is None: break
            chain.append('<-' + pr[1]); p = pr[0]
        print('why', w, ' '.join(chain) if chain else 'NOT REACHED')
    # dead byte ranges
    rngs = []
    for p in dead:
        a, b = p - B, p - B + ins[p][2]
        if rngs and rngs[-1][1] == a: rngs[-1][1] = b
        else: rngs.append([a, b])
    for a in sorted(jt):
        rngs.append([a, a + 1])
    rngs.sort(); m = []
    for a, b in rngs:                # (a single 00 between two dead ranges = word-alignment pad, goes with them)
        if m and (m[-1][1] >= a or (a - m[-1][1] == 1 and rom[m[-1][1]] == 0)): m[-1][1] = max(m[-1][1], b)
        else: m.append([a, b])
    rngs = m
    tot = sum(b - a for a, b in rngs)
    if emit:
        with open(emit, 'w') as f:
            f.write('# ROM ranges [start, end) freed by kill v2.7: dead stock code + jump tables (reach.py), then text\n')
            f.write('# cuts: ' + ' '.join(sorted(cuts)) + '\n')
            for a, b in rngs: f.write(f'{a:05X} {b:05X} code\n')
            for a, b in TEXT: f.write(f'{a:05X} {b:05X} text\n')
        print('wrote', emit, len(rngs), 'code ranges', tot, 'B +', sum(b - a for a, b in TEXT), 'B text')
    dead_f = sorted(full - live)
    print(f'functions: stock-reachable {len(full)}, live {len(live)}, dead {len(dead_f)}; dead code bytes {tot}')
    for f in dead_f: print('  dead fn', name(f), f'rom {f-B:05X}')
    big = sorted(rngs, key=lambda r: r[0] - r[1])[:25]
    for a, b in sorted(big): print(f'  range {a:05X}-{b-1:05X} {b-a} B')
    code_all = sum(v[2] for v in ins.values())
    unreached = sum(ins[p][2] for p in ins if p not in full_body)
    print(f'listing code {code_all} B; not reached even in stock (from these roots): {unreached} B')


def callers_report(dead_f):
    """for each dead function: its call sites in the stock graph (site in which function)"""
    site_fn = {}
    for f, (body, calls) in funcs.items():
        for s, c in calls: site_fn.setdefault(c, []).append((s, f))
    for f in dead_f:
        cl = site_fn.get(f, [])
        print(f'  {name(f)} size~{sum(ins[p][2] for p in funcs[f][0])} <- ' +
              ', '.join(f'{s}({name(g)})' for s, g in cl[:6]) + (' ...' if len(cl) > 6 else ''))
