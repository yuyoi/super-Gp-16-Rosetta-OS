#!/usr/bin/env python3
"""Exact per-step DSP writes from the firmware bus log (dsptwin.py -> out/dsp_buslog.json).
Bus: latches 8000:0/1 (16 bit), 8000:2, 8000:3, 8000:4/5 (coefficient), 8000:8/9/A (instruction); a write of v to
8000:1000 + chip*0x400 + step commits the step. Firmware commit values: 0 (3109x), 1 after [0]/[1], 2 after [2],
4 after [3], 8 after [4]/[5], 0x0C after [3]+[4]/[5]. On hardware commit 0 also takes the coefficient latch, so a commit
may take every latch: restore therefore sets ALL latches to the values they had at each of the step's firmware commits.
  history(chip, step) -> [(latches dict, commit value), ...] in firmware order
  restore(out, chip, step)          replay those commits exactly
  poke(out, chip, step, **fields)   last firmware commit with fields replaced: instr=, coef=, a=(16-bit [0]/[1]),
                                    b=([2]), r3=([3]), commit=
"""
import json, os, time
import gp16poke as G

HERE = os.path.dirname(os.path.abspath(__file__))
LATCH = (0, 1, 2, 3, 4, 5, 8, 9, 10)
_hist = None


def _load():
    global _hist
    if _hist is None:
        _hist = {}
        cur = {o: 0 for o in LATCH}
        log = json.load(open(os.path.join(HERE, 'out', 'dsp_buslog.json')))
        st = os.path.join(HERE, 'out', 'dsp_state.json')               # pedal segment applied by dspstate.py
        if os.path.exists(st):
            log += json.load(open(st))['log']
        for o, v in log:
            if o in cur:
                cur[o] = v
            elif 0x1000 <= o < 0x1C00 and (o - 0x1000) % 0x400 < 512:
                key = ((o - 0x1000) // 0x400, (o - 0x1000) % 0x400)
                _hist.setdefault(key, []).append((dict(cur), v))
    return _hist


def history(chip, step):
    return _load().get((chip, step), [])


def fields(lat):
    return {'instr': lat[8] | lat[9] << 8 | lat[10] << 16, 'coef': lat[4] | lat[5] << 8, 'a': lat[0] | lat[1] << 8,
            'b': lat[2], 'r3': lat[3]}


_shadow = {}                    # latch values this process has sent (nothing else writes the bus while the unit idles)
_inp = None                     # set by sync(): input port for flow control


def _raw(out, o, v):
    G.send(out, [0x47, 2] + G.nib(o, 4) + G.nib(v, 2))
    time.sleep(0.004)


def _send(out, chip, step, lat, commit):
    """write one step the way the firmware does. Commits 0 / 8: one cmd-01 message (instruction A,9,8 + coefficient
    5,4 + commit), plus raw writes for latches 0-3 that changed. Commits with a field bit (1 = A [1],[0], 2 = B [2],
    4 = reg3 [3]): raw writes in firmware order - instruction, then the field latch(es), then the commit."""
    if commit & 7:
        for o in (10, 9, 8):
            _raw(out, o, lat[o])
        for o in (5, 4):                                            # a commit takes EVERY latch: the coefficient
            if commit & 8 or _shadow.get(o) != lat[o]:              # too, even when the firmware didn't write it
                _raw(out, o, lat[o])
        for bit, offs in ((4, (3,)), (2, (2,)), (1, (1, 0))):
            if commit & bit:
                for o in offs:
                    _raw(out, o, lat[o])
        for o in (3, 2, 1, 0):                                      # other latches the firmware had at that commit
            if not (commit & {3: 4, 2: 2, 1: 1, 0: 1}[o]) and _shadow.get(o) != lat[o]:
                _raw(out, o, lat[o])
        _raw(out, 0x1000 + chip * 0x400 + step, commit)
        for o in LATCH:
            _shadow[o] = lat[o]
        return
    a_changed = _shadow.get(0) != lat[0] or _shadow.get(1) != lat[1]
    for o in (3, 2, 1, 0):                                          # high byte first ([1] then [0])
        if _shadow.get(o) != lat[o] or (o in (0, 1) and a_changed):
            _raw(out, o, lat[o])
            _shadow[o] = lat[o]
    G.send(out, G.msg_write(chip, step, lat[8] | lat[9] << 8 | lat[10] << 16, lat[4] | lat[5] << 8, commit))
    for o in (4, 5, 8, 9, 10):
        _shadow[o] = lat[o]
    time.sleep(0.008)


def sync(inp, out, timeout=2.0):
    """ping the debug port and wait for the answer: every byte sent before it has been processed"""
    G.send(out, [0x47, 4])
    return G.wait_reply(inp, 0x44, timeout) is not None


def forget():
    """latches were changed by something else (e.g. dspreplay): send everything next time"""
    _shadow.clear()


def final(chip, step):
    """the last firmware commit of each commit value, in firmware order (skips the boot fade ramps)"""
    h = history(chip, step)
    last = {c: i for i, (lat, c) in enumerate(h)}
    return [h[i] for i in sorted(last.values())]


def restore(out, chip, step):
    for lat, commit in final(chip, step):
        _send(out, chip, step, lat, commit)


def poke(out, chip, step, instr=None, coef=None, a=None, b=None, r3=None, commit=None):
    h = history(chip, step)
    lat, c = (dict(h[-1][0]), h[-1][1]) if h else ({o: 0 for o in LATCH}, 0)
    if instr is not None:
        lat[8], lat[9], lat[10] = instr & 0xFF, instr >> 8 & 0xFF, instr >> 16 & 0xFF
    if coef is not None:
        lat[4], lat[5] = coef & 0xFF, coef >> 8 & 0xFF
    if a is not None:
        lat[0], lat[1] = a & 0xFF, a >> 8 & 0xFF
    if b is not None:
        lat[2] = b
    if r3 is not None:
        lat[3] = r3
    _send(out, chip, step, lat, c if commit is None else commit)


if __name__ == '__main__':
    import sys
    c, s = int(sys.argv[1]), int(sys.argv[2], 16)
    for lat, commit in final(c, s):
        f = fields(lat)
        print(f'commit {commit:02x}: instr {f["instr"]:06x} coef {f["coef"]:04x} a {f["a"]:04x} b {f["b"]:02x} r3 {f["r3"]:02x}')
