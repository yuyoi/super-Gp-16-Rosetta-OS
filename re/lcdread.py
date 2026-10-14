#!/usr/bin/env python3
"""Read the GP-16 LCD (HD44780 at 2000:0 command/status, 2000:1 data; R/W is wired, the firmware reads it back
too) over the debug port: both DDRAM lines + the 8 CGRAM glyphs. Puts the address counter back afterwards.
Display only: never touches RAM or the DSP. Usage: py -3.10 lcdread.py [--write "TEXT"]"""
import sys
import revload as RL

LCD = 0x2000


def rd(io):
    return RL.peek(io, LCD, 1, 1)[0]


if __name__ == '__main__':
    io = RL.ports()
    try:
        st = RL.peek(io, LCD, 0, 1)[0]
        print(f'status {st:02x} (busy {st >> 7}, address {st & 0x7f:02x})')
        if '--write' in sys.argv:
            txt = sys.argv[sys.argv.index('--write') + 1][:16].ljust(16)
            RL.poke(io, LCD, 0, 0x80)
            for c in txt:
                RL.poke(io, LCD, 1, ord(c))
        for base in (0x80, 0xC0):
            RL.poke(io, LCD, 0, base)
            codes = [rd(io) for _ in range(16)]
            print(f'{base:02x}:', ' '.join(f'{c:02x}' for c in codes), ' |' + ''.join(chr(c) if 32 <= c < 127 else '?' for c in codes) + '|')
        RL.poke(io, LCD, 0, 0x40)
        cg = [rd(io) for _ in range(64)]
        for g in range(8):
            print(f'CG{g}:', ' '.join(f'{b & 0x1f:05b}'.replace('0', '.').replace('1', '#') for b in cg[8 * g:8 * g + 8]))
        RL.poke(io, LCD, 0, 0x80 | (st & 0x7f))
    finally:
        io[0].close(); io[1].close()
