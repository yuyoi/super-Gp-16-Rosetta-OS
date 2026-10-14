#!/usr/bin/env python3
"""v2.8 WIP REVERSE DELAY check (unicorn, py -3.11): the emu_v10 harness with a REV pedal script.
 - pick REVERSE DLY: the 6-knob screen (BP NT MX F T L, BPM 3 digits, note names),
 - rev_now after the sound change: borrowed memory (17 NOPs, tap write 2:092 -> 0x0100, L/R reads -> 0x0101),
   dry cancel 2:07A = -1.0, chain A level 2:076, chain B 2:07C = 0, the REV pedal's own program at those steps,
 - the engine: vectors 29/30 -> the FINT stubs, bank 6 registers (span = BPM x note), timer 0 on,
 - every sound change (LOADBUF hook) stops the engine first; ESC / other pedals leave it off; BPM / note / mix knobs
   restart it with the new values; F/T knobs go through the live setters and leave it running.
Usage: py -3.11 -I emu_v28.py <rom.bin>"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'emu_v10.py')).read()
H = {'__file__': os.path.join(here, 'emu_v10.py'), '__name__': 'emu10'}
exec(compile(src[:src.index("g['SCRIPT'][:] = []")], 'emu_v10.py', 'exec'), H)
g, st, mu, C, check, phys, eq, lcdh, rd, dmark, ped, last = (H[k] for k in
    ('g', 'st', 'mu', 'C', 'check', 'phys', 'eq', 'lcdh', 'rd', 'dmark', 'ped', 'last'))
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UcError
from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_IP

# ---- every DSP commit: (chip, step, commit, instr, coef, A) with the latches as they were
st['dsp'] = []
_L = [0] * 11
def dspc_w(uc, acc, addr, size, val, ud):
    o = addr - 0x80000
    if o <= 10:
        _L[o] = val & 0xFF
    elif 0x1000 <= o < 0x1C00:
        c, s = divmod(o - 0x1000, 0x400)
        st['dsp'].append((c, s, val & 0xFF, _L[8] | _L[9] << 8 | _L[10] << 16, _L[4] | _L[5] << 8, _L[0] | _L[1] << 8))
mu.hook_add(UC_HOOK_MEM_WRITE, dspc_w, None, 0x80000, 0x81C00)
# ---- timer 0 SFR writes (TMC0 40F0:90, TMIC0 40F0:9C)
st['t0'] = []
def t0_w(uc, acc, addr, size, val, ud):
    st['t0'].append((addr - 0x40F00, val & 0xFF))
mu.hook_add(UC_HOOK_MEM_WRITE, t0_w, None, 0x40F90, 0x40F90)
mu.hook_add(UC_HOOK_MEM_WRITE, t0_w, None, 0x40F9C, 0x40F9C)
# ---- the reverse entry points
REVP = 0xF3010
st['revnow'] = 0; st['hook'] = 0
def rn(uc, a, s, u): st['revnow'] += 1
def hk(uc, a, s, u): st['hook'] += 1
mu.hook_add(UC_HOOK_CODE, rn, None, REVP + 0, REVP + 0)
mu.hook_add(UC_HOOK_CODE, hk, None, REVP + 6, REVP + 6)
st['holdv'] = set()
def hold_w(uc, acc, addr, size, val, ud): st['holdv'].add(val & 0xFF)
mu.hook_add(UC_HOOK_MEM_WRITE, hold_w, None, 0x6E47, 0x6E47)
mu.hook_add(UC_HOOK_MEM_WRITE, hold_w, None, 0x106E47, 0x106E47)

def final(c, s):
    """last commit-0 instruction and last commit-8 coefficient of a step, from the whole log"""
    i = [x[3] for x in st['dsp'] if x[:2] == (c, s) and x[2] == 0]
    k = [x[4] for x in st['dsp'] if x[:2] == (c, s) and x[2] == 8]
    a = [x[5] for x in st['dsp'] if x[:2] == (c, s) and x[2] == 1]
    return (i[-1] if i else None, k[-1] if k else None, a[-1] if a else None)

def first0(c, s):
    i = [x[3] for x in st['dsp'] if x[:2] == (c, s) and x[2] == 0]
    return i[0] if i else None

UNB = [0x039, 0x041, 0x048, 0x05D, 0x0B6, 0x0C0, 0x0C4, 0x0CC, 0x0D0, 0x0D7, 0x0DB, 0x0EC, 0x0F9, 0x10C, 0x119,
       0x126, 0x136, 0x092, 0x07A]
def boot(x):
    b = mu.mem_read(0xE0000 + 0x1A000 + 0x14C4 + 3 * x, 3)
    return b[0] | b[1] << 8 | b[2] << 16

def bank6(r):
    off = {'vpc': 2, 'ds0': 8, 'ss': 0xA, 'ps': 0xC, 'ds1': 0xE, 'iy': 0x10, 'ix': 0x12, 'bp': 0x14, 'sp': 0x16,
           'bw': 0x18, 'dw': 0x1A, 'cw': 0x1C, 'aw': 0x1E}[r]
    return int.from_bytes(mu.mem_read(0x40EC0 + off, 2), 'little')

def vec(n):
    b = mu.mem_read(4 * n, 4)
    return int.from_bytes(b[2:4], 'little'), int.from_bytes(b[0:2], 'little')

def t0_on(): return st['t0'][-2:] == [(0x90, 0x80), (0x9C, 0x16)] if st['t0'] else False
def t0_off(): return bool(st['t0']) and st['t0'][-1] == (0x90, 0x50)

MEMW = [0x039, 0x041, 0x048, 0x05D, 0x0B6, 0x0C0, 0x0C4, 0x0CC, 0x0D0, 0x0D7, 0x0DB, 0x0EC, 0x0F9, 0x10C, 0x119,
        0x126, 0x136]
SPAN = lambda bpm, q: 2 * 31980 * 60 * q / bpm
NOTES = [0.25, 1 / 3, 0.5, 2 / 3, 0.75, 1, 1.5, 2]

def span_ok(bpm, n):
    want = int(SPAN(bpm, NOTES[n]))
    while want > 0xFFBF - 0x120:
        want //= 2
    got = bank6('cw')
    return abs(got - want) <= 2, got, want

S = {}
SCRIPT = [
    lcdh('boot (fresh): pedal OFF', 'OFF', 'NO KNOBS'),
    C(lambda: eq('engine never started at boot', st['revnow'], 0)),
    ('key', 0x0F), lcdh('pick page', 'PEDAL MODE'),
    C(lambda: st['dsp'].clear()),
    ('dial', ped('revdelay')), ('wait',), ('wait',), ('wait',),
    lcdh('REVERSE DLY picked', 'REVERSE DLY'),
    C(lambda: check(f'sound change went through the hook ({st["hook"]})', st['hook'] >= 1)),
    C(lambda: check(f'rev_now ran after it ({st["revnow"]})', st['revnow'] >= 1)),
    # the REV pedal's own program at the steps rev_blob rewrites (firmware commit-0 instructions)
    C(lambda: eq('the pedal\'s program (first commit 0 per step): C tap read, chain-B dry, C levels, L/R reads, tap write',
                 [boot(s) for s in (0x72, 0x7A, 0x76, 0x7C, 0x69, 0x6C, 0x92)],
                 [0x00FFFF, 0x01FFC0, 0x090038, 0x090038, 0x009C00, 0x01CE00, 0x0369FF])),
    C(lambda: eq('...and the 17 writes rev_blob silences are memory writes (bit 17) in it',
                 [bool(boot(s) & 0x020000) for s in MEMW], [True] * 17)),
    C(lambda: eq('borrowed memory: 17 writes -> NOP (commit 0, instr 0)', [final(2, s)[0] for s in MEMW], [0] * 17)),
    C(lambda: eq('tap write 2:092 -> 030100', final(2, 0x92)[0], 0x030100)),
    C(lambda: eq('L/R reads -> A 0x0101 (commit 1)', (final(2, 0x69)[2], final(2, 0x6C)[2]), (0x0101, 0x0101))),
    C(lambda: eq('MIX 10: 2:07A coef 0x800 (-1.0)', final(2, 0x7A)[1], 0x800)),
    C(lambda: eq('LVL 8: 2:076 coef 0x333, 2:07C 0', (final(2, 0x76)[1], final(2, 0x7C)[1]), (0x333, 0))),
    C(lambda: eq('vectors 29/30 -> F301 stubs', (vec(29)[0], vec(30)[0]), (0xF301, 0xF301))),
    C(lambda: eq('bank 6: PS F301, DS0 8000, DS1 40F0, IY 1872, BP 4, A 0120',
                 [bank6(r) for r in ('ps', 'ds0', 'ds1', 'iy', 'bp', 'bw')], [0xF301, 0x8000, 0x40F0, 0x1872, 4, 0x120])),
    C(lambda: eq('span 92 BPM 1/4 (41713) and amax = 0120 + span', (bank6('cw'), bank6('dw')), (41713, 0x120 + 41713))),
    C(lambda: check(f'timer 0 on (TMC0 80, TMIC0 16): {st["t0"][-3:]}', t0_on())),
    C(lambda: eq('ST_REVON', rd(0xCE45)[0], 1)),
    C(lambda: eq('menu-hold byte toggles (engine skips its DSP write during OS dispatch)', sorted(st['holdv']), [0, 1])),
    # knob page
    ('key', 0x0F), lcdh('REV 6-knob screen', 'BP NT MX F  T  L', ' 92  410 4  6  8'),
    C(lambda: S.update(n=st['revnow'], h=st['hook'])),
    dmark('BPM: dial -> 80 = 120 BPM'), ('dial', 80), ('wait',), ('wait',),
    lcdh('BPM 120', '120  4'),
    C(lambda: check(f'BPM knob restarted the engine (no sound change): rev_now {st["revnow"] - S["n"]}, hooks '
                    f'{st["hook"] - S["h"]}', st['revnow'] > S['n'] and st['hook'] == S['h'])),
    C(lambda: eq('span 120 BPM 1/4', span_ok(120, 5)[0], True)),
    dmark('button 2 = NOTE, VALUE up -> 1/4.'), ('key', 2), ('key', 0x0A), ('wait',), ('wait',),
    lcdh('note 4.', '120 4.'),
    C(lambda: eq('span 120 BPM 1/4. (47970)', span_ok(120, 6)[1:], (47970, 47970))),
    ('key', 0x0A), ('wait',), ('wait',), lcdh('note 2', '120  2'),
    C(lambda: eq('1/2 at 120 = 63960 fits', span_ok(120, 7)[0], True)),
    dmark('BPM 40 + 1/2: auto-halved to fit'), ('key', 1), ('dial', 0), ('wait',), ('wait',),
    lcdh('BPM 40', ' 40  2'),
    C(lambda: eq('40 BPM 1/2 -> halved twice (47970)', span_ok(40, 7)[1:], (47970, 47970))),
    ('dial', 52), ('wait',), ('wait',), lcdh('back to 92', ' 92  2'),
    dmark('button 3 = MIX, VALUE down -> 9'), ('key', 3), ('key', 0x09), ('wait',), ('wait',),
    lcdh('MIX 9', ' 9 '),
    C(lambda: eq('MIX 9: 2:07A = 2047 - 3685 = -1638 (0x99A)', final(2, 0x7A)[1], 0x99A)),
    ('key', 0x0A), ('wait',), ('wait',),
    C(lambda: eq('MIX 10 again: 0x800', final(2, 0x7A)[1], 0x800)),
    C(lambda: S.update(n=st['revnow'], live=len(st['live']))),
    dmark('button 4 = F (feedback), VALUE up -> 5'), ('key', 4), ('key', 0x0A), ('wait',), ('wait',),
    C(lambda: eq('F 5 -> fb 45', last(0x4E), 45)),
    C(lambda: check(f'F = live setter, engine untouched (rev_now +{st["revnow"] - S["n"]})',
                    len(st['live']) > S['live'] and st['revnow'] == S['n'] and t0_on())),
    dmark('button 6 = L, VALUE up -> 9'), ('key', 6), ('key', 0x0A), ('wait',), ('wait',),
    C(lambda: eq('L 9: 2:076 = 0x399', final(2, 0x76)[1], 0x399)),
    # leaving
    C(lambda: S.update(n=st['revnow'])),
    ('key', 0x0D), ('wait',), lcdh('ESC -> split', 'PEDAL'),
    C(lambda: check(f'ESC stopped the engine (TMC0 50): {st["t0"][-2:]}', t0_off())),
    C(lambda: eq('ST_REVON 0', rd(0xCE45)[0], 0)),
    C(lambda: eq('ESC: program back to boot', [final(2, x)[0] for x in UNB], [boot(x) for x in UNB])),
    ('key', 0x0F), ('wait',), ('wait',), ('wait',),
    C(lambda: check('back into PEDAL: REV pedal restarts the engine', st['revnow'] > S['n'] and t0_on())),
    ('key', 0x0F), lcdh('pick page', 'REVERSE DLY'),
    C(lambda: S.update(h=st['hook'])),
    C(lambda: S.update(k=len(st['dsp']))),
    ('dial', ped('digital')), ('wait',), ('wait',), ('wait',),
    C(lambda: eq('leaving REV: the 17 writes, tap write 2:092 and dry gain 2:07A back to the boot program (commit 0)',
                 [final(2, x)[0] for x in UNB], [boot(x) for x in UNB])),
    C(lambda: eq('ST_REVMEM 0', rd(0xCE46)[0], 0)),
    lcdh('DIGITAL DLY picked', 'DIGITAL DLY'),
    C(lambda: check(f'other pedal: hook stopped the engine and it stays off ({st["t0"][-2:]})',
                    st['hook'] > S['h'] and t0_off() and rd(0xCE45)[0] == 0)),
    ('dial', ped('revdelay')), ('wait',), ('wait',), ('wait',),
    C(lambda: check('REV again: engine on, MIX 10 / L 9 / F 5 kept', t0_on() and final(2, 0x7A)[1] == 0x800
                    and final(2, 0x76)[1] == 0x399 and last(0x4E) == 45)),
    # exit to the patch screen
    ('key', 0x0D), ('key', 0x0D), ('wait',), ('wait',),
    C(lambda: check(f'exit: engine off ({st["t0"][-2:]})', t0_off() and rd(0xCE45)[0] == 0)),
    C(lambda: eq('exit: program back to boot', [final(2, x)[0] for x in UNB], [boot(x) for x in UNB])),
    ('key', 0x0E), ('key', 0x0E),
]
g['SCRIPT'][:] = []
g['SCRIPT'].extend(SCRIPT)
mu.reg_write(UC_X86_REG_CS, 0xE83B); mu.reg_write(UC_X86_REG_IP, 0x0088)
try:
    mu.emu_start(phys(0xE83B, 0x0088), 0xFFFFFFFF, count=500_000_000)
except UcError as e:
    st['log'].append(f'UC ERROR {e} at {mu.reg_read(UC_X86_REG_CS):04X}:{mu.reg_read(UC_X86_REG_IP):04X}')
for l in st['log']:
    print(l)
print('script steps done', st['step'], '/', len(SCRIPT), ' rev_now', st['revnow'], ' hook', st['hook'])
ok = st['step'] == len(SCRIPT) and not any(l.startswith(('FAIL', 'UC')) for l in st['log'])
print('PASS' if ok else 'NOT OK')
