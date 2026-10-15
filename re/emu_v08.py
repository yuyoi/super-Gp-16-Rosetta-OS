#!/usr/bin/env python3
"""Full-firmware emulation of v0.8 PEDAL/RIG knobs (unicorn, py -3.11). Boots INTO the pedal (boot entry).
Boots the modded ROM from reset to the main loop (real init, real patch load), then drives a key/dial script.
Only keytest F00E:1CD2 is scripted; service, the DT1 setter, the sound-change service, LCD and DSP writers all run
for real. Models: LCD (HD44780 at 2000:0/1), DSP bus writes (8000:x) counted, 20-bit address wrap (DS=FA00).
Usage: py -3.11 -I emu_menu.py <rom.bin>"""
import sys, ctypes
from unicorn import *
from unicorn.x86_const import *

rom = open(sys.argv[1], 'rb').read()
assert len(rom) == 0x20000
mu = Uc(UC_ARCH_X86, UC_MODE_16)
ram = ctypes.create_string_buffer(0x10000)
mu.mem_map_ptr(0x00000, 0x10000, UC_PROT_ALL, ram)
mu.mem_map_ptr(0x100000, 0x10000, UC_PROT_ALL, ram)        # A20-style wrap: FA00:6000+ -> RAM
mu.mem_map(0x10000, 0x10000)                                 # unused RAM-ish space
mu.mem_map(0x40000, 0x1000)                                  # V25 internal RAM + SFR (IDB=0x40)
mu.mem_map(0x60000, 0x1000)                                  # output latches
mu.mem_map(0xE0000, 0x20000)
mu.mem_write(0xE0000, rom)
mu.mem_write(0x40F38, b'\xff')                               # PT: no keys held
mu.mem_write(0xE93C0 + 0x0422, b'\x33\xc0\xcb')              # E93C:0422 spin delay -> xor ax,ax; retf (speed)
mu.mem_write(0xF2FC0 + 0x183A, b'\x33\xc0\xcb')              # F2FC:183A DSP read-back self-test -> pass

lcd = {'ddram': [0x20] * 0x80, 'cgram': [0] * 64, 'addr': 0, 'cg': False}
def lcd_text():
    d = lcd['ddram']
    f = lambda a: ''.join(chr(c) if 32 <= c < 127 else '#' for c in d[a:a + 16])
    return f(0) + ' | ' + f(0x40)
def lcd_r(uc, off, size, ud):                                # never busy; reg0 = address counter, reg1 = data
    if off == 0:
        return lcd['addr'] & 0x7F
    if lcd['cg']:
        v = lcd['cgram'][lcd['addr'] & 0x3F]; lcd['addr'] = (lcd['addr'] + 1) & 0x3F
    else:
        v = lcd['ddram'][lcd['addr'] & 0x7F]; lcd['addr'] = (lcd['addr'] + 1) & 0x7F
    return v
def lcd_w(uc, off, size, val, ud):
    if off == 0:
        if val & 0x80: lcd['addr'] = val & 0x7F; lcd['cg'] = False
        elif val & 0x40: lcd['addr'] = val & 0x3F; lcd['cg'] = True
        elif val == 1: lcd['ddram'] = [0x20] * 0x80; lcd['addr'] = 0; lcd['cg'] = False
        elif val == 2: lcd['addr'] = 0; lcd['cg'] = False
    elif off == 1:
        if lcd['cg']:
            lcd['cgram'][lcd['addr'] & 0x3F] = val; lcd['addr'] = (lcd['addr'] + 1) & 0x3F
        else:
            lcd['ddram'][lcd['addr'] & 0x7F] = val; lcd['addr'] = (lcd['addr'] + 1) & 0x7F
mu.mmio_map(0x20000, 0x1000, lcd_r, None, lcd_w, None)

dsp = {'n': 0}                                               # DSP bus as plain memory (self-test reads back)
mu.mem_map(0x80000, 0x10000)
def dsp_w(uc, acc, addr, size, val, ud): dsp['n'] += 1
mu.hook_add(UC_HOOK_MEM_WRITE, dsp_w, None, 0x80000, 0x8FFFF)
def dsp_status(uc, acc, addr, size, val, ud): uc.mem_write(0x80000, b'\x00')   # status: never busy
mu.hook_add(UC_HOOK_MEM_READ, dsp_status, None, 0x80000, 0x80000)

def phys(seg, off): return (seg << 4) + off
def rd(off, n=1): return bytes(ram[(0xFA000 + off) & 0xFFFF:((0xFA000 + off) & 0xFFFF) + n])
def wr(off, data): ram[(0xFA000 + off) & 0xFFFF:((0xFA000 + off) & 0xFFFF) + len(data)] = data
def w16(off): return int.from_bytes(rd(off, 2), 'little')

KEYT = phys(0xF00E, 0x1CD2)
mu.mem_write(KEYT, b'\xcb')                                  # keytest -> retf, AX set by the hook
SERVICE = phys(0xF6A1, 0x03BC)
MAINLOOP = phys(0xF6A1, 0x006B)
MSEG = int.from_bytes(rom[0x16B3C + 3:0x16B3C + 5], 'little')   # OS segment from the SYSTEM-key hook (E0A0 / E020)
BOOT = phys(MSEG, 3)
MENU = phys(MSEG, 0)
SYSMENU = phys(0xF6A1, 0x1530)
LOADBUF = phys(0xF6A1, 0x0382)
import struct
SETTERS = {}                                                  # descriptor live setters -> param number
for p in range(71):
    o = 0x1C396 + p * 22
    off, seg = struct.unpack('<HH', rom[o + 0x12:o + 0x16])
    SETTERS.setdefault(phys(seg, off), p)

st = {'booted': False, 'step': 0, 'calls': [], 'log': [], 'svc': 0, 'live': [], 'reload': 0}
SCRIPT = []
def check(name, cond):
    st['log'].append(('PASS ' if cond else 'FAIL ') + name)

def hook(uc, addr, size, ud):
    if addr == BOOT and not st['booted']:
        st['booted'] = True
        st['log'].append(f'boot entry reached, LCD: {lcd_text()}')
    if addr == MAINLOOP and st['booted'] and 'main' not in st:
        st['main'] = True; st['calls'].append('MAINLOOP')
    if not st['booted']:
        return
    if addr == MENU: st['calls'].append('MENU')
    if addr == SYSMENU: st['calls'].append('SYSMENU'); uc.emu_stop()
    if addr == LOADBUF: st['reload'] += 1
    if addr in SETTERS:
        sp = uc.reg_read(UC_X86_REG_SP); ss = uc.reg_read(UC_X86_REG_SS)
        v = int.from_bytes(uc.mem_read(phys(ss, sp + 4), 2), 'little')
        st['live'].append((SETTERS[addr], v))
    if addr == SERVICE:
        st['svc'] += 1
        while st['step'] < len(SCRIPT) and SCRIPT[st['step']][0] != 'key':
            act = SCRIPT[st['step']]; st['step'] += 1
            if act[0] == 'dial': wr(0xA654, act[1].to_bytes(2, 'little'))
            elif act[0] == 'check': act[1]()
            elif act[0] == 'wait': break
    if addr == KEYT:
        sp = uc.reg_read(UC_X86_REG_SP); ss = uc.reg_read(UC_X86_REG_SS)
        k = int.from_bytes(uc.mem_read(phys(ss, sp + 4), 2), 'little') & 0xFF
        ax = 0
        if st['step'] < len(SCRIPT) and SCRIPT[st['step']] == ('key', k):
            ax = 1; st['step'] += 1
        uc.reg_write(UC_X86_REG_AX, ax)

mu.hook_add(UC_HOOK_CODE, hook)

def onoff(): return w16(0x9D12)
def name(): return rd(0x9D67, 16).decode('latin-1')
def ib(off): return rd(0x9D06 + off)[0]
def C(f): return ('check', f)
def lcdh(tag, *subs):
    return C(lambda: [check(f'{tag}: LCD {lcd_text()!r} has {s!r}', s in lcd_text()) for s in subs])
def mark(tag):
    def f():
        st['live'] = []; st['reload'] = 0; st['log'].append(f'-- {tag}')
    return C(f)
def eq(tag, got, want): check(f'{tag}: {got!r} == {want!r}', got == want)

import importlib.util, os
spec = importlib.util.spec_from_file_location('pedals', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pedals.py'))
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
_po = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ped_order.txt')   # v2.8: the ROM's sorted pick order
if not os.path.exists(_po):
    raise SystemExit('ped_order.txt missing -- run build_all.py (or gen_pedal_data.py) first')
PK = open(_po).read().split(); AK = list(P.AMPS)
mz = PK.index('metalzone') + 1; jcm = AK.index('jcm800') + 1
def word(*recs):
    c = d = e = 0
    for r in recs:
        c |= r.get(0x0C, 0); d |= r.get(0x0D, 0); e |= r.get(0x0E, 0)
    return (c << 14) | ((d << 7) & 0x2F80) | (e & 0x7F)

SCRIPT = [
    lcdh('first boot, pedal OFF', 'OFF', 'NO KNOBS'),
    ('key', 0x0F), lcdh('FUNCTION -> pick page', 'PEDAL MODE'),
    mark('dial -> metal zone'), ('dial', mz), ('wait',),
    lcdh('pick page', 'PEDAL MODE', 'METAL ZONE'),
    C(lambda: eq('mz on/off', onoff(), word(P.PEDALS['metalzone']))),
    C(lambda: eq('mz one full reload', st['reload'], 1)),
    C(lambda: eq('mz name', name()[:10], 'METAL ZONE')),
    C(lambda: eq('mz DST default k=17 -> dist 30+70*17/20=89 (internal 0x13)', ib(0x13), 89)),
    ('key', 0x0F), lcdh('FUNCTION -> knob page', 'LVL*HI  MID DST ', '5.0 7.5 2.0 8.5 '),
    mark('button 4 = DST up'), ('key', 4),
    lcdh('DST up', 'LVL HI  MID DST*', '5.0 7.5 2.0 9.0 '),
    C(lambda: eq('DST 9.0 -> dist 30+70*18/20=93', ib(0x13), 93)),
    C(lambda: eq('live setter p5 (DISTORTION) only, value 93', st['live'], [(5, 93)])),
    C(lambda: eq('no full reload on knob move', st['reload'], 0)),
    mark('dial follows DST -> 10'), ('dial', 20), ('wait',),
    lcdh('dial on DST', 'DST*', '10 '),
    C(lambda: eq('DST 10 -> 100', ib(0x13), 100)),
    C(lambda: eq('live p5 = 100', st['live'], [(5, 100)])),
    mark('button 6 = HI down'), ('key', 6),
    lcdh('HI down', 'HI *', '7.0 '),
    C(lambda: eq('HI 7.0 -> EQ hi lvl 12+32*14/20=34 -> internal x2 = 68', ib(0x23), 68)),
    C(lambda: eq('live p21 (HI LEVEL) = 68', st['live'], [(21, 68)])),
    C(lambda: eq('dial now on HI (k=14)', w16(0xA654), 14)),
    mark('button 8 = DST down'), ('key', 8),
    C(lambda: eq('DST 9.5 -> 30+70*19/20=96', ib(0x13), 96)),
    ('key', 0x0D), lcdh('ESC -> split', 'RIG'),
    ('key', 0x10), lcdh('DOWN -> rig, pedal knobs', 'LVL*HI  MID DST ', '5.0 7.0 2.0 9.5 '),
    ('key', 0x10), lcdh('FUNC DOWN -> page 3 pick amp', '>A:OFF'),
    mark('dial -> jcm800'), ('dial', jcm), ('wait',),
    lcdh('amp picked', ' P:METAL ZONE', '>A:JCM800'),
    C(lambda: eq('rig on/off', onoff(), word(P.PEDALS['metalzone'], P.AMPS['jcm800']))),
    C(lambda: eq('pedal knobs kept in rig (DST 9.5 -> 96)', ib(0x13), 96)),
    mark('button 1 on pick-amp page -> amp knobs, PRS up'), ('key', 1),
    lcdh('amp knob page', 'PRS*BAS MID TRB ', '6.5 4.5 6.0 5.5 '),
    C(lambda: eq('PRS 6.5 -> line-out presence 65 (internal 0x54)', ib(0x54), 65)),
    C(lambda: eq('live p66 (PRESENCE) = 65', st['live'], [(66, 65)])),
    ('key', 0x0D), ('key', 0x0D),
    ('wait',), ('wait',),
    C(lambda: check(f'patch screen after exit: {lcd_text()!r}', 'METAL ZONE' in lcd_text())),
    C(lambda: eq('exit reached the main loop', 'MAINLOOP' in st['calls'], True)),
    ('key', 0x0E), lcdh('SYSTEM -> split', 'RIG'),
    ('key', 0x0F), lcdh('pedal mode keeps knobs', 'METAL' if False else 'DST', '9.5 '),
    ('key', 0x0D), ('key', 0x0E),                             # ESC -> split, SYSTEM -> stock System menu
]

mu.reg_write(UC_X86_REG_CS, 0xE83B); mu.reg_write(UC_X86_REG_IP, 0x0088)
try:
    mu.emu_start(phys(0xE83B, 0x0088), 0xFFFFFFFF, count=300_000_000)
except UcError as e:
    st['log'].append(f'UC ERROR {e} at {mu.reg_read(UC_X86_REG_CS):04X}:{mu.reg_read(UC_X86_REG_IP):04X}')
for l in st['log']:
    print(l)
print('calls:', st['calls'], ' script steps done', st['step'], '/', len(SCRIPT), ' service calls', st['svc'])
ok = st['step'] == len(SCRIPT) and not any(l.startswith(('FAIL', 'UC')) for l in st['log']) and st['calls'][-1:] == ['SYSMENU']
print('PASS' if ok else 'NOT OK')
