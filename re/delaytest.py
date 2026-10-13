#!/usr/bin/env python3
"""Doubler delay-address test: poke chip2 step 05A's A field (commit 1), measure the stereo IR, report the echo time.
Usage: py -3.10 delaytest.py <a_hex> [...]"""
import sys, subprocess, numpy as np
import gp16poke as G, dsplive as D, loop_rig as L

inp, out = G.open_ports('Focusrite')
dev = L.devices('Focusrite'); x, inv = L.sweep(level_db=-12)
for av in sys.argv[1:]:
    a = int(av, 16)
    D.poke(out, 2, 0x05a, a=a, commit=1); D.sync(inp, out)
    rec = L.playrec(x, dev)
    ir = np.convolve(rec[:, 0], inv)[len(x) - 1:]
    lat = int(np.argmax(np.abs(ir[:L.RATE])))
    seg = np.abs(ir[lat + 48:lat + 48 * 200])                      # 1 ms .. 200 ms after the main peak
    j = int(np.argmax(seg)) + 48
    # sub-sample peak position (parabolic)
    y0, y1, y2 = np.abs(ir[lat + j - 1:lat + j + 2]); frac = 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2) if (y0 - 2 * y1 + y2) else 0
    t = (j + frac) / L.RATE * 1000
    print(f'A {a:04x} ({a:5d}): echo {t:8.3f} ms  ({(j + frac) * 32000 / L.RATE:8.2f} samples @32k)  level {20*np.log10(seg.max()/abs(ir[lat])):+.1f} dB')
D.restore(out, 2, 0x05a); D.sync(inp, out)
