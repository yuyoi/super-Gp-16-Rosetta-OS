#!/usr/bin/env python3
"""Hot-load the REVERSE engine (rev_isr.asm) into the GP-16's RAM over the debug port and run it from timer 0 - no burn.
Code at RAM 06C0:0000 (= DS FA00:CC00, unused by the stock firmware and the OS), vector 28 (timer unit 0) -> it,
timer 0 in interval mode at 1.3333 MHz / (MD0 + 1). Needs the tap delay on (C tap = chip 2 step 0x072) and the GP-16 on
its patch screen for the DT1 push. A power cycle undoes everything (vectors, timer, RAM code).
Usage: py -3.10 revload.py start [chunk_ms] [rate_hz] | stop | status | tune <k (16.16 address per timer-1 count)>"""
import os, subprocess, sys, time
import mido
import gp16poke as G

HERE = os.path.dirname(os.path.abspath(__file__))
SEG = 0x06C0                                       # physical 0x6C00
VARS = ('addr', 'frac', 'k', 'period', 'last', 'amin', 'amax', 'count')   # words, then run (byte)
BASE = 0x69FF                                      # C tap address for 0 ms; +32 per ms (coefsweep p53)
FS = 32000.0
TCLK = 8e6 / 6
_n = 0


def port_names():
    """The Focusrite's MIDI port names: Windows renumbers them (4/5, 2/3...) whenever the device reconnects."""
    i = next(p for p in mido.get_input_names() if p.startswith('Focusrite USB MIDI'))
    o = next(p for p in mido.get_output_names() if p.startswith('Focusrite USB MIDI'))
    return i, o


def ports():
    i, o = port_names()
    return mido.open_input(i), mido.open_output(o)


def assemble():
    nasm = os.path.join(HERE, '..', 'tools', 'nasm-2.16.03', 'nasm.exe')
    subprocess.run([nasm, '-f', 'bin', 'rev_isr.asm', '-o', 'rev_isr.bin'], cwd=HERE, check=True)
    code = open(os.path.join(HERE, 'rev_isr.bin'), 'rb').read()
    vo = len(code) - (2 * len(VARS) + 1)
    return code, {k: vo + 2 * i for i, k in enumerate(VARS)} | {'run': vo + 2 * len(VARS)}


def poke(io, seg, off, val):
    global _n
    inp, out = io
    G.send(out, G.msg_poke(seg, off, val & 0xFF))
    _n += 1
    if _n % 6 == 0:                                  # tiny MIDI receive ring on the GP-16: flow control
        G.send(out, [0x47, 4])
        if G.wait_reply(inp, 0x44, 2.0) is None:
            raise RuntimeError('debug port stopped answering')


def poke16(io, seg, off, val):
    poke(io, seg, off, val); poke(io, seg, off + 1, val >> 8)


def peek(io, seg, off, n):
    inp, out = io
    G.send(out, G.msg_peek(seg, off, n)); r = G.wait_reply(inp, 0x45)
    return None if not r else [r[8 + 2 * i] << 4 | r[8 + 2 * i + 1] for i in range(n)]


def sfr(io, off, val):
    poke(io, 0x40F0, off, val)


def stop(io):
    sfr(io, 0x9C, 0x47)                              # TMIC0 masked
    sfr(io, 0x90, 0x50)                              # TMC0 as the firmware left it (stopped)


def start(io, chunk_ms=250.0, rate=None, dmin_ms=10.0):
    code, v = assemble()
    md0 = int(round(TCLK / rate)) - 1 if rate else 83   # tick rate only sets how often the address is written
    tick = TCLK / (md0 + 1)
    kf = int(round(2 * FS / TCLK * 65536))            # address per timer-1 count (16.16): +2 per DSP sample
    amin = BASE + int(32 * dmin_ms); amax = amin + int(2 * chunk_ms * 32)
    if amax > 0xFFFE:
        raise ValueError('chunk too long for the 1.2 s tap memory')
    stop(io)
    for i, b in enumerate(code):                       # code + vars
        poke(io, SEG, i, b)
    for k, val in (('addr', amin), ('frac', 0), ('k', kf), ('period', 1334), ('last', 0), ('amin', amin),
                   ('amax', amax), ('count', 0)):
        poke16(io, SEG, v[k], val)
    poke(io, SEG, v['run'], 1)
    for i, b in enumerate((0x00, 0x00, SEG & 0xFF, SEG >> 8)):   # vector 28 -> 06C0:0000
        poke(io, 0x0000, 28 * 4 + i, b)
    poke16(io, 0x40F0, 0x82, md0)                     # MD0
    sfr(io, 0x90, 0x80)                               # TMC0: start, fCLK/6, interval
    sfr(io, 0x9C, 0x07)                               # TMIC0: unmasked, priority 7 (lowest: MIDI keeps priority)
    print(f'REVERSE on: tick {tick:.0f} Hz, k {kf}, chunk {chunk_ms:.0f} ms (A {amin:04x}-{amax:04x})')
    return v


def status(io):
    _, v = assemble()
    a = peek(io, SEG, v['count'], 2); t = time.time(); time.sleep(1.0)
    b = peek(io, SEG, v['count'], 2); t2 = time.time()
    ad = peek(io, SEG, v['addr'], 2)
    ca, cb = a[0] | a[1] << 8, b[0] | b[1] << 8
    print(f'ticks writing: {((cb - ca) & 0xFFFF) / (t2 - t):.0f}/s, addr {ad[0] | ad[1] << 8:04x}, '
          f'TMIC0 {peek(io, 0x40F0, 0x9C, 1)[0]:02x} TMC0 {peek(io, 0x40F0, 0x90, 1)[0]:02x}')


def main():
    a = sys.argv[1:] or ['status']
    io = ports()
    try:
        if a[0] == 'start':
            start(io, float(a[1]) if len(a) > 1 else 250.0, float(a[2]) if len(a) > 2 else None)
            status(io)
        elif a[0] == 'stop':
            stop(io); print('timer 0 stopped (tap address stays where it was: reload the patch to reset)')
        elif a[0] == 'tune':
            _, v = assemble(); poke16(io, SEG, v['k'], int(a[1], 0)); print('k', a[1])
        else:
            status(io)
    finally:
        io[0].close(); io[1].close()


if __name__ == '__main__':
    main()
