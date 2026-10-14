#!/usr/bin/env python3
"""100% WET for the tap delay (found 2026-10-14, bench.py): DSP coefficients are 12-bit signed (0x7FF = +1.0,
0x800 = -1.0). The block's dry reaches the output twice (two mixer chains); 2:07A's coefficient slot is the gain of
chain B's dry (stock +1.0). Set it to -1.0 and chain B cancels chain A's dry: dry -29 dB (meter floor), wet unchanged.
The C level MACs 2:076/2:07C top out at 0x400 (+0.5) from the firmware; 0x7FF = +1.0 = +6 dB wet.
Engine paused around the writes (they share the bus latches), resumed with the C-tap latch first.
Any OS DSP rewrite (patch push, knob, menu) undoes it: run it again. Hands off the front panel while the engine runs.
Usage: py -3.10 wet100.py on [clevel hex, default 7ff] [chain-B clevel hex] | off   (076 = chain A, 07C = chain B)"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault('DSP_BUSLOG', os.path.join(HERE, 'out', 'dsp_buslog_rev2.json'))
import dsplive as D, revload as RL, rk7

DRY_B = 0x07A          # chain B dry gain (instr 01ffc0, commit 00 from the firmware; slot = +1.0 at boot)
CLEV = (0x076, 0x07C)  # C level MACs (instr 090038, commit 8)

if __name__ == '__main__':
    on = sys.argv[1] == 'on'
    cl = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x7FF
    clb = int(sys.argv[3], 16) if len(sys.argv) > 3 else cl
    io = RL.ports()
    try:
        RL.stop(io)
        D.poke(io[1], 2, DRY_B, instr=0x01ffc0, coef=0x800 if on else 0x7FF, commit=8)
        for s, c in zip(CLEV, (cl, clb)):
            if on:
                D.poke(io[1], 2, s, instr=0x090038, coef=c, commit=8)
            else:
                D.restore(io[1], 2, s)
        D.sync(io[0], io[1])
        rk7.resume(io)
    finally:
        io[0].close(); io[1].close()
    print(f'wet100 {"ON (dry cancelled, C level A %03x B %03x)" % (cl, clb) if on else "OFF (stock dry, stock C level)"} - engine resumed')
