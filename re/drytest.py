#!/usr/bin/env python3
"""Find the dry path through the REVERSE DELAY patch's delay block (user wants 100% wet).
Engine stopped, static C tap at 300 ms. One click per test: dry level (direct) and wet level (300 ms echo), both
in dB vs the baseline. A step whose zeroing kills the dry but keeps the wet = the dry path.
Exact restores from the twin of this patch (DSP_BUSLOG=out/dsp_buslog_rev.json).
Usage: py -3.10 drytest.py setup | scan <chip> <from> <to> | test "<chip> <step> k=v ..." """
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault('DSP_BUSLOG', os.path.join(HERE, 'out', 'dsp_buslog_rev.json'))
import numpy as np
import dsplive as D
import revload as RL
import revtest as RT

R = RT.R
P = RT.P
REC = P.R(P.on('dirt', 'dly', 'eq', 'amp', od=True), P.OD(0, 70, 90),
          P.EQ(hi=(2500, 0), hm=(1000, +8, 1.5), lm=(200, -6, 1.0), lo=(250, -12)),
          P.TAP(10, 100, fb=0, cutf=None), P.LINE(0, 0, 50, 55, 100))
TAP_MS = 300


def setup():
    io = RL.ports(); RL.stop(io); io[0].close(); io[1].close()
    RT.T.push({'recipe': REC, 'name': 'REVERSE DELAY'}, RT.MIN, RT.MOUT, progress=lambda s: None)
    time.sleep(1.2)


def static_tap(io):
    D.poke(io[1], 2, 0x072, a=0x69FF + 32 * TAP_MS, commit=1)


def click():
    n = int(0.0006 * R); p = np.sin(2 * np.pi * 1000 * np.arange(n) / R) * np.hanning(n)
    x = np.zeros(int(1.4 * R)); x[int(0.3 * R):int(0.3 * R) + n] = 0.5 * p
    y = RT.playrec(x)
    from scipy.signal import hilbert
    env = np.abs(hilbert(np.convolve(y, p[::-1], 'same')))
    i0 = int(np.argmax(env[:int(0.75 * R)]))
    lo, hi = i0 + int((TAP_MS / 1000 - 0.01) * R), i0 + int((TAP_MS / 1000 + 0.01) * R)
    return env, i0, env[i0], env[lo:hi].max()


BASE = {}


def measure(tag, ws):
    io = RL.ports()
    try:
        for c, s, kw in ws:
            D.poke(io[1], c, s, **kw)
        D.sync(io[0], io[1])
    finally:
        io[0].close(); io[1].close()
    time.sleep(0.2)
    env, i0, dry, wet = click()
    io = RL.ports()
    try:
        for c, s, _ in ws:
            D.restore(io[1], c, s)
        D.sync(io[0], io[1])
    finally:
        io[0].close(); io[1].close()
    if not BASE:
        BASE.update(dry=dry, wet=wet)
    d, w = 20 * np.log10(dry / BASE['dry']), 20 * np.log10(wet / BASE['wet'])
    flag = '  <-- DRY GONE, WET KEPT' if d < -15 and w > -6 else ''
    print(f'{tag:28s} dry {d:+6.1f} dB  wet {w:+6.1f} dB  (wet-dry {20*np.log10(wet/dry):+6.1f}){flag}', flush=True)


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'setup':
        setup(); print('patch pushed (engine stopped); now: ramdump + twin_apply -> out/dsp_buslog_rev.json')
    elif cmd == 'scan':
        c, a, b = int(sys.argv[2]), int(sys.argv[3], 16), int(sys.argv[4], 16)
        io = RL.ports()
        try:
            D.forget(); static_tap(io); D.sync(io[0], io[1])
        finally:
            io[0].close(); io[1].close()
        measure('baseline', [])
        for s in range(a, b + 1):
            h = D.history(c, s)
            if not h or D.fields(h[-1][0])['instr'] == 0:
                continue
            measure(f'{c}:{s:03x} {D.fields(h[-1][0])["instr"]:06x} -> 0', [(c, s, {'instr': 0, 'commit': 8})])
        measure('baseline again', [])
