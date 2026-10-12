#!/usr/bin/env python3
"""GP-16 DSP measurement rig: play a log sine sweep from the OCTA-CAPTURE into the GP-16, record its output,
deconvolve -> frequency response. Combined with the backdoor (gp16poke.py) to measure what a DSP poke does.
py -3.10 (sounddevice, numpy, scipy, matplotlib, mido). WASAPI 48 kHz.

Wiring: OCTA output pair --out (default 3-4, left ch) -> GP-16 INPUT (keep level low)
        GP-16 OUTPUT A -> OCTA input pair --in (default 5-6, left ch)

  py -3.10 dsprig.py measure [--name base]                       one response -> rig_out/<name>.csv/.png
  py -3.10 dsprig.py poke <chip> <step> <instr> <coef> [commit]   baseline, poke, measure, restore, overlay plot
  py -3.10 dsprig.py coefsweep <chip> <step> <c1,c2,...>          stock instruction, one curve per coefficient
All numbers hex. Restore = stock instruction (commit 0) + SOUND CHANGE REQUEST so the firmware reloads coefficients.
"""
import os, sys, time, argparse
import numpy as np

RATE = 48000
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rig_out')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def find_dev(pair, kind):
    import sounddevice as sd
    api = [i for i, h in enumerate(sd.query_hostapis()) if 'WASAPI' in h['name']][0]
    for i, d in enumerate(sd.query_devices()):
        if d['hostapi'] == api and d['name'].startswith(pair + ' (OCTA') and d[f'max_{kind}_channels'] > 0:
            return i
    raise SystemExit(f'no WASAPI {kind} device "{pair} (OCTA-CAPTURE)"')


def sweep(T=3.0, f1=20.0, f2=20000.0, level_db=-20.0):
    t = np.arange(int(T * RATE)) / RATE
    K = T / np.log(f2 / f1)
    x = np.sin(2 * np.pi * f1 * K * (np.exp(t / K) - 1)) * 10 ** (level_db / 20)
    fade = int(0.02 * RATE)
    x[:fade] *= np.linspace(0, 1, fade); x[-fade:] *= np.linspace(1, 0, fade)
    inv = x[::-1] * np.exp(-t / K)                      # Farina inverse filter (amplitude-compensated)
    return x.astype(np.float32), inv


def measure(args, name):
    import sounddevice as sd
    x, inv = sweep()
    pad = np.zeros(int(0.5 * RATE), np.float32)
    play = np.concatenate([pad, x, pad, pad])
    out2 = np.zeros((len(play), 2), np.float32); out2[:, 0] = play
    rec = sd.playrec(out2, RATE, channels=2, device=(find_dev(args.inp, 'input'), find_dev(args.out, 'output')),
                     dtype='float32', blocking=True)[:, 0]
    peak = float(np.max(np.abs(rec)))
    ir = np.fft.irfft(np.fft.rfft(rec, 2 * len(rec)) * np.fft.rfft(inv, 2 * len(rec)))
    k = int(np.argmax(np.abs(ir)))
    ir = ir[max(0, k - 256): k + RATE // 2]               # linear part only (drops harmonic IRs before the peak)
    H = np.fft.rfft(ir, RATE)
    f = np.fft.rfftfreq(RATE, 1 / RATE)
    db = 20 * np.log10(np.abs(H) + 1e-12)
    bands = np.geomspace(25, 18000, 120)                  # 1/12-octave-ish smoothing onto log grid
    sm = np.array([db[(f > b / 2 ** (1 / 24)) & (f < b * 2 ** (1 / 24))].mean() for b in bands])
    os.makedirs(OUT_DIR, exist_ok=True)
    np.savetxt(os.path.join(OUT_DIR, name + '.csv'), np.c_[bands, sm], delimiter=',', header='hz,db', comments='')
    print(f'{name}: rec peak {20*np.log10(peak+1e-12):.1f} dBFS, response saved')
    if peak > 0.9: print('  WARNING: recording near clipping, lower GP-16 output / OCTA input gain')
    if peak < 0.003: print('  WARNING: almost no signal: check loop wiring and effects bypass')
    return bands, sm


def plot(curves, title, fname):
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    plt.figure(figsize=(9, 4.5))
    for lab, (b, d) in curves.items(): plt.semilogx(b, d, label=lab)
    plt.grid(True, which='both', alpha=.3); plt.xlabel('Hz'); plt.ylabel('dB'); plt.title(title); plt.legend(fontsize=8)
    p = os.path.join(OUT_DIR, fname); plt.tight_layout(); plt.savefig(p, dpi=110); plt.close(); print('plot', p)


def restore(out, chip, step):
    import gp16poke as g, mido
    g.send(out, g.msg_write(chip, step, g.stock_instr(chip, step), 0, 0)); time.sleep(0.1)
    a = [0, 0, 0x75]; cs = (128 - sum(a) % 128) % 128
    out.send(mido.Message('sysex', data=[0x41, 0, 0x2A, 0x12] + a + [0, cs])); time.sleep(0.4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd'); ap.add_argument('args', nargs='*')
    ap.add_argument('--out', default='3-4'); ap.add_argument('--inp', '--in', dest='inp', default='5-6')
    ap.add_argument('--name', default='base'); ap.add_argument('--port', default='OCTA-CAPTURE')
    a = ap.parse_args()
    if a.cmd == 'measure':
        b, d = measure(a, a.name); plot({a.name: (b, d)}, a.name, a.name + '.png'); return
    import gp16poke as g
    inp, out = g.open_ports(a.port)
    if a.cmd == 'poke':
        h = [int(x, 16) for x in a.args]; chip, step, instr, coef = h[:4]; commit = h[4] if len(h) > 4 else 8
        tag = f'c{chip}_s{step:03x}_{instr:06x}_{coef:04x}'
        curves = {'stock': measure(a, tag + '_base')}
        g.send(out, g.msg_write(chip, step, instr, coef, commit)); time.sleep(0.2)
        curves[f'poke {instr:06x}/{coef:04x}'] = measure(a, tag + '_poke')
        restore(out, chip, step)
        plot(curves, f'chip{chip} step {step:03x}', tag + '.png')
    elif a.cmd == 'coefsweep':
        chip, step = int(a.args[0], 16), int(a.args[1], 16)
        coefs = [int(x, 16) for x in a.args[2].split(',')]
        ins = g.stock_instr(chip, step); curves = {}
        for c in coefs:
            g.send(out, g.msg_write(chip, step, ins, c, 8)); time.sleep(0.2)
            curves[f'coef {c:04x}'] = measure(a, f'c{chip}_s{step:03x}_coef{c:04x}')
        restore(out, chip, step)
        plot(curves, f'chip{chip} step {step:03x} coef sweep (instr {ins:06x})', f'c{chip}_s{step:03x}_coefsweep.png')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
