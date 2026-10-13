"""GP Tone Zone: a synthetic 'capture' with known insides, to test the analyse -> fit -> refine-on-unit chain without
a real NAM file: pre-emphasis high-pass, tanh clipper, post low-pass + mid bump (a Tube Screamer-ish overdrive).
Same interface as tz_capture.Capture (name, meta, input_dbu, describe, process)."""
import numpy as np
from scipy.signal import butter, sosfilt

from tz_capture import SR


def _peak(f0, g_db, q):
    a = 10 ** (g_db / 40); w = 2 * np.pi * f0 / SR; al = np.sin(w) / (2 * q)
    b = [1 + al * a, -2 * np.cos(w), 1 - al * a]; d = [1 + al / a, -2 * np.cos(w), 1 - al / a]
    return np.array([[b[0] / d[0], b[1] / d[0], b[2] / d[0], 1, d[1] / d[0], d[2] / d[0]]])


class SynthCapture:
    kind, arch, sr = 'nam', 'synthetic', SR

    def __init__(self, name='SYNTH TS', gain_db=34.0, hp=500.0, lp=3500.0, mid=(900, 4.0, 1.0), hard=False):
        self.file = name.lower().replace(' ', '_') + '.synth'
        self.path = self.file
        self.meta = {'name': name, 'gear_type': 'pedal', 'tone_type': 'overdrive', 'input_level_dbu': 12.0}
        self.g, self.hard = 10 ** (gain_db / 20), hard
        self.pre = butter(1, hp, 'highpass', fs=SR, output='sos')
        self.post = np.vstack([butter(2, lp, 'lowpass', fs=SR, output='sos'), _peak(*mid)])

    @property
    def name(self): return self.meta['name']

    @property
    def input_dbu(self): return self.meta['input_level_dbu']

    def describe(self): return f'{self.file}: synthetic overdrive (test capture)'

    def process(self, x):
        v = self.g * sosfilt(self.pre, np.asarray(x, dtype=np.float64))
        v = np.clip(v, -1, 1) if self.hard else np.tanh(v)
        return 0.5 * sosfilt(self.post, v)
