#!/usr/bin/env python3
"""GP-16 (NEC V25) recursive-descent disassembler.
ROM = 128 KB mapped at E0000-FFFFF. Handles V20/V25 0F-prefixed extras that capstone does not know.
Usage: py -3.11 -I gp16dis.py <rom.bin> <out_dir>
Writes: listing.asm, functions.txt, xrefs.txt, far_targets.txt
"""
import sys, os, collections, capstone

ROM_BASE = 0xE0000
PREFIXES = {0x26, 0x2E, 0x36, 0x3E, 0xF0, 0xF2, 0xF3}
SEGPFX = {0x26: 'es', 0x2E: 'cs', 0x36: 'ss', 0x3E: 'ds'}

# V25 SFR names (offset inside the 256-byte SFR page, page base = IDB*0x1000 + 0xF00)
SFR = {0x00:'P0',0x01:'PM0',0x02:'PMC0',0x08:'P1',0x09:'PM1',0x0A:'PMC1',0x10:'P2',0x11:'PM2',0x12:'PMC2',
       0x38:'PT',0x3B:'PMT',0x40:'INTM',0x44:'EMS0',0x45:'EMS1',0x46:'EMS2',0x4C:'EXIC0',0x4D:'EXIC1',0x4E:'EXIC2',
       0x60:'RXB0',0x62:'TXB0',0x65:'SRMS0',0x66:'STMS0',0x68:'SCM0',0x69:'SCC0',0x6A:'BRG0',0x6B:'SCE0',
       0x6C:'SEIC0',0x6D:'SRIC0',0x6E:'STIC0',0x70:'RXB1',0x72:'TXB1',0x75:'SRMS1',0x76:'STMS1',0x78:'SCM1',
       0x79:'SCC1',0x7A:'BRG1',0x7B:'SCE1',0x7C:'SEIC1',0x7D:'SRIC1',0x7E:'STIC1',0x80:'TM0',0x82:'MD0',0x88:'TM1',
       0x8A:'MD1',0x90:'TMC0',0x91:'TMC1',0x9C:'TMIC0',0x9D:'TMIC1',0x9E:'TMIC2',0xA0:'DMAC0',0xA1:'DMAM0',
       0xA2:'DMAC1',0xA3:'DMAM1',0xAC:'DIC0',0xAD:'DIC1',0xE0:'STBC',0xE1:'RFM',0xE8:'WTC',0xEA:'FLAG',0xEB:'PRC',
       0xEC:'TBIC',0xEF:'IRQS',0xFC:'ISPR',0xFF:'IDB'}


def modrm_len(b, i):
    """length of modrm + displacement starting at b[i]"""
    m = b[i]; mod = m >> 6; rm = m & 7
    if mod == 0: return 3 if rm == 6 else 1
    if mod == 1: return 2
    if mod == 2: return 3
    return 1


class Insn:
    __slots__ = ('phys', 'cs', 'ip', 'size', 'text', 'kind', 'targets', 'raw')


def decode_0f(b, i):
    """V20/V25 extended opcode at b[i]==0x0F. returns (len_from_0F, text, kind, rel_target_or_None)"""
    op = b[i + 1]
    if 0x10 <= op <= 0x17:
        names = ['TEST1', 'TEST1', 'CLR1', 'CLR1', 'SET1', 'SET1', 'NOT1', 'NOT1']
        n = 2 + modrm_len(b, i + 2)
        return n, f"{names[op-0x10]} {'w' if op & 1 else 'b'}[modrm {b[i+2]:02x}], cl", 'seq', None
    if 0x18 <= op <= 0x1F:
        names = ['TEST1', 'TEST1', 'CLR1', 'CLR1', 'SET1', 'SET1', 'NOT1', 'NOT1']
        ml = modrm_len(b, i + 2); n = 2 + ml + 1
        return n, f"{names[op-0x18]} {'w' if op & 1 else 'b'}[modrm {b[i+2]:02x} {b[i+3:i+2+ml].hex()}], bit {b[i+2+ml]}", 'seq', None
    if op in (0x20, 0x22, 0x26):
        return 2, {0x20: 'ADD4S', 0x22: 'SUB4S', 0x26: 'CMP4S'}[op], 'seq', None
    if op in (0x28, 0x2A):
        return 2 + modrm_len(b, i + 2), ('ROL4' if op == 0x28 else 'ROR4') + f" [modrm {b[i+2]:02x}]", 'seq', None
    if op in (0x31, 0x33):
        return 3, ('INS' if op == 0x31 else 'EXT') + f" modrm {b[i+2]:02x}", 'seq', None
    if op in (0x39, 0x3B):
        return 4, ('INS' if op == 0x39 else 'EXT') + f" modrm {b[i+2]:02x}, {b[i+3]}", 'seq', None
    if op == 0x25: return 2, 'MOVSPA', 'seq', None
    if op == 0x2D: return 3, f"BRKCS modrm {b[i+2]:02x}", 'seq', None
    if op == 0x91: return 2, 'RETRBI', 'ret', None
    if op == 0x92: return 2, 'FINT', 'seq', None
    if op == 0x94: return 3, f"TSKSW modrm {b[i+2]:02x}", 'ret', None
    if op == 0x95: return 3, f"MOVSPB modrm {b[i+2]:02x}", 'seq', None
    if op == 0x9C:
        sfr = b[i + 2]; bit = b[i + 3] & 7; disp = b[i + 4]; disp = disp - 256 if disp > 127 else disp
        return 5, f"BTCLR {SFR.get(sfr, hex(sfr))}, {bit}", 'jcc', disp
    if op == 0x9E: return 2, 'STOP', 'seq', None
    if op == 0xFF: return 3, f"BRKEM {b[i+2]:02x}", 'seq', None
    return None


def main():
    rom = open(sys.argv[1], 'rb').read()
    out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    md.detail = False

    def rb(phys):
        o = phys - ROM_BASE
        return rom[o:o + 16] if 0 <= o < len(rom) else b''

    insns = {}          # phys -> Insn
    owner = {}          # phys byte -> insn phys
    funcs = {}          # phys -> (cs, ip, kind)
    xref = collections.defaultdict(list)   # target phys -> [(from phys, kind)]
    bad = []
    work = []

    def add(cs, ip, why, src=None):
        ip &= 0xFFFF
        p = (cs * 16 + ip) & 0xFFFFF
        if not (ROM_BASE <= p < ROM_BASE + len(rom)): return
        if src is not None: xref[p].append((src, why))
        if why in ('call', 'callf', 'entry', 'vector'):
            funcs.setdefault(p, (cs, ip, why))
        work.append((cs, ip))

    add(0xE83B, 0x0088, 'entry')
    extra = sys.argv[3:] if len(sys.argv) > 3 else []
    for e in extra:
        s, o = e.split(':'); add(int(s, 16), int(o, 16), 'vector')

    while work:
        cs, ip = work.pop()
        while True:
            p = (cs * 16 + ip) & 0xFFFFF
            if p in insns or not (ROM_BASE <= p < ROM_BASE + len(rom)): break
            if p in owner:   # jumped into the middle of an instruction
                bad.append((p, 'overlap')); break
            b = rb(p) + b'\x00' * 8
            j = 0
            while j < len(b) and b[j] in PREFIXES: j += 1
            I = Insn(); I.phys = p; I.cs = cs; I.ip = ip; I.targets = []
            if b[j] == 0x0F:
                r = decode_0f(b, j)
                if r is None:
                    bad.append((p, f'unknown 0F {b[j+1]:02x}')); break
                n, text, kind, rel = r
                I.size = j + n; pre = ' '.join(SEGPFX.get(x, hex(x)) for x in b[:j])
                I.text = (pre + ': ' if pre else '') + text; I.kind = kind
                if rel is not None:
                    I.targets.append((cs, (ip + I.size + rel) & 0xFFFF))
            else:
                ins = next(md.disasm(b, ip, 1), None)
                if ins is None:
                    bad.append((p, f'undecodable {b[:4].hex()}')); break
                I.size = ins.size; I.text = f"{ins.mnemonic} {ins.op_str}".strip()
                m = ins.mnemonic; ops = ins.op_str
                I.kind = 'seq'
                if m in ('ret', 'retf', 'iret', 'hlt'): I.kind = 'ret'
                elif m == 'jmp':
                    if ins.bytes[-5 + 0:][:1] == b'\xea' or (ins.bytes[0] == 0xEA or b[j] == 0xEA):
                        tip = int.from_bytes(b[j+1:j+3], 'little'); tcs = int.from_bytes(b[j+3:j+5], 'little')
                        I.kind = 'jmpf'; I.targets.append((tcs, tip))
                    elif ops.startswith('0x'):
                        I.kind = 'jmp'; I.targets.append((cs, int(ops, 16)))
                    else: I.kind = 'jmpi'
                elif m == 'call' or m == 'lcall':
                    if b[j] == 0x9A:
                        tip = int.from_bytes(b[j+1:j+3], 'little'); tcs = int.from_bytes(b[j+3:j+5], 'little')
                        I.kind = 'callf'; I.targets.append((tcs, tip))
                    elif ops.startswith('0x'):
                        I.kind = 'call'; I.targets.append((cs, int(ops, 16)))
                    else: I.kind = 'calli'
                elif m == 'ljmp':
                    tip = int.from_bytes(b[j+1:j+3], 'little'); tcs = int.from_bytes(b[j+3:j+5], 'little')
                    I.kind = 'jmpf'; I.targets.append((tcs, tip))
                elif m.startswith('j') or m.startswith('loop'):
                    I.kind = 'jcc'; I.targets.append((cs, int(ops, 16)))
            I.raw = rb(p)[:I.size]
            insns[p] = I
            for k in range(I.size): owner[p + k] = p
            for tcs, tip in I.targets:
                add(tcs, tip, I.kind, p)
            if I.kind in ('ret', 'jmp', 'jmpf', 'jmpi'): break
            ip = (ip + I.size) & 0xFFFF

    # ---- listing
    with open(os.path.join(out, 'listing.asm'), 'w') as f:
        last = None
        for p in sorted(insns):
            I = insns[p]
            if last is not None and p != last:
                f.write(f"\n; ---- gap {last-ROM_BASE:05X}-{p-ROM_BASE-1:05X} ({p-last} bytes)\n")
            if p in funcs:
                f.write(f"\n; ======== FUNCTION {I.cs:04X}:{I.ip:04X}  (rom {p-ROM_BASE:05X})  via {funcs[p][2]}\n")
            elif p in xref:
                f.write(f"L_{p-ROM_BASE:05X}:\n")
            f.write(f"  {p-ROM_BASE:05X} {I.cs:04X}:{I.ip:04X}  {I.raw.hex():16s} {I.text}\n")
            last = p + I.size
    with open(os.path.join(out, 'functions.txt'), 'w') as f:
        for p in sorted(funcs):
            cs, ip, why = funcs[p]
            f.write(f"{p-ROM_BASE:05X} {cs:04X}:{ip:04X} {why} callers={len(xref.get(p, []))}\n")
    with open(os.path.join(out, 'bad.txt'), 'w') as f:
        for p, why in bad: f.write(f"{p-ROM_BASE:05X} {why}\n")
    code = sum(I.size for I in insns.values())
    segs = collections.Counter(I.cs for I in insns.values())
    print(f"insns {len(insns)}  code bytes {code} ({code/1024:.1f} KB)  functions {len(funcs)}  bad {len(bad)}")
    print("code segments:", ', '.join(f"{s:04X}x{n}" for s, n in segs.most_common()))
    lo = min(insns) - ROM_BASE; hi = max(insns) - ROM_BASE
    print(f"code span rom {lo:05X}-{hi:05X}")


if __name__ == '__main__':
    main()
