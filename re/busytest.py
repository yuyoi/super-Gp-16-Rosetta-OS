#!/usr/bin/env python3
"""Commit timing probe (busytest.asm): times the DSP busy flag after a commit 1 written at 16 delays after a P0.0
rising edge. Writes the current tap address (no sound change). Needs revfast.py running; the engine pauses ~1 ms.
Usage: py -3.10 busytest.py"""
import os, subprocess, time
import gp16poke as G
import revload as RL
import revfast as RF

HERE = os.path.dirname(os.path.abspath(__file__))
ORG = 0x100


def main():
    nasm = os.path.join(HERE, '..', 'tools', 'nasm-2.16.03', 'nasm.exe')
    subprocess.run([nasm, '-f', 'bin', 'busytest.asm', '-o', 'busytest.bin'], cwd=HERE, check=True)
    code = open(os.path.join(HERE, 'busytest.bin'), 'rb').read()
    cv, tab = ORG + len(code) - 2, ORG + len(code)
    io = RL.ports()
    try:
        for i, b in enumerate(code):
            RL.poke(io, RF.SEG, ORG + i, b)
        RL.peek(io, RF.SEG, cv, 2)
        G.send(io[1], G.msg_poke(0x40E0, RF.BANK + RF.REG['vpc'] + 1, ORG >> 8))
        time.sleep(0.3)
        c = RL.peek(io, RF.SEG, cv, 2)
        t = RL.peek(io, RF.SEG, tab, 48) + RL.peek(io, RF.SEG, tab + 48, 48)
        G.send(io[1], G.msg_poke(0x40E0, RF.BANK + RF.REG['vpc'] + 1, 0))
        RL.sfr(io, 0x9C, 0x16)
    finally:
        io[0].close(); io[1].close()
    n = c[0] | c[1] << 8
    w = [t[i] | t[i + 1] << 8 for i in range(0, 96, 2)]
    us = lambda a, b: ((a - b) % 1334) / RL.TCLK * 1e6
    print(f'{n} rows (us after the P0.0 rising edge)')
    for i in range(min(n, 16)):
        e, wr, cl = w[3 * i:3 * i + 3]
        print(f'{i:2d}: write {us(e, wr):6.1f}  clear {us(e, cl):6.1f}  busy {us(wr, cl):6.1f}')


if __name__ == '__main__':
    main()
