#!/usr/bin/env python3
"""Diff the DSP state after a pedal segment against the unit's base state: every step whose final latches (per commit
value) change. Usage: py -3.10 dspstate_diff.py <pedal>"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
LATCH = (0, 1, 2, 3, 4, 5, 8, 9, 10)


def state(log):
    cur = {o: 0 for o in LATCH}; d = {}
    for o, v in log:
        if o in cur:
            cur[o] = v
        elif 0x1000 <= o < 0x1C00 and (o - 0x1000) % 0x400 < 512:
            d.setdefault(((o - 0x1000) // 0x400, (o - 0x1000) % 0x400), {})[v] = dict(cur)
    return d


def fmt(l):
    return 'none' if l is None else (f'i {l[8] | l[9] << 8 | l[10] << 16:06x} c {l[4] | l[5] << 8:04x} '
                                     f'a {l[0] | l[1] << 8:04x} b {l[2]:02x} r3 {l[3]:02x}')


if __name__ == '__main__':
    base = json.load(open(os.path.join(HERE, 'out', 'dsp_buslog.json')))
    seg = json.load(open(os.path.join(HERE, 'out', 'dspstate', sys.argv[1] + '.json')))
    A, B = state(base), state(base + seg)
    for k in sorted(B):
        for cm in sorted(B[k]):
            a, b = A.get(k, {}).get(cm), B[k][cm]
            if a != b:
                print(f'chip {k[0]} step {k[1]:03x} commit {cm:x}: {fmt(b)}   (was {fmt(a)})')
