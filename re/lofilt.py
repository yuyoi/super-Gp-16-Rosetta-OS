#!/usr/bin/env python3
"""Line-out filter gains, live (twin diff 2026-10-14): presence = 1:148 `100035` slot, treble = 1:14B `4dffc0` slot
(firmware 0..100 -> 0..0x7FF), mid 1:149 (0x417 = 50), bass 1:14A (0x460 = 55). Slots are 12-bit signed, so
negative gains (0x800 = -1.0) are possible that the firmware never uses. Engine paused around each write.
Usage: py -3.10 lofilt.py set <pres hex> <treb hex> | cycle <secs> <p,t> <p,t> ... (prints each step's start)"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault('DSP_BUSLOG', os.path.join(HERE, 'out', 'dsp_buslog_rev2.json'))
import dsplive as D, revload as RL, rk7

PRES, TREB = 0x148, 0x14B
INSTR = {PRES: 0x100035, TREB: 0x4dffc0}


def setg(pres, treb):
    io = RL.ports()
    try:
        RL.stop(io)
        for s, g in ((PRES, pres), (TREB, treb)):
            D.poke(io[1], 1, s, instr=INSTR[s], coef=g & 0xFFF, commit=8)
        D.sync(io[0], io[1])
        rk7.resume(io)
    finally:
        io[0].close(); io[1].close()


if __name__ == '__main__':
    if sys.argv[1] == 'set':
        setg(int(sys.argv[2], 16), int(sys.argv[3], 16)); print('set', sys.argv[2], sys.argv[3])
    else:
        secs = float(sys.argv[2]); t0 = time.time()
        for k, pt in enumerate(sys.argv[3:]):
            p, t = (int(x, 16) for x in pt.split(','))
            setg(p, t)
            print(f'{time.time() - t0:5.1f} s  #{k + 1}: presence {p:03x} treble {t:03x}', flush=True)
            time.sleep(max(0.0, secs - 0.5))
        setg(0, 0); print('back to presence 0, treble 0 (your patch)')
