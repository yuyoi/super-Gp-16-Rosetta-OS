#!/usr/bin/env python3
"""v2.7 kill check (unicorn, py -3.11): the whole emu_v10 script, plus
 - a tripwire on every range in dead_ranges.txt that the ROM has wiped (FF): executing one = FAIL,
 - the real stock System menu (no stub): all 12 pages stepped with FUNCTION, LCD logged per page, ESC + yes = exit,
 - the patch screen's EDIT key opens the OS split (stock Edit menu is gone), ESC back.
Run it on the v2.6 and v2.7 builds and compare the 'sys page' lines: they must match.
Usage: py -3.11 -I emu_v11.py <rom.bin>"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'emu_v10.py')).read()
H = {'__file__': os.path.join(here, 'emu_v10.py'), '__name__': 'emu10'}
exec(compile(src[:src.index("g['SCRIPT'][:] = []")], 'emu_v10.py', 'exec'), H)
g, st, mu, C, check, phys, SCRIPT = H['g'], H['st'], H['mu'], H['C'], H['check'], H['phys'], H['SCRIPT']
from unicorn import UC_HOOK_CODE, UcError
from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_IP
rom = g['rom']

# ---- tripwire on wiped dead code / text
wiped = []
for l in open(os.path.join(here, 'dead_ranges.txt')):
    if l.startswith('#'): continue
    a, b, _ = l.split(); a, b = int(a, 16), int(b, 16)
    if set(rom[a:b]) == {0xFF}: wiped.append((a, b))
st['trip'] = []
def trip(uc, addr, size, ud):
    st['trip'].append((uc.reg_read(UC_X86_REG_CS), uc.reg_read(UC_X86_REG_IP)))
    st['log'].append(f'FAIL tripwire: executed wiped ROM {addr - 0xE0000:05X}'); uc.emu_stop()
for a, b in wiped:
    mu.hook_add(UC_HOOK_CODE, trip, None, 0xE0000 + a, 0xE0000 + b - 1)

# ---- let the stock System menu run (emu_v08 stops at its entry); stop on a stuck script instead
SYSM = g['SYSMENU']; g['SYSMENU'] = -1
_svc = {'last': -1, 'idle': 0}
def mon(uc, addr, size, ud):
    if addr == SYSM:
        st['calls'].append('SYSMENU')
    elif addr == g['SERVICE'] and st['booted']:
        if st['step'] == _svc['last']:
            _svc['idle'] += 1
            if _svc['idle'] > 400:
                st['log'].append(f'FAIL stuck at script step {st["step"]}: {SCRIPT[st["step"]] if st["step"] < len(SCRIPT) else "end"}'
                                 f' LCD {g["lcd_text"]()!r}'); uc.emu_stop()
        else:
            _svc['last'] = st['step']; _svc['idle'] = 0
mu.hook_add(UC_HOOK_CODE, mon, None, SYSM, SYSM)
mu.hook_add(UC_HOOK_CODE, mon, None, g['SERVICE'], g['SERVICE'])

def snap(tag):
    return C(lambda: st['log'].append(f'{tag}: {g["lcd_text"]()!r}'))
def stop():
    return C(lambda: mu.emu_stop())
lcd = lambda: g['lcd_text']()

assert SCRIPT[-2:] == [('key', 0x0E), ('key', 0x0E)]          # v10 ends: patch screen -> SYSTEM (split) -> SYSTEM (stock menu)
SCRIPT += [('wait',), ('wait',), snap('sys page 0')]
for k in range(1, 12):
    SCRIPT += [('key', 0x0F), ('wait',), ('wait',), snap(f'sys page {k}')]
SCRIPT += [('key', 0x0D), ('wait',), snap('escape prompt'), ('key', 0x0D), ('wait',), ('wait',),
           C(lambda: check(f'System menu exit -> patch screen: {lcd()!r}', 'PEDALBOARD' in lcd())),
           C(lambda: st.update({'menus_before_edit': st['calls'].count('MENU')})),
           ('key', 0x0C), ('wait',), ('wait',),
           C(lambda: check(f'EDIT on the patch screen opens the OS split: {lcd()!r}',
                           st['calls'].count('MENU') == st['menus_before_edit'] + 1)),
           ('key', 0x0D), ('wait',), ('wait',),
           C(lambda: check(f'ESC -> patch screen again: {lcd()!r}', 'PEDALBOARD' in lcd())),
           C(lambda: H['eq']('no wiped byte executed', st['trip'], [])),
           stop()]
g['SCRIPT'][:] = []
g['SCRIPT'].extend(SCRIPT)
mu.reg_write(UC_X86_REG_CS, 0xE83B); mu.reg_write(UC_X86_REG_IP, 0x0088)
try:
    mu.emu_start(phys(0xE83B, 0x0088), 0xFFFFFFFF, count=800_000_000)
except UcError as e:
    st['log'].append(f'UC ERROR {e} at {mu.reg_read(UC_X86_REG_CS):04X}:{mu.reg_read(UC_X86_REG_IP):04X}')
for l in st['log']:
    if l.startswith(('FAIL', 'UC', 'sys page', 'escape', 'PASS System', 'PASS EDIT', 'PASS ESC', 'PASS no wiped')) or '-v' in sys.argv:
        print(l)
print(f'wiped ranges watched: {len(wiped)} ({sum(b - a for a, b in wiped)} B)')
print('calls:', st['calls'], ' script steps done', st['step'], '/', len(SCRIPT), ' service calls', st['svc'])
ok = st['step'] == len(SCRIPT) and not any(l.startswith(('FAIL', 'UC')) for l in st['log'])
print('PASS' if ok else 'NOT OK')
