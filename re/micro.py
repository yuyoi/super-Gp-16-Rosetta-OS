#!/usr/bin/env python3
"""MICRO REVERSE live ear session: the B2 pitch block runs as a DSP-native reverse (1:154 phase scale x(-2) +
oscillator 1:152), 64 ms window = 32 ms reversed grains. No CPU engine. Guitar straight into the GP-16.
Usage: py -3.10 micro.py push [bal]   your REVERSE DELAY tone (OD/EQ/amp/line) + pitch block, delay off, preset A
       py -3.10 micro.py A|B|C|D|U|S  switch preset live (see PRESETS)
       py -3.10 micro.py mix <0-200>  re-push with that balance (100 = 50/50, 200 = all wet), keeps the preset"""
import json, os, sys, time
os.environ.setdefault('DSP_BUSLOG', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'dsp_buslog_pitchfull.json'))
import dsplive as D
import revload as RL
import revtest as RT

P = RT.P
ST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'micro_state.json')
PRESETS = {                      # (1:154 instr, 1:152 osc coef, what you should hear)
    'A': (0x02001f, 0x800, 'reverse grains at pitch (rate 2.0)'),
    'B': (0x02001f, 0xa00, 'reverse grains an octave down (rate 1.5)'),
    'C': (0x02001f, 0x900, 'reverse grains a fourth down (rate 1.75)'),
    'D': (0x02001f, 0x880, 'reverse grains ~2 semitones down (rate 1.875)'),
    'U': (0x02001f, 0x7ff, 'FORWARD grains an octave + fifth UP (rate -2)'),
    'S': (0x01001f, 0x000, 'stock pitch block at 0 st (no reverse) for A/B'),
}


def state():
    try:
        return json.load(open(ST))
    except (OSError, ValueError):
        return {'preset': 'A', 'bal': 100}


def apply(name):
    ins, osc, what = PRESETS[name]
    io = RL.ports()
    try:
        D.forget()
        D.poke(io[1], 1, 0x154, instr=ins, commit=0)
        D.poke(io[1], 1, 0x152, coef=osc)
        ok = D.sync(io[0], io[1])
    finally:
        io[0].close(); io[1].close()
    s = state(); s['preset'] = name; json.dump(s, open(ST, 'w'))
    print(f'{name}: {what}' + ('' if ok else '  (debug port did not answer!)'))


def push(bal):
    io = RL.ports(); RL.stop(io); io[0].close(); io[1].close()
    rec = P.R(P.on('dirt', 'eq', 'amp', 'mod', od=True, b2='pitch'), P.OD(0, 40, 60),
              P.EQ(hi=(2500, -12), hm=(1000, +8, 1.5), lm=(200, -6, 1.0), lo=(250, -12)),
              P.PITCH(0, bal), P.LINE(0, 0, 50, 55, 80))
    RT.T.push({'recipe': rec, 'name': 'MICRO REVERSE'}, RT.MIN, RT.MOUT, progress=lambda s: None)
    time.sleep(1.2)
    s = state(); s['bal'] = bal; json.dump(s, open(ST, 'w'))


if __name__ == "__main__" and sys.argv[1:2] not in (["state"], ["lofi"]):
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'push'
    if cmd == 'push':
        push(int(sys.argv[2]) if len(sys.argv) > 2 else 100); apply('A')
    elif cmd == 'mix':
        push(int(sys.argv[2])); apply(state()['preset'])
    else:
        apply(cmd.upper())


def replay_state(n):
    """in-between states of the first 'push' (user heard something perfect on the way)"""
    import revlock as RK
    io = RL.ports(); RL.stop(io); io[0].close(); io[1].close()
    if n == 1:      # REVERSE DELAY patch, CPU engine stopped: the C tap sits wherever it was
        RT.T.push({'recipe': RK.base_patch(), 'name': 'REVERSE DELAY'}, RT.MIN, RT.MOUT, progress=lambda s: None)
        io = RL.ports()
        try:
            RK.start(io, 300, -1, 1, fade=False); time.sleep(0.7); RL.stop(io)
        finally:
            io[0].close(); io[1].close()
        return 'REVERSE DELAY tone, engine stopped: plain delay at a random spot in the 300 ms chunk, feedback 45'
    rec = lambda pitch: P.R(P.on('dirt', 'eq', 'amp', 'mod', od=True, b2='pitch'), P.OD(0, 40, 60),
                            P.EQ(hi=(2500, -12), hm=(1000, +8, 1.5), lm=(200, -6, 1.0), lo=(250, -12)),
                            pitch, P.LINE(0, 0, 50, 55, 80))
    if n == 2:      # pitch block on with the leftover test settings
        RT.T.push({'recipe': rec(P.PITCH(-5, 200)), 'name': 'MICRO REVERSE'}, RT.MIN, RT.MOUT, progress=lambda s: None)
        return 'stock pitch shifter -5 semitones, all wet'
    if n == 3:      # 0 st + the reverse scale, oscillator still 0
        RT.T.push({'recipe': rec(P.PITCH(0, 100)), 'name': 'MICRO REVERSE'}, RT.MIN, RT.MOUT, progress=lambda s: None)
        time.sleep(1.2)
        io = RL.ports()
        try:
            D.forget(); D.poke(io[1], 1, 0x154, instr=0x02001f, commit=0); D.sync(io[0], io[1])
        finally:
            io[0].close(); io[1].close()
        return 'pitch block 0 st + reverse scale, no speed: static copy 50/50'


if __name__ == '__main__' and sys.argv[1:2] == ['state']:
    print(f'state {sys.argv[2]}:', replay_state(int(sys.argv[2])))


def lofi(semi, bal=200, fine=0, fb=0):
    """PITCH LOFI family: stock pitch shifter on the REVERSE DELAY tone (user's 2026-10-14 pick at -5 st, all wet)"""
    io = RL.ports(); RL.stop(io); io[0].close(); io[1].close()
    rec = P.R(P.on('dirt', 'eq', 'amp', 'mod', od=True, b2='pitch'), P.OD(0, 40, 60),
              P.EQ(hi=(2500, -12), hm=(1000, +8, 1.5), lm=(200, -6, 1.0), lo=(250, -12)),
              P.PITCH(semi, bal, fine, fb), P.LINE(0, 0, 50, 55, 80))
    RT.T.push({'recipe': rec, 'name': 'PITCH LOFI'}, RT.MIN, RT.MOUT, progress=lambda s: None)
    return f'PITCH LOFI {semi:+d} st, balance {bal}, fine {fine}, feedback {fb}'


if __name__ == '__main__' and sys.argv[1:2] == ['lofi']:
    a = [int(v) for v in sys.argv[2:]]
    print(lofi(*a))
