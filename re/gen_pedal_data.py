#!/usr/bin/env python3
"""Generate pedal_data.inc (NASM) from pedals.py + the KNOBS below: PEDAL (OFF+30) and AMP (OFF+7) tables.
Recipes stay in SYSEX addresses: the menu feeds every (addr, value) pair through the firmware's own DT1 setter
EE11:17F4, so packing (on/off word, 2-byte params, x10/x5/x2 scaling, exp-pedal globals) is done by Roland's code.
Knobs: each knob drives 1-2 SysEx params linearly (v0 at 0, v10 at full). Live updates call the param's own setter
from the descriptor table DS:2396 (p = assignable param number), fed with the INTERNAL value read back from the
buffer (offset parsed from the 17F4 jump table in the stock ROM -- never hand-mapped).
Entry:  name[16], dw kptr, dw extras (block mask, BOARD mode), db npairs, npairs x (sysex addr, value)
Knobs:  db n, def0..def3, n x 22-byte record:
        label[3], steps, disp (0 = 0-10 in halves, 1 = 1-based int), ntg, 2 x (addr, p, ioff, flags, dw v0, dw v10)
        flags bit0 = 2-byte SysEx (msb at addr, lsb at addr+1), bit1 = internal word, bits 4-7 = block (0xF global).
BOARD tables: ped_home (slot per pedal), blk_of (SysEx 0x0C..0x63 -> block), slot_lists, s_slots."""
import importlib.util, os, sys, hashlib, struct

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pedals', os.path.join(here, 'pedals.py'))
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
ROM = open(os.path.join(here, '..', 'dumps', 'gp16_u1_ic11.bin'), 'rb').read()

TWO = {0x3B, 0x45, 0x47, 0x49, 0x4F, 0x53, 0x5F, 0x61}          # 2-byte SysEx params (msb addr)
# assignable param number p (descriptor DS:2396): SysEx 0x0F..0x5B in order, skipping the lsb of 2-byte pairs
SYSEX_P = {}
for a in range(0x0F, 0x5C):
    if a - 1 in TWO:
        continue
    SYSEX_P[a] = len(SYSEX_P)
assert len(SYSEX_P) == 71 and SYSEX_P[0x57] == 66 and SYSEX_P[0x5B] == 70


def internal_map():
    """SysEx addr -> (internal offset, is_word), parsed from the DT1 setter jump table EE11:17F4 (cs:1EDC)."""
    import capstone, re
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    base = 0xE110
    out = {}
    for a in range(0x0F, 0x5C):
        tgt = struct.unpack('<H', ROM[base + 0x1EDC + 2 * a:base + 0x1EDC + 2 * a + 2])[0]
        for i in md.disasm(ROM[base + tgt:base + tgt + 40], tgt):
            m = re.search(r'(byte|word) ptr es:\[bx(?: \+ (0x[0-9a-f]+|\d+))?\]', i.op_str)
            if m:
                out[a] = (int(m.group(2), 0) if m.group(2) else 0, m.group(1) == 'word')
                break
            if i.mnemonic in ('jmp', 'retf', 'ret') and i.op_str == '0x1ed6':
                break
    return out


IMAP = internal_map()
# spot checks against the documented map
assert IMAP[0x0F] == (0x0E, False) and IMAP[0x27] == (0x26, False) and IMAP[0x45] == (0x44, True)
assert IMAP[0x53] == (0x51, False) and IMAP[0x57] == (0x54, False)

# ---------------------------------------------------------------- knobs (label, [(addr, v0, v10)], steps, disp)
REV = [('DEC', [(0x51, 1, 75)]), ('TON', [(0x53, 10, 200)]), ('PRE', [(0x55, 0, 100)]), ('LVL', [(0x56, 0, 100)])]
KNOBS = {
 'tubescreamer': [('DRV', [(0x17, 0, 100)]), ('TON', [(0x16, 0, 100)]), ('LVL', [(0x19, 0, 100)])],
 'rat':          [('DST', [(0x14, 0, 100)]), ('FLT', [(0x13, 85, 10)]), ('VOL', [(0x15, 0, 100)])],
 'ds1':          [('TON', [(0x13, 0, 100)]), ('LVL', [(0x15, 0, 100)]), ('DST', [(0x14, 0, 100)])],
 'bigmuff':      [('VOL', [(0x15, 0, 100)]), ('TON', [(0x13, 0, 100)]), ('SUS', [(0x14, 40, 100), (0x11, 30, 90)])],
 'metalzone':    [('LVL', [(0x15, 0, 100)]), ('HI', [(0x24, 12, 44)]), ('MID', [(0x2A, 0, 44)]), ('DST', [(0x14, 30, 100)])],
 'sd1':          [('LVL', [(0x19, 0, 100)]), ('TON', [(0x16, 0, 100)]), ('DRV', [(0x17, 0, 100)])],
 'klon':         [('GAN', [(0x17, 0, 100)]), ('TRB', [(0x24, 12, 40)]), ('OUT', [(0x19, 0, 100)])],
 'fuzzface':     [('VOL', [(0x15, 0, 100)]), ('FUZ', [(0x14, 30, 100)])],
 'metalmuff':    [('VOL', [(0x15, 0, 100)]), ('BOT', [(0x2C, 8, 40)]), ('TOP', [(0x24, 8, 44)]), ('DST', [(0x14, 30, 100)])],
 'funeral':      [('VOL', [(0x15, 0, 100)]), ('TON', [(0x13, 0, 80)]), ('FUZ', [(0x14, 50, 100)]), ('LOW', [(0x2C, 16, 44)])],
 'ironman':      [('BST', [(0x17, 20, 100)]), ('TRB', [(0x24, 16, 44)]), ('VOL', [(0x19, 0, 100)])],
 'chorus':       [('RAT', [(0x34, 0, 100)]), ('DEP', [(0x35, 0, 100)])],
 'dimensiond':   [('MOD', [(0x41, 0, 3)], 3, 1)],
 'phaser':       [('SPD', [(0x1E, 0, 100)])],
 'flanger':      [('MAN', [(0x39, 0, 100)]), ('DEP', [(0x38, 0, 100)]), ('RAT', [(0x37, 0, 100)]), ('RES', [(0x3A, 0, 100)])],
 'tremolo':      [('RAT', [(0x42, 0, 100)]), ('DEP', [(0x43, 0, 100)])],
 'leslie':       [('SPD', [(0x42, 10, 90), (0x34, 5, 80)]), ('DEP', [(0x43, 0, 100), (0x35, 0, 100)])],
 'slapback':     [('TIM', [(0x31, 0, 100)]), ('LVL', [(0x32, 0, 100)])],
 'digital':      [('LVL', [(0x4B, 0, 100)]), ('FBK', [(0x4E, 0, 100)]), ('TIM', [(0x45, 20, 1200)])],
 'spaceecho':    [('RPT', [(0x45, 800, 100)]), ('INT', [(0x4E, 0, 95)]), ('ECH', [(0x4B, 0, 100)]), ('TON', [(0x4F, 20, 200)])],
 'spring': REV, 'hallplate': REV, 'shimmer': REV, 'cathedral': REV, 'cave': REV, 'church': REV, 'stage': REV,
 'ambient': REV,
 'crybaby':      [('Q', [(0x1C, 0, 40)])],
 'dynacomp':     [('OUT', [(0x12, 0, 100)]), ('SNS', [(0x11, 0, 100)])],
 'cs3':          [('LVL', [(0x12, 0, 100)]), ('TON', [(0x0F, 0, 100)]), ('ATK', [(0x10, 0, 100)]), ('SUS', [(0x11, 0, 100)])],
 'touchwah':     [('SNS', [(0x1A, 0, 100)]), ('RNG', [(0x1B, 0, 100)]), ('Q', [(0x1C, 0, 40)])],
 'slicer':       [('RAT', [(0x1E, 0, 100)]), ('DEP', [(0x1F, 0, 100)]), ('STP', [(0x22, 0, 100)])],
 'ge7':          [('LO', [(0x2C, 0, 48)]), ('LM', [(0x2A, 0, 48)]), ('HM', [(0x27, 0, 48)]), ('HI', [(0x24, 0, 48)])],
 'ns2':          [('THR', [(0x2E, 0, 100)]), ('DEC', [(0x2F, 0, 100)])],
 'doubler':      [('TIM', [(0x31, 0, 30)]), ('LVL', [(0x32, 0, 100)])],
 'octave':       [('INT', [(0x3D, 0, 24)], 24, 2), ('MIX', [(0x3B, 0, 200)]), ('FIN', [(0x3E, 0, 100)])],
 'autopan':      [('RAT', [(0x42, 0, 100)]), ('DEP', [(0x43, 0, 100)])],
 'resowah':      [('Q', [(0x1C, 0, 40)])],
}
AMP_KNOBS = {
 'clean':  [('VOL', [(0x5B, 40, 100)]), ('TRB', [(0x58, 0, 100)]), ('BAS', [(0x5A, 0, 100)])],
 'twin':   [('VOL', [(0x5B, 40, 100)]), ('TRB', [(0x58, 0, 100)]), ('MID', [(0x59, 0, 100)]), ('BAS', [(0x5A, 0, 100)])],
 'jcm800': [('PRS', [(0x57, 0, 100)]), ('BAS', [(0x5A, 0, 100)]), ('MID', [(0x59, 0, 100)]), ('TRB', [(0x58, 0, 100)])],
 'ac30':   [('VOL', [(0x5B, 40, 100)]), ('TRB', [(0x58, 0, 100)]), ('BAS', [(0x5A, 0, 100)]), ('CUT', [(0x57, 90, 10)])],
 'doom':   [('VOL', [(0x5B, 40, 100)]), ('BAS', [(0x5A, 0, 100)]), ('MID', [(0x59, 0, 100)]), ('TRB', [(0x58, 0, 100)])],
 'di':     [('VOL', [(0x5B, 40, 100)])],
 'radio':  [('TUN', [(0x28, 20, 80), (0x25, 30, 90)]), ('VOL', [(0x5B, 40, 100)])],
}

# ---------------------------------------------------------------- BOARD mode (v0.9)
# 12 blocks in chain order = board slots. A pedal sits in its HOME slot and may grab EXTRA blocks its recipe uses.
SLOTS = ['A1 COMP', 'A2 DIRT', 'A3 WAH/FILTER', 'A4 PHASER', 'A5 EQ', 'A6 GATE', 'B1 SHORT DELAY', 'B2 MOD',
         'B3 TREM/PAN', 'B4 DELAY', 'B5 REVERB', 'B6 AMP/CAB', 'ORDER', 'OUT A/B/Y BOX']
HOME = {}
for k in ('dynacomp', 'cs3'): HOME[k] = 0
for k in ('tubescreamer', 'rat', 'ds1', 'bigmuff', 'metalzone', 'sd1', 'klon', 'fuzzface', 'metalmuff', 'funeral',
          'ironman'): HOME[k] = 1
for k in ('crybaby', 'resowah', 'touchwah'): HOME[k] = 2
for k in ('phaser', 'slicer'): HOME[k] = 3
HOME['ge7'] = 4; HOME['ns2'] = 5
for k in ('slapback', 'doubler'): HOME[k] = 6
for k in ('chorus', 'dimensiond', 'flanger', 'leslie', 'octave'): HOME[k] = 7
for k in ('tremolo', 'autopan'): HOME[k] = 8
for k in ('digital', 'spaceecho'): HOME[k] = 9
for k in ('spring', 'hallplate', 'shimmer', 'cathedral', 'cave', 'church', 'stage', 'ambient'): HOME[k] = 10
GLOBAL = 0x0F


def blk_of(a):
    for lo, hi, b in ((0x0F, 0x12, 0), (0x13, 0x19, 1), (0x1A, 0x1D, 2), (0x1E, 0x22, 3), (0x23, 0x2D, 4),
                      (0x2E, 0x30, 5), (0x31, 0x32, 6), (0x33, 0x41, 7), (0x42, 0x44, 8), (0x45, 0x50, 9),
                      (0x51, 0x56, 10), (0x57, 0x5B, 11)):
        if lo <= a <= hi:
            return b
    if 0x0C <= a <= 0x0E:
        return 0xEE
    return GLOBAL


def blocks_on(rec):
    return rec.get(0x0E, 0) & 0x7F | (rec.get(0x0D, 0) & 0x1F) << 7


def extras(rec, home):
    m = blocks_on(rec) & ~(1 << home)
    if home != 5:
        m &= ~(1 << 5)                    # dirt recipes' gate stays in the gate slot
    return m


NAMES = {  # display names, <= 13 chars (rig rows use 3 for the label)
 'tubescreamer': 'TUBE SCREAMER', 'rat': 'RAT', 'ds1': 'DS-1', 'bigmuff': 'BIG MUFF', 'metalzone': 'METAL ZONE',
 'sd1': 'SD-1', 'klon': 'KLON', 'fuzzface': 'FUZZ FACE', 'metalmuff': 'METAL MUFF', 'funeral': 'FUNERAL',
 'ironman': 'IRON MAN', 'chorus': 'CHORUS CE-2', 'dimensiond': 'DIMENSION D', 'phaser': 'PHASE 90',
 'flanger': 'FLANGER', 'tremolo': 'TREMOLO', 'leslie': 'LESLIE', 'slapback': 'SLAPBACK', 'digital': 'DIGITAL DLY',
 'spaceecho': 'SPACE ECHO', 'spring': 'SPRING', 'hallplate': 'HALL/PLATE', 'shimmer': 'SHIMMER',
 'cathedral': 'CATHEDRAL', 'cave': 'CAVE', 'church': 'CHURCH', 'stage': 'STAGE', 'ambient': 'AMBIENT',
 'crybaby': 'CRYBABY WAH', 'resowah': 'RESO WAH',
 'dynacomp': 'DYNA COMP', 'cs3': 'CS-3 COMP', 'touchwah': 'TOUCH WAH', 'slicer': 'SLICER', 'ge7': 'GE-7 EQ',
 'ns2': 'NS-2 GATE', 'doubler': 'DOUBLER', 'octave': 'PITCH/OCTAVE', 'autopan': 'AUTOPAN',
 'clean': 'CLEAN', 'twin': 'TWIN', 'jcm800': 'JCM800', 'ac30': 'AC30', 'doom': 'DOOM', 'di': 'DI / FLAT',
 'radio': 'RADIO',
}


def pairs_of(rec):
    out = []
    for a, v in sorted(rec.items()):
        assert 0x0C <= a <= 0x63, f'addr {a:#x} outside the patch params (order/name/request bytes not allowed)'
        assert 0 <= v <= 0x7F, f'value {v} at {a:#x} not 7-bit'
        out.append((a, v))
    return out


def knob_block(knobs, rec):
    """-> (defaults[4], records[] as byte strings)"""
    assert len(knobs) <= 4
    defs, recs = [], []
    for kn in knobs:
        label, tg = kn[0], kn[1]
        steps = kn[2] if len(kn) > 2 else 20
        disp = kn[3] if len(kn) > 3 else 0      # 0 = 0-10 in halves, 1 = 1-based int, 2 = signed (k - steps/2)
        assert 1 <= len(tg) <= 2 and len(label) <= 3
        a0, v0, v10 = tg[0]
        cur = rec.get(a0, 0) * 128 + rec.get(a0 + 1, 0) if a0 in TWO else rec.get(a0)
        if cur is None:
            d = steps // 2 if disp in (0, 2) else 0
        else:
            d = max(0, min(steps, round((cur - v0) / (v10 - v0) * steps)))
        defs.append(d)
        b = label.ljust(3).encode() + bytes([steps, disp, len(tg)])
        for a, lo, hi in tg + [(0, 0, 0)] * (2 - len(tg)):
            if a == 0:
                b += bytes(8); continue
            two = a in TWO
            assert two or (0 <= lo <= 127 and 0 <= hi <= 127), f'{label} {a:#x} needs 7-bit range'
            ioff, word = IMAP[a]
            b += bytes([a, SYSEX_P.get(a, 0xFF), ioff, (1 if two else 0) | (2 if word else 0) | blk_of(a) << 4])
            b += struct.pack('<hh', lo, hi)
        assert len(b) == 22
        recs.append(b)
    return defs + [0] * (4 - len(defs)), recs


def table(label, recs, knobs, home):
    lines = [f'{label}_off:']
    lines.append('    dw ' + ', '.join(f'{label}_e{i}' for i in range(len(recs) + 1)))
    entries = [('OFF', [], [], 0)]
    for k, r in recs.items():
        entries.append((NAMES[k], pairs_of(r), knob_block(knobs.get(k, []), r), extras(r, home(k))))
    kdata = b''
    for i, (nm, pairs, kb, ex) in enumerate(entries):
        nm16 = nm.ljust(16)[:16]
        lines.append(f'{label}_e{i}: db "{nm16}"')
        lines.append(f'    dw {label}_k{i}, 0x{ex:04x}')
        lines.append(f'    db {len(pairs)}' + (', ' + ', '.join(f'0x{a:02x},{v}' for a, v in pairs) if pairs else ''))
        defs, krecs = kb if kb else ([0] * 4, [])
        blob = bytes([len(krecs)] + defs) + b''.join(krecs)
        kdata += blob
        lines.append(f'{label}_k{i}: db ' + ', '.join(str(x) for x in blob))
    return lines, kdata


if __name__ == '__main__':
    missing = [k for k in P.PEDALS if k not in KNOBS] + [k for k in P.AMPS if k not in AMP_KNOBS]
    missing += [k for k in P.PEDALS if k not in HOME]
    assert not missing, f'no knobs/home for {missing}'
    pl, pk = table('ped', P.PEDALS, KNOBS, lambda k: HOME[k])
    al, ak = table('amp', P.AMPS, AMP_KNOBS, lambda k: 11)
    PK = list(P.PEDALS)
    body = pl + al
    body.append('ped_home: db 0xff, ' + ', '.join(str(HOME[k]) for k in PK))
    body.append('blk_of: db ' + ', '.join(f'0x{blk_of(a):02x}' for a in range(0x0C, 0x64)))
    body.append('slot_lists: dw ' + ', '.join(f'sl{i}' for i in range(12)))
    for i in range(11):
        idx = [PK.index(k) + 1 for k in PK if HOME[k] == i]
        body.append(f'sl{i}: db {len(idx)}, ' + ', '.join(str(x) for x in idx))
    body.append(f'sl11: db {len(P.AMPS)}, ' + ', '.join(str(i + 1) for i in range(len(P.AMPS))))
    body.append('s_slots: db ' + ', '.join('"' + n.ljust(16) + '"' for n in SLOTS))
    magic = hashlib.md5('\n'.join(body).encode()).digest()[0] | 0x01
    if magic == 0xFF: magic = 0x81
    out = ['; generated by gen_pedal_data.py -- do not edit',
           f'KMAGIC equ 0x{magic:02x}          ; changes whenever the tables change -> stored knobs/board reset',
           f'NPED equ {len(P.PEDALS)}', f'NAMP equ {len(P.AMPS)}'] + body
    open(os.path.join(here, 'pedal_data.inc'), 'w').write('\n'.join(out) + '\n')
    print(f'pedal_data.inc: {len(P.PEDALS)+1} pedals, {len(P.AMPS)+1} amps, knob data {len(pk)+len(ak)} B, magic {magic:#04x}')
    for k in ('bigmuff', 'leslie', 'tubescreamer'):
        print(f'  {k}: home {SLOTS[HOME[k]]}, extras', [SLOTS[b] for b in range(12) if extras(P.PEDALS[k], HOME[k]) >> b & 1])
    for k in ('jcm800', 'doom'):
        print(f'  {k}: extras', [SLOTS[b] for b in range(12) if extras(P.AMPS[k], 11) >> b & 1])
