#!/usr/bin/env python3
"""Map the B2 pitch shifter's read-head path on the unit (Focusrite loop), looking for a x2 in the delay rate.
PITCH patch at -5 st (osc 1:152 coef 0x201 -> rate 0.251 -> 330 Hz from 440). Rate x2 -> 219 Hz, x0.5 -> 385 Hz.
Each test = commit-8 writes (instr + coef), one 440 Hz measurement, then every touched step goes back to its
pitch-mode value from the twin (out/dsp_live_pitch.json, twin_apply.py).
Usage: py -3.10 pitchmap.py <suite>   (suites below)"""
import json, sys, time
import numpy as np
import gp16poke as G
import revload as RL
import revtest as RT
import dsplive as D

R = RT.R
TW = json.load(open('out/dsp_live_pitch.json'))['prog']


def orig(c, s):
    i, co, _ = TW[str(c)][s]
    return i, co


def write_all(ws):
    """ws: (chip, step, fields dict) -> dsplive.poke with exact firmware latches; fields None = exact restore."""
    io = RL.ports()
    try:
        for n, (c, s, kw) in enumerate(ws):
            if kw is None:
                D.restore(io[1], c, s)
            else:
                D.poke(io[1], c, s, **kw)
            if n % 3 == 2:
                D.sync(io[0], io[1])
        ok = D.sync(io[0], io[1])
    finally:
        io[0].close(); io[1].close()
    time.sleep(0.25)
    return ok


def measure():
    n = int(1.4 * R); t = np.arange(n) / R
    x = 0.1 * np.sin(2 * np.pi * 440 * t) * np.minimum(1, np.minimum(t, t[::-1]) / 0.01)
    y = RT.playrec(x)
    seg = y[int(0.45 * R):int(1.25 * R)]
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))); f = np.fft.rfftfreq(len(seg), 1 / R)
    m = (f > 30) & (f < 3000)
    order = np.argsort(np.where(m, S, 0))[::-1]
    out = []
    for i in order:
        if all(abs(f[i] - g) > 12 for g, _ in out):
            out.append((f[i], 20 * np.log10(S[i] / S[order[0]] + 1e-12)))
        if len(out) == 3:
            break
    rms = 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-12)
    return rms, out


def test(tag, ws):
    write_all(ws)
    rms, pk = measure()
    write_all([(c, s, None) for c, s, _ in ws])
    line = f'{tag:30s} rms {rms:6.1f}  ' + '  '.join(f'{fr:6.1f}({lv:+.0f})' for fr, lv in pk)
    print(line, flush=True)
    return rms, pk


def instr(c, s):
    return D.fields(D.history(c, s)[-1][0])['instr']


def suite_r3():
    for v in list(range(0x00, 0x40)) + [0x4f, 0x8f, 0xcf]:
        test(f'2:003 r3 {v:02x}', [(2, 0x003, {'r3': v})])


def suite_r3b():
    for v in list(range(0x00, 0x40)) + [0x4c, 0x8c, 0xcc]:
        test(f'2:01b r3 {v:02x}', [(2, 0x01b, {'r3': v})])


def suite_osc():
    for s in (0x154, 0x155, 0x156, 0x157, 0x158, 0x159):
        for b in (16, 17, 18, 21, 22, 23):
            test(f'1:{s:03x} {instr(1, s):06x} bit {b}', [(1, s, {'instr': instr(1, s) ^ (1 << b)})])


SUITES = {'r3': suite_r3, 'r3b': suite_r3b, 'osc': suite_osc}

if __name__ == '__main__':
    io = RL.ports(); RL.stop(io); io[0].close(); io[1].close()
    D.forget()
    test('baseline', [])
    for name in sys.argv[1:]:
        print('--', name, flush=True)
        SUITES[name]()
    test('baseline again', [])
