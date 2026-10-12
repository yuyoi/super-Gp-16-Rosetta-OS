#!/usr/bin/env python3
"""GP-16 'pedal mode' voicings over SysEx. py -3.10 (mido + python-rtmidi), OCTA-CAPTURE, GP-16 on MIDI ch1, PLAY screen.
Reads the live edit buffer (RQ1), applies a pedal recipe by SysEx address, writes it back in 8-byte blocks + SOUND CHANGE.

  py -3.10 pedals.py dump                 print the current edit buffer
  py -3.10 pedals.py list                 list pedal recipes
  py -3.10 pedals.py load <name>          PEDAL only (into a real amp)
  py -3.10 pedals.py amp <name>           AMP only (clean through amp EQ/cab)
  py -3.10 pedals.py combo <pedal> <amp>  RIG: pedal + amp (amp EQ/cab wins; dirt from pedal)
  py -3.10 pedals.py set <name> addr=val  load a pedal with one-off overrides (hex addr, dec val) for tuning
Addresses (SysEx = buffer index for these 1-byte params):
  0x0C mode  0x0D on/off-MSB  0x0E on/off-LSB
  COMP 0x0F tone 0x10 att 0x11 sus 0x12 lev | DIST 0x13 tone 0x14 drive 0x15 lev
  OD 0x16 tone 0x17 drive 0x18 turbo 0x19 lev | EQ HI 0x23 f 0x24 l  HM 0x25 f 0x26 q 0x27 l
  LM 0x28 f 0x29 q 0x2A l  LO 0x2B f 0x2C l  OUTLEV 0x2D | NS 0x2E sens 0x2F rel 0x30 lev
EQ level bytes: 24 = 0 dB, +/-0.5 dB per step (36 = +6 dB, 12 = -6 dB, 4 = -10 dB).
on/off LSB 0x0E bits: A1comp1 A2dist/od2 A3pick4 A4phaser8 A5eq16 A6ns32 B1delay64
on/off MSB 0x0D bits: B2 1 B3 2 B4 4 B5 8 B6lineout16  A2type(0=DIST,64=OVERDRIVE)
"""
import sys, time

# each recipe: dict of {sysex_addr: value}. Starting points -- tune by ear.
PEDALS = {
 'tubescreamer': {  # OD, mid hump ~720, low cut, soft top
   0x0E: 0x32, 0x0D: 0x40, 0x0C: 0,
   0x16: 55, 0x17: 42, 0x18: 10, 0x19: 60,          # OD tone/drive/turbo-off/level
   0x23: 60, 0x24: 18,                              # HI f, -3dB
   0x25: 55, 0x26: 25, 0x27: 24,                    # HM flat
   0x28: 45, 0x29: 30, 0x2A: 34,                    # LM ~720 +5dB
   0x2B: 20, 0x2C: 16, 0x2D: 24,                    # LO cut -4dB, out 0
   0x2E: 30, 0x2F: 50, 0x30: 50,
 },
 'rat': {  # DIST, high-mid push ~1.5-2k, treble rolled (filter), full lows
   0x0E: 0x32, 0x0D: 0x00, 0x0C: 0,
   0x13: 40, 0x14: 60, 0x15: 55,                    # DIST darker tone, drive, level
   0x23: 55, 0x24: 18,                              # HI -3dB (filter)
   0x25: 55, 0x26: 25, 0x27: 30,                    # HM +3dB ~1.5-2k
   0x28: 40, 0x29: 30, 0x2A: 24,
   0x2B: 35, 0x2C: 24, 0x2D: 24,
   0x2E: 30, 0x2F: 50, 0x30: 50,
 },
 'ds1': {  # DIST, bright buzzy, slight low-mid dip, tight lows
   0x0E: 0x32, 0x0D: 0x00, 0x0C: 0,
   0x13: 62, 0x14: 50, 0x15: 55,
   0x23: 70, 0x24: 28,                              # bright +2dB
   0x25: 55, 0x26: 25, 0x27: 26,
   0x28: 30, 0x29: 25, 0x2A: 20,                    # LM dip ~500 -2dB
   0x2B: 38, 0x2C: 22, 0x2D: 24,
   0x2E: 30, 0x2F: 50, 0x30: 50,
 },
 'bigmuff': {  # DIST max + comp sustain, deep scoop, dark
   0x0E: 0x33, 0x0D: 0x00, 0x0C: 0,
   0x0F: 50, 0x10: 50, 0x11: 70, 0x12: 55,          # COMP sustain
   0x13: 40, 0x14: 80, 0x15: 50,                    # DIST dark, huge gain
   0x23: 50, 0x24: 20,                              # HI -2dB dark
   0x25: 50, 0x26: 20, 0x27: 24,
   0x28: 45, 0x29: 20, 0x2A: 4,                     # LM deep scoop -10dB ~700
   0x2B: 25, 0x2C: 28, 0x2D: 24,                    # LO bump +2dB
   0x2E: 30, 0x2F: 50, 0x30: 50,
 },
 'metalzone': {  # DIST near-max, scoop + bright fizz, tight lows
   0x0E: 0x33, 0x0D: 0x00, 0x0C: 0,
   0x0F: 50, 0x10: 50, 0x11: 50, 0x12: 55,
   0x13: 55, 0x14: 90, 0x15: 50,                    # near-max gain
   0x23: 75, 0x24: 36,                              # bright +6dB fizz
   0x25: 60, 0x26: 25, 0x27: 27,                    # HM +1.5dB
   0x28: 42, 0x29: 18, 0x2A: 8,                     # deep mid scoop -8dB ~600
   0x2B: 40, 0x2C: 22, 0x2D: 24,                    # tight lows -1dB
   0x2E: 30, 0x2F: 50, 0x30: 50,
 },
 # --- more dirt ---
 'sd1': {  # OD asymmetric, brighter than TS
   0x0E: 0x32, 0x0D: 0x40, 0x0C: 0,
   0x16: 62, 0x17: 48, 0x18: 0, 0x19: 58,
   0x23: 65, 0x24: 26, 0x25: 55, 0x26: 25, 0x27: 26, 0x28: 45, 0x29: 28, 0x2A: 30, 0x2B: 25, 0x2C: 18, 0x2D: 24,
   0x2E: 30, 0x2F: 50, 0x30: 50,
 },
 'klon': {  # transparent OD + mid push, clean lows, boost-ish level
   0x0E: 0x32, 0x0D: 0x40, 0x0C: 0,
   0x16: 58, 0x17: 35, 0x18: 0, 0x19: 65,
   0x23: 62, 0x24: 26, 0x25: 55, 0x26: 20, 0x27: 28, 0x28: 48, 0x29: 22, 0x2A: 28, 0x2B: 35, 0x2C: 24, 0x2D: 24,
   0x2E: 25, 0x2F: 50, 0x30: 55,
 },
 'fuzzface': {  # germanium fuzz, splatty, gated
   0x0E: 0x32, 0x0D: 0x00, 0x0C: 0,
   0x13: 45, 0x14: 72, 0x15: 52,
   0x23: 50, 0x24: 18, 0x25: 50, 0x26: 20, 0x27: 26, 0x28: 40, 0x29: 20, 0x2A: 26, 0x2B: 30, 0x2C: 28, 0x2D: 24,
   0x2E: 40, 0x2F: 45, 0x30: 50,
 },
 'metalmuff': {  # modern aggressive hi-gain
   0x0E: 0x33, 0x0D: 0x00, 0x0C: 0,
   0x0F: 50, 0x10: 50, 0x11: 55, 0x12: 55,
   0x13: 50, 0x14: 88, 0x15: 50,
   0x23: 70, 0x24: 32, 0x25: 58, 0x26: 25, 0x27: 30, 0x28: 42, 0x29: 18, 0x2A: 14, 0x2B: 38, 0x2C: 22, 0x2D: 24,
   0x2E: 30, 0x2F: 50, 0x30: 50,
 },
 'funeral': {  # doom fuzz (Funeralopolis): max fuzz, deep lows, dark, woolly sustain
   0x0E: 0x33, 0x0D: 0x00, 0x0C: 0,
   0x0F: 45, 0x10: 55, 0x11: 75, 0x12: 50,
   0x13: 35, 0x14: 95, 0x15: 48,
   0x23: 42, 0x24: 6, 0x25: 45, 0x26: 18, 0x27: 22, 0x28: 45, 0x29: 18, 0x2A: 10, 0x2B: 22, 0x2C: 34, 0x2D: 24,
   0x2E: 28, 0x2F: 50, 0x30: 50,
 },
 'ironman': {  # Iommi: Rangemaster treble-boost into Laney; upper-mid/treble forward, lows trimmed
   0x0E: 0x33, 0x0D: 0x40, 0x0C: 0,
   0x0F: 50, 0x10: 50, 0x11: 65, 0x12: 55,
   0x16: 66, 0x17: 70, 0x18: 1, 0x19: 58,
   0x23: 72, 0x24: 34, 0x25: 58, 0x26: 25, 0x27: 36, 0x28: 50, 0x29: 25, 0x2A: 24, 0x2B: 30, 0x2C: 16, 0x2D: 24,
   0x2E: 30, 0x2F: 50, 0x30: 50,
 },
 # --- compressors (A1) ---
 'dynacomp': {0x0E: 0x01, 0x0F: 60, 0x10: 30, 0x11: 65, 0x12: 55},             # MXR Dyna Comp: squash + snap
 'cs3': {0x0E: 0x01, 0x0F: 50, 0x10: 50, 0x11: 50, 0x12: 55},                  # Boss CS-3
 # --- filters (A3), phasers (A4), EQ (A5), gate (A6) ---
 'touchwah': {0x0E: 0x04, 0x1A: 60, 0x1B: 35, 0x1C: 30, 0x1D: 1, 0x5C: 127},   # envelope wah, exp pedal off
 'slicer': {0x0E: 0x08, 0x1E: 55, 0x1F: 90, 0x20: 40, 0x21: 60, 0x22: 100},   # step phaser chop
 'ge7': {0x0E: 0x10, 0x23: 65, 0x24: 24, 0x25: 55, 0x26: 20, 0x27: 24, 0x28: 35, 0x29: 20, 0x2A: 24,
         0x2B: 25, 0x2C: 24, 0x2D: 24},                                       # 4-band EQ pedal, flat
 'ns2': {0x0E: 0x20, 0x2E: 30, 0x2F: 50, 0x30: 50},                            # Boss NS-2 gate
 # --- short delay (B1), pitch (B2), pan (B3) ---
 'doubler': {0x0E: 0x40, 0x31: 6, 0x32: 50},
 'octave': {0x0D: 0x01, 0x0C: 2, 0x3B: 0, 0x3C: 100, 0x3D: 0, 0x3E: 50, 0x3F: 0, 0x40: 0},   # pitch -12, 50/50
 'autopan': {0x0D: 0x02, 0x42: 30, 0x43: 80, 0x44: 0},
 # --- modulation ---
 'chorus': {0x0D: 1, 0x0C: 0, 0x33: 20, 0x34: 28, 0x35: 42, 0x36: 50},          # CE-2
 'dimensiond': {0x0D: 1, 0x0C: 3, 0x41: 1},                                     # SPACE-D
 'phaser': {0x0E: 8, 0x1E: 40, 0x1F: 70, 0x20: 50, 0x21: 55, 0x22: 0},          # Phase 90
 'flanger': {0x0D: 1, 0x0C: 1, 0x37: 25, 0x38: 60, 0x39: 40, 0x3A: 55},
 'tremolo': {0x0D: 2, 0x42: 42, 0x43: 70, 0x44: 1},                             # pan=tremolo
 'leslie': {0x0D: 3, 0x0C: 0, 0x33: 15, 0x34: 55, 0x35: 55, 0x36: 50, 0x42: 55, 0x43: 60, 0x44: 0},  # chorus+pan rotary
 # --- delay ---
 'slapback': {0x0E: 0x40, 0x31: 18, 0x32: 35},                                  # short delay
 'digital': {0x0D: 4, 0x45: 2, 0x46: 119, 0x4B: 50, 0x4E: 35, 0x4F: 1, 0x50: 72},   # tap ~375ms dotted-8th
 'spaceecho': {0x0D: 4, 0x45: 3, 0x46: 16, 0x4B: 45, 0x4E: 48, 0x4F: 0, 0x50: 120},  # ~400ms dark repeats
 # --- reverb (0x0D bit3 = B5) mode: 0-9 ROOM1..SPRING2; cut 2-byte ---
 'spring': {0x0D: 8, 0x51: 25, 0x52: 8, 0x53: 1, 0x54: 52, 0x55: 5, 0x56: 40},
 'hallplate': {0x0D: 8, 0x51: 40, 0x52: 6, 0x53: 1, 0x54: 32, 0x55: 10, 0x56: 35},
 'shimmer': {0x0D: 8, 0x51: 70, 0x52: 5, 0x53: 1, 0x54: 42, 0x55: 20, 0x56: 45},
 'cathedral': {0x0D: 8, 0x51: 75, 0x52: 5, 0x53: 1, 0x54: 52, 0x55: 60, 0x56: 45},
 'cave': {0x0D: 8, 0x51: 70, 0x52: 4, 0x53: 0, 0x54: 80, 0x55: 40, 0x56: 45},
 'church': {0x0D: 8, 0x51: 65, 0x52: 5, 0x53: 0, 0x54: 110, 0x55: 50, 0x56: 40},
 'stage': {0x0D: 8, 0x51: 30, 0x52: 2, 0x53: 1, 0x54: 52, 0x55: 20, 0x56: 35},
 'ambient': {0x0D: 8, 0x51: 75, 0x52: 5, 0x53: 1, 0x54: 62, 0x55: 70, 0x56: 55},
 # --- wah (picking filter swept by expression pedal; assign #12 = pf cutoff) ---
 'crybaby': {0x0E: 4, 0x1A: 0, 0x1B: 50, 0x1C: 25, 0x1D: 0, 0x5C: 12, 0x5D: 0, 0x5F: 0, 0x60: 90, 0x61: 0, 0x62: 12},
 'resowah': {0x0E: 4, 0x1A: 0, 0x1B: 50, 0x1C: 40, 0x1D: 0, 0x5C: 12, 0x5D: 0, 0x5F: 0, 0x60: 90, 0x61: 0, 0x62: 12},
}


# AMP voicings = EQ(4-band) + line-out cab + power-amp comp, NO distortion (gain comes from the pedal).
# EQ level bytes: 24 = 0 dB, +/-0.5 dB/step. on/off handled by the merge loader. Starting points -- tune by ear.
AMPS = {
 'clean': {      # Fendery: tight low, slight mid dip, bright sparkle
   0x0E: 0x10, 0x0D: 0x10,
   0x2b: 40, 0x2c: 26, 0x28: 40, 0x29: 20, 0x2a: 21, 0x25: 55, 0x27: 24, 0x23: 65, 0x24: 28, 0x2d: 24,
   0x57: 55, 0x58: 55, 0x59: 45, 0x5a: 50, 0x5b: 80,
 },
 'twin': {       # bright scooped clean, big headroom
   0x0E: 0x10, 0x0D: 0x10,
   0x2c: 26, 0x28: 38, 0x29: 18, 0x2a: 19, 0x25: 55, 0x27: 24, 0x23: 72, 0x24: 36,
   0x57: 58, 0x58: 62, 0x59: 40, 0x5a: 48, 0x5b: 80,
 },
 'jcm800': {     # mid-forward, presence, tight low (pair with a dirt pedal)
   0x0E: 0x10, 0x0D: 0x10,
   0x2b: 42, 0x2c: 22, 0x28: 45, 0x29: 25, 0x2a: 26, 0x25: 55, 0x26: 25, 0x27: 36, 0x23: 68, 0x24: 28,
   0x57: 62, 0x58: 55, 0x59: 58, 0x5a: 45, 0x5b: 80,
 },
 'ac30': {       # Vox chime: upper-mid + top
   0x0E: 0x10, 0x0D: 0x10,
   0x2c: 24, 0x28: 45, 0x2a: 24, 0x25: 62, 0x26: 22, 0x27: 34, 0x23: 70, 0x24: 34,
   0x57: 55, 0x58: 60, 0x59: 52, 0x5a: 48, 0x5b: 80,
 },
 'doom': {       # dark Orange/Laney: thick low-mid, rolled highs, squashy
   0x0E: 0x11, 0x0D: 0x10,
   0x2b: 28, 0x2c: 34, 0x28: 42, 0x29: 20, 0x2a: 32, 0x25: 45, 0x27: 22, 0x23: 45, 0x24: 8,
   0x0f: 50, 0x11: 55, 0x12: 55, 0x57: 40, 0x58: 35, 0x59: 55, 0x5a: 62, 0x5b: 80,
 },
 'di': {         # flat / true DI (cab off -- loader leaves line-out disabled)
   0x23: 24, 0x24: 24, 0x25: 24, 0x27: 24, 0x28: 24, 0x29: 20, 0x2a: 24, 0x2b: 24, 0x2c: 24, 0x2d: 24, 0x5b: 80,
 },
 'radio': {      # germanium transistor radio: bandpass honk, lows+highs gutted
   0x0E: 0x11, 0x0D: 0x10,
   0x2b: 55, 0x2c: 4, 0x28: 55, 0x29: 35, 0x2a: 20, 0x25: 45, 0x26: 40, 0x27: 40, 0x23: 50, 0x24: 4, 0x2d: 24,
   0x0f: 50, 0x11: 60, 0x12: 50, 0x57: 40, 0x58: 30, 0x59: 65, 0x5a: 25, 0x5b: 72,
 },
}


def ports(name='OCTA-CAPTURE'):
    import mido
    i = next(p for p in mido.get_input_names() if name in p and not p.startswith('CTRL'))
    o = next(p for p in mido.get_output_names() if name in p and not p.startswith('CTRL'))
    return mido.open_input(i), mido.open_output(o)


def roland(data):
    cs = (128 - sum(data) % 128) % 128
    return [0x41, 0, 0x2A] + data + [cs]


def rq1(inp, out):
    import mido
    out.send(mido.Message('sysex', data=roland([0x11, 0, 0, 0, 0, 0, 0x76])))
    t = time.time()
    while time.time() - t < 1.5:
        for m in inp.iter_pending():
            if m.type == 'sysex' and list(m.data[:5]) == [0x41, 0, 0x2A, 0x12, 0]:
                return list(m.data[7:7 + 118])
        time.sleep(0.01)
    return None


def write_buf(out, buf):
    import mido
    for k in range(0, len(buf), 8):
        blk = buf[k:k + 8]
        out.send(mido.Message('sysex', data=roland([0x12, 0, 0, k] + blk)))
        time.sleep(0.1)
    out.send(mido.Message('sysex', data=roland([0x12, 0, 0, 0x75, 0])))  # SOUND CHANGE REQUEST
    time.sleep(0.3)


def apply_rec(buf, rec):
    for addr, val in rec.items():
        if addr in (0x0C, 0x0D, 0x0E):   # mode + on/off bitfields -> OR (merge blocks)
            buf[addr] |= val
        else:
            buf[addr] = val


def load(inp, out, recs, overrides=None, tag=''):
    buf = rq1(inp, out)
    if buf is None:
        sys.exit('no reply from GP-16 (play screen? ch1? cables?)')
    buf[0x0C] = 0; buf[0x0D] = 0; buf[0x0E] = 0        # start clean: all blocks off
    for r in recs:
        apply_rec(buf, r)
    if overrides:
        for k, v in overrides.items():
            buf[k] = v
    write_buf(out, buf)
    print(f'loaded {tag}  on/off {buf[0x0D]:02x}/{buf[0x0E]:02x} mode {buf[0x0C]:02x}')


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'list':
        print('PEDALS:', ', '.join(PEDALS)); print('AMPS:', ', '.join(AMPS))
        return
    inp, out = ports()
    if cmd == 'dump':
        b = rq1(inp, out)
        print('no reply' if b is None else ' '.join(f'{x:02x}' for x in b))
        return

    def ov(args):
        return {int(k, 16): int(v) for k, v in (a.split('=') for a in args)}

    if cmd in ('load', 'set'):        # pedal only (into a real amp)
        name = sys.argv[2]
        load(inp, out, [PEDALS[name]], ov(sys.argv[3:]), f'pedal {name}')
    elif cmd == 'amp':                # amp only (clean through amp EQ/cab)
        name = sys.argv[2]
        load(inp, out, [AMPS[name]], ov(sys.argv[3:]), f'amp {name}')
    elif cmd == 'combo':              # RIG: pedal + amp (amp EQ/cab wins)
        ped, amp = sys.argv[2], sys.argv[3]
        load(inp, out, [PEDALS[ped], AMPS[amp]], ov(sys.argv[4:]), f'rig {ped}+{amp}')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
