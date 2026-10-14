#!/usr/bin/env python3
"""Is the reverse wet there? 0.5 s 440 Hz burst; dry = mean level 0.1-0.4 s after the onset, wet = loudest 100 ms
window 0.7-2.0 s after the onset (the reversed slice + repeats), both dBFS. Needs the loop."""
import numpy as np
import revtest as RT
R = RT.R


def check(tag):
    n = int(3.2 * R); t = np.arange(n) / R
    y = RT.playrec(0.1 * np.sin(2 * np.pi * 440 * t) * np.minimum(1, t / 0.01) * (t < 0.5))
    e = np.sqrt(np.convolve(y ** 2, np.ones(int(0.02 * R)) / int(0.02 * R), 'same'))
    fl = np.median(e)
    on = int(np.argmax(e > 10 * fl))
    seg = lambda a, b: e[on + int(a * R):on + int(b * R)]
    dry = 20 * np.log10(seg(0.1, 0.4).mean() + 1e-9)
    w = seg(0.7, 2.0)
    wins = [w[i:i + int(0.1 * R)].mean() for i in range(0, len(w) - int(0.1 * R), int(0.05 * R))]
    wet = 20 * np.log10(max(wins) + 1e-9)
    print(f'{tag:28s} dry {dry:6.1f} dBFS  wet {wet:6.1f} dBFS  (wet - dry {wet - dry:+5.1f})  floor {20*np.log10(fl+1e-9):6.1f}', flush=True)
    return dry, wet
