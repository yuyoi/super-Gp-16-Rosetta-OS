#!/usr/bin/env python3
"""Soft-reload the GP-16 DSPs over MIDI: replay the firmware's own DSP bus writes (captured by dsptwin.py from the unit's
RAM -> out/dsp_buslog.json) through the debug port's raw write (cmd 02), in order. Every latch (8000:0/1, 2, 3, 4/5,
8/9/A) and every commit value goes out exactly as the firmware wrote them, so the result is the unit's real state.
Usage: py -3.10 dspreplay.py [--port Focusrite] [--from N] [--to N] [--steps-only]"""
import argparse, json, os, sys, time
import gp16poke as G

HERE = os.path.dirname(os.path.abspath(__file__))


def replay(out, log, progress=True, inp=None):
    """with inp: flow control (ping + wait every 6 writes) so the GP-16's small MIDI receive ring never overflows"""
    t = time.time()
    for k, (o, v) in enumerate(log):
        G.send(out, [0x47, 2] + G.nib(o, 4) + G.nib(v, 2))
        if inp is not None and k % 6 == 5:
            G.send(out, [0x47, 4])
            if G.wait_reply(inp, 0x44, 2.0) is None:
                print('no flow-control reply at write', k)
        if progress and k % 2000 == 0:
            print(f'{k}/{len(log)} {time.time() - t:5.1f}s', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', default='Focusrite')
    ap.add_argument('--from', dest='lo', type=int, default=0)
    ap.add_argument('--to', dest='hi', type=int)
    a = ap.parse_args()
    log = json.load(open(os.path.join(HERE, 'out', 'dsp_buslog.json')))[a.lo:a.hi]
    inp, out = G.open_ports(a.port)
    G.send(out, [0x47, 4])
    if not G.wait_reply(inp, 0x44):
        sys.exit('debug port does not answer')
    replay(out, log, inp=inp)
    G.send(out, [0x47, 4])
    print('done,', len(log), 'writes; debug port', 'ok' if G.wait_reply(inp, 0x44, 3.0) else 'NOT answering')


if __name__ == '__main__':
    main()
