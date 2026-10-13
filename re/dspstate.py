#!/usr/bin/env python3
"""Put the unit's DSPs into a pedal's state (or back to OFF) by replaying the twin's write segment
(dspstate_gen.py -> out/dspstate/<pedal>.json) over the debug port. The CPU is not told (its RAM still says OFF), so
nothing rewrites the DSP behind our back unless the pedal has CPU-driven modulation.
The applied segment is recorded in out/dsp_state.json so dsplive.py restores steps to the pedal's values.
Usage: py -3.10 dspstate.py <pedal> | off [--port Focusrite]"""
import argparse, json, os, sys
import gp16poke as G
from dspreplay import replay

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, 'out', 'dsp_state.json')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pedal')
    ap.add_argument('--port', default='Focusrite')
    a = ap.parse_args()
    inp, out = G.open_ports(a.port)
    if a.pedal == 'off':
        if not os.path.exists(STATE):
            sys.exit('unit is already in the OFF state')
        cur = json.load(open(STATE))['pedal']
        replay(out, json.load(open(os.path.join(HERE, 'out', 'dspstate', cur + '_off.json'))), progress=False, inp=inp)
        os.remove(STATE)
        print('back to OFF from', cur)
        return
    if os.path.exists(STATE):
        sys.exit('run "dspstate.py off" first (unit is in ' + json.load(open(STATE))['pedal'] + ')')
    seg = json.load(open(os.path.join(HERE, 'out', 'dspstate', a.pedal + '.json')))
    replay(out, seg, progress=False, inp=inp)
    json.dump({'pedal': a.pedal, 'log': seg}, open(STATE, 'w'))
    G.send(out, [0x47, 4])
    print(a.pedal, 'applied,', len(seg), 'writes; debug port', 'ok' if G.wait_reply(inp, 0x44, 3.0) else 'NOT answering')


if __name__ == '__main__':
    main()
