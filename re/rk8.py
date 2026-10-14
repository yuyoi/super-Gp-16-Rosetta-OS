#!/usr/bin/env python3
"""REVERSE engine v8 loader (rev_v8.asm = v6 locked + in-engine fades + the instruction-latch fix), NLEV 16 (4 ms
fades, a level step every 0.25 ms), borrowed 2 s memory (mem2s). Reuses revlock's helpers.
Usage: py -3.10 rk8.py [fade on|off] [chunk_ms] [speed]   (after revsetup-style patch + mem2s on)"""
import sys
import revload as RL
import revlock as RK

RK.NLEV = 16
RK.FADE = {'fstate': 0x140, 'fi': 0x141, 'tog': 0x142, 'fwin': 0x144, 'ftrig': 0x146, 'tout': 0x148, 'tin': 0x168}
CNT = 0x18E                                       # nfw, nwr, nbusy (3 words), nfad 18A, nlev 18C, bc 188


def tap_latch(io):
    for o, v in ((0xA, 0x00), (0x9, 0xFF), (0x8, 0xFF)):
        RL.poke(io, 0x8000, o, v)


def start(io, chunk_ms, speed=-1.0, base=0x0100, dmin_ms=1.0, fade=True):
    RL.BASE = base
    code = RK.assemble('rev_v8')
    amin = RL.BASE + int(32 * dmin_ms); n = RK.span(chunk_ms, speed); amax = amin + n
    assert amax <= 0xFFBF, f'chunk too long: {amax:04x}'
    RL.stop(io)
    RK.stock_vectors(io)
    for i, b in enumerate(code):
        RL.poke(io, RK.SEG, i, b)
    for i, b in enumerate(RK.assemble('vec_stubs')):
        RL.poke(io, RK.SEG, RK.STUB[29] + i, b)
    for vec, off in RK.STUB.items():
        RK.setvec(io, vec, RK.SEG, off)
    for r, v in (('vpc', 0), ('ds0', 0x8000), ('ss', RK.SEG), ('ps', RK.SEG), ('ds1', 0x40F0), ('sp', RK.SP),
                 ('aw', 0x0001), ('bw', amin), ('bp', RK.step(speed)), ('dw', amax), ('cw', n), ('ix', 0),
                 ('iy', 0x1872)):
        RK.setreg(io, r, v)
    v = RL.peek(io, 0x40E0, RK.BANK, 32)
    got = {r: v[o] | v[o + 1] << 8 for r, o in RK.REG.items()}
    for r, want in (('bw', amin), ('bp', RK.step(speed)), ('dw', amax), ('cw', n), ('ix', 0), ('iy', 0x1872)):
        if got[r] != want:
            print(f'bank 6 {r} read back {got[r]:04x}, want {want:04x}: rewriting'); RK.setreg(io, r, want)
    RK.set_fade(io, fade, speed, amax)
    resume(io)
    print(f'REVERSE v8 on (fades {"on" if fade else "off"}, {RK.NLEV} steps = {RK.NLEV / 4:.0f} ms): speed {speed:+.1f}, '
          f'chunk {chunk_ms:.0f} ms, A {amin:04x}-{amax:04x}')
    return amax


def resume(io):
    tap_latch(io)
    RK.resume(io)


def counters(io):
    v = RL.peek(io, RK.SEG, 0x188, 12)
    w = [v[i] | v[i + 1] << 8 for i in range(2, 12, 2)]
    return dict(bc=v[0], nfad=w[0], nlev=w[1], nfw=w[2], nwr=w[3], nbusy=w[4], fstate=RL.peek(io, RK.SEG, 0x140, 1)[0])
