#!/usr/bin/env python3
"""Generate pedal_data.inc (NASM) from pedals.py + the KNOBS below: PEDAL (OFF+n) and AMP (OFF+n) tables. (v1.0 format)
Recipes stay in SYSEX addresses: the menu feeds every (addr, value) pair through the firmware's own DT1 setter
EE11:17F4, so packing (on/off word, 2-byte params, x10/x5/x2 scaling, exp-pedal globals) is done by Roland's code.
Knobs: each knob drives any number of SysEx params ("macro"), each either linear (v0 at 0, v10 at full) or by a value
table (one value per step, 0xFF = leave alone). Live updates call the param's own setter from the descriptor table
DS:2396 (p = assignable param number), fed with the INTERNAL value read back from the buffer (offset parsed from the
17F4 jump table in the stock ROM -- never hand-mapped).
Entry:  name[16], dw kptr, dw extras (block mask, BOARD mode), dw kstore (RAM), db npairs, npairs x (sysex addr, value)
Knobs:  db n, def[n], n records: rlen, label[3], steps, disp, ntg, deps (bit j = re-apply knob j after a live move), targets
        target: linear 1-byte param  addr, v0, v10            (3 B)
                linear 2-byte param  addr, dw v0, dw v10      (5 B, msb at addr, lsb at addr+1)
                table                addr|0x80, steps+1 values (0xFF = skip)
        disp: 0 = 0-10 in halves, 1 = 1-based int, 2 = signed (k - steps/2), 3 = OFF/ON, 4 = LO/HI,
              5 = mode buttons (knob 0 only: buttons 1-4 pick mode 1-4, the lit one again = 0).
        5-6 knobs: names-over-numbers screen, 2-char labels, whole steps 0-10.
ainfo:  3 B per SysEx addr 0x0C..0x63: block | two << 4 | word << 5, p (FF none), internal offset.
BOARD tables: ped_home (slot per pedal), slot_lists, s_slots."""
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
assert len(SYSEX_P) == 71 and SYSEX_P[0x57] == 66 and SYSEX_P[0x5B] == 70 and SYSEX_P[0x3D] == 45

KS_BASE = 0xB000          # knob stores in battery RAM (no stock refs in DS A800-CDFF)
KS_END = 0xB400           # board memories follow (pedal_menu.asm BMEM)


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

# ---------------------------------------------------------------- knobs (label, [targets], steps, disp, default)
# target = (addr, v0, v10) linear, or (addr, [value per step]) table (0xFF = leave alone). v2: real-unit ranges via
# pedals.py helpers (db = EQ dB, cut = delay/reverb cutoff Hz); each knob does what the original pedal's knob does.
db, cut = P.db, P.cut
REV = [('DEC', [(0x51, 1, 75)]), ('TON', [(0x53, cut(1000), 200)]), ('PRE', [(0x55, 0, 100)]), ('LVL', [(0x56, 0, 100)])]
TILT_MUFF = [(0x24, db(-10), db(+6)), (0x2C, db(+6), db(-6))]        # Muff tone stack: lows <-> highs, scoop stays
KNOBS = {
 'tubescreamer': [('DRV', [(0x17, 5, 90)]), ('TON', [(0x16, 20, 80), (0x24, db(-10), db(+2))]), ('LVL', [(0x19, 0, 100)])],
 'rat':          [('DST', [(0x14, 15, 100)]), ('FLT', [(0x24, db(+3), db(-12)), (0x27, db(+4), db(-4)), (0x13, 75, 20)]),
                  ('VOL', [(0x15, 0, 100)])],
 'ds1':          [('TON', [(0x24, db(-8), db(+7)), (0x2C, db(+4), db(-4)), (0x13, 30, 80)]), ('LVL', [(0x15, 0, 100)]),
                  ('DST', [(0x14, 10, 100)])],
 'bigmuff':      [('VOL', [(0x15, 0, 100)]), ('TON', TILT_MUFF), ('SUS', [(0x14, 45, 100), (0x11, 30, 85)])],
 'metalzone':    [('LO', [(0x2C, 0, 48)], 10), ('HM', [(0x27, 0, 48)], 10), ('LM', [(0x2A, 0, 48)], 10),
                  ('H', [(0x24, 0, 48)], 10), ('G', [(0x14, 30, 100)], 10), ('L', [(0x15, 0, 100)], 10)],
 'sd1':          [('LVL', [(0x19, 0, 100)]), ('TON', [(0x16, 25, 85), (0x24, db(-6), db(+4))]), ('DRV', [(0x17, 5, 90)])],
 'klon':         [('GAN', [(0x17, 0, 75), (0x27, db(+1), db(+5))]), ('TRB', [(0x24, db(-6), db(+8))]), ('OUT', [(0x19, 30, 100)])],
 'fuzzface':     [('VOL', [(0x15, 0, 100)]), ('FUZ', [(0x14, 30, 100), (0x24, db(-2), db(-8))])],
 'metalmuff':    [('VOL', [(0x15, 0, 100)]), ('BOT', [(0x2C, db(-8), db(+10))]), ('TOP', [(0x24, db(-6), db(+10))]),
                  ('DST', [(0x14, 40, 100)])],
 # Funeral VOL goes past real-pedal range: top half = boost (fuzz level + comp makeup gain + EQ out, all to max)
 'funeral':      [('VOL', [(0x15, 20, 100), (0x12, 40, 100), (0x2D, db(+2), db(+12))], 20, 0, 12),
                  ('FUZ', [(0x14, 50, 100), (0x11, 40, 90)]), ('WAH', [(0x1B, 5, 95)]),
                  ('LOW', [(0x2C, db(-4), db(+10))])],          # WAH = where the wah is parked
 'ironman':      [('BST', [(0x17, 30, 100), (0x27, db(+2), db(+7))]), ('TRB', [(0x24, db(-4), db(+8))]), ('VOL', [(0x19, 0, 100)])],
 'chorus':       [('RAT', [(0x34, 0, 100)]), ('DEP', [(0x35, 0, 100)])],
 'dimensiond':   [('MOD', [(0x41, 0, 3)], 3, 1)],
 'phaser':       [('SPD', [(0x1E, 0, 100)]), ('BLK', [(0x21, [25, 60])], 1, 3)],       # script / block-logo feedback
 'flanger':      [('MAN', [(0x39, 0, 100)]), ('DEP', [(0x38, 0, 100)]), ('RAT', [(0x37, 0, 100)]), ('RES', [(0x3A, 0, 100)])],
 'tremolo':      [('RAT', [(0x42, 0, 100)]), ('DEP', [(0x43, 0, 100)])],
 'leslie':       [('SPD', [(0x42, [12, 72]), (0x34, [10, 65])], 1, 4), ('DEP', [(0x43, 20, 100), (0x35, 20, 90)]),
                  ('DRV', [(0x17, 0, 60)])],                    # chorale / tremolo switch, preamp growl
 'slapback':     [('TIM', [(0x31, 40, 100)]), ('LVL', [(0x32, 0, 100)])],
 'digital':      [('LVL', [(0x4B, 0, 100)]), ('FBK', [(0x4E, 0, 100)]), ('TIM', [(0x45, 20, 1200)])],
 'spaceecho':    [('RPT', [(0x45, 900, 150), (0x47, 300, 50), (0x49, 600, 100)]), ('INT', [(0x4E, 0, 95)]),
                  ('MOD', [(0x4C, [70, 0, 0, 50]), (0x4D, [0, 70, 0, 50]), (0x4B, [0, 0, 70, 50])], 3, 1),   # head 1/2/3/all
                  ('REV', [(0x56, 0, 60)])],
 'spring':       [('DWL', [(0x56, 15, 85), (0x51, 8, 30)]), ('TON', [(0x53, cut(1500), cut(6000))]), ('TYP', [(0x52, [8, 9])], 1, 1)],
 'hallplate': REV, 'cathedral': REV, 'church': REV, 'stage': REV,
 'shimmer':      [('DEC', [(0x51, 20, 75)]), ('SHM', [(0x3B, 0, 120), (0x3F, 0, 70)]), ('TON', [(0x53, cut(1000), 200)]),
                  ('LVL', [(0x56, 0, 100)])],
 'cave':         [('DEC', [(0x51, 20, 75)]), ('ECH', [(0x4B, 0, 60), (0x4C, 0, 50), (0x4D, 0, 50)]),
                  ('TON', [(0x53, cut(800), cut(5000))]), ('LVL', [(0x56, 0, 100)])],
 'ambient':      [('DEC', [(0x51, 20, 75)]), ('SWL', [(0x35, 0, 90), (0x36, 0, 70)]), ('TON', [(0x53, cut(1000), 200)]),
                  ('LVL', [(0x56, 0, 100)])],
 'crybaby':      [('Q', [(0x1C, 10, 40)]), ('TOP', [(0x60, 60, 100)]), ('BOT', [(0x62, 0, 40)])],   # sweep range = exp max/min
 'resowah':      [('Q', [(0x1C, 10, 40)]), ('TOP', [(0x60, 60, 100)]), ('BOT', [(0x62, 0, 40)])],
 'dynacomp':     [('OUT', [(0x12, 0, 100)]), ('SNS', [(0x11, 0, 100)])],
 'cs3':          [('LVL', [(0x12, 0, 100)]), ('TON', [(0x0F, 0, 100)]), ('ATK', [(0x10, 0, 100)]), ('SUS', [(0x11, 0, 100)])],
 'touchwah':     [('SNS', [(0x1A, 0, 100)]), ('RNG', [(0x1B, 0, 100)]), ('Q', [(0x1C, 0, 40)])],
 'slicer':       [('RAT', [(0x1E, 0, 100)]), ('DEP', [(0x1F, 0, 100)]), ('STP', [(0x22, 0, 100)])],
 'ge7':          [('LO', [(0x2C, 0, 48)]), ('LM', [(0x2A, 0, 48)]), ('HM', [(0x27, 0, 48)]), ('HI', [(0x24, 0, 48)])],
 'ns2':          [('THR', [(0x2E, 0, 100)]), ('DEC', [(0x2F, 0, 100)])],
 'doubler':      [('TIM', [(0x31, 0, 30)]), ('LVL', [(0x32, 0, 100)])],
 'octave':       [('INT', [(0x3D, 0, 24)], 24, 2), ('MIX', [(0x3B, 0, 200)]), ('FIN', [(0x3E, 0, 100)])],
 'autopan':      [('RAT', [(0x42, 0, 100)]), ('DEP', [(0x43, 0, 100)])],
 # v1 picks
 'hm2':          [('LVL', [(0x15, 0, 100)]), ('LOW', [(0x2C, db(0), db(+12))]),
                  ('HI', [(0x27, db(0), db(+12)), (0x24, db(0), db(+5))]), ('DST', [(0x14, 40, 100)])],
 'rangemaster':  [('BST', [(0x17, 10, 65), (0x27, db(+3), db(+9))]), ('VOL', [(0x19, 0, 100)])],
 'od1':          [('LVL', [(0x19, 0, 100)]), ('DRV', [(0x17, 5, 90), (0x27, db(+4), db(+6))])],
 'fuzzfactory':  [('VL', [(0x15, 0, 100)], 10), ('GT', [(0x2E, 0, 100), (0x2F, 60, 5)], 10), ('CP', [(0x11, 0, 100)], 10),
                  ('DR', [(0x14, 50, 100)], 10), ('SB', [(0x13, 100, 20)], 10)],
 'octavia':      [('VOL', [(0x15, 0, 100)]), ('FUZ', [(0x14, 40, 100)]), ('OCT', [(0x3B, 0, 200)]), ('TON', [(0x13, 20, 100)])],
 'ramshead':     [('VOL', [(0x15, 0, 100)]), ('TON', TILT_MUFF), ('SUS', [(0x14, 40, 100), (0x11, 30, 85)])],
 'greenrussian': [('VOL', [(0x15, 0, 100)]), ('TON', [(0x24, db(-12), db(+3)), (0x2C, db(+8), db(-2))]),
                  ('SUS', [(0x14, 45, 100), (0x11, 40, 90)])],
 'mistress':     [('RAT', [(0x37, 0, 100)]), ('RNG', [(0x38, 0, 100)]), ('COL', [(0x39, 0, 100), (0x3A, 40, 90)]),
                  ('FM', [(0x37, [0xFF, 0]), (0x38, [0xFF, 0])], 1, 3, 0)],          # filter matrix: freezes the sweep
 'ce1':          [('INT', [(0x35, 10, 85), (0x34, 10, 40)]), ('LVL', [(0x36, 0, 100)]), ('GRT', [(0x17, 0, 40)]),
                  ('VIB', [(0x36, [0xFF, 100]), (0x34, [0xFF, 55]), (0x35, [0xFF, 70])], 1, 3, 0)],
 'whammy':       [('MOD', [(0x60, [24, 0, 19, 17, 13])], 4, 1, 0), ('MIX', [(0x3B, 0, 200)])],   # oct up/down, 5th, 4th, +1
 'memoryman':    [('BLD', [(0x4B, 0, 100)]), ('FBK', [(0x4E, 0, 90)]), ('DLY', [(0x45, 30, 550)]),
                  ('CHO', [(0x35, 0, 70), (0x36, 0, 60)])],
 'shoegaze':     [('WSH', [(0x56, 20, 100), (0x51, 30, 75), (0x4E, 10, 75), (0x35, 20, 85)]), ('TIM', [(0x45, 150, 900)]),
                  ('TON', [(0x53, cut(1000), cut(6000)), (0x4F, cut(1000), cut(6000))])],
 'ross':         [('LVL', [(0x12, 0, 100)]), ('SUS', [(0x11, 0, 100), (0x0F, 55, 35)])],
 'squeezer':     [('SQZ', [(0x11, 10, 80), (0x10, 50, 15)]), ('LVL', [(0x12, 0, 100)])],
 'smallclone':   [('RAT', [(0x34, 0, 100)]), ('DEP', [(0x35, [40, 85]), (0x36, [55, 65])], 1, 4)],
 'detroit':      [('DRV', [(0x17, 30, 90)]), ('TON', [(0x16, 30, 75), (0x24, db(-3), db(+5))]),
                  ('ROM', [(0x56, 0, 35), (0x32, 0, 40)]), ('VOL', [(0x19, 30, 100)])],    # ROM = plate + double-track
 'flood1':       [('GAN', [(0x14, 50, 100)]), ('SCP', [(0x27, db(-2), db(-12)), (0x24, db(+2), db(+6))]),   # deeper V
                  ('LOW', [(0x2C, db(0), db(+10))]), ('VOL', [(0x15, 20, 100)])],
 'flood2':       [('GAN', [(0x14, 50, 100)]), ('MID', [(0x27, db(-6), db(+6))]),
                  ('DLY', [(0x4B, 0, 70), (0x4E, 10, 50)]), ('AMB', [(0x56, 0, 60)])],
 'holywar':      [('GAN', [(0x14, 40, 100)]), ('BRK', [(0x27, db(0), db(+8))]),
                  ('TGT', [(0x2C, db(0), db(-8)), (0x2A, db(0), db(-6))]), ('VOL', [(0x15, 20, 100)])],
 'dimc':         [('MOD', [(0x36, [0, 50, 55, 60, 65]), (0x32, [0, 20, 25, 30, 35]), (0x34, [15, 15, 20, 25, 35]),
                           (0x35, [0, 25, 35, 45, 55]), (0x33, [20, 20, 25, 30, 35]), (0x31, [8, 8, 10, 12, 14])], 4, 5, 2)],
}
AMP_KNOBS = {
 'clean':  [('VOL', [(0x5B, 40, 100)]), ('TRB', [(0x58, 0, 100)]), ('BAS', [(0x5A, 0, 100)])],
 'twin':   [('VOL', [(0x5B, 40, 100)]), ('TRB', [(0x58, 0, 100)]), ('MID', [(0x59, 0, 100)]), ('BAS', [(0x5A, 0, 100)])],
 'jcm800': [('PRS', [(0x57, 0, 100)]), ('BAS', [(0x5A, 0, 100)]), ('MID', [(0x59, 0, 100)]), ('TRB', [(0x58, 0, 100)])],
 'ac30':   [('VOL', [(0x5B, 40, 100)]), ('TRB', [(0x58, 0, 100)]), ('BAS', [(0x5A, 0, 100)]), ('CUT', [(0x57, 90, 10)])],
 'doom':   [('VOL', [(0x5B, 40, 100)]), ('BAS', [(0x5A, 0, 100)]), ('MID', [(0x59, 0, 100)]), ('TRB', [(0x58, 0, 100)])],
 'di':     [('VOL', [(0x5B, 40, 100)])],
 'radio':  [('TUN', [(0x28, 20, 80), (0x25, 30, 90)]), ('VOL', [(0x5B, 40, 100)])],
 'jc120':  [('VOL', [(0x5B, 40, 100)]), ('TRB', [(0x58, 0, 100)]), ('MID', [(0x59, 0, 100)]), ('BAS', [(0x5A, 0, 100)])],
 '5150':   [('PRS', [(0x57, 0, 100)]), ('BAS', [(0x5A, 0, 100)]), ('MID', [(0x59, 0, 100)]), ('TRB', [(0x58, 0, 100)])],
 'superlead': [('PRS', [(0x57, 0, 100)]), ('BAS', [(0x5A, 0, 100)]), ('MID', [(0x59, 0, 100)]), ('TRB', [(0x58, 0, 100)])],
 'randall':   [('VOL', [(0x5B, 40, 100)]), ('TRB', [(0x58, 0, 100)]), ('MID', [(0x59, 0, 100)]), ('BAS', [(0x5A, 0, 100)])],
 'jcm800rip': [('PRS', [(0x57, 0, 100)]), ('BAS', [(0x5A, 0, 100)]), ('MID', [(0x59, 0, 100)]), ('TRB', [(0x58, 0, 100)])],
}

# ---------------------------------------------------------------- BOARD mode
# 12 blocks in chain order = board slots. A pedal sits in its HOME slot and may grab EXTRA blocks its recipe uses.
SLOTS = ['A1 COMP', 'A2 DIRT', 'A3 WAH/FILTER', 'A4 PHASER', 'A5 EQ', 'A6 GATE', 'B1 SHORT DELAY', 'B2 MOD',
         'B3 TREM/PAN', 'B4 DELAY', 'B5 REVERB', 'B6 AMP/CAB', 'ORDER', 'OUT A/B/Y BOX', 'BOARD MEMORY']
HOME = {}
for k in ('dynacomp', 'cs3', 'ross', 'squeezer'): HOME[k] = 0
for k in ('tubescreamer', 'rat', 'ds1', 'bigmuff', 'metalzone', 'sd1', 'klon', 'fuzzface', 'metalmuff', 'funeral',
          'ironman', 'hm2', 'rangemaster', 'od1', 'fuzzfactory', 'octavia', 'ramshead', 'greenrussian', 'detroit', 'flood1',
          'flood2', 'holywar'): HOME[k] = 1
for k in ('crybaby', 'resowah', 'touchwah'): HOME[k] = 2
for k in ('phaser', 'slicer'): HOME[k] = 3
HOME['ge7'] = 4; HOME['ns2'] = 5
for k in ('slapback', 'doubler'): HOME[k] = 6
for k in ('chorus', 'dimensiond', 'flanger', 'leslie', 'octave', 'mistress', 'ce1', 'whammy', 'smallclone',
          'dimc'): HOME[k] = 7
for k in ('tremolo', 'autopan'): HOME[k] = 8
for k in ('digital', 'spaceecho', 'memoryman'): HOME[k] = 9
for k in ('spring', 'hallplate', 'shimmer', 'cathedral', 'cave', 'church', 'stage', 'ambient', 'shoegaze'): HOME[k] = 10
GRAB_GATE = {'fuzzfactory'}         # its GATE knob is the sound: may grab the gate slot
GLOBAL = 0x0F


def blk_of(a):
    for lo, hi, b in ((0x0F, 0x12, 0), (0x13, 0x19, 1), (0x1A, 0x1D, 2), (0x1E, 0x22, 3), (0x23, 0x2D, 4),
                      (0x2E, 0x30, 5), (0x31, 0x32, 6), (0x33, 0x41, 7), (0x42, 0x44, 8), (0x45, 0x50, 9),
                      (0x51, 0x56, 10), (0x57, 0x5B, 11)):
        if lo <= a <= hi:
            return b
    if 0x0C <= a <= 0x0E or a < 0x0C:
        return 0x0E
    return GLOBAL


def blocks_on(rec):
    return rec.get(0x0E, 0) & 0x7F | (rec.get(0x0D, 0) & 0x1F) << 7


def extras(rec, home, key=''):
    m = blocks_on(rec) & ~(1 << home)
    if home != 5 and key not in GRAB_GATE:
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
 'hm2': 'HM-2', 'rangemaster': 'RANGEMASTER', 'od1': 'OD-1', 'fuzzfactory': 'FUZZ FACTORY', 'octavia': 'OCTAVIA',
 'ramshead': "RAM'S HEAD", 'greenrussian': 'GREEN RUSSIAN', 'mistress': 'ELEC MISTRESS', 'ce1': 'CE-1',
 'whammy': 'WHAMMY', 'memoryman': 'MEMORY MAN', 'shoegaze': 'SHOEGAZE WASH', 'ross': 'ROSS COMP',
 'squeezer': 'OR SQUEEZER', 'smallclone': 'SMALL CLONE', 'dimc': 'DIMENSION C',
 'detroit': 'DETROIT', 'flood1': 'FLOOD 1', 'flood2': 'FLOOD 2', 'holywar': 'HOLYWAR',
 'clean': 'CLEAN', 'twin': 'TWIN', 'jcm800': 'JCM800', 'ac30': 'AC30', 'doom': 'DOOM', 'di': 'DI / FLAT',
 'radio': 'RADIO', 'jc120': 'JC-120', '5150': '5150', 'superlead': 'SUPER LEAD', 'randall': 'RANDALL',
 'jcm800rip': 'JCM800 RIP',
}


# ---------------------------------------------------------------- GP Tone Zone sounds (tonezone/ "Add to OS build")
TZ_DIR = os.path.join(here, 'tz_sounds')


def _tz_merge():
    """re/tz_sounds/*.json (written by tonezone/tz_gp16.add_to_os) -> appended after the built-in pedals / amps"""
    import json
    if not os.path.isdir(TZ_DIR):
        return []
    added = []
    for f in sorted(os.listdir(TZ_DIR)):
        if not f.endswith('.json'):
            continue
        with open(os.path.join(TZ_DIR, f), encoding='utf-8') as fp:
            d = json.load(fp)
        key = 'tz_' + os.path.splitext(f)[0]
        rec = {int(a, 16): int(v) for a, v in d['recipe'].items()}
        knobs = [tuple([lab, [tuple(t) for t in tg]]) for lab, tg in d['knobs']]
        NAMES[key] = d['name'][:13]
        if d['kind'] == 'amp':
            P.AMPS[key], AMP_KNOBS[key] = rec, knobs
        else:
            P.PEDALS[key], KNOBS[key], HOME[key] = rec, knobs, 1
        added.append(f'{d["name"]} ({d["kind"]})')
    return added


TZ_ADDED = _tz_merge()


def pairs_of(rec):
    out = []
    for a, v in sorted(rec.items()):
        assert 0x00 <= a <= 0x04 or 0x0C <= a <= 0x63, f'addr {a:#x}: only A-chain order (0-4) and params 0C-63'
        assert 0 <= v <= 0x7F, f'value {v} at {a:#x} not 7-bit'
        out.append((a, v))
    return out


def norm(kn):
    label, tg = kn[0], kn[1]
    steps = kn[2] if len(kn) > 2 else 20
    disp = kn[3] if len(kn) > 3 else 0
    dflt = kn[4] if len(kn) > 4 else None
    return label, tg, steps, disp, dflt


def cur_val(rec, a):
    if a in TWO:
        return rec.get(a, 0) * 128 + rec.get(a + 1, 0) if a in rec else None
    return rec.get(a)


def knob_block(knobs, rec, key):
    """-> bytes: n, defaults[n], records"""
    n = len(knobs)
    assert n <= 6, key
    six = n >= 5
    ks = [norm(k) for k in knobs]
    defs, recs = [], []
    for j, (label, tg, steps, disp, dflt) in enumerate(ks):
        assert 1 <= len(tg) and 1 <= steps <= 24, (key, label)
        if six:
            assert steps == 10 and disp == 0 and len(label) <= 2, f'{key} {label}: 6-knob screen = whole steps, 2-char names'
            lab = label.rjust(2) + ' '
        else:
            assert len(label) <= 3, (key, label)
            lab = label.ljust(3)
        assert disp != 5 or (j == 0 and n == 1), f'{key}: mode buttons = single knob'
        assert disp not in (3, 4) or steps == 1, f'{key} {label}: switch = 1 step'
        if dflt is None:
            t0 = tg[0]
            cur = cur_val(rec, t0[0])
            if len(t0) == 2:
                dflt = t0[1].index(cur) if cur in t0[1] else 0
            elif cur is None:
                dflt = steps // 2 if disp in (0, 2) else 0
            else:
                dflt = max(0, min(steps, round((cur - t0[1]) / (t0[2] - t0[1]) * steps)))
        defs.append(dflt)
        body = b''
        for t in tg:
            a = t[0]
            assert 0x0F <= a <= 0x62, f'{key} {label}: knob target {a:#x}'
            if len(t) == 2:
                assert a not in TWO and len(t[1]) == steps + 1, f'{key} {label}: table needs steps+1 values, 1-byte param'
                assert all(0 <= v <= 127 or v == 0xFF for v in t[1])
                body += bytes([a | 0x80]) + bytes(t[1])
            elif a in TWO:
                body += bytes([a]) + struct.pack('<hh', t[1], t[2])
            else:
                assert 0 <= t[1] <= 127 and 0 <= t[2] <= 127, f'{key} {label} {a:#x} needs 7-bit range'
                body += bytes([a, t[1], t[2]])
        recs.append((lab, steps, disp, tg, body))
    out = bytes([n] + defs)
    addrs = [{t[0] for t in r[3]} for r in recs]
    for j, (lab, steps, disp, tg, body) in enumerate(recs):
        deps = sum(1 << i for i in range(n) if i == j or addrs[i] & addrs[j])
        r = lab.encode() + bytes([steps, disp, len(tg), deps]) + body
        out += bytes([len(r) + 1]) + r
    return out


def ainfo():
    b = []
    for a in range(0x0C, 0x64):
        ioff, word = IMAP.get(a, (0, False))
        b += [blk_of(a) | (0x10 if a in TWO else 0) | (0x20 if word else 0), SYSEX_P.get(a, 0xFF), ioff]
    return b


SIG = []


def knob_steps(kb):
    n, steps, o = kb[0], [], 1 + kb[0]
    for _ in range(n):
        steps.append(kb[o + 4]); o += kb[o]
    return steps


def table(label, recs, knobs, home, ks):
    lines = [f'{label}_off:']
    lines.append('    dw ' + ', '.join(f'{label}_e{i}' for i in range(len(recs) + 1)))
    entries = [('OFF', [], b'\x00', 0)]
    for k, r in recs.items():
        entries.append((NAMES[k], pairs_of(r), knob_block(knobs.get(k, []), r, k), extras(r, home(k), k)))
    kdata = b''
    for i, (nm, pairs, kb, ex) in enumerate(entries):
        nm16 = nm.ljust(16)[:16]
        SIG.append(f'{label}|{nm}|{kb[0]}|{ks[0]:04x}|' + ','.join(str(x) for x in knob_steps(kb)))
        lines.append(f'{label}_e{i}: db "{nm16}"')
        lines.append(f'    dw {label}_k{i}, 0x{ex:04x}, 0x{ks[0]:04x}')
        ks[0] += kb[0]
        lines.append(f'    db {len(pairs)}' + (', ' + ', '.join(f'0x{a:02x},{v}' for a, v in pairs) if pairs else ''))
        kdata += kb
        lines.append(f'{label}_k{i}: db ' + ', '.join(str(x) for x in kb))
    return lines, kdata


if __name__ == '__main__':
    missing = [k for k in P.PEDALS if k not in KNOBS] + [k for k in P.AMPS if k not in AMP_KNOBS]
    missing += [k for k in P.PEDALS if k not in HOME] + [k for k in list(P.PEDALS) + list(P.AMPS) if k not in NAMES]
    assert not missing, f'no knobs/home/name for {missing}'
    assert all(len(NAMES[k]) <= 13 for k in NAMES)
    ks = [KS_BASE]
    pl, pk = table('ped', P.PEDALS, KNOBS, lambda k: HOME[k], ks)
    al, ak = table('amp', P.AMPS, AMP_KNOBS, lambda k: 11, ks)
    assert ks[0] <= KS_END, hex(ks[0])
    PK = list(P.PEDALS)
    body = pl + al
    body.append('ped_home: db 0xff, ' + ', '.join(str(HOME[k]) for k in PK))
    body.append('ainfo: db ' + ', '.join(f'0x{x:02x}' for x in ainfo()))
    body.append('slot_lists: dw ' + ', '.join(f'sl{i}' for i in range(12)))
    for i in range(11):
        idx = [PK.index(k) + 1 for k in PK if HOME[k] == i]
        body.append(f'sl{i}: db {len(idx)}, ' + ', '.join(str(x) for x in idx))
    body.append(f'sl11: db {len(P.AMPS)}, ' + ', '.join(str(i + 1) for i in range(len(P.AMPS))))
    body.append('s_slots: db ' + ', '.join('"' + n.ljust(16) + '"' for n in SLOTS))
    # structure only (entry names, knob counts + steps, store addresses, homes, slot lists): recipes, knob targets and
    # defaults may change without wiping the user's knob positions and board memories
    layout = SIG + [l for l in body if l.startswith(('ped_home', 'sl', 'slot_lists'))]
    magic = hashlib.md5('\n'.join(layout).encode()).digest()[0] | 0x01
    if magic == 0xFF: magic = 0x81
    # v2.1 (flashed) used KMAGIC 0x0d for this same structure; keep it so its knobs + board memories carry over.
    # A different structure hashes to something else (bumped off 0x0d) and resets as intended.
    PIN = {0x89: 0x0d}
    if magic in PIN.values() and magic not in PIN:
        magic ^= 0x02
    magic = PIN.get(magic, magic)
    out = ['; generated by gen_pedal_data.py -- do not edit',
           f'KMAGIC equ 0x{magic:02x}          ; changes whenever the tables change -> stored knobs/board reset',
           f'NPED equ {len(P.PEDALS)}', f'NAMP equ {len(P.AMPS)}', f'KS_BASE equ 0x{KS_BASE:04x}',
           f'KS_USED equ 0x{ks[0]:04x}'] + body
    open(os.path.join(here, 'pedal_data.inc'), 'w').write('\n'.join(out) + '\n')
    if TZ_ADDED:
        print('GP Tone Zone sounds:', ', '.join(TZ_ADDED))
    print(f'pedal_data.inc: {len(P.PEDALS)+1} pedals, {len(P.AMPS)+1} amps, knob data {len(pk)+len(ak)} B, '
          f'stores {ks[0]-KS_BASE} B, magic {magic:#04x}')
    for k in ('bigmuff', 'leslie', 'tubescreamer', 'ce1', 'memoryman', 'shoegaze', 'fuzzfactory', 'dimc'):
        print(f'  {k}: home {SLOTS[HOME[k]]}, extras',
              [SLOTS[b] for b in range(12) if extras(P.PEDALS[k], HOME[k], k) >> b & 1])
    for k in ('jcm800', 'doom'):
        print(f'  {k}: extras', [SLOTS[b] for b in range(12) if extras(P.AMPS[k], 11) >> b & 1])
