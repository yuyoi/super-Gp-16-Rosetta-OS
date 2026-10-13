#!/usr/bin/env python3
"""Per-pedal DSP write segments from the digital twin: boot the OS build with the unit's RAM (out/unit_ram.bin), open the
PEDAL pick page, then for each pedal log every DSP bus write of OFF -> pedal and pedal -> OFF.
-> out/dspstate/<pedal>.json and <pedal>_off.json (lists of [offset, value]); dspstate.py replays them on the unit.
Usage: py -3.11 -I dspstate_gen.py <os_build.bin> <pedal> [pedal ...]"""
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'emu_v08.py')).read()
G = {'__file__': os.path.join(here, 'emu_v08.py'), '__name__': 'emu'}
exec(compile(src[:src.index('SCRIPT = [\n')], 'emu_v08.py', 'exec'), G)
mu, phys, ram, PK = G['mu'], G['phys'], G['ram'], G['PK']
from unicorn import UC_HOOK_MEM_WRITE, UcError
from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_IP

ram[:] = open(os.path.join(here, 'out', 'unit_ram.bin'), 'rb').read()
log = []
mu.hook_add(UC_HOOK_MEM_WRITE, lambda uc, acc, addr, size, val, ud: log.append((addr - 0x80000, val & 0xFF)),
            None, 0x80000, 0x8FFFF)
seg = {}
sys.path.insert(0, here)
import emu_tick


def mark(tag):
    def f():
        seg[tag] = len(log)
    return G['C'](f)


ctl = {'settle': False, 'done': False}


def settle():                                                       # timer ticks (deferred un-mute writes) can't run
    def f():                                                        # inside a hook (no nested emu_start): stop here,
        ctl['settle'] = True                                        # tick outside, resume
        mu.emu_stop()
    return G['C'](f)


def finish():
    ctl['done'] = True
    mu.emu_stop()


pedals = sys.argv[2:]
S = [('wait',)] * 8 + [settle(), ('wait',), ('key', 0x0F), ('wait',), ('wait',)]
for p in pedals:
    S += [mark(p + '<'), ('dial', PK.index(p) + 1)] + [('wait',)] * 4 + [settle(), ('wait',), mark(p + '>'), ('dial', 0)] + \
         [('wait',)] * 4 + [settle(), ('wait',), mark(p + '_off>')]
S += [G['C'](finish)]
G['SCRIPT'][:] = S
mu.reg_write(UC_X86_REG_CS, 0xE83B); mu.reg_write(UC_X86_REG_IP, 0x0088)
pc = phys(0xE83B, 0x0088)
while not ctl['done']:
    try:
        mu.emu_start(pc, 0xFFFFFFFF, count=900_000_000)
    except UcError as e:
        print('UC', e); break
    if not ctl['settle']:
        break
    ctl['settle'] = False
    cs, ip = mu.reg_read(UC_X86_REG_CS), mu.reg_read(UC_X86_REG_IP)
    f0, c0 = G["w16"](0xA20A), G["w16"](0xA65E)
    nt = emu_tick.settle(mu, G)
    print(f"settle: [A20A] {f0:04x} -> {G['w16'](0xA20A):04x}, [A65E] {c0:04x} -> {G['w16'](0xA65E):04x}, ticks {nt}, writes so far {len(log)}")
    mu.reg_write(UC_X86_REG_CS, cs); mu.reg_write(UC_X86_REG_IP, ip)
    pc = phys(cs, ip)
os.makedirs(os.path.join(here, 'out', 'dspstate'), exist_ok=True)
for p in pedals:
    if p + '_off>' not in seg:
        print(p, 'not reached'); continue
    on, off = log[seg[p + '<']:seg[p + '>']], log[seg[p + '>']:seg[p + '_off>']]
    json.dump(on, open(os.path.join(here, 'out', 'dspstate', p + '.json'), 'w'))
    json.dump(off, open(os.path.join(here, 'out', 'dspstate', p + '_off.json'), 'w'))
    print(f'{p}: {len(on)} writes on, {len(off)} off')
print('LCD:', G['lcd_text']())
