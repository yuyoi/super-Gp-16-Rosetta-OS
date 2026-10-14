#!/usr/bin/env python3
"""Clock probe (clocktest.asm): P0.0 period vs the DSP frame period, both in timer-1 counts (1.3333 MHz).
DSP frames come from commit-complete events (each cycle = a whole number of frames; jitter < half a frame, so the
frame count between the first and last event is an integer). Needs revlock.py running; the engine pauses ~10 ms.
Usage: py -3.10 clocktest.py"""
import os, subprocess, time
import numpy as np
import gp16poke as G
import revload as RL
import revlock as RK

HERE = os.path.dirname(os.path.abspath(__file__))
ORG = 0x100


def unwrap(t):
    return np.concatenate([[0], np.cumsum([(a - b) % 1334 for a, b in zip(t[:-1], t[1:])])])


def main():
    nasm = os.path.join(HERE, '..', 'tools', 'nasm-2.16.03', 'nasm.exe')
    subprocess.run([nasm, '-f', 'bin', 'clocktest.asm', '-o', 'clocktest.bin'], cwd=HERE, check=True)
    code = open(os.path.join(HERE, 'clocktest.bin'), 'rb').read()
    okv = ORG + len(code) - 258
    io = RL.ports()
    try:
        for i, b in enumerate(code):
            RL.poke(io, RK.SEG, ORG + i, b)
        RL.peek(io, RK.SEG, okv, 2)
        G.send(io[1], G.msg_poke(0x40E0, RK.BANK + RK.REG['vpc'] + 1, ORG >> 8))
        time.sleep(0.3)
        raw = []
        for o in range(0, 258, 43):
            raw += RL.peek(io, RK.SEG, okv + o, min(43, 258 - o))
        G.send(io[1], G.msg_poke(0x40E0, RK.BANK + RK.REG['vpc'] + 1, 0))
        RL.sfr(io, 0x9C, 0x16)
    finally:
        io[0].close(); io[1].close()
    w = [raw[i] | raw[i + 1] << 8 for i in range(0, 258, 2)]
    print('ok', w[0])
    a, b = unwrap(w[1:65]), unwrap(w[65:129])
    pa = a[-1] / 63
    print(f'P0.0: {pa:.3f} counts/period = {RL.TCLK / pa / 1000:.3f} kHz  (diffs {np.diff(a).min()}..{np.diff(a).max()})')
    for T0 in (RL.TCLK / 32000, pa):
        m = np.round(np.diff(b) / T0)
        T = b[-1] / m.sum()
        res = np.diff(b) - m * T
        print(f'events vs T0 {T0:.2f}: frames per cycle {sorted(set(m.astype(int)))}, T = {T:.3f} counts = '
              f'{RL.TCLK / T / 1000:.3f} kHz, residual {res.std():.1f} counts')


if __name__ == '__main__':
    main()
