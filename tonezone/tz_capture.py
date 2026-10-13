"""GP Tone Zone: load tone captures and run audio through them.
NAM .nam (WaveNet / LSTM, old 0.5.x and new files) through Steven Atkinson's own NAM code (vendored in _vendor, MIT),
cab IRs (.wav) by convolution. Everything at 48 kHz, float64 numpy in, numpy out."""
import copy, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '_vendor'))
SR = 48000


class Capture:
    """kind: 'nam' or 'ir'; meta: dict (gear_type, tone_type, gear_make, gear_model, name, input_level_dbu, ...)"""

    def __init__(self, path):
        self.path = path
        self.file = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        if ext == '.nam':
            self.kind = 'nam'
            with open(path, 'r', encoding='utf-8') as f:
                self.raw = json.load(f)
            self.meta = dict(self.raw.get('metadata') or {})
            self.meta.pop('training', None)
            self.arch = self.raw.get('architecture', '?')
            self.sr = float(self.raw.get('sample_rate') or 48000)
            self._model = None
        elif ext == '.wav':
            import soundfile as sf
            self.kind = 'ir'
            ir, sr = sf.read(path, always_2d=True)
            ir = ir[:, 0]
            if sr != SR:
                ir = _resample(ir, sr, SR)
            self.ir = ir
            self.meta = {'gear_type': 'cab', 'name': os.path.splitext(self.file)[0]}
            self.arch = 'IR'
            self.sr = SR
        else:
            raise ValueError(f'{self.file}: not a .nam or .wav')

    @property
    def name(self):
        m = self.meta
        return (m.get('gear_model') or m.get('name') or os.path.splitext(self.file)[0]).strip()

    @property
    def input_dbu(self):
        """dBu that 0 dBFS at the capture input corresponds to (NAM metadata; 12 dBu is a typical interface)"""
        return float(self.meta.get('input_level_dbu') or 12.0)

    def describe(self):
        m = self.meta
        bits = [m.get('gear_type', '?'), m.get('tone_type', '?')]
        mk = ' '.join(x for x in (m.get('gear_make'), m.get('gear_model')) if x)
        return f'{self.file}: {self.arch}, {" / ".join(bits)}' + (f', {mk}' if mk else '')

    # ---- NAM
    def model(self):
        if self._model is None:
            import torch
            from nam.models import init_from_nam
            torch.set_grad_enabled(False)
            if self.arch not in ('WaveNet', 'LSTM', 'Linear'):
                raise NotImplementedError(f'{self.file}: architecture {self.arch} not supported yet (use a WaveNet/LSTM capture)')
            self._model = init_from_nam(_upgrade(self.raw))
            self._model.eval()
        return self._model

    def process(self, x):
        """x: float array at 48 kHz, full scale = the capture's 0 dBFS -> output array (same length)"""
        x = np.asarray(x, dtype=np.float64)
        if self.kind == 'ir':
            return np.convolve(x, self.ir)[:len(x)]
        import torch
        xs = x if self.sr == SR else _resample(x, SR, self.sr)
        y = self.model()(torch.tensor(xs, dtype=torch.float32), pad_start=True).numpy().astype(np.float64)
        if self.sr != SR:
            y = _resample(y, self.sr, SR)[:len(x)]
        return y


def _upgrade(raw):
    """Old (0.5.x) WaveNet layer configs -> the layout the current NAM loader expects."""
    d = copy.deepcopy(raw)
    if d.get('architecture') != 'WaveNet':
        return d
    c = d['config']
    for lc in c['layers']:
        if 'head' not in lc and 'head_size' in lc:
            lc['head'] = {'out_channels': lc.pop('head_size'), 'kernel_size': 1, 'bias': bool(lc.pop('head_bias', False))}
        if 'gated' in lc:
            gated = lc.pop('gated')
            if gated:
                prim = lc.get('activation', 'Tanh')
                lc['activation'] = {'name': 'PairMultiply', 'primary': prim, 'secondary': 'Sigmoid'}
    return d


def _resample(x, sr_in, sr_out):
    from scipy.signal import resample_poly
    from fractions import Fraction
    fr = Fraction(int(round(sr_out)), int(round(sr_in))).limit_denominator(1000)
    return resample_poly(x, fr.numerator, fr.denominator)


def find(folder):
    out = []
    for f in sorted(os.listdir(folder)):
        if f.lower().endswith(('.nam', '.wav')):
            try:
                out.append(Capture(os.path.join(folder, f)))
            except Exception as e:                      # a bad file must not stop the list
                print(f'skip {f}: {e}')
    return out
