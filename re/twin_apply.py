#!/usr/bin/env python3
"""Twin of a patch that was pushed into the unit's EDIT BUFFER (DT1), not stored: dsptwin.py boots the OS build with the
unit's RAM, but the OS boots into its own pedal and overwrites the buffer. Here: boot, settle, then copy the unit's edit
buffer (FA00:9D06, 0x76 B from the dump) in, raise the sound-change request ([A43C] |= 0x20) and let the main loop's
own service apply it (F00E:0764 + F6A1:0382 -> E980:0A78), settle the timer ticks, capture every step.
Usage: py -3.11 -I twin_apply.py <os_build.bin> <unit_ram.bin> <out.json>"""
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'dsptwin.py')).read()
cut = src.index("G['SCRIPT'][:] =")
sys.argv = [sys.argv[0], sys.argv[1], sys.argv[2], sys.argv[3]]
OUT = sys.argv[3]
exec(compile(src[:cut], 'dsptwin.py', 'exec'))
from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_IP


def run(script, count=300_000_000):
    G['SCRIPT'][:] = script
    G['st']['step'] = 0
    cs, ip = mu.reg_read(UC_X86_REG_CS), mu.reg_read(UC_X86_REG_IP)
    try:
        mu.emu_start(phys(cs, ip), 0xFFFFFFFF, count=count)
    except UcError as e:
        print('UC', e)


mu.reg_write(UC_X86_REG_CS, 0xE83B); mu.reg_write(UC_X86_REG_IP, 0x0088)
G['SCRIPT'][:] = [('wait',)] * 8 + [G['C'](snap)]
try:
    mu.emu_start(phys(0xE83B, 0x0088), 0xFFFFFFFF, count=300_000_000)
except UcError as e:
    print('UC', e)
print('booted, ticks', emu_tick.settle(mu, G), 'LCD:', G['lcd_text']())
G['wr'](0x9D06, unit[0x9D06 - 0x6000:0x9D06 - 0x6000 + 0x76])
G['wr'](0x9D67, unit[0x9D67 - 0x6000:0x9D67 - 0x6000 + 16])
from unicorn.x86_const import UC_X86_REG_SS, UC_X86_REG_SP, UC_X86_REG_DS, UC_X86_REG_ES
HALT = (0x06C0, 0x01F0)


def farcall(seg, off, args):
    """Far-call seg:off with word args (memory order: first = [sp]), return to a halt address."""
    regs = {r: mu.reg_read(r) for r in (UC_X86_REG_SS, UC_X86_REG_SP, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_CS, UC_X86_REG_IP)}
    ss, sp = regs[UC_X86_REG_SS], regs[UC_X86_REG_SP] - 0x40
    frame = [HALT[1], HALT[0]] + list(args)
    sp -= 2 * len(frame)
    mu.mem_write(phys(ss, sp), b''.join(w.to_bytes(2, 'little') for w in frame))
    mu.reg_write(UC_X86_REG_SP, sp); mu.reg_write(UC_X86_REG_DS, 0xFA00); mu.reg_write(UC_X86_REG_ES, 0xFA00)
    mu.reg_write(UC_X86_REG_CS, seg); mu.reg_write(UC_X86_REG_IP, off)
    mu.emu_start(phys(seg, off), phys(*HALT), count=200_000_000)
    for r, v in regs.items():
        mu.reg_write(r, v)


n0 = len(buslog)
farcall(0xF00E, 0x0764, [0x9D06, 0xFA00, 1])
farcall(0xF6A1, 0x0382, [])
done['buf'] = G['rd'](0x9D06, 0x76)
print('apply: bus writes', len(buslog) - n0, ' ticks', emu_tick.settle(mu, G), ' [A20A]', hex(G['w16'](0xA20A)))
same = done['buf'] == unit[0x9D06 - 0x6000:0x9D06 - 0x6000 + 0x76]
print('LCD:', G['lcd_text'](), ' edit buffer matches the unit:', same)
json.dump({'buf_match': same, 'prog': {str(c): prog[c] for c in range(3)}}, open(OUT, 'w'))
print('wrote', OUT)
json.dump(buslog[n0:], open(OUT.replace('.json', '_bus.json'), 'w'))
print('apply bus log ->', OUT.replace('.json', '_bus.json'))
