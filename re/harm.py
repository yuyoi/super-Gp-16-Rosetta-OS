#!/usr/bin/env python3
"""Harmonic check: for each test (dspx syntax), poke, play a 440 Hz sine, print fundamental, H2-H7 and the noise floor
(median of non-harmonic bins) on OUT A, then restore. Usage: py -3.10 harm.py [--level -30] "<test>" ..."""
import argparse, numpy as np
import gp16poke as G, dsplive as D, loop_rig as L
from dspx import parse

ap = argparse.ArgumentParser(); ap.add_argument('tests', nargs='+'); ap.add_argument('--level', type=float, default=-30)
a = ap.parse_args()
inp, out = G.open_ports('Focusrite'); dev = L.devices('Focusrite'); R = L.RATE
t = np.arange(int(1.5 * R)) / R
x = np.sin(2 * np.pi * 440 * t) * 10 ** (a.level / 20)
print(f'{"test":40s} fund   H2    H3    H4    H5    H6    H7   noise  (dBFS)')
for tst in a.tests:
    ws = parse(tst) if tst != 'stock' else []
    for w in ws:
        D.poke(out, w[1], w[2], **w[3]) if w[0] == 'p' else D.restore(out, w[1], w[2])
    D.sync(inp, out)
    y = L.playrec(x, dev, tail=0.2)[int(0.5 * R):int(1.5 * R), 0]
    Y = np.abs(np.fft.rfft(y * np.hanning(len(y)))) / (len(y) / 4)
    f = np.fft.rfftfreq(len(y), 1 / R)
    h = [20 * np.log10(Y[np.argmin(abs(f - 440 * k)) - 2:np.argmin(abs(f - 440 * k)) + 3].max() + 1e-12) for k in range(1, 8)]
    mask = np.ones(len(f), bool)
    for k in range(1, 30):
        i = np.argmin(abs(f - 440 * k)); mask[max(0, i - 6):i + 7] = False
    mask &= (f > 100) & (f < 12000)
    nf = 20 * np.log10(np.median(Y[mask]) + 1e-12)
    print(f'{tst[:40]:40s}' + ' '.join(f'{v:5.1f}' for v in h) + f'  {nf:6.1f}')
    for w in ws:
        D.restore(out, w[1], w[2])
    D.sync(inp, out)
