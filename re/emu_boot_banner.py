#!/usr/bin/env python3
"""Boot a modded ROM in the emu_v08.py harness and print the LCD right after the stock banner draw, i.e. what the
boot dragon is about to fly across. Usage: py -3.11 -I emu_boot_banner.py <rom.bin>"""
import os
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'emu_v08.py')).read()
G = {'__file__': os.path.join(here, 'emu_v08.py'), '__name__': 'emu'}
exec(compile(src[:src.index('SCRIPT = [\n')], 'emu_v08.py', 'exec'), G)
mu, rom, phys = G['mu'], G['rom'], G['phys']
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_IP
dseg = int.from_bytes(rom[0x16A30 + 3:0x16A30 + 5], 'little')        # dragon segment from the banner-draw hook
AFTER = phys(dseg, 0x19)                                             # dragon_boot.asm: add sp, 8 after the banner draw
def h(uc, addr, size, ud):
    print(f'dragon at {dseg:04X}:0000, LCD after banner: {G["lcd_text"]()!r}')
    uc.emu_stop()
mu.hook_add(UC_HOOK_CODE, h, None, AFTER, AFTER)
mu.reg_write(UC_X86_REG_CS, 0xE83B); mu.reg_write(UC_X86_REG_IP, 0x0088)
mu.emu_start(phys(0xE83B, 0x0088), 0xFFFFFFFF, count=50_000_000)
