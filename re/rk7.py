#!/usr/bin/env python3
"""REVERSE engine v7 loader (rev_v7.asm): v5 locked core + chunk-jump fades written from the pedal tick (vector 30).
Uses the borrowed 2 s memory (mem2s.py) when base=0x0100. Data offsets match rev_v7.asm.
Usage (module): start(io, chunk_ms, speed, base, fade_ms_unused) / fade(io, on) / counters(io)"""
import math
import revload as RL
import revlock as RK

SEG = 0x06C0
NL = 5
D = {'fon': 0x140, 'li': 0x141, 'bc': 0x142, 'nlv': 0x143, 'ftrig': 0x144, 'ltab': 0x148, 'cnt': 0x180}
C_LEVEL = 100


def ltab(nl=NL, level=C_LEVEL):
    """C level coefficients (11-bit two's complement on 2:076/07C, level 100 = 0x400 = -1.0, sign kept): index 0 silent
    .. NL full, raised-cosine."""
    full = (level << 10) // 100
    s = full - 0x800 if full >= 0x400 else full
    return [int(round(s * i / nl)) & 0x7FF for i in range(nl + 1)]       # linear: equal (smallest) steps


def start(io, chunk_ms, speed=-1.0, base=None, dmin_ms=1.0, fades=True, nl=NL):
    if base is not None:
        RL.BASE = base
    code = RK.assemble('rev_v7')
    assert len(code) <= 0x200
    amin = RL.BASE + int(32 * dmin_ms); n = RK.span(chunk_ms, speed); amax = amin + n
    assert amax <= 0xFFBF, f'chunk too long: {amax:04x}'
    RL.stop(io)
    RK.stock_vectors(io)                          # never rewrite stub code while a vector points at it
    for i, b in enumerate(code):
        if i < 0x1A0 or i >= 0x1B0:               # skip the bank-6 stack area
            RL.poke(io, SEG, i, b)
    set_len(io, nl, speed, amax)
    for vec, off in RK.STUB.items():
        RK.setvec(io, vec, SEG, off)
    for r, v in (('vpc', 0), ('ds0', 0x8000), ('ss', SEG), ('ps', SEG), ('ds1', 0x40F0), ('sp', RK.SP),
                 ('aw', 0x0001), ('bw', amin), ('bp', RK.step(speed)), ('dw', amax), ('cw', n), ('ix', 0),
                 ('iy', 0x1872)):
        RK.setreg(io, r, v)
    v = RL.peek(io, 0x40E0, RK.BANK, 32)
    got = {r: v[o] | v[o + 1] << 8 for r, o in RK.REG.items()}
    for r, want in (('bw', amin), ('bp', RK.step(speed)), ('dw', amax), ('cw', n), ('ix', 0), ('iy', 0x1872)):
        if got[r] != want:
            print(f'bank 6 {r} read back {got[r]:04x}, want {want:04x}: rewriting'); RK.setreg(io, r, want)
    RL.poke(io, SEG, D['fon'], 1 if fades else 0)
    resume(io)
    print(f'REVERSE v7 on (fades {"on" if fades else "off"}): speed {speed:+.1f}, chunk {chunk_ms:.0f} ms, '
          f'A {amin:04x}-{amax:04x}, fade {nl} ms each way')


def set_len(io, nl, speed=-1.0, amax=None):
    """fade length = nl steps of 1 ms each way (1..24), linear. Safe live: fades off while the table changes."""
    assert 1 <= nl <= 24
    if amax is None:
        v = RL.peek(io, 0x40E0, RK.BANK + RK.REG['dw'], 2); amax = v[0] | v[1] << 8
    on = RL.peek(io, SEG, D['fon'], 1)[0]
    RL.poke(io, SEG, D['fon'], 0)
    for i, c in enumerate(ltab(nl)):
        RL.poke16(io, SEG, D['ltab'] + 2 * i, c)
    RL.poke16(io, SEG, D['ftrig'], amax - (nl + 2) * RK.step(speed) * 16)
    RL.poke(io, SEG, D['nlv'], nl)
    RL.poke(io, SEG, D['li'], nl)
    RL.poke(io, SEG, D['fon'], on)


def fade(io, on):
    RL.poke(io, SEG, D['fon'], 1 if on else 0)


def counters(io):
    v = RL.peek(io, SEG, D['cnt'], 10)
    w = [v[i] | v[i + 1] << 8 for i in range(0, 10, 2)]
    bc = RL.peek(io, SEG, D['bc'], 1)[0]; li = RL.peek(io, SEG, D['li'], 1)[0]
    return dict(zip(('nwr', 'nbusy', 'nfw', 'nlw', 'nto'), w), bc=bc, li=li)


def tap_latch(io):
    """DSP instruction latch = 00ffff (the C tap's own class). The engine's commit 1 takes the instruction latch's top
    byte as well as A, so any other DSP write (firmware setters, fades, debug pokes) must be followed by this before the
    engine runs, or the C tap stops being a memory read (wet gone)."""
    for o, v in ((0xA, 0x00), (0x9, 0xFF), (0x8, 0xFF)):
        RL.poke(io, 0x8000, o, v)


def resume(io):
    tap_latch(io)
    RK.resume(io)
