#!/usr/bin/env python3
"""DSP experiments on the real GP-16: one continuous 3-tone stream through the unit, a list of debug-port writes, the
output level (150 Hz / 1 kHz / 4 kHz + residual) measured after each one. Builds on dspscan.py.
Usage: py -3.10 dspx.py "<chip> <step> [instr=X] [coef=X] [a=X] [b=X] [r3=X] [commit=X][; more]" [...]   (hex)
       "r <chip> <step>" restores a step exactly. One quoted arg = one test; writes go through dsplive.poke, so every
       latch the test doesn't name keeps the firmware's value. e.g.  py -3.10 dspx.py "1 16e coef=400" "r 1 16e"
Each test's level (and delay change from tone phase) is printed relative to the baseline before the first test."""
import argparse, sys, time
import numpy as np
import gp16poke as G
import dsplive as D
import loop_rig as L
from dspscan import Stream, levels, phasors, delay, R


def parse(arg):
    out = []
    for w in arg.split(';'):
        f = w.split()
        if not f:
            continue
        if f[0] == 'r':
            out.append(('r', int(f[1]), int(f[2], 16), {}))
        else:
            out.append(('p', int(f[0]), int(f[1], 16), {k: int(v, 16) for k, v in (x.split('=') for x in f[2:])}))
    return out


def send(out, w):
    kind, chip, step, kw = w
    if kind == 'r':
        D.restore(out, chip, step)
        return 10 * len(D.final(chip, step))
    D.poke(out, chip, step, **kw)
    return 10


def run(tests, port='Focusrite', dev='Focusrite', level=-18.0, hold=0.3, quiet=False):
    inp, out = G.open_ports(port)
    G.send(out, [0x47, 4])
    if not G.wait_reply(inp, 0x44):
        sys.exit('debug port does not answer')
    st = Stream(L.devices(dev), level)
    st.s.start()
    time.sleep(1.5)
    y = st.data()
    ch = int(np.argmax(np.abs(y[R // 2:]).max(axis=0)))
    y = y[:, ch]
    floor = np.abs(y[:R // 4]).max()
    lat = int(np.argmax(np.abs(y[R // 2:]) > max(4 * floor, 1e-4)))
    b0 = R // 2 + lat + R // 4
    base = levels(y[b0:])
    bph = phasors(y[b0:], b0)
    marks = []
    for t in tests:
        for w in t:
            send(out, w)
        D.sync(inp, out)                                              # all writes processed
        p0 = st.now()
        time.sleep(lat / R + hold)
        marks.append((p0, st.now()))
    time.sleep(0.1)
    st.s.stop()
    y = st.data()[:, ch]
    res = []
    for (p0, p1), t in zip(marks, tests):
        w0 = p0 + lat + int(0.08 * R)
        v = levels(y[w0:p1])
        d = [v[i] - base[i] for i in range(4)]
        dl = delay(phasors(y[w0:p1], w0), bph)
        res.append(d + dl)
        if not quiet:
            print(f'{" ; ".join(f"{w[0]} {w[1]} {w[2]:03x} " + " ".join(f"{k}={v:x}" for k, v in w[3].items()) for w in t):40s} {d[0]:+6.1f} {d[1]:+6.1f} {d[2]:+6.1f}  res {d[3]:+6.1f}'
                  f'   delay {dl[0]:+7.2f} {dl[1]:+7.2f} {dl[2]:+7.2f} smp')
    if st.xruns:
        print(f'WARNING: {st.xruns} audio over/underruns: delay readings shifted')
    return base, res


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('tests', nargs='+')
    ap.add_argument('--port', default='Focusrite')
    ap.add_argument('--level', type=float, default=-18.0)
    ap.add_argument('--hold', type=float, default=0.3)
    a = ap.parse_args()
    base, _ = run([parse(t) for t in a.tests], a.port, level=a.level, hold=a.hold)
    print('baseline dBFS', ' '.join(f'{v:.1f}' for v in base))
