#!/usr/bin/env python3
"""Estimate each dirt pedal's loudness from its recipe and print EQ OUT trims that match the overdrives (TS / SD-1 /
OD-1 / Klon). Model (no audio, a guide for the ear):
  level param  -> 20 log10(level / 50)
  clipping     -> denser waveform = louder at the same peak: DIST +12 dB x drive, OD +3 dB x drive (+1.5 dB turbo)
                  (DIST calibrated by ear 2026-10-13: v2 fuzzes heard clearly louder than the overdrives, Funeral not)
  EQ           -> 4-band response (bells + shelves) power-averaged over a distorted-guitar spectrum (peak ~800 Hz)
  extras       -> parked picking filter (band-pass) -8 dB, comp after the dirt +2 dB, comp before +1 dB
Usage: py -3.11 level_match.py      (prints the table; pedals.py applies TRIM)"""
import importlib.util, math, os
here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pedals', os.path.join(here, 'pedals.py'))
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)

FREQS = [80 * 2 ** (i / 3) for i in range(22)]                     # 80 Hz .. ~10 kHz, 1/3 octave
W = [math.exp(-0.5 * (math.log2(f / 800) / 1.3) ** 2) for f in FREQS]


def inv(lo, hi, v, n=100): return lo * (hi / lo) ** (v / n)


def eq_curve(r):
    if not r.get(0x0E, 0) & 0x10:
        return 0.0
    g = lambda a: (r.get(a, 24) - 24) / 2
    hi_f, hm_f, lm_f, lo_f = inv(2000, 8000, r[0x23]), inv(500, 4000, r[0x25]), inv(125, 1000, r[0x28]), inv(60, 250, r[0x2B])
    hm_q, lm_q = 1 + r[0x26] / 10, 1 + r[0x29] / 10
    tot = 0
    for f, w in zip(FREQS, W):
        d = g(0x24) / (1 + (hi_f / f) ** 2) + g(0x2C) / (1 + (f / lo_f) ** 2)
        d += g(0x27) / (1 + (hm_q * (f / hm_f - hm_f / f)) ** 2) + g(0x2A) / (1 + (lm_q * (f / lm_f - lm_f / f)) ** 2)
        tot += w * 10 ** (d / 10)
    return 10 * math.log10(tot / sum(W)) + g(0x2D)


def loudness(r):
    od = bool(r.get(0x0D, 0) & 0x40)
    if od:
        lvl, drv, base = r.get(0x19, 50), r.get(0x17, 50), 3.0 + 1.5 * r.get(0x18, 0)
    else:
        lvl, drv, base = r.get(0x15, 50), r.get(0x14, 50), 12.0
    L = 20 * math.log10(max(lvl, 1) / 50) + base * drv / 100 + eq_curve(r)
    if r.get(0x0E, 0) & 0x04 and r.get(0x1A, 100) == 0:
        L -= 8                                                         # parked wah = band-pass
    if r.get(0x0E, 0) & 0x01:
        L += 2 if r.get(0x00, 0) == 1 else 1                           # comp after the dirt (Funeral path) / before
    return L


DIRT = [k for k, r in P.PEDALS.items() if r.get(0x0E, 0) & 0x02 and k not in ('leslie', 'ce1')]
REF = ['tubescreamer', 'sd1', 'od1', 'klon']


def trims(recipes):
    target = sum(loudness(recipes[k]) for k in REF) / len(REF)
    out = {}
    for k in DIRT:
        t = round((target - loudness(recipes[k])) * 2) / 2
        if abs(t) >= 1.0:
            out[k] = t
    return target, out


if __name__ == '__main__':
    base = {k: dict(r) for k, r in P.PEDALS.items()}
    for k in base:                                                     # undo any applied trim to see the raw model
        if k in P.TRIM:
            base[k][0x2D] = P.db((base[k][0x2D] - 24) / 2 - P.TRIM[k])
    target, t = trims(base)
    print(f'target (overdrive average) {target:+.1f} dB')
    for k in DIRT:
        print(f'  {k:13s} {loudness(base[k]):+5.1f} dB  trim {t.get(k, 0):+5.1f}   applied {P.TRIM.get(k, 0):+5.1f}')
    print('TRIM =', t)
