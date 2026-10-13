#!/usr/bin/env python3
"""Poke coefficients (dsplive), measure the loop response, restore; print the change vs a reference measurement.
Usage: py -3.10 eqtest.py <ref.npz name> "<chip> <step> coef=X ..." [...]  (one quoted arg = one measurement)"""
import sys, numpy as np
import gp16poke as G, dsplive as D, loop_rig as L
from dspx import parse

ref = np.load(f'{L.OUT_DIR}/{sys.argv[1]}.npz')
inp, out = G.open_ports('Focusrite')
dev = L.devices('Focusrite'); x, inv = L.sweep(level_db=-12)
FQ = (50, 100, 200, 500, 1000, 2000, 3000, 4000, 6000, 8000, 10000, 13000)
print('change vs ref (dB):' + ''.join(f'{f:>7d}' for f in FQ))
for t in sys.argv[2:]:
    ws = parse(t)
    for w in ws:
        D.poke(out, w[1], w[2], **w[3]) if w[0] == 'p' else D.restore(out, w[1], w[2])
    D.sync(inp, out)
    r = L.analyse(L.playrec(x, dev), x, inv)
    m = r['mag'] + r['gain_1k'] - (ref['mag'] + float(ref['gain_1k']))
    print(f'{t[:34]:34s}' + ''.join(f'{np.interp(f, r["f"], m):+7.1f}' for f in FQ))
    for w in ws:
        D.restore(out, w[1], w[2])
    D.sync(inp, out)
