"""GP Tone Zone: measured capture -> GP-16 recipe (SysEx pairs in real units) + knobs, in the OS's own formats.
EQ: the GP-16's 4 bands (HI shelf 2-8 kHz, HM bell 500 Hz-4 kHz, LM bell 125 Hz-1 kHz, LO shelf 60-250 Hz, Q 1-5,
+-12 dB, firmware frequency tables) least-squares fitted to the capture's voicing curve. Dirt type from the clipping
character, drive from the matched clipper gain, level matched to the OS's fuzz level (re/level_match.py)."""
import importlib.util, os
import numpy as np
from scipy.optimize import least_squares

from tz_capture import HERE
import tz_gpeq as G

RE = os.path.join(HERE, '..', 're')


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(RE, name + '.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


P = _load('pedals')
LM = _load('level_match')
FUZZ_LEVEL = 10.0                       # level_match units: where the user likes the fuzzes (v2.1 calibration)

# band limits (Hz) and shape model, same as re/level_match.py
LIM = {'hi': (2000, 8000), 'hm': (500, 4000), 'lm': (125, 1000), 'lo': (60, 250)}


def eq_db(f, p):
    """the GP-16 EQ's real response (tz_gpeq: decoded DSP math, checked against cabs measured on the unit)"""
    return G.response_db(f, p)


def fit_eq(freqs, target):
    w = np.where((freqs >= 80) & (freqs <= 6000), 1.0, 0.3)
    p0 = [4000, 0, 1200, 0, 1.2, 400, 0, 1.2, 120, 0]
    lo = [2000, -12, 500, -12, 1.0, 125, -12, 1.0, 60, -12]
    hi = [8000, 12, 4000, 12, 5.0, 1000, 12, 5.0, 250, 12]
    best = None
    for hm0 in (700, 1500, 2800):                               # a few starts: the bells can trade places
        for lm0 in (200, 450):
            p0[2], p0[5] = hm0, lm0
            r = least_squares(lambda p: w * (eq_db(freqs, p) - target), p0, bounds=(lo, hi))
            if best is None or r.cost < best.cost:
                best = r
    return best.x, float(np.sqrt(np.mean((eq_db(freqs, best.x) - target) ** 2)))


def fit(cap, m):
    """-> dict: name, kind ('pedal' | 'amp'), recipe {addr: value}, knobs, report lines"""
    p, err = fit_eq(m['freqs'], m['voicing'])
    name = ''.join(ch for ch in cap.name.upper() if 32 <= ord(ch) < 127)[:13] or 'CAPTURE'
    report = [f'{cap.describe()}',
              f'clipping: {m["kind"]}  THD {100 * m["thd"]:.0f}%  hard-clip index {m["hard"]:.2f}  '
              f'odd/even {m["odd_even"]:.1f}  compression slope {m["slope"]:.2f}']
    kind = 'amp' if m['kind'] == 'clean' else m['kind']
    drive = int(np.clip(round(5 + m['drive_db'] * 1.6), 5, 100))       # ~+60 dB into clipping = GP drive 100
    return make(name, kind, p, err, drive, report, m)


def make(name, kind, p, err, drive=50, report=(), m=None, trim=None, gate=True):
    """kind 'amp' | 'od' | 'dist', p = the 10 EQ fit values, drive 5-100; trim = EQ OUT dB (None: loudness model)"""
    hi_f, hi_g, hm_f, hm_g, hm_q, lm_f, lm_g, lm_q, lo_f, lo_g = p
    eq = P.EQ(hi=(hi_f, hi_g), hm=(hm_f, hm_g, hm_q), lm=(lm_f, lm_g, lm_q), lo=(lo_f, lo_g))
    report = list(report) + [
        f'EQ fit (rms error {err:.1f} dB): LO {lo_f:.0f} Hz {lo_g:+.1f} | LM {lm_f:.0f} Hz {lm_g:+.1f} Q{lm_q:.1f} | '
        f'HM {hm_f:.0f} Hz {hm_g:+.1f} Q{hm_q:.1f} | HI {hi_f:.0f} Hz {hi_g:+.1f}']
    fitd = {'eq': [float(v) for v in p], 'rms_err_db': err, 'dirt': kind}
    if kind == 'amp':
        rec = P.R(P.on('eq', 'amp'), eq, P.LINE(50, 50, 50, 50, 80))
        knobs = [('VOL', [(0x5B, 40, 100)]), ('TRB', [(0x24, P.db(hi_g - 6), P.db(hi_g + 6))]),
                 ('MID', [(0x27, P.db(hm_g - 6), P.db(hm_g + 6))]), ('BAS', [(0x2C, P.db(lo_g - 6), P.db(lo_g + 6))])]
        report.append('-> AMP (RIG mode): EQ + cab, no dirt')
        return {'name': name, 'kind': 'amp', 'recipe': rec, 'knobs': knobs, 'report': report, 'fit': fitd}
    drive = int(np.clip(round(drive), 5, 100))
    if kind == 'dist':
        dirt = P.DIST(0, drive, 50)
        a_drv, a_ton, a_lvl, od = 0x14, 0x13, 0x15, False
    else:
        dirt = P.OD(0, drive, 60)
        a_drv, a_ton, a_lvl, od = 0x17, 0x16, 0x19, True
    if gate:
        rec = P.R(P.on('dirt', 'eq', 'ns', od=od), dirt, eq, P.NS(45 if kind == 'dist' else 25, 30 if kind == 'dist' else 50))
    else:                                               # measuring on the unit: the gate would eat the quiet rungs
        rec = P.R(P.on('dirt', 'eq', od=od), dirt, eq)
    if trim is None:                                    # level: same loudness as the OS's fuzzes (EQ OUT)
        trim = FUZZ_LEVEL - LM.loudness(rec)
    rec[0x2D] = P.db(max(-12, min(12, round(trim * 2) / 2)))
    knobs = [('GAN', [(a_drv, max(0, drive - 40), min(100, drive + 30))]),
             ('TON', [(0x24, P.db(hi_g - 6), P.db(hi_g + 6)), (a_ton, 30, 70)]),
             ('MID', [(0x27, P.db(hm_g - 6), P.db(hm_g + 6))]),
             ('VOL', [(a_lvl, 20, 100)])]
    into = f' (+{m["drive_db"]:.0f} dB into clipping, knee {m["knee_db"]:+.0f} dB)' if m else ''
    report.append(f'-> PEDAL (A2 {"OD" if od else "DIST"}): drive {drive}{into}, '
                  f'EQ out {(rec[0x2D] - 24) / 2:+.1f} dB')
    fitd.update(drive=drive, trim=(rec[0x2D] - 24) / 2)
    return {'name': name, 'kind': 'pedal', 'recipe': rec, 'knobs': knobs, 'report': report, 'fit': fitd}


def fitted_curve(freqs, result):
    return eq_db(freqs, result['fit']['eq'])
