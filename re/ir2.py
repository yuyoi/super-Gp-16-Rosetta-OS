#!/usr/bin/env python3
"""Stereo impulse response of the GP-16 (OUT A -> in 1, OUT B -> in 2) from one log sweep: both channels share the
stream, so their relative timing is exact. Prints the main peak of each and the biggest later peaks (echoes).
Usage: py -3.10 ir2.py [name] [--level -12]   -> out/loop/<name>_ir2.npy  (2 x N, from 100 samples before ch1's peak)"""
import argparse, os
import numpy as np
import loop_rig as L

ap = argparse.ArgumentParser(); ap.add_argument('name', nargs='?', default='ir2'); ap.add_argument('--level', type=float, default=-12)
a = ap.parse_args()
dev = L.devices('Focusrite'); x, inv = L.sweep(level_db=a.level)
rec = L.playrec(x, dev)
irs = [np.convolve(rec[:, c], inv)[len(x) - 1:] for c in range(2)]
lat = int(np.argmax(np.abs(irs[0][:L.RATE])))
ref = max(np.abs(irs[0][lat]), np.abs(irs[1][:L.RATE]).max())
for c in range(2):
    ir = irs[c][lat - 100:lat + 6000]
    e = 20 * np.log10(np.abs(ir) / ref + 1e-12)
    j0 = int(np.argmax(e))
    print(f'OUT {"AB"[c]}: main peak {e[j0]:6.1f} dB at {j0 - 100:+d} smp; later peaks:', end='')
    order = np.argsort(e)[::-1]
    shown = []
    for j in order:
        if abs(j - j0) > 40 and all(abs(j - k) > 40 for k in shown):
            shown.append(j)
            print(f'  {e[j]:.1f} dB @ {(j - 100) / 48:.3f} ms', end='')
        if len(shown) == 3:
            break
    print()
np.save(os.path.join(L.OUT_DIR, a.name + '_ir2.npy'), np.array([irs[c][lat - 100:lat + 6000] for c in range(2)]))
