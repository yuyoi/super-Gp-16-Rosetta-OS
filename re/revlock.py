#!/usr/bin/env python3
"""REVERSE engine v6 "locked + fades" (rev_lock.asm): one tap-address write every 2 DSP frames, phase-locked to the DSP
through its busy flag by a software PLL on timer 0 (register bank 6). The wet fades out ~2 ms before each chunk jump and
back in after it (C level steps 2:076/07C, commit 8), so the jump happens in silence. Integer step per update = 2 * (1 - speed), so speeds in
0.5 steps are exact (-1 = true reverse, -0.5, 0 = freeze, +0.5 = octave down forwards, -2). Hot-loaded, no burn.
Needs the tap delay on (C tap = chip 2 step 0x072). A power cycle undoes everything. v3e (revfast.py) = the crushed one.
Usage: py -3.10 revlock.py start [chunk_ms] [speed] [dmin_ms] | speed <s> | chunk <ms> | fade on|off | patch | stop
       | status
(patch = push the REVERSE DELAY base with the engine paused)"""
import os, subprocess, sys, time
import revload as RL

HERE = os.path.dirname(os.path.abspath(__file__))
BANK = 0xC0                                       # bank 6 in segment 40E0
SEG = 0x06C0
MD0 = 82                                          # 83 counts = 62.25 us; the PLL toggles 82 / 83 (2 frames = 83.38)
REG = {'vpc': 0x02, 'ds0': 0x08, 'ss': 0x0A, 'ps': 0x0C, 'ds1': 0x0E, 'iy': 0x10, 'ix': 0x12, 'bp': 0x14, 'sp': 0x16,
       'bw': 0x18, 'dw': 0x1A, 'cw': 0x1C, 'aw': 0x1E}
_state = os.path.join(HERE, 'revlock_state.txt')


STOCK = {29: (0xE83B, 0x0C92, 0x9D), 30: (0xE83B, 0x0CF0, 0x9E)}   # vector: stock seg, off, its xxIC register
STUB = {29: 0x1C0, 30: 0x1D0}                     # vec_stubs.asm (06C0:01C0, below the OS state at DS CE20)
SP = 0x01B0                                       # engine stack (fade path pushes): 06C0:01A0-01AF, below the stubs
FADE = {'fstate': 0x140, 'fi': 0x141, 'tog': 0x142, 'fwin': 0x144, 'ftrig': 0x146, 'tout': 0x148, 'tin': 0x158}
NLEV = 8                                          # rev_lock.asm NLEV: levels per fade (4 * NLEV ticks = 2 ms)
C_LEVEL = 100                                     # the patch's C level (base_patch): the fade's full scale


def assemble(name='rev_lock'):
    nasm = os.path.join(HERE, '..', 'tools', 'nasm-2.16.03', 'nasm.exe')
    subprocess.run([nasm, '-f', 'bin', name + '.asm', '-o', name + '.bin'], cwd=HERE, check=True)
    return open(os.path.join(HERE, name + '.bin'), 'rb').read()


def setvec(io, n, seg, off):
    """Vector n -> seg:off with its interrupt masked while the 4 bytes change (a half-written vector = crash)."""
    ic = STOCK[n][2]
    old = RL.peek(io, 0x40F0, ic, 1)[0]
    RL.sfr(io, ic, old | 0x40)
    for i, b in enumerate((off & 0xFF, off >> 8, seg & 0xFF, seg >> 8)):
        RL.poke(io, 0, 4 * n + i, b)
    RL.sfr(io, ic, old)


def stock_vectors(io):
    for n, (seg, off, _) in STOCK.items():
        setvec(io, n, seg, off)


def step(speed):
    s = 2 * (1 - speed)
    if abs(s - round(s)) > 1e-6:
        raise ValueError('speed must be a multiple of 0.5 (integer step per 2 frames)')
    return int(round(s))


def span(chunk_ms, speed):
    return int(max(2.0, abs(1 - speed)) * chunk_ms * 32)


def setreg(io, r, v):
    RL.poke16(io, 0x40E0, BANK + REG[r], v)


def fade_tables(level=C_LEVEL):
    """C level coefficients for the fades. The firmware writes level * 1024 / 100 to 2:076/07C, read there as 11-bit
    two's complement (100 -> 0x400 = -1.0), so the fade keeps that sign all the way (a sign flip would click itself).
    Raised-cosine: out = cos^2, in = sin^2, NLEV steps each, ending at 0 / full."""
    import math
    full = (level << 10) // 100
    s = full - 0x800 if full >= 0x400 else full
    code = lambda m: int(round(s * m)) & 0x7FF
    tout = [code(math.cos(math.pi / 2 * i / NLEV) ** 2) for i in range(1, NLEV + 1)]
    tin = [code(math.sin(math.pi / 2 * i / NLEV) ** 2) for i in range(1, NLEV + 1)]
    return tout, tin


def set_fade(io, on, speed, amax=None):
    """Fade block (rev_lock.asm, fixed at 06C0:0140): tables, window, trigger (amax - window), state 0 = on / 4 = off,
    written last. amax defaults to the engine's DX (bank 6)."""
    RL.poke(io, SEG, FADE['fstate'], 4)
    if amax is None:
        v = RL.peek(io, 0x40E0, BANK + REG['dw'], 2); amax = v[0] | v[1] << 8
    tout, tin = fade_tables()
    for i, (a, b) in enumerate(zip(tout, tin)):
        RL.poke16(io, SEG, FADE['tout'] + 2 * i, a); RL.poke16(io, SEG, FADE['tin'] + 2 * i, b)
    win = step(speed) * (4 * NLEV + 8)                # ticks to finish the fade-out, + margin, in address units
    RL.poke16(io, SEG, FADE['fwin'], win); RL.poke16(io, SEG, FADE['ftrig'], amax - win)
    RL.poke(io, SEG, FADE['fi'], 0); RL.poke(io, SEG, FADE['tog'], 0)
    RL.poke(io, SEG, FADE['fstate'], 0 if on else 4)


def start(io, chunk_ms=15.0, speed=-1.0, dmin_ms=1.0, fade=True):
    code = assemble()
    amin = RL.BASE + int(32 * dmin_ms); n = span(chunk_ms, speed); amax = amin + n
    assert amax <= 0xFFFE, 'chunk too long for the 1.2 s tap memory'
    RL.stop(io)
    stock_vectors(io)                            # never rewrite stub code while a vector points at it
    for i, b in enumerate(code):
        RL.poke(io, SEG, i, b)
    for i, b in enumerate(assemble('vec_stubs')):
        RL.poke(io, SEG, STUB[29] + i, b)
    for vec, off in STUB.items():
        setvec(io, vec, SEG, off)                 # 1 ms ISRs FINT first: the engine's ticks get through
    for r, v in (('vpc', 0), ('ds0', 0x8000), ('ss', SEG), ('ps', SEG), ('ds1', 0x40F0), ('sp', SP),
                 ('aw', 0x0001), ('bw', amin), ('bp', step(speed)), ('dw', amax), ('cw', n), ('ix', 0),
                 ('iy', 0x1872)):
        setreg(io, r, v)
    v = RL.peek(io, 0x40E0, BANK, 32)
    got = {r: v[o] | v[o + 1] << 8 for r, o in REG.items()}
    for r, want in (('bw', amin), ('bp', step(speed)), ('dw', amax), ('cw', n), ('ix', 0), ('iy', 0x1872)):
        if got[r] != want:
            print(f'bank 6 {r} read back {got[r]:04x}, want {want:04x}: rewriting'); setreg(io, r, want)
    set_fade(io, fade, speed, amax)
    RL.poke16(io, 0x40F0, 0x82, MD0)
    RL.sfr(io, 0x90, 0x80)                       # TMC0: start, fCLK/6, interval
    RL.sfr(io, 0x9C, 0x16)                       # TMIC0: ENCS (bank switching), priority 6 = bank 6, unmasked
    open(_state, 'w').write(f'{chunk_ms} {speed} {dmin_ms}')
    print(f'REVERSE v6 locked on (fades {"on" if fade else "off"}): speed {speed:+.1f} (step {step(speed)} per 2 frames), chunk {chunk_ms:.0f} ms '
          f'(A {amin:04x}-{amax:04x})')


def resume(io):
    """Timer 0 back on after RL.stop (patch pushes need the engine stopped). Bank 6 state and the stubs are kept."""
    RL.poke16(io, 0x40F0, 0x82, MD0)
    RL.sfr(io, 0x90, 0x80)
    RL.sfr(io, 0x9C, 0x16)


def push(rec, name='REVERSE DELAY'):
    """Engine stopped, DT1 patch push (patch screen), engine resumed. Opens its own ports (Windows MM: one opener)."""
    import revtest as RT
    io = RL.ports(); RL.stop(io); io[0].close(); io[1].close()
    RT.T.push({'recipe': rec, 'name': name}, RT.MIN, RT.MOUT, progress=lambda s: None)
    time.sleep(1.2)
    io = RL.ports()
    try:
        resume(io); status(io)
    finally:
        io[0].close(); io[1].close()


def base_patch():
    """REVERSE DELAY base the user picked by ear (2026-10-13, setting 4 of 4): OD 40, EQ band-pass (250 Hz - 2.5 kHz,
    +8 dB at 1 kHz), tap delay 10 ms C 100 fb 45 (user: less feed) cut 3 kHz, line-out filter ON with presence/treble 0. The engine moves
    the C tap; the line-out filter is the only filter after the tap (the tap's cut filter sits before the delay line)."""
    import revtest as RT
    P = RT.P
    return P.R(P.on('dirt', 'dly', 'eq', 'amp', od=True), P.OD(0, 40, 60),
               P.EQ(hi=(2500, -12), hm=(1000, +8, 1.5), lm=(200, -6, 1.0), lo=(250, -12)),
               P.TAP(10, 100, fb=45, cutf=3000), P.LINE(0, 0, 50, 55, 80))


def wet(io, coef=0x7FF):
    """DON'T: measured on the loop 2026-10-13, coef 0x7FF on 2:076/07C KILLS the wet (-6 -> -32..-40 dB). On these
    steps the coefficient acts as 11-bit two's complement: 0x400 (C level 100, setter E980:3274 = level * 1024 / 100)
    is already full scale (-1.0), 0x7FF wraps to ~0, 0xC00 == 0x400. More wet needs another route (dry level, or an
    instruction gain bit), not this coefficient."""
    raise RuntimeError('wet boost via 2:076/07C coefficients kills the wet (see docstring)')


def counters(io):
    """nfw, nwr, nbusy (the 3 words at the end of rev_lock.bin)"""
    v = RL.peek(io, SEG, len(assemble()) - 6, 6)
    return None if not v else [v[i] | v[i + 1] << 8 for i in range(0, 6, 2)]


def status(io):
    v = RL.peek(io, 0x40E0, BANK, 32)
    a = counters(io); t0 = time.time(); time.sleep(2.0); b = counters(io); dt = time.time() - t0
    if not v or not a or not b:
        print('no reply'); return
    w = [v[i] | v[i + 1] << 8 for i in range(0, 32, 2)]
    r = [((y - x) & 0xFFFF) / dt for x, y in zip(a, b)]
    f = RL.peek(io, SEG, FADE['fstate'], 1)
    print(f'bank 6: A {w[12]:04x} step {w[10]} amax {w[13]:04x} len {w[14]}   per s: address writes {r[1]:.0f} '
          f'(locked = 15991 minus fade slots) fw-skip {r[0]:.0f} gave-up {r[2]:.0f}  fade state {f[0] if f else "?"}')


def main():
    a = sys.argv[1:] or ['status']
    io = RL.ports()
    try:
        if a[0] == 'start':
            start(io, *(float(x) for x in a[1:4]))
            time.sleep(0.5); status(io)
        elif a[0] == 'speed':
            c, s_, d = (float(x) for x in open(_state).read().split())
            on = RL.peek(io, SEG, FADE['fstate'], 1)[0] != 4
            setreg(io, 'bp', step(float(a[1]))); set_fade(io, on, float(a[1]))
            open(_state, 'w').write(f'{c} {a[1]} {d}')
            print('speed', a[1], 'step', step(float(a[1])))
        elif a[0] == 'fade':
            c, s_, d = (float(x) for x in open(_state).read().split())
            set_fade(io, a[1] == 'on', s_); print('fades', a[1])
        elif a[0] == 'chunk':
            c, s, d = (float(x) for x in open(_state).read().split())
            start(io, float(a[1]), s, d)
        elif a[0] == 'patch':
            io[0].close(); io[1].close(); push(base_patch()); io = RL.ports()
        elif a[0] == 'stop':
            RL.stop(io); stock_vectors(io); print('stopped, stock vectors back')
        else:
            status(io)
    finally:
        io[0].close(); io[1].close()


if __name__ == '__main__':
    main()
