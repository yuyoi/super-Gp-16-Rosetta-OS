#!/usr/bin/env python3
"""DSP-native reverse attempt: the B2 PITCH shifter is a two-head crossfading modulated delay whose read speed caps at
freeze (the 12-bit oscillator step 1:152, coef = 2048 * (1 - ratio), maxes at +2047 = ratio ~0). Its read-head depth
steps 2:003 (51ffcf) and 2:01b (51fe0c, coef 0x7FF in pitch mode) carry instruction bit 22, which is a clean x0.5 on
the 09 family (2:076/07C, 2026-10-13). Clearing it may double the depth: the delay then changes at 2 * (1 - ratio) per
sample, so near-freeze (+2047) becomes true reverse with the shifter's own crossfade, no CPU.
Focusrite loop, engine stopped. Steps: stock -5 st (expect 329.6 Hz) / bit 22 cleared (x2 -> 219.6 Hz) / near-freeze.
The patch push at the end restores everything (the mod-type setter rewrites the depth steps).
Usage: py -3.10 pitchx2.py"""
import time
import numpy as np
import gp16poke as G
import revload as RL
import revtest as RT

R = RT.R
P = RT.P


def write(chip, step, instr, coef):
    io = RL.ports()
    try:
        G.send(io[1], G.msg_write(chip, step, instr, coef, 8))
        G.send(io[1], [0x47, 4]); G.wait_reply(io[0], 0x44, 2.0)
    finally:
        io[0].close(); io[1].close()
    time.sleep(0.2)


def peaks(tag):
    n = int(1.6 * R); t = np.arange(n) / R
    x = 0.1 * np.sin(2 * np.pi * 440 * t) * np.minimum(1, np.minimum(t, t[::-1]) / 0.01)
    y = RT.playrec(x)
    seg = y[int(0.5 * R):int(1.4 * R)]
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))); f = np.fft.rfftfreq(len(seg), 1 / R)
    m = (f > 40) & (f < 3000)
    order = np.argsort(np.where(m, S, 0))[::-1]
    out = []
    for i in order:
        if all(abs(f[i] - g) > 15 for g, _ in out):
            out.append((f[i], 20 * np.log10(S[i] / S[order[0]] + 1e-12)))
        if len(out) == 3:
            break
    rms = 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-12)
    print(f'{tag:34s} rms {rms:6.1f} dBFS  peaks ' + '  '.join(f'{fr:6.1f} Hz ({lv:+.0f} dB)' for fr, lv in out), flush=True)


def main():
    io = RL.ports(); RL.stop(io); io[0].close(); io[1].close()
    RT.T.push({'recipe': P.R(P.on('mod', b2='pitch'), P.PITCH(-5, 100)), 'name': 'PITCH X2 TEST'}, RT.MIN, RT.MOUT,
              progress=lambda s: None)
    time.sleep(1.5)
    peaks('stock, -5 st (expect 329.6)')
    write(2, 0x003, 0x11FFCF, 0x7FF); write(2, 0x01B, 0x11FE0C, 0x7FF)
    peaks('bit 22 cleared (x2 -> 219.6?)')
    write(2, 0x003, 0x51FFCF, 0x7FF); write(2, 0x01B, 0x51FE0C, 0x7FF)
    peaks('bit 22 back (329.6 again?)')


if __name__ == '__main__':
    main()
