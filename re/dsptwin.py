#!/usr/bin/env python3
"""Digital twin of the unit's DSP state: boot the OS build in the full-firmware emulator with the unit's own battery RAM
(ramdump.py -> out/unit_ram.bin), so it loads the same patch and OS state, then capture every step's instruction and
coefficient -> out/dsp_live.json. dspscan.py / dspx.py restore steps from it (commit 8 = instruction + coefficient).
Usage: py -3.11 -I dsptwin.py <os_build.bin> [unit_ram.bin]"""
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'emu_v08.py')).read()
G = {'__file__': os.path.join(here, 'emu_v08.py'), '__name__': 'emu'}
exec(compile(src[:src.index('SCRIPT = [\n')], 'emu_v08.py', 'exec'), G)
mu, phys, ram = G['mu'], G['phys'], G['ram']
from unicorn import UC_HOOK_MEM_WRITE, UcError
from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_IP

unit = open(sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, 'out', 'unit_ram.bin'), 'rb').read()
assert len(unit) == 0x10000
ram[:] = unit
prog = {c: [[None, None, None]] * 512 for c in range(3)}       # [instr, coef, reg3 (None = never committed with 0x0C)]
lat = {'i': [0, 0, 0], 'c': [0, 0], 'r3': 0}


buslog = []                                                     # every DSP bus write in order (offset, value)


def bus_w(uc, acc, addr, size, val, ud):
    o = addr - 0x80000
    buslog.append((o, val & 0xFF))
    if o in (8, 9, 10):
        lat['i'][o - 8] = val & 0xFF
    elif o in (4, 5):
        lat['c'][o - 4] = val & 0xFF
    elif o == 3:
        lat['r3'] = val & 0xFF
    elif 0x1000 <= o < 0x1C00:
        chip, step = (o - 0x1000) // 0x400, (o - 0x1000) % 0x400
        if step < 512:
            ins = lat['i'][0] | lat['i'][1] << 8 | lat['i'][2] << 16
            coef = lat['c'][0] | lat['c'][1] << 8
            old = prog[chip][step]
            prog[chip][step] = [ins, coef, old[2]] if val in (0, 8) else [old[0], coef, lat['r3']]   # hw: commit 0 writes the coef too


mu.hook_add(UC_HOOK_MEM_WRITE, bus_w, None, 0x80000, 0x8FFFF)
done = {}


def snap():
    done['buf'] = G['rd'](0x9D06, 0x76)
    mu.emu_stop()


sys.path.insert(0, here)
import emu_tick


G['SCRIPT'][:] = [('wait',)] * 8 + [G['C'](snap)]
mu.reg_write(UC_X86_REG_CS, 0xE83B); mu.reg_write(UC_X86_REG_IP, 0x0088)
try:
    mu.emu_start(phys(0xE83B, 0x0088), 0xFFFFFFFF, count=300_000_000)
except UcError as e:
    print('UC', e)
if 'buf' not in done:
    sys.exit('emulator never reached the snapshot (LCD: ' + G['lcd_text']() + ')')
n = emu_tick.settle(mu, G)                                           # timer ISR stand-in: deferred un-mute writes
print('timer ticks until settled:', n, ' [A20A] =', hex(G['w16'](0xA20A)))
same = done['buf'] == unit[0x9D06 - 0x6000:0x9D06 - 0x6000 + 0x76]
print('LCD:', G['lcd_text']())
print('edit buffer matches the unit:', same)
unk = sum(1 for c in range(3) for s in prog[c] if s[1] is None)
json.dump({'note': 'chip -> 512 x [instr, coef, reg3] (reg3 None = step never committed with 0x0C)', 'buf_match': same,
           'prog': {str(c): prog[c] for c in range(3)}}, open(os.path.join(here, 'out', 'dsp_live.json'), 'w'))
json.dump(buslog, open(os.path.join(here, 'out', 'dsp_buslog.json'), 'w'))
from collections import Counter
k = Counter('step' if 0x1000 <= o < 0x1C00 else f'{o:04x}' for o, v in buslog)
print('bus writes', len(buslog), dict(sorted(k.items())))
print('wrote out/dsp_live.json; steps without a firmware-written coefficient:', unk)
