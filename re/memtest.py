#!/usr/bin/env python3
"""Borrowed-memory check over the Focusrite loop: one click, static C tap at D ms (mem2s.echo), record.
The dry click is the in-stream reference: echo time = (echo peak - dry peak), level = echo vs dry, and 'junk' =
the strongest other content between dry and echo (should sit at the noise floor if no foreign write hits the line).
Usage: py -3.10 memtest.py [ms ...]"""
import sys
import numpy as np
import revtest as RT
import revload as RL
import mem2s as M2

R = RT.R


def one(ms):
    io = RL.ports()
    try:
        M2.echo(io, ms)
    finally:
        io[0].close(); io[1].close()
    n = int(0.0006 * R); p = np.sin(2 * np.pi * 1000 * np.arange(n) / R) * np.hanning(n)
    x = np.zeros(int((0.6 + ms / 1000 + 0.5) * R)); x[int(0.3 * R):int(0.3 * R) + n] = 0.5 * p
    y = RT.playrec(x)
    from scipy.signal import hilbert
    env = np.abs(hilbert(np.convolve(y, p[::-1], 'same')))
    i0 = int(np.argmax(env[:int((0.3 + 0.6) * R)]))             # dry click (loop latency < 0.6 s)
    lo = i0 + int((ms / 1000 - 0.05) * R); hi = i0 + int((ms / 1000 + 0.05) * R)
    i1 = lo + int(np.argmax(env[lo:hi]))
    mid = env[i0 + int(0.02 * R):lo]
    floor = np.median(env[i0 + int(0.02 * R):lo])
    print(f'{ms:6.0f} ms: echo at {(i1 - i0) / R * 1000:7.1f} ms, level {20*np.log10(env[i1]/env[i0]):+6.1f} dB vs dry, '
          f'junk peak {20*np.log10(mid.max()/env[i0]):+6.1f} dB, floor {20*np.log10(floor/env[i0]):+6.1f} dB', flush=True)


if __name__ == '__main__':
    io = RL.ports()
    try:
        print('borrowed memory on:', M2.on(io))
    finally:
        io[0].close(); io[1].close()
    for ms in [float(v) for v in sys.argv[1:]] or [800, 1150, 1300, 1600, 1900, 2000]:
        one(ms)
