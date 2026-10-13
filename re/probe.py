#!/usr/bin/env python3
"""Read a DSP host port (8000:chip*0x400+6) N times over the debug port. Usage: py -3.10 probe.py <chip> [n]"""
import sys, gp16poke as G
i, o = G.open_ports('Focusrite')
chip = int(sys.argv[1]); n = int(sys.argv[2]) if len(sys.argv) > 2 else 24
vals = []
for k in range(n):
    G.send(o, [0x47, 3] + G.nib(chip * 0x400 + 6, 4)); r = G.wait_reply(i, 0x43)
    vals.append(r[4] << 4 | r[5] if r else None)
print(' '.join('--' if v is None else f'{v:02x}' for v in vals))
