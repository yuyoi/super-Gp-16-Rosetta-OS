#!/usr/bin/env python3
"""Give the REVERSE tap (chip 2) almost the whole 64K-sample delay memory (2.05 s instead of 1.2 s).
Every chip-2 memory write (bit 17 set) into WBASE..0xFFBF except the tap's own is silenced (pitch line 2:039,
doubler 2:05D, reverb, modulated writes), then the tap's write 2:092 `0369ff` moves from 0x69FF down to WBASE, so reads run
WBASE .. 0xFFBF without wrapping (0xFFC0+ stays clear of chip-2 0xFFxx stores). A patch push undoes everything.
Address of a memory step = instruction low 16 bits (commit 1 replaces only those).
Usage: py -3.10 mem2s.py on | echo <ms> | rev <chunk_ms> [speed] | off"""
import os, sys, time
os.environ.setdefault('DSP_BUSLOG', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'dsp_buslog_offboot.json'))
import dsplive as D
import revload as RL
import revlock as RK

WRITES = [int(v, 16) for v in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'mem2s_writes.txt')).read().split()]
TAPW = 0x092                      # the tap's input write `0369ff` (bit 17 = write; address = low 16 bits)
WBASE = 0x0100                    # new tap write address
AMAX = 0xFFBF


def on(io):
    RL.stop(io)
    D.forget()
    for n, s in enumerate(WRITES):
        D.poke(io[1], 2, s, instr=0, commit=0)
        if n % 3 == 2:
            D.sync(io[0], io[1])
    D.restore(io[1], 2, 0x017)                  # undo the first (wrong) try: 017 is a B2 step, 069/06C are L/R reads
    D.poke(io[1], 2, TAPW, instr=0x030000 | WBASE, commit=0)
    for s in (0x069, 0x06c):
        D.poke(io[1], 2, s, a=WBASE + 1, commit=1)
    return D.sync(io[0], io[1])


def echo(io, ms):
    """static C tap at ms (engine stopped): a clean echo past 1.2 s = the borrowed memory works"""
    RL.stop(io)
    a = WBASE + int(32 * ms)
    assert a <= AMAX
    D.poke(io[1], 2, 0x072, a=a, commit=1)
    return D.sync(io[0], io[1]), a


def rev(io, chunk_ms, speed=-1.0):
    RL.BASE = WBASE
    amax = RL.BASE + 32 + RK.span(chunk_ms, speed)
    assert amax <= AMAX, f'chunk too long: A {amax:04x} > {AMAX:04x}'
    RK.start(io, chunk_ms, speed, 1, fade=False)


if __name__ == '__main__':
    cmd = sys.argv[1]
    io = RL.ports()
    try:
        if cmd == 'on':
            print('borrowed memory on:', on(io))
        elif cmd == 'echo':
            ok, a = echo(io, float(sys.argv[2])); print(f'static echo {sys.argv[2]} ms (A {a:04x})', ok)
        elif cmd == 'rev':
            rev(io, float(sys.argv[2]), float(sys.argv[3]) if len(sys.argv) > 3 else -1.0)
    finally:
        io[0].close(); io[1].close()
