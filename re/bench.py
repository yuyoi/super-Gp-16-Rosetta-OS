#!/usr/bin/env python3
"""DSP instruction decode bench on the tap-delay mixer (chip 2 half B, steps 2:079-07E; output -> reg 2C -> chip 1).
Engine stopped, static C tap at 300 ms (drytest.setup first). Inputs: r23 = block input (dry), r38 = C tap (wet).
run(tag, ws): pokes, one click, restores in REVERSE order, then checks the baseline is back (re-restores if not).
Prints dry / wet in dB vs the first baseline. Exact restores from DSP_BUSLOG (default out/dsp_buslog_rev2.json)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault('DSP_BUSLOG', os.path.join(HERE, 'out', 'dsp_buslog_rev2.json'))
import numpy as np
import drytest as T, dsplive as D, revload as RL

BASE = {}
B = [(2, 0x79, dict(instr=0x000038, commit=8))]          # half B loads the tap: half the dry gone


def I(s, v, **k):
    return (2, s, dict(instr=v, commit=8, **k))


def _io(fn):
    io = RL.ports()
    try:
        fn(io); D.sync(io[0], io[1])
    finally:
        io[0].close(); io[1].close()


def _click():
    env, i0, dry, wet = T.click()
    return dry, wet


def _db(x, k):
    return 20 * np.log10(x / BASE[k])


def run(tag, ws, check=True):
    _io(lambda io: [D.poke(io[1], c, s, **kw) for c, s, kw in ws])
    dry, wet = _click()
    touched = [(c, s) for c, s, _ in ws][::-1]
    _io(lambda io: [D.restore(io[1], c, s) for c, s in touched])
    if not BASE:
        BASE.update(dry=dry, wet=wet)
    d, w = _db(dry, 'dry'), _db(wet, 'wet')
    print(f'{tag:34s} dry {d:+6.1f}  wet {w:+6.1f}  (wet-dry {w - d - 6.0:+5.1f} vs stock)', flush=True)
    if check and ws:
        for tries in range(3):
            d0, w0 = _click()
            if abs(_db(d0, 'dry')) < 1.5 and abs(_db(w0, 'wet')) < 1.5:
                break
            print(f'   ! baseline off (dry {_db(d0, "dry"):+.1f} wet {_db(w0, "wet"):+.1f}): re-restoring', flush=True)
            _io(lambda io: [D.restore(io[1], c, s) for c, s in touched])
        else:
            raise SystemExit('baseline did not come back: stop and fix by hand')
    return d, w


def start():
    _io(T.static_tap)
    run('baseline', [])
