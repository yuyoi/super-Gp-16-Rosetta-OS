#!/usr/bin/env python3
"""Per-effect DSP program maps: boot a JSW ROSETTA OS build in the full-firmware emulator, pick one pedal at a time in
PEDAL mode (so the OS turns exactly that pedal's blocks on), capture the complete DSP program after each pick, and diff
against the OFF program: which chip/steps each block changes (instruction rewrites = routing, coefficients = params).
Usage: py -3.11 -I dspdiff.py <os_build.bin> [pedal ...]     -> out/dsp_blocks.txt"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'emu_v08.py')).read()
G = {'__file__': os.path.join(here, 'emu_v08.py'), '__name__': 'emu'}
exec(compile(src[:src.index('SCRIPT = [\n')], 'emu_v08.py', 'exec'), G)
mu, phys, st, P, PK = G['mu'], G['phys'], G['st'], G['P'], G['PK']
from unicorn import UC_HOOK_MEM_WRITE, UcError
from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_IP

prog = {c: [(0, 0)] * 512 for c in range(3)}
lat = {'i': [0, 0, 0], 'c': [0, 0]}


def bus_w(uc, acc, addr, size, val, ud):
    o = addr - 0x80000
    if o in (8, 9, 10):
        lat['i'][o - 8] = val & 0xFF
    elif o in (4, 5):
        lat['c'][o - 4] = val & 0xFF
    elif 0x1000 <= o < 0x1C00:
        chip, step = (o - 0x1000) // 0x400, (o - 0x1000) % 0x400
        if step < 512:
            ins = lat['i'][0] | lat['i'][1] << 8 | lat['i'][2] << 16
            coef = lat['c'][0] | lat['c'][1] << 8
            old = prog[chip][step]
            prog[chip][step] = (ins, coef if val & 8 else old[1]) if val in (0, 8) else (old[0], coef)


mu.hook_add(UC_HOOK_MEM_WRITE, bus_w, None, 0x80000, 0x81C00)
BLOCK_PEDALS = ['dynacomp', 'tubescreamer', 'rat', 'touchwah', 'phaser', 'ge7', 'ns2', 'doubler', 'chorus', 'flanger',
                'octave', 'dimensiond', 'tremolo', 'autopan', 'digital', 'spring', 'hallplate']
pedals = sys.argv[2:] or BLOCK_PEDALS
snaps = {}


def snap(tag):
    def f():
        snaps[tag] = {c: list(prog[c]) for c in range(3)}
    return G['C'](f)


SCRIPT = [snap('OFF'), ('key', 0x0F)]                    # pick page; OFF -> pedal -> OFF for each pedal
for k in pedals:
    SCRIPT += [('dial', 0), ('wait',), ('wait',), ('wait',), snap('off_' + k),
               ('dial', PK.index(k) + 1), ('wait',), ('wait',), ('wait',), snap(k)]
SCRIPT += [('dial', 0), ('wait',), ('wait',), snap('OFF2'), ('key', 0x0D), ('key', 0x0E)]
G['SCRIPT'][:] = []
G['SCRIPT'].extend(SCRIPT)
mu.reg_write(UC_X86_REG_CS, 0xE83B); mu.reg_write(UC_X86_REG_IP, 0x0088)
try:
    mu.emu_start(phys(0xE83B, 0x0088), 0xFFFFFFFF, count=600_000_000)
except UcError as e:
    print('UC', e)

base = snaps.get('OFF')
lines = ['# per-effect DSP diffs: pedal vs the OFF state just before it (JSW ROSETTA OS PEDAL mode). chip step: instr coef  (before)']
for k in pedals:
    s, base = snaps.get(k), snaps.get('off_' + k)
    if not s or not base:
        lines.append(f'\n## {k}: no snapshot')
        continue
    ch = [(c, i) for c in range(3) for i in range(512) if s[c][i] != base[c][i]]
    ins = [(c, i) for c, i in ch if s[c][i][0] != base[c][i][0]]
    lines.append(f'\n## {k}: {len(ch)} steps changed ({len(ins)} instruction rewrites); chips '
                 + ', '.join(f'{c}:{sum(1 for x, _ in ch if x == c)}' for c in range(3)))
    for c, i in ch:
        a, b = s[c][i], base[c][i]
        lines.append(f'{c} {i:03x}: {a[0]:06x} {a[1]:04x}   ({b[0]:06x} {b[1]:04x}){"  INSTR" if a[0] != b[0] else ""}')
same = snaps.get('OFF2') == snaps.get('OFF')
lines.append(f'\nOFF again == first OFF: {same}')
out = os.path.join(here, 'out', 'dsp_blocks.txt')
open(out, 'w').write('\n'.join(lines) + '\n')
print('steps done', st['step'], '/', len(SCRIPT), '| snapshots', len(snaps), '| wrote', out)
for l in lines:
    if l.strip().startswith('## ') or l.startswith('OFF again'):
        print(l)
