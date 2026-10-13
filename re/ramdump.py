#!/usr/bin/env python3
"""Read the GP-16's whole 64 KB battery RAM (physical 00000-0FFFF = DS FA00:6000-FFFF plus the low area) over the
debug port (backdoor peek, cmd 05) -> out/unit_ram.bin. The emulator can then boot in the unit's exact state (same
patches, same OS settings), so its DSP program and coefficients match the real unit (dsptwin.py).
Usage: py -3.10 ramdump.py [--port Focusrite] [out.bin]"""
import argparse, os, sys, time
import gp16poke as G

CH = 0x80


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out', nargs='?', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'unit_ram.bin'))
    ap.add_argument('--port', default='Focusrite')
    a = ap.parse_args()
    inp, out = G.open_ports(a.port)
    data = bytearray()
    t = time.time()
    for off in range(0, 0x10000, CH):
        for tries in range(4):
            G.send(out, G.msg_peek(0, off, CH))
            r = G.wait_reply(inp, 0x45)
            if r and len(r) >= 8 + 2 * CH:
                break
        else:
            sys.exit(f'no reply at {off:04x}')
        data += bytes(r[8 + 2 * i] << 4 | r[9 + 2 * i] for i in range(CH))
        if off % 0x1000 == 0:
            print(f'{off:04x} {time.time() - t:5.1f}s', flush=True)
    open(a.out, 'wb').write(data)
    print('wrote', a.out, len(data), 'bytes')


if __name__ == '__main__':
    main()
