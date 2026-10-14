#!/usr/bin/env python3
"""Wet-path probe for the REVERSE sample smoother (Focusrite loop: OUT 1 -> GP-16 IN, GP-16 OUT A/B -> in 1/2).
Clean patch: tap delay only, C 100 ms, level 100 (coef 0x400), feedback 0, engine paused (static tap). One log sweep
-> stereo IR; the echo's spectrum over the dry's = the wet path. Variants rewrite chip 2 step 075 (the R-level MAC,
unused at R level 0) with commit 8 (instruction + coefficient):
  stock | 090038 (same internal-RAM slot as the C level steps 076/07C) | 090037 | 090039 (the neighbour slots).
If internal RAM rotates one slot per sample, one neighbour holds the C tap's previous sample: C(n) + C(n-1) = the
2-sample smoother (zero at 16 kHz, where the reverse's mirror lives). A patch push restores 075.
Usage: py -3.10 smoothtest.py"""
import time
import numpy as np
import gp16poke as G
import loop_rig as L
import revload as RL
import revtest as RT

P = RT.P
FREQS = (500, 1000, 2000, 4000, 6000, 8000, 10000, 12000, 14000, 15000)


def ir(dev, x, inv):
    rec = L.playrec(x, dev)
    return [np.convolve(rec[:, c], inv)[len(x) - 1:] for c in range(2)]


def wet_curve(irs):
    """echo / dry magnitude per channel at FREQS (dB), echo delay (samples)"""
    lat = int(np.argmax(np.abs(irs[0][:L.RATE])))
    out = []
    for c in range(2):
        h = irs[c]
        j = lat + 3000 + int(np.argmax(np.abs(h[lat + 3000:lat + 8000])))
        w = np.hanning(512)
        D = np.fft.rfft(h[lat - 128:lat + 384] * w); E = np.fft.rfft(h[j - 128:j + 384] * w)
        f = np.fft.rfftfreq(512, 1 / L.RATE)
        r = 20 * np.log10(np.abs(E) / (np.abs(D) + 1e-12) + 1e-12)
        out.append(([float(np.interp(q, f, r)) for q in FREQS], j - lat))
    return out


def poke075(instr, coef):
    io = RL.ports()
    try:
        G.send(io[1], G.msg_write(2, 0x075, instr, coef, 8))
        G.send(io[1], [0x47, 4]); G.wait_reply(io[0], 0x44, 2.0)
    finally:
        io[0].close(); io[1].close()


def main():
    io = RL.ports(); RL.stop(io); io[0].close(); io[1].close()
    RT.T.push({'recipe': P.R(P.on('dly'), P.TAP(100, 100, fb=0)), 'name': 'SMOOTH TEST'}, RT.MIN, RT.MOUT,
              progress=lambda s: None)
    time.sleep(1.2)
    dev = L.devices('Focusrite'); x, inv = L.sweep(level_db=-12)
    print('Hz        ' + ''.join(f'{q:>7d}' for q in FREQS))
    for tag, v in (('stock', None), ('090038', 0x090038), ('090037', 0x090037), ('090039', 0x090039)):
        if v is not None:
            poke075(v, 0x400); time.sleep(0.3)
        for c, (r, d) in enumerate(wet_curve(ir(dev, x, inv))):
            print(f'{tag:6s} {"AB"[c]} ' + ''.join(f'{q:7.1f}' for q in r) + f'   echo +{d} smp')


if __name__ == '__main__':
    main()
