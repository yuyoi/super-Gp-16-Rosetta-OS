#!/usr/bin/env python3
"""One shot: the user's current REVERSE DELAY (2026-10-14 settings) + borrowed 2 s memory + reverse engine.
Usage: py -3.10 revsetup.py [chunk_ms (default 1/4 @ 92 BPM)] [speed]"""
import sys, time
import revtest as RT, revload as RL, mem2s as M2
P = RT.P
REC = P.R(P.on('dirt', 'dly', 'eq', 'amp', od=True), P.OD(0, 70, 90),
          P.EQ(hi=(2500, 0), hm=(1000, +8, 1.5), lm=(200, -6, 1.0), lo=(250, -12)),
          P.TAP(10, 100, fb=45, cutf=None), P.LINE(0, 0, 50, 55, 100))

if __name__ == '__main__':
    ms = float(sys.argv[1]) if len(sys.argv) > 1 else 60000 / 92 * 31980 / 32000
    sp = float(sys.argv[2]) if len(sys.argv) > 2 else -1.0
    io = RL.ports(); RL.stop(io); io[0].close(); io[1].close()
    RT.T.push({'recipe': REC, 'name': 'REVERSE DELAY'}, RT.MIN, RT.MOUT, progress=lambda s: None)
    time.sleep(1.2)
    io = RL.ports()
    try:
        print('borrowed memory', M2.on(io))
        M2.rev(io, ms, sp)
    finally:
        io[0].close(); io[1].close()
