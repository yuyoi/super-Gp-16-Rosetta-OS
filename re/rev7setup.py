#!/usr/bin/env python3
"""One shot, engine v7: the user's REVERSE DELAY (revsetup.REC) + borrowed 2 s memory + v7 engine with chunk fades.
Usage: py -3.10 rev7setup.py [fade_ms 1-24 | 0 = fades off] [chunk_ms (default 1/4 @ 92)] [speed]"""
import sys, time
import revtest as RT, revload as RL, mem2s as M2, rk7
from revsetup import REC

if __name__ == '__main__':
    nl = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    ms = float(sys.argv[2]) if len(sys.argv) > 2 else 60000 / 92 * 31980 / 32000
    sp = float(sys.argv[3]) if len(sys.argv) > 3 else -1.0
    io = RL.ports(); RL.stop(io); io[0].close(); io[1].close()
    RT.T.push({'recipe': REC, 'name': 'REVERSE DELAY'}, RT.MIN, RT.MOUT, progress=lambda s: None)
    time.sleep(1.2)
    io = RL.ports()
    try:
        print('borrowed memory', M2.on(io))
        RL.stop(io)
        rk7.start(io, ms, sp, base=M2.WBASE, fades=nl > 0, nl=max(nl, 1))
    finally:
        io[0].close(); io[1].close()
