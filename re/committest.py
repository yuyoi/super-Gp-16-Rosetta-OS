#!/usr/bin/env python3
"""Does a commit 1 (address-field write) take only the A latch, or the instruction / coefficient latches too?
Tap delay C tap = chip 2 step 0x072, address A = 0x69FF + 32 * ms (twin: coefsweep p53). Echo at 300 ms, then the
instruction + coefficient latches are poisoned (0) and only A (-> 500 ms) is written with commit 1. Echo at 500 ms
and intact = commit 1 takes only A: the CPU-driven reverse needs 3 bus writes per sample. Restore = sound change."""
import subprocess, sys, time
import numpy as np
import revtest as RT

P = RT.P


def raw(o, v):
    r = subprocess.run([sys.executable, 'gp16poke.py', 'raww', f'{o:x}', f'{v:x}', '--port', 'Focusrite'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-200:]


def echo():
    R = RT.R
    x = np.zeros(int(1.0 * R)); n = int(0.004 * R)
    x[int(0.1 * R):int(0.1 * R) + n] = 0.4 * np.hanning(n) * np.sin(2 * np.pi * 2000 * np.arange(n) / R)
    y = RT.playrec(x)
    env = np.sqrt(np.convolve(y ** 2, np.ones(96) / 96, 'same'))
    t0 = int(np.argmax(env))                                     # the dry click (dry > echo? take the first big one)
    first = int(np.argmax(env > 0.5 * env.max()))
    rest = env[first + int(0.05 * R):]
    i = int(np.argmax(rest)) + first + int(0.05 * R)
    return (i - first) / R * 1000, 20 * np.log10(env[i] / env[first] + 1e-9)


def addr(ms):
    return 0x69FF + 32 * ms


RT.T.push({'recipe': P.R(P.on('dly'), P.TAP(300, 100, fb=0)), 'name': 'COMMIT TEST'}, RT.MIN, RT.MOUT,
          progress=lambda s: None)
time.sleep(1.0)
print('stock C tap 300 ms: echo at %.0f ms, %+.1f dB' % echo())
for o in (8, 9, 0xA, 4, 5, 2, 3):                                # poison instr, coef, B, reg3 latches
    raw(o, 0)
a = addr(500)
raw(1, a >> 8); raw(0, a & 0xFF); raw(0x1000 + 2 * 0x400 + 0x72, 1)
time.sleep(0.3)
print('latches poisoned, A -> 500 ms, commit 1: echo at %.0f ms, %+.1f dB' % echo())
RT.T.push({'recipe': P.R(P.on('dly'), P.TAP(300, 100, fb=0)), 'name': 'COMMIT TEST'}, RT.MIN, RT.MOUT,
          progress=lambda s: None)
time.sleep(1.0)
print('restored: echo at %.0f ms, %+.1f dB' % echo())
