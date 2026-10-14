#!/usr/bin/env python3
"""Find the B2 MOD block's depth steps and a x2 on them (step 2 of the REVERSE work, see revtest.py).
Pitch block 100% wet; ramp 1:152 = coef 0x200 (k 0.25 -> 331 Hz from 440). If a chip-2 step is the depth that turns the
ramp into a read position, halving it gives ~385 Hz and doubling it (a x2 bit) gives ~220 Hz.
Writes use the firmware's own latches for these steps (A 0x1734, B 1, reg3 0x0B, commit 0x0C), restore = sound change.
Usage: py -3.10 depthtest.py [scan | bits <step hex> | <step hex> <instr hex> <coef hex> ...]"""
import sys, time
import mido
import dsplive as D
import revtest as RT

STEPS = {0x003: 0x51ffcf, 0x01b: 0x51fe0c}          # instruction words as the pitch path loads them (dspdiff)


def setup():
    RT.T.push({'recipe': RT.P.R(RT.P.on('mod', b2='pitch'), RT.P.PITCH(0, 200)), 'name': 'REV DEPTH'}, RT.MIN, RT.MOUT,
              progress=lambda s: None)
    time.sleep(0.8)
    D.forget()
    RT.poke(RT.STOCK, 0x200)                       # ramp k = 0.25 -> 331 Hz


def put(step, instr, coef):
    D.forget()                                      # the port is reopened: send every latch
    with mido.open_input(RT.MIN) as inp, mido.open_output(RT.MOUT) as out:
        D.poke(out, 2, step, instr=instr, coef=coef, a=0x1734, b=1, r3=0x0B, commit=12)
        D.sync(inp, out)
    time.sleep(0.3)


def main():
    a = sys.argv[1:] or ['scan']
    setup()
    RT.tone_test('ramp 0x200, depth stock (331)')
    if a[0] == 'scan':
        for step, ins in STEPS.items():
            put(step, ins, 0x400); RT.tone_test(f'2:{step:03x} coef 400 (depth? -> 385)')
            put(step, ins, 0x7FF)
        for step, ins in STEPS.items():
            put(step, ins, 0x400)
        RT.tone_test('both coef 400 (-> 385)')
    elif a[0] == 'bits':
        step = int(a[1], 16); ins = STEPS[step]
        other = [s for s in STEPS if s != step][0]
        for b in list(range(16, 24)):
            v = ins ^ (1 << b)
            put(step, v, 0x7FF); put(other, STEPS[other], 0x7FF)
            RT.tone_test(f'2:{step:03x} flip bit {b} ({v:06x}) (x2 -> 220)')
            put(step, ins, 0x7FF)
    else:
        args = a
        for i in range(0, len(args), 3):
            put(int(args[i], 16), int(args[i + 1], 16), int(args[i + 2], 16))
        RT.tone_test('custom')
    RT.restore()
    print('restored')


if __name__ == '__main__':
    main()
