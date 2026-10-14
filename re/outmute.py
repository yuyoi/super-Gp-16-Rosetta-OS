#!/usr/bin/env python3
"""Mute one GP-16 output in the DSP (chip 1 output stores: 1:16F `00003e` = output A, 1:176 `00003f` = output B;
NOP = the output register stops updating = silence). Ear test: does the dry come back on one side alone (then the
wet100 dry cancel happens ACROSS the two outputs). Engine paused around the writes.
Usage: py -3.10 outmute.py A | B | none"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault('DSP_BUSLOG', os.path.join(HERE, 'out', 'dsp_buslog_rev2.json'))
import dsplive as D, revload as RL, rk7

OUT = {'A': 0x16F, 'B': 0x176}

if __name__ == '__main__':
    which = sys.argv[1]
    io = RL.ports()
    try:
        RL.stop(io)
        for k, s in OUT.items():
            if k == which:
                D.poke(io[1], 1, s, instr=0, commit=0)
            else:
                D.restore(io[1], 1, s)
        D.sync(io[0], io[1])
        rk7.resume(io)
    finally:
        io[0].close(); io[1].close()
    print('muted output', which if which in OUT else 'none', '- engine resumed')
