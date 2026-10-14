#!/usr/bin/env python3
"""What is the reverse's fizz? A 997 Hz tone through the patch with the engine running vs stopped (static echo).
Prints: fundamental, the 2-frame mirror at fs/2 - f (fs = 31.98 kHz), high-band energy 6-10 / 10-14 / 14-16 kHz
(dB vs the fundamental), and how spiky the high band is over time (chunk-jump clicks).
Usage: py -3.10 fizz.py [run|stopped|both]"""
import sys
import numpy as np
import revtest as RT
import revload as RL
import revlock as RK

R = RT.R
FS = 31980.0
F = 997.0


def capture():
    n = int(3.2 * R); t = np.arange(n) / R
    x = 0.1 * np.sin(2 * np.pi * F * t) * np.minimum(1, np.minimum(t, t[::-1]) / 0.02)
    return RT.playrec(x)


def analyse(tag, y):
    seg = y[int(0.9 * R):int(3.0 * R)]
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2; f = np.fft.rfftfreq(len(seg), 1 / R)
    def pk(fr, w=25):
        m = (f > fr - w) & (f < fr + w); return 10 * np.log10(S[m].max() + 1e-30)
    def band(a, b):
        m = (f > a) & (f < b); return 10 * np.log10(S[m].sum() + 1e-30)
    f0 = pk(F)
    mir = pk(FS / 2 - F)
    out = f'{tag:8s} mirror {FS/2-F:.0f} Hz {mir - f0:+6.1f} dB | bands 6-10k {band(6000, 10000) - f0:+6.1f}  10-14k {band(10000, 14000) - f0:+6.1f}  14-16k {band(14000, 16000) - f0:+6.1f}'
    from scipy.signal import butter, sosfilt
    hb = sosfilt(butter(6, 6000, 'hp', fs=R, output='sos'), seg)
    e = np.sqrt(np.convolve(hb ** 2, np.ones(int(0.005 * R)) / int(0.005 * R), 'same'))
    out += f' | HF spikiness (peak/median 5 ms) {20 * np.log10(e.max() / (np.median(e) + 1e-12)):+5.1f} dB'
    print(out, flush=True)


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'both'
    if what in ('run', 'both'):
        analyse('running', capture())
    if what in ('stopped', 'both'):
        io = RL.ports(); RL.stop(io); io[0].close(); io[1].close()
        analyse('stopped', capture())
        io = RL.ports()
        try:
            RK.resume(io)
        finally:
            io[0].close(); io[1].close()
        print('engine resumed')
