#!/usr/bin/env python3
"""Parameter -> DSP coefficient tables straight from the firmware: boot the twin (unit RAM), then call one parameter's
live setter (descriptor far ptr at ROM 1C396 + p*22 + 0x12, one word arg = internal value) for each value and log the
DSP commits it makes. Usage: py -3.11 -I coefsweep.py <os_build.bin> <param> <v0> <v1> [step]
-> out/coefsweep/p<param>.json  {value: [[chip, step, commit, coef, a, b, r3, instr], ...]}"""
import json, os, struct, sys
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'emu_v08.py')).read()
G = {'__file__': os.path.join(here, 'emu_v08.py'), '__name__': 'emu'}
exec(compile(src[:src.index('SCRIPT = [\n')], 'emu_v08.py', 'exec'), G)
mu, phys, ram, rom = G['mu'], G['phys'], G['ram'], G['rom']
from unicorn import UC_HOOK_MEM_WRITE, UcError
from unicorn.x86_const import *

ram[:] = open(os.path.join(here, 'out', 'unit_ram.bin'), 'rb').read()
lat = {o: 0 for o in (0, 1, 2, 3, 4, 5, 8, 9, 10)}
rec = []


def bus_w(uc, acc, addr, size, val, ud):
    o = addr - 0x80000
    if o in lat:
        lat[o] = val & 0xFF
    elif 0x1000 <= o < 0x1C00 and (o - 0x1000) % 0x400 < 512:
        rec.append([(o - 0x1000) // 0x400, (o - 0x1000) % 0x400, val & 0xFF, lat[4] | lat[5] << 8,
                    lat[0] | lat[1] << 8, lat[2], lat[3], lat[8] | lat[9] << 8 | lat[10] << 16])


mu.hook_add(UC_HOOK_MEM_WRITE, bus_w, None, 0x80000, 0x8FFFF)
G['SCRIPT'][:] = [('wait',)] * 8 + [G['C'](lambda: mu.emu_stop())]
mu.reg_write(UC_X86_REG_CS, 0xE83B); mu.reg_write(UC_X86_REG_IP, 0x0088)
mu.emu_start(phys(0xE83B, 0x0088), 0xFFFFFFFF, count=300_000_000)
regs = {r: mu.reg_read(r) for r in (UC_X86_REG_SS, UC_X86_REG_SP, UC_X86_REG_DS, UC_X86_REG_ES)}

p, v0, v1 = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
stepv = int(sys.argv[5]) if len(sys.argv) > 5 else 1
off, seg = struct.unpack('<HH', rom[0x1C396 + p * 22 + 0x12:0x1C396 + p * 22 + 0x16])
STUB = 0x10000                                                     # free mapped space: push v; lcall setter; add sp,2
res = {}
from unicorn import UC_HOOK_CODE
seen = {}
def ent(uc, addr, size, ud):
    sp, ss = uc.reg_read(UC_X86_REG_SP), uc.reg_read(UC_X86_REG_SS)
    seen['arg'] = int.from_bytes(uc.mem_read(phys(ss, sp + 4), 2), 'little')
mu.hook_add(UC_HOOK_CODE, ent, None, phys(seg, off), phys(seg, off))
for v in range(v0, v1 + 1, stepv):
    code = bytes([0x68, v & 0xFF, v >> 8, 0x9A, off & 0xFF, off >> 8, seg & 0xFF, seg >> 8, 0x83, 0xC4, 0x02, 0x90])
    stub = STUB + 16 * (v % 0x1000)                                 # fresh address: unicorn caches translated code
    mu.mem_write(stub, code)
    for r, val in regs.items():
        mu.reg_write(r, val)
    mu.reg_write(UC_X86_REG_DS, 0xFA00)
    mu.reg_write(UC_X86_REG_CS, stub >> 4); mu.reg_write(UC_X86_REG_IP, 0)
    rec.clear()
    try:
        mu.emu_start(stub, stub + len(code) - 1, count=5_000_000)
    except UcError as e:
        print('UC', v, e)
    res[v] = list(rec)
    if v in (v0, v1):
        print('value', v, 'setter saw arg', seen.get('arg'))
os.makedirs(os.path.join(here, 'out', 'coefsweep'), exist_ok=True)
json.dump(res, open(os.path.join(here, 'out', 'coefsweep', f'p{p}.json'), 'w'))
steps = sorted({(c, s) for r in res.values() for c, s, *_ in r})
print(f'param {p} setter {seg:04x}:{off:04x}: {len(res)} values, steps', ' '.join(f'{c}:{s:03x}' for c, s in steps))
for v in list(res)[:3] + list(res)[-2:]:
    print(v, ' '.join(f'{c}:{s:03x}/{cm:x}={co & 0xfff:03x}' for c, s, cm, co, *_ in res[v]))
