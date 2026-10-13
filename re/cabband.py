#!/usr/bin/env python3
"""Custom HI-band coefficients (chip1 0B1/0B3/0B4/0B5/0B6, gain 0B9) from the decoded firmware design: Butterworth-
style 2nd-order section, bilinear without prewarp, fs = 32 kHz, K = pi f / fs, a0 = 1 + K/Q + K^2:
  c0 = (1 + K/Q)/a0, c1 = -1/a0, c2 = (1 - K/Q)/a0, c3 = (1 - K^2)/a0, c4 = -(1 - K/Q + K^2)/a0;  gain = (G - 1)/4
G = 0 turns the HI shelf into a 2nd-order low-pass (cab roll-off).
  hi_coefs(f, q=0.7071, g_db=None) -> {step: 12-bit coef}"""
import math

FS = 32000.0
STEPS = (0x0B1, 0x0B3, 0x0B4, 0x0B5, 0x0B6)


def q12(x):
    v = int(round(x * 2048))
    assert -2048 <= v <= 2047, f'coef {x} out of range'
    return v & 0xFFF


def hi_coefs(f, q=1 / math.sqrt(2), g_db=None):
    K = math.pi * f / FS
    a0 = 1 + K / q + K * K
    c = [(1 + K / q) / a0, -1 / a0, (1 - K / q) / a0, (1 - K * K) / a0, -(1 - K / q + K * K) / a0]
    out = {s: q12(v) for s, v in zip(STEPS, c)}
    g = 0.0 if g_db is None else 10 ** (g_db / 20)
    out[0x0B9] = q12((g - 1) / 4)
    return out


if __name__ == '__main__':
    import sys
    f = float(sys.argv[1]); q = float(sys.argv[2]) if len(sys.argv) > 2 else 1 / math.sqrt(2)
    print(' ; '.join(f'1 {s:03x} coef={v:x}' for s, v in hi_coefs(f, q).items()))


def svf_f(f):
    """Chamberlin SVF frequency coefficient (HM 1:09C+0A0, LM 1:090+094, LO 1:0AC+0AF): 2 sin(pi f / fs)"""
    return q12(2 * math.sin(math.pi * f / FS))


def peak_gain(db):
    """HM / LM peak: (cut step, boost step) = HM (1:089, 1:0A5), LM (1:088, 1:0A4). G = 10^(dB/20):
    cut = (1/G - 1)/4 (G < 1), boost = (G - 1)/4 (G > 1). Firmware range +-12 dB (4 knob units per dB)."""
    g = 10 ** (db / 20)
    return (q12((1 / g - 1) / 4), 0) if db < 0 else (0, q12((g - 1) / 4))


def shelf_gain(db):
    """HI (1:0B9) / LO (1:0BA) shelf: (G - 1)/4; None = G 0 (-0.25). HI then is a true 2nd-order low-pass; LO is
    built as x + k*LP, so G 0 gives a dip below f and a bump above it, not a clean high-pass."""
    g = 0.0 if db is None else 10 ** (db / 20)
    return q12((g - 1) / 4)


def qcoef(v):
    """HM (1:07C) / LM (1:07A) damping as the firmware writes it for knob value v (0-40 = 'Q 1.0-5.0')"""
    return q12(0.25 / (1 + v / 40))


def cab(hi_f=4500, hi_q=1.2, lo_f=70, lo_db=-12, lm_f=110, lm_db=6, lm_qv=40, hm_f=1400, hm_db=-5, hm_qv=10):
    w = {}
    w.update(hi_coefs(hi_f, hi_q))                                     # HI: low-pass (gain G = 0)
    w[0x0AC] = w[0x0AF] = svf_f(lo_f); w[0x0BA] = shelf_gain(lo_db)     # LO: shelf cut
    w[0x090] = w[0x094] = svf_f(lm_f); w[0x088], w[0x0A4] = peak_gain(lm_db); w[0x07A] = qcoef(lm_qv)
    w[0x09C] = w[0x0A0] = svf_f(hm_f); w[0x089], w[0x0A5] = peak_gain(hm_db); w[0x07C] = qcoef(hm_qv)
    return w


def pokes(w):
    return ' ; '.join(f'1 {s:03x} coef={v:x}' for s, v in sorted(w.items()))
