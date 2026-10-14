#!/usr/bin/env python3
"""Live single-parameter DT1 (no patch reload, so mem2s borrowed memory survives). Engine paused around the write:
the firmware's coefficient writes and the ISR's address commits share the bus latches.
Usage: py -3.10 gain.py <sysex addr hex> <value> [...pairs]   e.g. gain.py 17 70  (OD drive)"""
import sys, time
import mido
import revload as RL
import revlock as RK
import rk7
import revtest as RT

P = RT.P

if __name__ == '__main__':
    pairs = [(int(sys.argv[i], 16), int(sys.argv[i + 1])) for i in range(1, len(sys.argv), 2)]
    io = RL.ports()
    try:
        RL.stop(io)
        for a, v in pairs:
            io[1].send(mido.Message('sysex', data=P.roland([0x12, 0, 0, a, v])))
            time.sleep(0.15)
        time.sleep(0.3)
        rk7.resume(io)                  # latch back to the C tap first (see rk7.tap_latch)
    finally:
        io[0].close(); io[1].close()
    print('set', ', '.join(f'{a:02x}={v}' for a, v in pairs), '- engine resumed')
