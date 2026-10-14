#!/usr/bin/env python3
"""Write battery-backed RAM areas back from a clean dump (only bytes that differ from a fresh 'now' dump).
Areas (DS FA00 offsets): stored patches 6400-9CFF, OS knob/board memories B000-B7FF, MIDI channel A6BA, system block
9D00-9D05 + 9D78-9E78 (boot loads it: F6A1:0006 -> F00E:1E78) and its live copies A0F4/A182 (PC maps), A42C, OS state
CE20-CEFF + CF30-CFFF (CF00-CF2F = the debug-port parser itself: never written). Runtime areas are left alone.
Usage: py -3.10 ramrestore.py <clean.bin> <now.bin>"""
import sys, time
import revload as RL, gp16poke as G

AREAS = [('patches', 0x6400, 0x9D00), ('knobs+boards', 0xB000, 0xB800), ('MIDI ch', 0xA6BA, 0xA6BB),
         ('sys block', 0x9D00, 0x9D06), ('sys PC maps', 0x9D78, 0x9E79), ('PC map 1', 0xA0F4, 0xA174),
         ('PC map 2', 0xA182, 0xA202), ('sys A42C', 0xA42C, 0xA42D),
         ('OS state', 0xCE20, 0xCF00), ('OS state 2', 0xCF30, 0xD000)]
P = lambda ds: ds - 0x6000

if __name__ == '__main__':
    good = open(sys.argv[1], 'rb').read(); now = open(sys.argv[2], 'rb').read()
    io = RL.ports()
    try:
        G.send(io[1], [0x47, 4]); assert G.wait_reply(io[0], 0x44, 2.0), 'debug port not answering'
        t = time.time()
        for tag, a, b in AREAS:
            todo = [x for x in range(a, b) if good[P(x)] != now[P(x)]]
            for k, x in enumerate(todo):
                RL.poke(io, 0xFA00, x, good[P(x)])
            print(f'{tag:14s} {len(todo):5d} bytes written  ({time.time() - t:.0f} s)', flush=True)
    finally:
        io[0].close(); io[1].close()
