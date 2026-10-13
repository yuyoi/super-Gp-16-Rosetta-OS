"""GP Tone Zone: measure a capture -- gain, clipping character, voicing curve, loudness.
The capture sees a calibrated guitar: peaks at GUITAR_PEAK_DBU, converted to its own dBFS through input_level_dbu."""
import os
import numpy as np
from scipy.signal import welch

from tz_capture import SR, HERE

GUITAR_PEAK_DBU = 2.0                     # a strong humbucker strum peaks around +2 dBu
FREQS = np.array([60 * 2 ** (i / 6) for i in range(44)])    # 60 Hz .. ~9.6 kHz, 1/6 octave


def guitar_di(seconds=4.0, seed=1):
    """NAM's own guitar DI clip (in the vendored package) + Karplus-Strong riffs, peak-normalised to 1.0"""
    import soundfile as sf
    parts = []
    p = os.path.join(HERE, '_vendor', 'nam', 'models', '_resources', 'loudness_input.wav')
    if os.path.exists(p):
        x, sr = sf.read(p)
        if x.ndim > 1:
            x = x[:, 0]
        parts.append(x / np.abs(x).max())
    rng = np.random.default_rng(seed)
    n_total = int(seconds * SR)
    out = np.zeros(n_total)
    t = 0
    notes = [82.4, 110, 146.8, 82.4, 98, 123.5, 196, 246.9, 329.6, 110, 164.8, 220]
    while t < n_total:
        f0 = notes[rng.integers(len(notes))]
        dur = int(SR * rng.choice([0.25, 0.5]))
        for mult in (1, 1.5, 2) if rng.random() < 0.5 else (1,):           # power chord or single note
            out[t:t + dur] += _pluck(f0 * mult, dur, rng)[:max(0, min(dur, n_total - t))]
        t += dur
    parts.append(out / np.abs(out).max())
    return np.concatenate(parts)


def _pluck(f0, n, rng):
    p = max(2, int(round(SR / f0)))
    buf = rng.uniform(-1, 1, p)
    y = np.empty(n)
    for i in range(n):
        y[i] = buf[i % p]
        buf[i % p] = 0.5 * (buf[i % p] + buf[(i + 1) % p]) * 0.996
    return y


def db(v):
    return 20 * np.log10(np.maximum(np.abs(v), 1e-12))


def rms(v):
    return np.sqrt(np.mean(v ** 2) + 1e-24)


def spectrum_db(x, y):
    f, px = welch(x, SR, nperseg=8192)
    _, py = welch(y, SR, nperseg=8192)
    t = 10 * np.log10((py + 1e-20) / (px + 1e-20))
    out = []
    for fc in FREQS:                                            # 1/3-octave average around each point
        m = (f >= fc / 2 ** (1 / 6)) & (f <= fc * 2 ** (1 / 6))
        out.append(np.mean(t[m]) if m.any() else np.interp(fc, f, t))
    return np.array(out)


def harmonics(y, f0):
    y = y[len(y) // 4:]
    Y = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    k0 = f0 * len(y) / SR
    return np.array([Y[int(round(k * k0)) - 2:int(round(k * k0)) + 3].max() for k in range(1, 10)])


def clipper(x, gain_db, hard):
    g = 10 ** (gain_db / 20)
    return np.clip(g * x, -1, 1) if hard else np.tanh(g * x)


def measure(cap, progress=print):
    """-> dict of features (see keys below)"""
    peak_dbfs = GUITAR_PEAK_DBU - cap.input_dbu
    scale = 10 ** (peak_dbfs / 20)
    progress(f'{cap.file}: guitar peaks at {peak_dbfs:+.1f} dBFS of the capture input')
    di = guitar_di() * scale
    y = cap.process(di)
    # gain / clipping: 220 Hz sine from 30 dB below playing level up to playing level
    t = np.arange(int(0.5 * SR)) / SR
    levels = np.array([-60, -48, -36, -30, -24, -18, -12, -6, 0])
    outs, thd, h_play = [], [], None
    for lv in levels:
        x = scale * 10 ** (lv / 20) * np.sin(2 * np.pi * 220 * t)
        yy = cap.process(x)
        h = harmonics(yy, 220)
        outs.append(db(rms(yy[len(yy) // 4:])))
        thd.append(np.sqrt(np.sum(h[1:] ** 2)) / max(h[0], 1e-12))
        if lv == 0:
            h_play = h
    outs = np.array(outs)
    slope = np.polyfit(levels[-3:], outs[-3:], 1)[0]           # dB out per dB in at playing level (1 = clean, 0 = limited)
    small_gain = outs[0] - db(scale * 10 ** (levels[0] / 20) / np.sqrt(2))
    # knee: lowest input level whose output is already within 3 dB of the playing-level output (= gain into clipping)
    within = np.where(outs >= outs[-1] - 3)[0]
    knee = float(levels[within[0]]) if len(within) else 0.0
    odd = np.sqrt(np.sum(h_play[2::2] ** 2))                   # 3rd, 5th, 7th, 9th
    even = np.sqrt(np.sum(h_play[1::2] ** 2))                  # 2nd, 4th, 6th, 8th
    hi_odd = np.sqrt(np.sum(h_play[4::2] ** 2)) / max(h_play[2], 1e-12)     # 5th.. vs 3rd: slow fall = hard clip
    thd_play = thd[-1]
    if thd_play < 0.03:
        kind = 'clean'
    elif hi_odd > 0.45 or thd_play > 0.6:
        kind = 'dist'
    else:
        kind = 'od'
    tt = (cap.meta.get('tone_type') or '').lower()
    if tt in ('hi_gain', 'fuzz'):
        kind = 'dist'
    elif tt in ('overdrive', 'crunch') and kind == 'clean':
        kind = 'od'
    elif tt == 'clean':
        kind = 'clean'
    # voicing: capture tone curve minus what a generic clipper of the same THD does to the same DI
    curve = spectrum_db(di, y)
    if kind != 'clean':
        g = max(_match_clipper(di, thd_play, kind == 'dist', scale), -knee + 3)   # THD saturates; the knee does not
        ref = spectrum_db(di, clipper(di, g, kind == 'dist'))
        voicing = curve - ref
        drive_db = g
    else:
        voicing = curve
        drive_db = 0.0
    voicing = voicing - np.interp(1000, FREQS, voicing)        # 0 dB at 1 kHz; level is set separately
    return {'kind': kind, 'thd': float(thd_play), 'odd_even': float(odd / max(even, 1e-12)), 'hard': float(hi_odd),
            'slope': float(slope), 'small_gain_db': float(small_gain), 'drive_db': float(drive_db), 'knee_db': knee,
            'freqs': FREQS, 'voicing': voicing, 'curve': curve, 'out_rms_db': float(db(rms(y))),
            'peak_dbfs': float(peak_dbfs)}


def _match_clipper(di, thd_target, hard, scale):
    t = np.arange(int(0.5 * SR)) / SR
    x = scale * np.sin(2 * np.pi * 220 * t)
    best = (1e9, 0)
    for g in np.arange(0, 72, 2):
        h = harmonics(clipper(x, g, hard), 220)
        th = np.sqrt(np.sum(h[1:] ** 2)) / max(h[0], 1e-12)
        best = min(best, (abs(th - thd_target), g))
    return float(best[1])
