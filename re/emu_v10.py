#!/usr/bin/env python3
"""Full-firmware emulation of JSW ROSETTA OS v1 (unicorn, py -3.11). Reuses the emu_v08.py harness (boot, LCD, DSP,
scripted keytest, live-setter + reload counters) and adds: a DT1-setter call log, the LCD cursor state, and a watch on
the new battery-RAM areas (knob stores + board memories, DS B000-B6FF) that fails if anything but the OS writes there.
Covers: macro knobs, the 6-knob (Metal Zone) and 5-knob screens, switches, mode buttons (Dimension C), filter-matrix
style overrides, the expression pedal per pedal, RIG with a new amp, BOARD grabs (gate), save/load board memories.
Usage: py -3.11 -I emu_v10.py <rom.bin>"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'emu_v08.py')).read()
cut = src.index('SCRIPT = [\n')
G = {'__file__': os.path.join(here, 'emu_v08.py'), '__name__': 'emu'}
exec(compile(src[:cut], 'emu_v08.py', 'exec'), G)
g = G
P, PK, AK = g['P'], g['PK'], g['AK']
C, lcdh, mark, eq, ib, w16, onoff, name, check, st, rd, phys, mu = (g[k] for k in
    ('C', 'lcdh', 'mark', 'eq', 'ib', 'w16', 'onoff', 'name', 'check', 'st', 'rd', 'phys', 'mu'))
MSEG = g['MSEG']
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UcError
from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_IP, UC_X86_REG_SP, UC_X86_REG_SS

# ---- DT1 setter log: (sysex addr, value) per call
DT1 = phys(0xEE11, 0x17F4)
st['dt1'] = []
def dt1_hook(uc, addr, size, ud):
    sp = uc.reg_read(UC_X86_REG_SP); ss = uc.reg_read(UC_X86_REG_SS)
    a = int.from_bytes(uc.mem_read(phys(ss, sp + 8), 2), 'little')
    v = int.from_bytes(uc.mem_read(phys(ss, sp + 10), 2), 'little')
    st['dt1'].append((a, v))
mu.hook_add(UC_HOOK_CODE, dt1_hook, None, DT1, DT1)

# ---- watch DS B000-B6FF (RAM 5000-56FF): only the OS may write there
st['foreign'] = set()
def ram_w(uc, acc, addr, size, val, ud):
    cs = uc.reg_read(UC_X86_REG_CS)
    if cs != MSEG:
        st['foreign'].add((cs, uc.reg_read(UC_X86_REG_IP), addr))
mu.hook_add(UC_HOOK_MEM_WRITE, ram_w, None, 0x5000, 0x56FF)
mu.hook_add(UC_HOOK_MEM_WRITE, ram_w, None, 0x105000, 0x1056FF)

def last(a):
    v = [x for b, x in st['dt1'] if b == a]
    return v[-1] if v else None
def dmark(tag):
    def f():
        st['live'] = []; st['reload'] = 0; st['dt1'] = []; st['log'].append(f'-- {tag}')
    return C(f)
def curon(): return bool(rd(0x9E82)[0] & 2)
def row2(): return g['lcd_text']().split(' | ')[1]

ped = lambda k: PK.index(k) + 1
amp = lambda k: AK.index(k) + 1
B = {}
SCRIPT = [
    lcdh('boot (fresh): pedal OFF', 'OFF', 'NO KNOBS'),
    C(lambda: eq('cursor off at boot', curon(), False)),
    # ---- macro knob (Big Muff SUS = drive + comp sustain)
    ('key', 0x0F), lcdh('pick page', 'PEDAL MODE'),
    ('dial', ped('bigmuff')), ('wait',), lcdh('big muff picked', 'BIG MUFF'),
    ('key', 0x0F), lcdh('big muff knobs', 'VOL*TON SUS ', '5.0 5.0 7.5 '),
    dmark('SUS up (macro)'), ('key', 3),
    lcdh('SUS 8.0', 'SUS*', '8.0 '),
    C(lambda: eq('SUS 8.0 -> drive 45+55*16/20 = 89, comp sus 30+55*16/20 = 74', (last(0x14), last(0x11)), (89, 74))),
    C(lambda: eq('live setters: p5 drive + p2 sustain, no reload', (sorted(p for p, v in st['live']), st['reload']), ([2, 5], 0))),
    # ---- 6-knob screen (Metal Zone)
    ('key', 0x0F), ('dial', ped('metalzone')), ('wait',), lcdh('MZ picked', 'METAL ZONE'),
    ('key', 0x0F), lcdh('MZ 6-knob screen', 'LO HM LM H  G  L', ' 6  7  2 6  9  5'),
    C(lambda: eq('underline cursor on (knob LO)', curon(), True)),
    C(lambda: eq('LCD cursor under LO value (row 2, col 1)', g['lcd']['addr'], 0x41)),
    dmark('button 5 = pick H'), ('key', 5),
    C(lambda: eq('active knob = H (3)', rd(0xCF39)[0], 3)),
    C(lambda: eq('cursor under H value (col 9)', g['lcd']['addr'], 0x49)),
    C(lambda: eq('picking does not change sound', st['dt1'], [])),
    dmark('button 4 = up'), ('key', 4),
    lcdh('H 7', ' 6  7  2 7  9  5'),
    C(lambda: eq('H 7 -> EQ HI level 48*7/10 = 33', last(0x24), 33)),
    C(lambda: eq('live p21 (HI LEVEL)', [p for p, v in st['live']], [21])),
    dmark('dial -> 10'), ('dial', 10), ('wait',),
    lcdh('H 10', ' 6  7  210  9  5'),
    C(lambda: eq('H 10 -> 48', last(0x24), 48)),
    ('key', 8), C(lambda: eq('button 8 = down -> 43', last(0x24), 43)),
    # ---- expression pedal per pedal (Whammy)
    ('key', 0x0F), ('dial', ped('whammy')), ('wait',), lcdh('whammy', 'WHAMMY'),
    C(lambda: eq('cursor off on the pick page', curon(), False)),
    C(lambda: eq('exp pedal assigned to PS CHROM (#45)', rd(0x9D5F)[0], 45)),
    C(lambda: st.update({'expoff': None})),
    ('dial', ped('bigmuff')), ('wait',),
    C(lambda: check(f'exp pedal released by Big Muff (assign {rd(0x9D5F)[0]})', rd(0x9D5F)[0] != 45)),
    C(lambda: eq('PEDAL mode default chain WAH>DIRT', list(rd(0x9D06, 5)), [0, 2, 1, 3, 4])),
    ('dial', ped('funeral')), ('wait',), lcdh('funeral', 'FUNERAL'),
    C(lambda: eq('Funeral brings its own path DIRT>WAH>COMP', list(rd(0x9D06, 5)), [1, 2, 0, 3, 4])),
    C(lambda: eq('Funeral: comp, dist, wah, EQ, gate on', onoff() & 0x7F, 0x37)),
    # ---- Dimension C mode buttons
    ('dial', ped('dimc')), ('wait',), ('wait',), ('key', 0x0F),
    lcdh('Dim C screen', 'DIMENSION C', ' 1  [2]  3   4  '),
    dmark('mode 3'), ('key', 3),
    lcdh('mode 3 lit', ' 1   2  [3]  4  '),
    C(lambda: eq('mode 3: cho level 60, delay level 30, depth 45', (last(0x36), last(0x32), last(0x35)), (60, 30, 45))),
    dmark('mode 3 again = off'), ('key', 3),
    lcdh('none lit', ' 1   2   3   4  '),
    C(lambda: eq('off: cho level 0, delay level 0', (last(0x36), last(0x32)), (0, 0))),
    dmark('button 6 does nothing'), ('key', 6), C(lambda: eq('no writes', st['dt1'], [])),
    # ---- switch (Small Clone depth)
    ('key', 0x0F), ('dial', ped('smallclone')), ('wait',), ('wait',), ('key', 0x0F),
    lcdh('small clone', 'RAT*DEP ', '3.0 LO  '),
    dmark('DEP up -> HI'), ('key', 2),
    lcdh('DEP HI', 'HI  '),
    C(lambda: eq('deep: depth 85, level 65', (last(0x35), last(0x36)), (85, 65))),
    # ---- override knob (Electric Mistress filter matrix)
    ('key', 0x0F), ('dial', ped('mistress')), ('wait',), ('wait',), ('key', 0x0F),
    lcdh('mistress', 'RAT*RNG COL FM ', '1.5 6.0 4.5 OFF '),
    dmark('FM on'), ('key', 4),
    lcdh('FM ON', 'ON  '),
    C(lambda: eq('FM on: rate 0, depth 0 (written last)', (last(0x37), last(0x38)), (0, 0))),
    dmark('RNG up while FM on'), ('key', 2),
    C(lambda: eq('RNG re-applies FM: depth stays 0', last(0x38), 0)),
    dmark('FM off'), ('key', 8),
    C(lambda: eq('FM off: rate back 15, depth back 65 (RNG 6.5)', (last(0x37), last(0x38)), (15, 65))),
    # ---- RIG with a new amp
    ('key', 0x0D), lcdh('ESC -> split', 'RIG'),
    C(lambda: eq('cursor off at split', curon(), False)),
    ('key', 0x10), ('key', 0x10), lcdh('rig pick amp', '>A:OFF'),
    ('dial', amp('jc120')), ('wait',), lcdh('JC-120 picked', ' P:ELEC MISTRESS', '>A:JC-120'),
    dmark('amp VOL up'), ('key', 1),
    lcdh('amp knobs', 'VOL*TRB MID BAS '),
    C(lambda: eq('VOL 7.0 -> master 40+60*14/20 = 82', last(0x5B), 82)),
    # ---- BOARD: fuzz factory grabs the gate, wah owns the exp pedal before whammy
    ('key', 0x0D), ('key', 0x0C), lcdh('board A1', 'A1 COMP', 'OUT'),
    ('key', 0x0F), ('key', 0x09), ('key', 0x09), ('key', 0x09), ('key', 0x09),
    lcdh('A2 = fuzz factory (BANK x4 from OUT)', 'A2 DIRT', 'FUZZ FACTORY'),
    C(lambda: eq('fuzz factory owns the gate block', rd(0xCE20 + 5)[0], 1)),
    ('key', 1), lcdh('5-knob screen', 'VL GT CP DR SB  '),
    C(lambda: eq('cursor on in board knob view', curon(), True)),
    ('key', 0x0F), ('key', 0x0A), ('key', 0x0A), lcdh('A3 = crybaby', 'A3 WAH/FILTER', 'CRYBABY WAH'),
    C(lambda: eq('cursor off on the slot page', curon(), False)),
    ('key', 0x0F), ('key', 0x0F), ('key', 0x0F), ('key', 0x0F), ('key', 0x0F),
    ('key', 0x09), ('key', 0x09), ('key', 0x09), lcdh('B2 = whammy', 'B2 MOD', 'WHAMMY'),
    C(lambda: eq('exp pedal stays with the wah (first in chain, #12 PICK CUTOFF)', rd(0x9D5F)[0], 12)),
    C(lambda: B.update({'brd': list(rd(0xCF20, 15))})),
    # ---- save + load a board memory
    ('key', 0x0B), lcdh('save prompt', 'SAVE BOARD TO', '1-8   ESC=CANCEL'),
    ('key', 3), lcdh('saved to 3 -> memory page', 'BOARD MEMORY', ' - ->3 - - - - -'),
    ('key', 0x0F), ('key', 0x0F), ('key', 0x09), lcdh('A2 changed', 'A2 DIRT', 'OD-1'),
    C(lambda: check('board differs now', list(rd(0xCF20, 15)) != B['brd'])),
    ('key', 0x10), ('key', 0x10), lcdh('back to memory page', 'BOARD MEMORY'),
    ('key', 1), C(lambda: check('empty memory 1: board unchanged', list(rd(0xCF20, 15)) != B['brd'])),
    dmark('load 3'), ('key', 3),
    C(lambda: eq('memory 3 restores slots, order, out', list(rd(0xCF20, 15)), B['brd'])),
    C(lambda: eq('fuzz factory knobs restored and applied (one full reload)', st['reload'], 1)),
    C(lambda: eq('exp back on the wah', rd(0x9D5F)[0], 12)),
    ('key', 0x0B), ('key', 0x0D), lcdh('save prompt, ESC cancels', 'BOARD MEMORY'),
    ('key', 0x10), ('key', 0x10), lcdh('ORDER page', '>A:WAH>DIRT'),
    ('key', 5), lcdh('A preset -1 wraps to the 4th', '>A:DIRT>WAH>COMP'),
    C(lambda: eq('board chain DIRT>WAH>COMP', list(rd(0x9D06, 5)), [1, 2, 0, 3, 4])),
    ('key', 1), lcdh('A preset +1 wraps back', '>A:WAH>DIRT'),
    # ---- exit
    ('key', 0x0D), ('key', 0x0D), ('wait',), ('wait',),
    C(lambda: check(f'patch screen after exit: {g["lcd_text"]()!r}', 'PEDALBOARD' in g['lcd_text']())),
    C(lambda: eq('cursor off on the patch screen', curon(), False)),
    C(lambda: eq('nothing but the OS wrote DS B000-B6FF', sorted(st['foreign'])[:5], [])),
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
print('calls:', st['calls'], ' script steps done', st['step'], '/', len(SCRIPT), ' service calls', st['svc'])
ok = st['step'] == len(SCRIPT) and not any(l.startswith(('FAIL', 'UC')) for l in st['log']) and st['calls'][-1:] == ['SYSMENU']
print('PASS' if ok else 'NOT OK')
