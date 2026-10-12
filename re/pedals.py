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

# ---------------------------------------------------------------- v2 voicing helpers (real units)
# Frequencies come from the firmware's own display tables: HI 2-8 kHz, HM 500 Hz-4 kHz, LM 125 Hz-1 kHz,
# LO 60-250 Hz, all log over 0-100 (DS:304C / 31E0 / 3374); delay/reverb CUTOFF = 500 Hz x 16^(i/200), 200 = THRU
# (DS:481C). EQ level: 24 + 2 x dB. Q: 1.0-5.0 = 0-40. Tone params (comp/dist/OD): -50..+50 = 0-100.
import math


def _lg(f, lo, hi, n=100):
    return max(0, min(n, round(n * math.log(f / lo) / math.log(hi / lo))))


def hz_hi(f): return _lg(f, 2000, 8000)
def hz_hm(f): return _lg(f, 500, 4000)
def hz_lm(f): return _lg(f, 125, 1000)
def hz_lo(f): return _lg(f, 60, 250)
def db(x): return max(0, min(48, round(24 + 2 * x)))
def qv(x): return max(0, min(40, round((x - 1.0) * 10)))
def cut(f): return 200 if f is None else min(199, _lg(f, 500, 8000, 200))     # None = THRU
def two(a, v): return {a: v >> 7, a + 1: v & 0x7F}                              # 2-byte SysEx param


BITS = {'comp': (0x0E, 1), 'dirt': (0x0E, 2), 'pick': (0x0E, 4), 'phaser': (0x0E, 8), 'eq': (0x0E, 16),
        'ns': (0x0E, 32), 'sdly': (0x0E, 64), 'mod': (0x0D, 1), 'pan': (0x0D, 2), 'dly': (0x0D, 4), 'rev': (0x0D, 8),
        'amp': (0x0D, 16)}
B2 = {'chorus': 0, 'flanger': 1, 'pitch': 2, 'spaced': 3}


def on(*blocks, od=False, b2=None):
    d = {0x0E: 0, 0x0D: 0x40 if od else 0, 0x0C: B2[b2] if b2 else 0}
    for b in blocks:
        a, bit = BITS[b]
        d[a] |= bit
    return d


def COMP(tone=0, att=50, sus=50, lev=50): return {0x0F: tone + 50, 0x10: att, 0x11: sus, 0x12: lev}
def DIST(tone=0, drive=50, lev=50): return {0x13: tone + 50, 0x14: drive, 0x15: lev}
def OD(tone=0, drive=50, lev=50, turbo=0): return {0x16: tone + 50, 0x17: drive, 0x18: turbo, 0x19: lev}
def PICK(sens=0, cutoff=50, q=2.0, up=0): return {0x1A: sens, 0x1B: cutoff, 0x1C: qv(q), 0x1D: up}
def PHASE(rate=40, depth=100, man=50, res=30, step=0): return {0x1E: rate, 0x1F: depth, 0x20: man, 0x21: res, 0x22: step}
def NS(sens=25, rel=50, lev=50): return {0x2E: sens, 0x2F: rel, 0x30: lev}
def SDLY(ms=30, lev=50): return {0x31: ms, 0x32: lev}
def CHORUS(pd=8, rate=30, depth=50, lev=50): return {0x33: pd, 0x34: rate, 0x35: depth, 0x36: lev}
def FLANGER(rate=30, depth=50, man=50, res=50): return {0x37: rate, 0x38: depth, 0x39: man, 0x3A: res}
def PITCH(semi=0, bal=100, fine=0, fb=0, pd=0): return {**two(0x3B, bal), 0x3D: semi + 12, 0x3E: fine + 50, 0x3F: fb, 0x40: pd}
def PAN(rate=30, depth=60, trem=0): return {0x42: rate, 0x43: depth, 0x44: trem}
def REVERB(decay=20, mode=6, cutf=None, pd=0, lev=30): return {0x51: decay, 0x52: mode, **two(0x53, cut(cutf)), 0x55: pd, 0x56: lev}
def LINE(pres=50, treb=50, mid=50, bass=50, master=80): return {0x57: pres, 0x58: treb, 0x59: mid, 0x5A: bass, 0x5B: master}
REV_MODES = ['ROOM1', 'ROOM2', 'ROOM3', 'HALL1', 'HALL2', 'HALL3', 'PLATE1', 'PLATE2', 'SPRING1', 'SPRING2']


def TAP(c_ms=350, c_lev=50, l_ms=0, l_lev=0, r_ms=0, r_lev=0, fb=30, cutf=None):
    return {**two(0x45, c_ms), **two(0x47, l_ms), **two(0x49, r_ms), 0x4B: c_lev, 0x4C: l_lev, 0x4D: r_lev, 0x4E: fb,
            **two(0x4F, cut(cutf))}


def EQ(hi=(4000, 0), hm=(1000, 0, 1.0), lm=(300, 0, 1.0), lo=(100, 0), out=0):
    return {0x23: hz_hi(hi[0]), 0x24: db(hi[1]), 0x25: hz_hm(hm[0]), 0x26: qv(hm[2]), 0x27: db(hm[1]),
            0x28: hz_lm(lm[0]), 0x29: qv(lm[2]), 0x2A: db(lm[1]), 0x2B: hz_lo(lo[0]), 0x2C: db(lo[1]), 0x2D: db(out)}


def R(*parts):
    d = {}
    for p in parts:
        for a, v in p.items():
            d[a] = d.get(a, 0) | v if a in (0x0C, 0x0D, 0x0E) else v
    return d


def EXP(param, lo, hi, lfo=None):
    """expression pedal (or its LFO when lfo = rate) on assignable param #param, range lo..hi (param units)"""
    return {0x5C: param, 0x5D: 1 if lfo is not None else 0, 0x5E: lfo or 0, **two(0x5F, hi), **two(0x61, lo)}


# ---------------------------------------------------------------- v2 voicings: modelled on the original circuits
# (vintage references, not modern takes). Starting points -- tune by ear.
PEDALS = {
 # TS808: op-amp soft clip, ~720 Hz hump (bass rolled off before the diodes), treble tamed by the tone LPF
 'tubescreamer': R(on('dirt', 'eq', 'ns', od=True), OD(0, 45, 60),
                   EQ(hi=(3500, -5), hm=(720, +6, 1.0), lm=(250, -2, 1.5), lo=(140, -9)), NS(22)),
 # RAT: hard silicon clip, upper-mid bite ~1.5k; FILTER = variable low-pass (clockwise darker)
 'rat': R(on('dirt', 'eq', 'ns'), DIST(+10, 60, 55),
          EQ(hi=(4500, 0), hm=(1600, +3, 1.2), lm=(400, -1, 1.0), lo=(100, +1)), NS(28)),
 # DS-1: transistor boost + hard clip; tone stack = tilt with a ~500 Hz dip
 'ds1': R(on('dirt', 'eq', 'ns'), DIST(+5, 50, 55),
          EQ(hi=(5000, +2), hm=(1800, +1, 1.0), lm=(500, -4, 1.0), lo=(100, 0)), NS(28)),
 # Big Muff (NYC '73): two clipping stages, huge sustain, tone stack scoop ~1 kHz
 'bigmuff': R(on('comp', 'dirt', 'eq', 'ns'), COMP(0, 50, 70, 55), DIST(-5, 85, 50),
              EQ(hi=(4000, -2), hm=(1000, -8, 1.0), lm=(300, +1, 1.0), lo=(100, +3), out=+1), NS(30)),
 # MT-2 ('91): two gain stages, scoop, 10 kHz-ish fizz; parametric mid (user layout LO HM LM H G L)
 'metalzone': R(on('comp', 'dirt', 'eq', 'ns'), COMP(0, 40, 50, 55), DIST(+10, 90, 50),
                EQ(hi=(6000, +2), hm=(2500, +5, 1.5), lm=(500, -7, 1.5), lo=(100, +2)), NS(32)),
 # SD-1: TS family, asymmetric clip -> brighter, less bass cut
 'sd1': R(on('dirt', 'eq', 'ns', od=True), OD(+8, 48, 58),
          EQ(hi=(4000, 0), hm=(750, +4, 1.0), lm=(250, -1, 1.5), lo=(140, -6)), NS(22)),
 # Klon: clean blend + germanium diodes, gentle ~1 kHz bump, active treble shelf, lots of clean output
 'klon': R(on('dirt', 'eq', 'ns', od=True), OD(0, 30, 65),
           EQ(hi=(3000, +1), hm=(1000, +3, 1.0), lm=(300, 0, 1.0), lo=(100, 0)), NS(18)),
 # Fuzz Face (germanium): splatty, woolly low-mids, soft top, gate barely there
 'fuzzface': R(on('dirt', 'eq', 'ns'), DIST(-12, 72, 52),
               EQ(hi=(5000, -6), hm=(2000, -2, 1.0), lm=(300, +2, 1.0), lo=(120, +3)), NS(12, 60)),
 # Metal Muff: Muff core + top boost, tighter lows
 'metalmuff': R(on('comp', 'dirt', 'eq', 'ns'), COMP(0, 45, 55, 55), DIST(+5, 88, 50),
                EQ(hi=(5000, +4), hm=(1000, -6, 1.0), lm=(300, 0, 1.0), lo=(90, +2)), NS(32)),
 # Funeralopolis path: Muff > cocked wah (picking filter parked) > something loud (comp after the wah = cranked amp)
 'funeral': R({0x00: 1, 0x01: 2, 0x02: 0, 0x03: 3, 0x04: 4}, on('comp', 'dirt', 'pick', 'eq', 'ns'),
              COMP(-10, 60, 75, 52), DIST(-15, 95, 48), PICK(0, 45, 4.2, 0),
              EQ(hi=(3000, -9), hm=(1000, -7, 1.0), lm=(250, +2, 1.0), lo=(100, +5)), NS(28)),
 # Iommi: Rangemaster into a cranked Laney -- treble-boosted OD, 1.6 kHz push, lows trimmed
 'ironman': R(on('dirt', 'eq', 'ns', od=True), OD(+16, 70, 58, turbo=1),
              EQ(hi=(4000, +2), hm=(1600, +5, 1.2), lm=(250, -3, 1.0), lo=(90, -4)), NS(30)),
 # Boss CS-3 / MXR Dyna Comp / others (A1)
 'dynacomp': R(on('comp'), COMP(-10, 10, 70, 55)),            # OTA squash, fast attack, slightly dull
 'cs3': R(on('comp'), COMP(0, 50, 50, 55)),
 'touchwah': R(on('pick'), PICK(60, 35, 3.0, 1), {0x5C: 127}),  # envelope filter up-sweep
 'slicer': R(on('phaser'), PHASE(60, 100, 20, 70, 100)),      # stepped (sample & hold) phaser chop
 'ge7': R(on('eq'), EQ(hi=(6400, 0), hm=(1600, 0, 1.4), lm=(400, 0, 1.4), lo=(100, 0))),   # GE-7 bands 100/400/1.6k/6.4k
 'ns2': R(on('ns'), NS(30, 50, 50)),
 'doubler': R(on('sdly'), SDLY(20, 55)),                      # 20 ms ADT
 'octave': R(on('mod', b2='pitch'), PITCH(-12, 100)),         # 50/50 octave down
 'autopan': R(on('pan'), PAN(30, 80, 0)),
 # CE-2: BBD chorus, short pre-delay, 50/50 mix, warm
 'chorus': R(on('mod', b2='chorus'), CHORUS(7, 30, 55, 70)),
 'dimensiond': R(on('mod', b2='spaced'), {0x41: 1}),          # Roland's own SPACE-D (SDD-320 modes)
 # Phase 90 (script): 4 stages, little feedback, smooth
 'phaser': R(on('phaser'), PHASE(35, 100, 50, 25, 0)),
 # BF-2: jet flanger
 'flanger': R(on('mod', b2='flanger'), FLANGER(25, 70, 45, 60)),
 # Fender-style bias trem
 'tremolo': R(on('pan'), PAN(45, 70, 1)),
 # Leslie 122: horn = pan + doppler chorus, drum/preamp growl from a little OD (grabs the dirt block if free)
 'leslie': R(on('mod', 'pan', 'dirt', od=True, b2='chorus'), CHORUS(3, 12, 60, 60), PAN(12, 60, 0), OD(-5, 15, 55)),
 # Slapback (B1 max 100 ms) and the B4 delays
 'slapback': R(on('sdly'), SDLY(95, 40)),
 'digital': R(on('dly'), TAP(375, 50, fb=35)),                # DD-3: clean, full range
 # RE-201: three heads = the three taps (1:2:3), dark tape, its spring reverb (grabs B5 if free)
 'spaceecho': R(on('dly', 'rev'), TAP(450, 0, 150, 70, 300, 0, fb=45, cutf=2500),
                REVERB(18, 8, 3500, 0, 0)),
 # reverbs (B5): mode 0-9 ROOM1-3 HALL1-3 PLATE1-2 SPRING1-2
 'spring': R(on('rev'), REVERB(18, 8, 3500, 0, 35)),          # Fender 6G15-ish drip
 'hallplate': R(on('rev'), REVERB(35, 6, 6000, 10, 30)),      # EMT plate
 'shimmer': R(on('mod', 'rev', b2='pitch'), PITCH(+12, 60, 0, 45, 30), REVERB(60, 5, None, 20, 60)),  # octave feedback into hall
 'cathedral': R(on('rev'), REVERB(70, 5, 2500, 60, 50)),      # huge, dark, long pre-delay
 'cave': R(on('rev', 'dly'), REVERB(55, 2, 2000, 10, 45), TAP(410, 30, 180, 25, 290, 25, fb=25, cutf=1800)),  # + rock echoes
 'church': R(on('rev'), REVERB(60, 4, 3500, 35, 45)),
 'stage': R(on('rev'), REVERB(12, 1, 6000, 5, 30)),
 'ambient': R(on('rev', 'mod', b2='chorus'), REVERB(65, 5, 5000, 25, 55), CHORUS(20, 10, 60, 35)),   # hall + slow swirl
 # wahs: picking filter swept by the expression pedal (assign #12 = cutoff)
 'crybaby': R(on('pick'), PICK(0, 50, 3.5, 0), EXP(12, 10, 85)),     # GCB-95: ~350 Hz-2.2 kHz, Q ~3.5
 'resowah': R(on('pick'), PICK(0, 50, 5.0, 0), EXP(12, 10, 85)),     # vocal, max Q
 # --- v1 picks ---
 # HM-2 chainsaw: hard clip, LOW = ~100 Hz boost, HIGH = ~1.1 kHz peak (+top), scoop between
 'hm2': R(on('dirt', 'eq', 'ns'), DIST(+12, 92, 50),
          EQ(hi=(3500, +3), hm=(1100, +10, 1.5), lm=(400, -5, 1.0), lo=(100, +10)), NS(35)),
 # Rangemaster (OC44): treble booster, lows cut hard, ~2 kHz push, light grit
 'rangemaster': R(on('dirt', 'eq', od=True), OD(+25, 35, 70),
                  EQ(hi=(4000, +3), hm=(2000, +6, 1.0), lm=(300, -6, 1.0), lo=(200, -12))),
 # OD-1: the first Boss OD, asymmetric, ~700 Hz hump, no tone control
 'od1': R(on('dirt', 'eq', 'ns', od=True), OD(-2, 45, 60),
          EQ(hi=(3500, -3), hm=(700, +5, 1.0), lm=(250, -1, 1.5), lo=(150, -6)), NS(22)),
 # Fuzz Factory: comp + max fuzz + gate on the edge (sputter); STAB = tone
 'fuzzfactory': R(on('comp', 'dirt', 'eq', 'ns'), COMP(+5, 30, 60, 55), DIST(+5, 90, 50),
                  EQ(hi=(5000, +1), hm=(1500, +1, 1.0), lm=(400, -3, 1.0), lo=(110, +2)), NS(60, 20)),
 # Octavia: bright fuzz + octave up after it (B2 pitch, grabs it if free)
 'octavia': R(on('dirt', 'eq', 'ns', 'mod', b2='pitch'), DIST(+20, 80, 50),
              EQ(hi=(4000, +4), hm=(1500, +3, 1.0), lm=(300, -3, 1.0), lo=(120, -5)), NS(30), PITCH(+12, 120)),
 # Ram's Head Muff ('73-'77): deeper ~900 Hz scoop, brighter, less bass
 'ramshead': R(on('comp', 'dirt', 'eq', 'ns'), COMP(0, 50, 60, 55), DIST(+5, 82, 50),
               EQ(hi=(4000, +1), hm=(900, -9, 1.2), lm=(300, 0, 1.0), lo=(100, +1)), NS(30)),
 # Green Russian (Sovtek '90s): darker, bassier, milder ~800 Hz scoop
 'greenrussian': R(on('comp', 'dirt', 'eq', 'ns'), COMP(-5, 50, 70, 55), DIST(-10, 78, 50),
                   EQ(hi=(3000, -3), hm=(800, -5, 1.0), lm=(250, +2, 1.0), lo=(100, +4)), NS(30)),
 # Electric Mistress: slow, deep flanger with chorus-like resonance
 'mistress': R(on('mod', b2='flanger'), FLANGER(15, 60, 45, 70)),
 # CE-1: chorus/vibrato + its preamp grit (a touch of OD, grabs the dirt block if free)
 'ce1': R(on('dirt', 'mod', od=True, b2='chorus'), OD(-5, 8, 55), CHORUS(10, 22, 55, 60)),
 # Whammy: pitch fully wet on the expression pedal (#45 = PS CHROM, heel 0, toe +12)
 'whammy': R(on('mod', b2='pitch'), PITCH(0, 200), EXP(45, 12, 24)),
 # Memory Man: dark BBD repeats + its chorus (B2, grabbed if free)
 'memoryman': R(on('dly', 'mod', b2='chorus'), TAP(350, 55, fb=40, cutf=2200), CHORUS(8, 35, 30, 30)),
 # Shoegaze wash: chorus into dark delay into hall
 'shoegaze': R(on('mod', 'dly', 'rev', b2='chorus'), CHORUS(30, 15, 60, 50), TAP(472, 45, fb=50, cutf=2500),
               REVERB(60, 5, 3000, 30, 70)),
 'ross': R(on('comp'), COMP(-8, 30, 60, 55)),                 # smoother, darker than the Dyna
 'squeezer': R(on('comp'), COMP(+10, 70, 40, 60)),            # JFET, gentle, mid-forward
 'smallclone': R(on('mod', b2='chorus'), CHORUS(5, 30, 40, 55)),
 'dimc': R(on('mod', 'sdly', b2='chorus'), CHORUS(25, 20, 35, 55), SDLY(10, 25)),   # DC-2: chorus + doubler width
}

# Level trims (EQ OUT, dB; tone unchanged). User 2026-10-13: "every fuzz is loud now except the funeral" = the fuzzes
# are right, bring Funeral up to them (NOT the fuzzes down); then "louder funeral and ts etc, a little eq gain" = the
# overdrives up to the fuzz level too. re/level_match.py estimates loudness from the recipes.
TRIM = {'funeral': 7.0, 'tubescreamer': 5.0, 'sd1': 6.0, 'klon': 5.0, 'ironman': 4.0, 'rangemaster': 4.5, 'od1': 5.5}   # v2.1: Funeral + overdrives up to the fuzz level
for _k, _t in TRIM.items():
    PEDALS[_k][0x2D] = db((PEDALS[_k].get(0x2D, 24) - 24) / 2 + _t)


# AMP voicings = EQ(4-band) + line-out cab + power-amp comp, NO distortion (gain comes from the pedal).
AMPS = {
 'clean': R(on('eq', 'amp'), EQ(hi=(5000, +3), hm=(1500, 0, 1.0), lm=(500, -5, 1.0), lo=(100, +2)),
            LINE(55, 55, 45, 50, 80)),                        # blackface: scooped ~500 Hz, sparkle
 'twin': R(on('eq', 'amp'), EQ(hi=(5000, +5), hm=(2000, +1, 1.0), lm=(500, -7, 1.0), lo=(90, +3)),
           LINE(58, 62, 40, 48, 80)),                         # deeper scoop, bright, big headroom
 'jcm800': R(on('eq', 'amp'), EQ(hi=(4000, +2), hm=(800, +5, 1.0), lm=(300, 0, 1.0), lo=(110, -2)),
             LINE(62, 55, 58, 45, 80)),                       # mid-forward 800 Hz, presence
 'ac30': R(on('eq', 'amp'), EQ(hi=(3000, +5), hm=(1200, +3, 1.2), lm=(400, -2, 1.0), lo=(100, -1)),
           LINE(55, 60, 52, 48, 80)),                         # top boost chime, loose bass
 'doom': R(on('comp', 'eq', 'amp'), COMP(0, 55, 55, 55), EQ(hi=(3500, -6), hm=(1200, -2, 1.0), lm=(400, +4, 1.0), lo=(100, +4)),
           LINE(40, 35, 55, 62, 80)),                         # Orange/Matamp: thick low-mids, rolled top, squash
 'di': R(EQ(hi=(4000, 0), hm=(1000, 0, 1.0), lm=(300, 0, 1.0), lo=(100, 0)), {0x5B: 80}),   # flat, cab off
 'radio': R(on('comp', 'eq', 'amp'), COMP(0, 50, 60, 50), EQ(hi=(2500, -12), hm=(1200, +6, 2.0), lm=(500, +3, 1.0), lo=(250, -12)),
            LINE(40, 30, 65, 25, 72)),                        # transistor radio band-pass
 'jc120': R(on('eq', 'amp'), EQ(hi=(6000, +4), hm=(2000, 0, 1.0), lm=(400, -1, 1.0), lo=(100, 0)),
            LINE(60, 62, 50, 45, 80)),                        # flat, glassy
 '5150': R(on('eq', 'amp'), EQ(hi=(4500, +3), hm=(2500, +4, 1.2), lm=(500, -4, 1.0), lo=(80, -3)),
           LINE(70, 58, 45, 55, 80)),                         # tight lows, upper-mid bite
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
