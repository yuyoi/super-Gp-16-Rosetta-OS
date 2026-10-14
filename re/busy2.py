#!/usr/bin/env python3
"""Pipelining probe (busy2.asm): is a commit written while the previous one is busy accepted (busy clears a frame
later) or dropped / merged (clears at the same time)? Writes the current tap address (no sound change). Needs revlock.py
running (v4 bank-6 segment layout); the engine pauses ~2 ms.
Usage: py -3.10 busy2.py"""
import os, subprocess, time
import gp16poke as G
import revload as RL
import revlock as RK

HERE = os.path.dirname(os.path.abspath(__file__))
ORG = 0x100


def main():
    nasm = os.path.join(HERE, '..', 'tools', 'nasm-2.16.03', 'nasm.exe')
    subprocess.run([nasm, '-f', 'bin', 'busy2.asm', '-o', 'busy2.bin'], cwd=HERE, check=True)
    code = open(os.path.join(HERE, 'busy2.bin'), 'rb').read()
    rv, tab = ORG + len(code) - 2, ORG + len(code)
    io = RL.ports()
    try:
        for i, b in enumerate(code):
            RL.poke(io, RK.SEG, ORG + i, b)
        RL.peek(io, RK.SEG, rv, 2)
        G.send(io[1], G.msg_poke(0x40E0, RK.BANK + RK.REG['vpc'] + 1, ORG >> 8))
        time.sleep(0.3)
        r = RL.peek(io, RK.SEG, rv, 2)
        n = r[0] | r[1] << 8
        t = []
        for o in range(0, n, 40):
            t += RL.peek(io, RK.SEG, tab + o, min(40, n - o))
        G.send(io[1], G.msg_poke(0x40E0, RK.BANK + RK.REG['vpc'] + 1, 0))
        RL.sfr(io, 0x9C, 0x16)
    finally:
        io[0].close(); io[1].close()
    w = [t[i] | t[i + 1] << 8 for i in range(0, len(t), 2)]
    us = lambda a, b: ((a - b) % 1334) / RL.TCLK * 1e6
    print('us after the P0.0 rising edge')
    for i in range(len(w) // 5):
        e, w1, w2, cl, bz = w[5 * i:5 * i + 5]
        s = f'write2 {us(e, w2):6.1f} (busy {bz & 1})' if w2 else 'no write2          '
        print(f'{i:2d}: write1 {us(e, w1):5.1f}  {s}  clear {us(e, cl):6.1f}')


if __name__ == '__main__':
    main()
