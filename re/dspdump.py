#!/usr/bin/env python3
"""Capture the GP-16's complete live DSP program from full-firmware emulation: every step of the 3 TC23SC260 chips
(24-bit instruction + 16-bit coefficient + extra reg3), as the real firmware leaves it after boot / a patch load, and
which CPU routine wrote each coefficient (-> which parameter, via out/coefmap.txt).
Bus model (GP16_RE.md): 8000:8/9/A instruction latch, 8000:4/5 coefficient latch, 8000:3 reg3, commit = write v to
8000:1000 + chip*0x400 + step (v=0 instr only, 8 instr+coef, 0x0C coef + reg3).
Usage: py -3.11 -I dspdump.py <rom.bin> [out.txt] [--sysex addr=val ...]   (patch edits applied through the DT1 setter)"""
import os, sys, re
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'emu_v08.py')).read()
G = {'__file__': os.path.join(here, 'emu_v08.py'), '__name__': 'emu'}
exec(compile(src[:src.index('SCRIPT = [\n')], 'emu_v08.py', 'exec'), G)
mu, phys, st = G['mu'], G['phys'], G['st']
from unicorn import UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_IP, UC_X86_REG_SS, UC_X86_REG_SP

prog = {c: [None] * 512 for c in range(3)}      # (instr, coef, reg3, writer cs:ip of the commit)
lat = {'i': [0, 0, 0], 'c': [0, 0], 'r3': 0}
callers = []


def bus_w(uc, acc, addr, size, val, ud):
    o = addr - 0x80000
    if o in (8, 9, 10):
        lat['i'][o - 8] = val & 0xFF
    elif o in (4, 5):
        lat['c'][o - 4] = val & 0xFF
    elif o == 3:
        lat['r3'] = val & 0xFF
    elif 0x1000 <= o < 0x1C00:
        chip, step = (o - 0x1000) // 0x400, (o - 0x1000) % 0x400
        if step >= 512:
            return
        old = prog[chip][step] or (0, 0, 0, '')
        ins = lat['i'][0] | lat['i'][1] << 8 | lat['i'][2] << 16
        coef = lat['c'][0] | lat['c'][1] << 8
        who = callers[-1] if callers else '?'
        if val == 0:
            prog[chip][step] = (ins, old[1], old[2], old[3])
        elif val == 8:
            prog[chip][step] = (ins, coef, old[2], who)
        else:
            prog[chip][step] = (old[0], coef, lat['r3'], who)


mu.hook_add(UC_HOOK_MEM_WRITE, bus_w, None, 0x80000, 0x81C00)
# who commits: remember the far caller of the set_coef / write routines (return address on the stack)
SETC = [phys(0xE83B, o) for o in (0x0626, 0x0679, 0x06CC, 0x08BF, 0x0569, 0x05A8, 0x05E7)]


def enter(uc, addr, size, ud):
    sp, ss = uc.reg_read(UC_X86_REG_SP), uc.reg_read(UC_X86_REG_SS)
    ip = int.from_bytes(uc.mem_read(phys(ss, sp), 2), 'little')
    cs = int.from_bytes(uc.mem_read(phys(ss, sp + 2), 2), 'little')
    callers.append(f'{cs:04X}:{ip:04X}')


for a in SETC:
    mu.hook_add(UC_HOOK_CODE, enter, None, a, a)
MAIN = G['MAINLOOP']
state = {'n': 0}


def stop(uc, addr, size, ud):
    state['n'] += 1
    if state['n'] > 3:                          # a few main-loop passes: boot patch fully applied
        uc.emu_stop()


mu.hook_add(UC_HOOK_CODE, stop, None, MAIN, MAIN)
mu.reg_write(UC_X86_REG_CS, 0xE83B); mu.reg_write(UC_X86_REG_IP, 0x0088)
mu.emu_start(phys(0xE83B, 0x0088), 0xFFFFFFFF, count=200_000_000)

# coefficient writers -> parameter names (out/coefmap.txt lines: "chipN step 0xS c CS:IP ...")
param = {}
cm = os.path.join(here, 'out', 'coefmap.txt')
if os.path.exists(cm):
    for line in open(cm, encoding='utf-8', errors='replace'):
        m = re.match(r'chip(\d) step\s+0x([0-9a-f]+) c (\w{4}:\w{4})', line)
        if m:
            param.setdefault((int(m.group(1)), int(m.group(2), 16)), set()).add(m.group(3))
out = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else os.path.join(here, 'out', 'dsp_program.txt')
with open(out, 'w') as f:
    f.write('# GP-16 live DSP program after boot (full-firmware emulation). chip step: instr coef reg3 | writer\n')
    for c in range(3):
        f.write(f'\n## chip {c}\n')
        for s in range(512):
            e = prog[c][s]
            if e is None:
                f.write(f'{c} {s:03x}: ------ ----\n')
                continue
            ins, coef, r3, who = e
            tag = ','.join(sorted(param.get((c, s), ()))) if (c, s) in param else ''
            f.write(f'{c} {s:03x}: {ins:06x} {coef:04x} {r3:02x}  {who:9s} {tag}\n')
print('wrote', out, ' steps with instructions:', sum(1 for c in range(3) for e in prog[c] if e))
