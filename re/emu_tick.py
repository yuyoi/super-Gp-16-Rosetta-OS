#!/usr/bin/env python3
"""Timer-interrupt stand-in for the unicorn firmware emulation. The real timer ISR (E83B:0C92) bumps [A202], counts
down the RAM timers below, then calls the periodic task F2FC:3660 (expression-pedal smoothing, and the delayed
un-mute ramps behind the [A20A] pending flags: a patch change first writes some block levels as 0 and only restores
them a few ticks later). Without ticks the emulator's DSP state keeps those levels at 0."""
from unicorn.x86_const import *

TIMERS = (0x9E7C, 0x9F36, 0xA434, 0xA6BC, 0xA6C0, 0xA65C, 0x9FD4)
STUB = 0x1F000                                  # far call F2FC:3660, then nop (mapped scratch space)


def tick(mu, G, n=1):
    rd, wr = G['rd'], G['wr']
    mu.mem_write(STUB, bytes([0x9A, 0x60, 0x36, 0xFC, 0xF2, 0x90]))
    save = {r: mu.reg_read(r) for r in (UC_X86_REG_SS, UC_X86_REG_SP, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_CS,
                                         UC_X86_REG_IP, UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CX, UC_X86_REG_DX,
                                         UC_X86_REG_SI, UC_X86_REG_DI, UC_X86_REG_BP)}
    for _ in range(n):
        wr(0xA202, ((int.from_bytes(rd(0xA202, 2), 'little') + 1) & 0xFFFF).to_bytes(2, 'little'))
        for a in TIMERS:
            v = int.from_bytes(rd(a, 2), 'little')
            if v:
                wr(a, (v - 1).to_bytes(2, 'little'))
        mu.reg_write(UC_X86_REG_DS, 0xFA00)
        mu.reg_write(UC_X86_REG_CS, STUB >> 4); mu.reg_write(UC_X86_REG_IP, 0)
        mu.emu_start(STUB, STUB + 5, count=2_000_000)
    for r, v in save.items():
        mu.reg_write(r, v)


def settle(mu, G, max_ticks=4000, quiet=60):
    """tick until the pending-ramp flags [A20A] stay clear for `quiet` ticks; returns ticks used"""
    rd = G['rd']
    calm = 0
    for t in range(max_ticks):
        tick(mu, G)
        calm = calm + 1 if int.from_bytes(rd(0xA20A, 2), 'little') == 0 else 0
        if calm >= quiet:
            return t + 1
    return max_ticks
