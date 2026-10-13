#!/usr/bin/env python3
"""Push steps from one full DSP state (bus log + optional segment) onto the unit, exactly (all latches, firmware commit
order). Usage: py -3.10 statepush.py <log.json>[+<seg.json>] <chip:from-to> [...]"""
import json, os, sys
import gp16poke as G, dsplive as D, dspstate_diff as S

HERE = os.path.dirname(os.path.abspath(__file__))
log = []
for f in sys.argv[1].split('+'):
    log += json.load(open(os.path.join(HERE, 'out', f)))
cur = {o: 0 for o in D.LATCH}; hist = {}
for o, v in log:                                                    # per step: commits in log order
    if o in cur:
        cur[o] = v
    elif 0x1000 <= o < 0x1C00 and (o - 0x1000) % 0x400 < 512:
        hist.setdefault(((o - 0x1000) // 0x400, (o - 0x1000) % 0x400), []).append((dict(cur), v))


def final(k):                                                       # last commit of each value, in log order
    h = hist.get(k, [])
    last = {c: i for i, (lat, c) in enumerate(h)}
    return [h[i] for i in sorted(last.values())]
inp, out = G.open_ports('Focusrite')
n = 0
for r in sys.argv[2:]:
    c, rng = r.split(':')
    lo, hi = (int(x, 16) for x in rng.split('-')) if '-' in rng else (int(rng, 16),) * 2
    for s in range(lo, hi + 1):
        for lat, cm in final((int(c), s)):
            D._send(out, int(c), s, lat, cm); n += 1
            if n % 6 == 0:
                D.sync(inp, out)                                    # flow control (small MIDI receive ring)
D.sync(inp, out)
print('pushed', n, 'commits')
