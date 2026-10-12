#!/usr/bin/env python3
"""Full-firmware emulation of the PEDAL/RIG menu (unicorn, py -3.11).
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
MENU = phys(0xE0A0, 0)
SYSMENU = phys(0xF6A1, 0x1530)
EDITMENU = phys(0xF6A1, 0x0520)
DT1SET = phys(0xEE11, 0x17F4)

st = {'booted': False, 'step': 0, 'calls': [], 'log': [], 'inmenu': 0, 'svc': 0}
SCRIPT = []
def check(name, cond):
    st['log'].append(('PASS ' if cond else 'FAIL ') + name)

def hook(uc, addr, size, ud):
    if addr == MAINLOOP and not st['booted']:
        st['booted'] = True
        st['log'].append(f'booted, LCD: {lcd_text()}  DSP writes {dsp["n"]}')
        st['dsp0'] = dsp['n']
    if not st['booted']:
        return
    if addr == MENU: st['inmenu'] += 1; st['calls'].append('MENU')
    if addr == SYSMENU: st['calls'].append('SYSMENU'); uc.emu_stop()
    if addr == EDITMENU: st['calls'].append('EDITMENU'); uc.emu_stop()
    if addr == DT1SET:
        sp = uc.reg_read(UC_X86_REG_SP); ss = uc.reg_read(UC_X86_REG_SS)
        a = int.from_bytes(uc.mem_read(phys(ss, sp + 8), 2), 'little')
        v = int.from_bytes(uc.mem_read(phys(ss, sp + 10), 2), 'little')
        st.setdefault('dt1', []).append((a, v))
    if addr == SERVICE:
        st['svc'] += 1
        while st['step'] < len(SCRIPT) and SCRIPT[st['step']][0] not in ('key',):
            act = SCRIPT[st['step']]; st['step'] += 1
            if act[0] == 'dial': wr(0xA654, act[1].to_bytes(2, 'little'))
            elif act[0] == 'check': act[2](act[1])
            elif act[0] == 'stop': uc.emu_stop()
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

def mark(tag):
    def f(_):
        st['dt1'] = []; st['dsp_mark'] = dsp['n']; st['log'].append(f'-- {tag}')
    return f
def expect(tag, word, nm, line1=None, line2=None):
    def f(_):
        check(f'{tag}: on/off word {onoff():#06x} == {word:#06x}', onoff() == word)
        check(f'{tag}: name {name()!r}', name().startswith(nm))
        n = dsp['n'] - st['dsp_mark']
        check(f'{tag}: DSP writes after apply = {n}', n > 0)
        check(f'{tag}: DT1 setter calls = {len(st.get("dt1", []))}', len(st.get('dt1', [])) > 3)
        t = lcd_text()
        if line1: check(f'{tag}: LCD {t!r} has {line1!r}', line1 in t)
        if line2: check(f'{tag}: LCD {t!r} has {line2!r}', line2 in t)
    return f
def lcdhas(tag, s):
    return lambda _: check(f'{tag}: LCD {lcd_text()!r} has {s!r}', s in lcd_text())
def bytes_at(tag, off, want):
    return lambda _: check(f'{tag}: buf[{off:#x}] = {rd(0x9D06 + off)[0]} == {want}', rd(0x9D06 + off)[0] == want)

# pedal list order from pedal_data.inc: 1 tubescreamer ... ; amp order: 1 clean 2 twin 3 jcm800 ...
import importlib.util, os
spec = importlib.util.spec_from_file_location('pedals', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pedals.py'))
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
PK = list(P.PEDALS); AK = list(P.AMPS)
mz = PK.index('metalzone') + 1; ds1 = PK.index('ds1') + 1; jcm = AK.index('jcm800') + 1; dig = PK.index('digital') + 1
def word(*recs):
    c = d = e = 0
    for r in recs:
        c |= r.get(0x0C, 0); d |= r.get(0x0D, 0); e |= r.get(0x0E, 0)
    return (c << 14) | ((d << 7) & 0x2F80) | (e & 0x7F)

SCRIPT = [
    ('check', 0, lambda _: st['log'].append(f'pre-menu on/off {onoff():#06x} name {name()!r}')),
    ('key', 0x0E),                                            # SYSTEM on the play screen -> our menu
    ('check', 0, lcdhas('split', 'UP  = PEDAL')),
    ('check', 0, mark('UP -> pedal mode')),
    ('key', 0x0F),
    ('check', 0, lcdhas('pedal mode', 'PEDAL MODE')),
    ('check', 0, mark(f'dial -> metalzone ({mz})')),
    ('dial', mz),
    ('wait',),
    ('check', 0, expect('metalzone', word(P.PEDALS['metalzone']), 'METAL ZONE', 'PEDAL MODE', 'METAL ZONE')),
    ('check', 0, mark(f'dial -> digital delay ({dig})')),
    ('dial', dig),
    ('wait',),
    ('check', 0, expect('digital', word(P.PEDALS['digital']), 'DIGITAL DLY')),
    ('check', 0, bytes_at('digital tap word lo (375ms)', 0x44, (2 * 128 + 119) & 0xFF)),
    ('check', 0, bytes_at('digital tap word hi', 0x45, (2 * 128 + 119) >> 8)),
    ('key', 0x0D),                                            # ESC -> split
    ('check', 0, lcdhas('esc->split', 'DOWN= RIG')),
    ('check', 0, mark('DOWN -> rig')),
    ('key', 0x10),
    ('check', 0, lcdhas('rig', 'P:')),
    ('key', 0x0F),                                            # toggle to amp row
    ('check', 0, mark(f'amp row dial -> jcm800 ({jcm})')),
    ('dial', jcm),
    ('wait',),
    ('check', 0, expect('rig digital+jcm800', word(P.PEDALS['digital'], P.AMPS['jcm800']), 'DIGITAL DLY', 'P:DIGITAL', '>A:JCM800')),
    ('key', 0x10),                                            # toggle back to pedal row
    ('check', 0, mark(f'pedal row dial -> ds1 ({ds1})')),
    ('dial', ds1),
    ('wait',),
    ('check', 0, expect('rig ds1+jcm800', word(P.PEDALS['ds1'], P.AMPS['jcm800']), 'DS-1', '>P:DS-1', 'A:JCM800')),
    ('check', 0, bytes_at('jcm800 EQ HM level (sysex 0x27=36 -> buf 0x26 = x2)', 0x26, 72)),
    ('key', 0x0D),                                            # ESC -> split
    ('key', 0x0D),                                            # ESC -> play
    ('wait',),
    ('check', 0, lambda _: check(f'play screen after exit: LCD {lcd_text()!r}', 'DS-1' in lcd_text())),
    ('check', 0, lambda _: check(f'kept after exit: name {name()!r}', name().startswith('DS-1'))),
    ('check', 0, lambda _: check(f'kept after exit: on/off {onoff():#06x}', onoff() == word(P.PEDALS['ds1'], P.AMPS['jcm800']))),
    ('key', 0x0E), ('key', 0x0E),                             # SYSTEM, SYSTEM again -> stock System menu
]

mu.reg_write(UC_X86_REG_CS, 0xE83B); mu.reg_write(UC_X86_REG_IP, 0x0088)
try:
    mu.emu_start(phys(0xE83B, 0x0088), 0xFFFFFFFF, count=200_000_000)
except UcError as e:
    cs = mu.reg_read(UC_X86_REG_CS); ip = mu.reg_read(UC_X86_REG_IP)
    st['log'].append(f'UC ERROR {e} at {cs:04X}:{ip:04X}')
for l in st['log']:
    print(l)
print('calls:', st['calls'], ' script steps done', st['step'], '/', len(SCRIPT), ' service calls', st['svc'])
print('PASS' if st['step'] == len(SCRIPT) and not any(l.startswith(('FAIL', 'UC')) for l in st['log']) and st['calls'][-1:] == ['SYSMENU'] else 'NOT OK')
