#!/usr/bin/env python3
"""REVERSE engine v3e (rev_fast.asm, "compressed"): timer 0 at ~31.7 kHz through V25 register bank switching (bank 6),
cheap per-tick step + an exact timer-1 resync every 8 ticks. Hot-loaded over the debug port - no burn.
Bank 6 = internal RAM 40E0:C0-DF (+02 VECTOR PC, +04/+06 PSW/PC save, +08 DS0, +0A SS, +0C PS, +0E DS1, +10 IY,
+12 IX, +14 BP, +16 SP, +18 BW, +1A DW, +1C CW, +1E AW; DS0/DS1 confirmed on the unit).
Needs the tap delay on (C tap = chip 2 step 0x072). A power cycle undoes everything.
Usage: py -3.10 revfast.py start [chunk_ms] [speed] | speed <s> | stop | status   (speed -1 = true reverse)"""
import os, subprocess, sys
import revload as RL

HERE = os.path.dirname(os.path.abspath(__file__))
BANK = 0xC0                                       # bank 6 in segment 40E0
SEG = 0x06C0
MD0 = 41                                          # 1.3333 MHz / 42 = 31746 Hz
TICK = RL.TCLK / (MD0 + 1)
REG = {'vpc': 0x02, 'ds0': 0x08, 'ss': 0x0A, 'ps': 0x0C, 'ds1': 0x0E, 'iy': 0x10, 'ix': 0x12, 'bp': 0x14, 'sp': 0x16,
       'bw': 0x18, 'dw': 0x1A, 'cw': 0x1C, 'aw': 0x1E}
VARS = ('k', 'period', 'last', 'sdx', 'applf', 'appli')


def assemble():
    nasm = os.path.join(HERE, '..', 'tools', 'nasm-2.16.03', 'nasm.exe')
    subprocess.run([nasm, '-f', 'bin', 'rev_fast.asm', '-o', 'rev_fast.bin'], cwd=HERE, check=True)
    return open(os.path.join(HERE, 'rev_fast.bin'), 'rb').read()


def var(name):
    n = len(open(os.path.join(HERE, 'rev_fast.bin'), 'rb').read())
    return n - 2 * len(VARS) + 2 * VARS.index(name)


def params(speed):
    """speed (1 = forward, -1 = true reverse) -> k (true advance per timer-1 count), step per tick, 8 ticks (16.16)"""
    adv = 1 - speed                               # read address change per DSP sample
    k = int(round(adv * RL.FS / RL.TCLK * 65536))
    step = int(round(adv * RL.FS / TICK * 65536))
    return k, step, 8 * step


def set_speed(io, speed):
    k, step, appl = params(speed)
    RL.poke16(io, SEG, var('k'), k)
    RL.poke16(io, SEG, var('applf'), appl & 0xFFFF); RL.poke16(io, SEG, var('appli'), appl >> 16)
    RL.poke16(io, 0x40E0, BANK + REG['dw'], step & 0xFFFF); RL.poke16(io, 0x40E0, BANK + REG['bp'], step >> 16)
    return k, step


def start(io, chunk_ms=500.0, speed=-1.0, dmin_ms=10.0):
    code = assemble()
    amin = RL.BASE + int(32 * dmin_ms); amax = amin + int(max(2.0, abs(1 - speed)) * chunk_ms * 32)
    assert amax <= 0xFFFE, 'chunk too long for the 1.2 s tap memory'
    RL.stop(io)
    for i, b in enumerate(code):
        RL.poke(io, SEG, i, b)
    for r, v in (('vpc', 0), ('ds0', 0x40F0), ('ss', SEG), ('ps', SEG), ('ds1', 0x8000), ('iy', amax), ('ix', amin),
                 ('sp', 0x0400), ('bw', amin), ('cw', 0), ('aw', 8)):
        RL.poke16(io, 0x40E0, BANK + REG[r], v)
    k, step = set_speed(io, speed)
    RL.poke16(io, 0x40F0, 0x82, MD0)
    RL.sfr(io, 0x90, 0x80)                       # TMC0: start, fCLK/6, interval
    RL.sfr(io, 0x9C, 0x16)                       # TMIC0: ENCS (bank switching), priority 6 = bank 6, unmasked
    print(f'REVERSE v3e on: tick {TICK:.0f} Hz, speed {speed:+.2f} (step {step / 65536:.4f}/tick, k {k}), '
          f'chunk {chunk_ms:.0f} ms')


def status(io):
    v = RL.peek(io, 0x40E0, BANK, 32)
    if not v:
        print('no reply'); return
    w = [v[i] | v[i + 1] << 8 for i in range(0, 32, 2)]
    print(f'bank 6: A {w[12]:04x}  step {w[10]}+{w[13]}/65536  amin {w[9]:04x} amax {w[8]:04x}  resync in {w[15] & 0xFF}')


def main():
    a = sys.argv[1:] or ['status']
    io = RL.ports()
    try:
        if a[0] == 'start':
            start(io, float(a[1]) if len(a) > 1 else 500.0, float(a[2]) if len(a) > 2 else -1.0)
            status(io)
        elif a[0] == 'speed':
            k, step = set_speed(io, float(a[1])); print('speed', a[1], 'k', k, 'step', step)
        elif a[0] == 'stop':
            RL.stop(io); print('stopped')
        else:
            status(io)
    finally:
        io[0].close(); io[1].close()


if __name__ == '__main__':
    main()
