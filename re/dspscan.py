#!/usr/bin/env python3
"""DSP signal-path scan on the real GP-16: one continuous audio stream (3 tones into the GP-16, its output recorded) while
the debug port replaces one step's instruction at a time (default 000000) and puts the stock one back. Steps whose
replacement changes the output are on the signal path; the size and kind of change says what they do.
Every latch is written as the firmware left it (dsplive.py), so only the instruction changes and each step is restored
exactly (out/dsp_buslog.json from dsptwin.py must match the unit's current patch).
Wiring as loop_rig.py; MIDI to the GP-16 debug port (backdoor v3).
Usage: py -3.10 dspscan.py <chip> <from> <to> [--instr 000000] [--port Focusrite] [--level -18] [--name tag]
       -> out/scan/<tag>.txt (one line per step: dB change at 150 Hz / 1 kHz / 4 kHz, noise change)"""
import argparse, os, sys, threading, time
import numpy as np
import sounddevice as sd
import gp16poke as G
import dsplive as D
import loop_rig as L

R = L.RATE
TONES = (150.0, 1000.0, 4000.0)


class Stream:
    def __init__(self, dev, level_db):
        self.amp = 10 ** (level_db / 20)
        self.pos = 0
        self.chunks = []
        self.lock = threading.Lock()
        self.xruns = 0
        self.s = sd.Stream(device=dev, samplerate=R, channels=2, dtype='float32', callback=self.cb, blocksize=1024,
                           latency='high')

    def cb(self, indata, outdata, frames, t, status):
        if status:
            self.xruns += 1
        n = np.arange(self.pos, self.pos + frames)
        x = sum(np.sin(2 * np.pi * f * n / R) for f in TONES) * self.amp * (n >= R // 2)
        outdata[:, 0] = x
        outdata[:, 1] = 0
        with self.lock:
            self.chunks.append(indata.copy())
            self.pos += frames

    def now(self):
        with self.lock:
            return self.pos

    def data(self):
        with self.lock:
            return np.concatenate(self.chunks)


def levels(y):
    """lock-in amplitude (dBFS) of each tone, plus the residual (noise / distortion / other) in dB"""
    t = np.arange(len(y)) / R
    out, res = [], y.copy()
    for f in TONES:
        c, s = np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t)
        a, b = 2 * np.dot(y, c) / len(y), 2 * np.dot(y, s) / len(y)
        res -= a * c + b * s
        out.append(20 * np.log10(np.hypot(a, b) + 1e-12))
    return out + [20 * np.log10(np.sqrt(np.mean(res ** 2)) + 1e-12)]


def phasors(y, start):
    """complex amplitude of each tone, phase referenced to absolute stream sample index `start`"""
    t = (start + np.arange(len(y))) / R
    return [2 * np.dot(y, np.exp(-2j * np.pi * f * t)) / len(y) for f in TONES]


def delay(p, p0):
    """delay change in samples (48 kHz) from tone phases vs the baseline: 150 Hz unwraps 1 kHz, 1 kHz unwraps 4 kHz"""
    d = [-np.angle(a / b) / (2 * np.pi * f) * R for a, b, f in zip(p, p0, TONES)]
    for i in (1, 2):
        per = R / TONES[i]
        d[i] += per * np.round((d[i - 1] - d[i]) / per)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('chip', type=int)
    ap.add_argument('lo', type=lambda v: int(v, 16))
    ap.add_argument('hi', type=lambda v: int(v, 16))
    ap.add_argument('--instr', type=lambda v: int(v, 16), default=0)
    ap.add_argument('--port', default='Focusrite')
    ap.add_argument('--dev', default='Focusrite')
    ap.add_argument('--level', type=float, default=-18.0)
    ap.add_argument('--hold', type=float, default=0.15, help='seconds the replacement stays, after the loop latency')
    ap.add_argument('--block', type=int, default=1, help='replace this many consecutive steps at once')
    ap.add_argument('--name')
    a = ap.parse_args()
    inp, out = G.open_ports(a.port)
    G.send(out, [0x47, 4])
    if not G.wait_reply(inp, 0x44):
        sys.exit('debug port does not answer')
    st = Stream(L.devices(a.dev), a.level)
    st.s.start()
    time.sleep(1.5)
    y = st.data()
    ch = int(np.argmax(np.abs(y[R // 2:]).max(axis=0)))
    y = y[:, ch]
    floor = np.abs(y[:R // 4]).max()
    lat = int(np.argmax(np.abs(y[R // 2:]) > max(4 * floor, 1e-4)))           # tone onset = loop latency
    base = levels(y[R // 2 + lat + R // 4:])
    print(f'input {ch + 1}, loop latency {lat} samples, baseline 150/1k/4k {base[0]:.1f} {base[1]:.1f} {base[2]:.1f} dBFS'
          f', residual {base[3]:.1f}')
    if base[1] < -70:
        st.s.stop(); sys.exit('no tone back through the GP-16')
    hold = lat / R + a.hold
    ev = []
    for s in range(a.lo, a.hi + 1, a.block):
        grp = range(s, min(s + a.block, a.hi + 1))
        for k in grp:
            D.poke(out, a.chip, k, instr=a.instr)
        D.sync(inp, out)                                               # all writes processed
        p0 = st.now()
        time.sleep(hold)
        p1 = st.now()
        for k in grp:
            D.restore(out, a.chip, k)
        ev.append((s, p0, p1))
        D.sync(inp, out)
        time.sleep(0.03)
    time.sleep(lat / R + 0.3)
    end = st.now()
    st.s.stop()
    y = st.data()[:, ch]
    tail = levels(y[end - R // 5:end])
    tag = a.name or f'c{a.chip}_{a.lo:03x}_{a.hi:03x}_{a.instr:06x}'
    os.makedirs(os.path.join(L.HERE, 'out', 'scan'), exist_ok=True)
    path = os.path.join(L.HERE, 'out', 'scan', tag + '.txt')
    lines = [f'# chip {a.chip} steps {a.lo:03x}-{a.hi:03x} replaced by {a.instr:06x}; dB vs baseline at 150 / 1k / 4k Hz, '
             f'residual dB. latency {lat}. baseline {" ".join(f"{v:.1f}" for v in base)}; after the scan '
             f'{" ".join(f"{v:.1f}" for v in tail)}']
    for s, p0, p1 in ev:
        w = y[p0 + lat + int(0.06 * R):p1]
        v = levels(w)
        d = [v[i] - base[i] for i in range(4)]
        mark = ' *' if max(abs(x) for x in d[:3]) > 1.0 or d[3] > 6 else ''
        lines.append(f'{a.chip} {s:03x}{f"+{a.block - 1:x}" if a.block > 1 else ""} {G.stock_instr(a.chip, s):06x}: {d[0]:+6.1f} {d[1]:+6.1f} {d[2]:+6.1f}  res {d[3]:+6.1f}{mark}')
    open(path, 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(l for l in lines if l.endswith('*') or l.startswith('#')))
    print('wrote', path)


if __name__ == '__main__':
    main()
