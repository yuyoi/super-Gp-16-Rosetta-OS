"""GP Tone Zone: the GP-16's 4-band EQ as the DSP actually computes it (decoded in re/DSP_CRACK.md, fs = 32 kHz).
- HI: shelf 1 + (G-1)*(1 - LP), LP = 2nd-order bilinear low-pass WITHOUT prewarp (K = pi f / fs). G = 0 = a true
  2nd-order low-pass (the cab knob), G = 1 = flat. The realised Q is HI_QMUL x the designed one (0.707 for the knob).
- HM / LM: Chamberlin state-variable filter, f = 2 sin(pi fc / fs), damping q = 1 / (1 + v/40) for the Q knob value
  v (0-40, labelled "Q 1.0-5.0" by Roland: the real Q is only 1-2). Boost 1 + (G-1)*qBP; cut is the inverse of a 1/G boost.
- LO: the same SVF as a shelf, 1 + (G-1)*LP (fixed damping LO_Q).
response_db(freqs, p) takes the fit's 10 values (hi_f, hi_g, hm_f, hm_g, hm_q, lm_f, lm_g, lm_q, lo_f, lo_g) with the Q
values in Roland's labelled units (1-5), like re/pedals.py."""
import numpy as np

FS = 32000.0
HI_QMUL = 1.3       # realised HI Q / designed Q   } fitted to Cab A as measured on the unit (0.65 dB rms over
LO_Q = 2.8          # LO shelf SVF damping         } 100 Hz-13 kHz); Cab B, not fitted: within 1.7 dB at 100 Hz-13 kHz


def _z1(freqs):
    return np.exp(-2j * np.pi * np.asarray(freqs, dtype=float) / FS)


def hi_lp(z1, f, q=1 / np.sqrt(2)):
    K = np.pi * f / FS
    q = q * HI_QMUL
    return K * K * (1 + z1) ** 2 / ((1 + K / q + K * K) + 2 * (K * K - 1) * z1 + (1 - K / q + K * K) * z1 * z1)


def hi_shelf(z1, f, g_db, q=1 / np.sqrt(2), lp=False):
    g = 0.0 if lp else 10 ** (g_db / 20)
    return 1 + (g - 1) * (1 - hi_lp(z1, f, q))


def _svf(z1, fc, q):
    f = 2 * np.sin(np.pi * fc / FS)
    d = 1 + (f * f + f * q - 2) * z1 + (1 - f * q) * z1 * z1
    return f * (1 - z1) / d, f * f * z1 / d             # band-pass, low-pass


def bell(z1, fc, g_db, q_label):
    v = np.clip((q_label - 1) * 10, 0, 40)
    q = 1 / (1 + v / 40)
    bp, _ = _svf(z1, fc, q)
    g = 10 ** (g_db / 20)
    return 1 + (g - 1) * q * bp if g_db >= 0 else 1 / (1 + (1 / g - 1) * q * bp)


def lo_shelf(z1, fc, g_db, q=None):
    _, lp = _svf(z1, fc, LO_Q if q is None else q)
    return 1 + (10 ** (g_db / 20) - 1) * lp


def response_db(freqs, p):
    hi_f, hi_g, hm_f, hm_g, hm_q, lm_f, lm_g, lm_q, lo_f, lo_g = p
    z1 = _z1(freqs)
    h = hi_shelf(z1, hi_f, hi_g) * bell(z1, hm_f, hm_g, hm_q) * bell(z1, lm_f, lm_g, lm_q) * lo_shelf(z1, lo_f, lo_g)
    return 20 * np.log10(np.abs(h) + 1e-12)


if __name__ == '__main__':
    # Cab A, measured on the unit (re/DSP_CRACK.md): HI LP 4.5 kHz Q1.2, LM 110 Hz +6 (v40), HM 1.4 kHz -5 (v10),
    # LO 70 Hz -12 -> +5.5 @100, -2 @1k, +2.7 @4k, -12.8 @8k, -34.7 @13k (change vs flat)
    fq = np.array([100, 1000, 4000, 8000, 13000.0])
    meas = np.array([5.5, -2, 2.7, -12.8, -34.7])
    z1 = _z1(fq)
    h = hi_shelf(z1, 4500, 0, q=1.2, lp=True) * bell(z1, 110, 6, 5.0) * bell(z1, 1400, -5, 2.0) * lo_shelf(z1, 70, -12)
    m = 20 * np.log10(np.abs(h))
    print('model', np.round(m, 1), 'measured', meas, 'rms err', round(float(np.sqrt(np.mean((m - meas) ** 2))), 2))
