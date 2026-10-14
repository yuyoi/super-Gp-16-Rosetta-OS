#!/usr/bin/env python3
"""EOS probe (eostest.asm): samples V25 P0 256 times in a tight loop from a one-shot in the REVERSE engine's bank-6 slot
and prints each bit's period and duty. Needs revfast.py running (bank 6 set up). The engine pauses ~1 ms.
Usage: py -3.10 eostest.py"""
import os, subprocess, time
import gp16poke as G
import revload as RL
import revfast as RF

HERE = os.path.dirname(os.path.abspath(__file__))
ORG = 0x100
N = 256


def main():
    nasm = os.path.join(HERE, '..', 'tools', 'nasm-2.16.03', 'nasm.exe')
    subprocess.run([nasm, '-f', 'bin', 'eostest.asm', '-o', 'eostest.bin'], cwd=HERE, check=True)
    code = open(os.path.join(HERE, 'eostest.bin'), 'rb').read()
    tv, buf = ORG + len(code) - 4, ORG + len(code)
    io = RL.ports()
    try:
        for i, b in enumerate(code):
            RL.poke(io, RF.SEG, ORG + i, b)
        RL.peek(io, RF.SEG, tv, 4)                                    # flush flow control before the one-shot
        G.send(io[1], G.msg_poke(0x40E0, RF.BANK + RF.REG['vpc'] + 1, ORG >> 8))   # next tick runs the probe
        time.sleep(0.3)
        t = RL.peek(io, RF.SEG, tv, 4)
        s = []
        for o in range(0, N, 32):
            s += RL.peek(io, RF.SEG, buf + o, 32)
        G.send(io[1], G.msg_poke(0x40E0, RF.BANK + RF.REG['vpc'] + 1, 0))           # back to the engine
        RL.sfr(io, 0x9C, 0x16)
    finally:
        io[0].close(); io[1].close()
    t0, t1 = t[0] | t[1] << 8, t[2] | t[3] << 8
    us = ((t0 - t1) % 1334) / RL.TCLK * 1e6
    dt = us / N
    print(f'{N} samples in {us:.1f} us = {dt:.3f} us/sample')
    for bit in range(8):
        v = [x >> bit & 1 for x in s]
        e = [i for i in range(1, N) if v[i] != v[i - 1]]
        if not e:
            print(f'P0.{bit}: steady {v[0]}'); continue
        rise = [i for i in e if v[i]]
        per = (rise[-1] - rise[0]) / (len(rise) - 1) if len(rise) > 1 else 0
        print(f'P0.{bit}: {len(e)} edges, period {per:.2f} samples = {per * dt:.2f} us '
              f'({1e3 / (per * dt) if per else 0:.2f} kHz), high {sum(v) / N * 100:.0f}%')
    print(''.join(str(x & 1) for x in s[:128]))


if __name__ == '__main__':
    main()
