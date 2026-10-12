#!/usr/bin/env python3
"""Full-firmware emulation of v0.9 BOARD mode (unicorn, py -3.11). Reuses the emu_v08.py harness (boot, LCD, DSP,
scripted keytest, live-setter + reload counters) and runs a board script.
Usage: py -3.11 -I emu_v09.py <rom.bin>"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'emu_v08.py')).read()
cut = src.index('SCRIPT = [\n')
G = {'__file__': os.path.join(here, 'emu_v08.py'), '__name__': 'emu'}
exec(compile(src[:cut], 'emu_v08.py', 'exec'), G)
g = G
P, PK, AK = g['P'], g['PK'], g['AK']
C, lcdh, mark, eq, ib, w16, onoff, name, check, st, rd = (g[k] for k in
    ('C', 'lcdh', 'mark', 'eq', 'ib', 'w16', 'onoff', 'name', 'check', 'st', 'rd'))

spec = __import__('importlib.util').util.spec_from_file_location('gen', os.path.join(here, 'gen_pedal_data.py'))
GEN = __import__('importlib.util').util.module_from_spec(spec); spec.loader.exec_module(GEN)


def model(board):
    """board: {slot: key} -> (on/off word, OWN list) by the same rules as the asm."""
    own = [s if s in board else 0xFF for s in range(12)]
    for s in range(12):
        if s in board:
            k = board[s]
            rec = P.AMPS[k] if s == 11 else P.PEDALS[k]
            ex = GEN.extras(rec, s)
            for b in range(12):
                if ex >> b & 1 and own[b] == 0xFF:
                    own[b] = s
    on = 0
    for b in range(12):
        if own[b] != 0xFF:
            on |= 1 << b
    c0c = 0
    for s, k in board.items():
        rec = P.AMPS[k] if s == 11 else P.PEDALS[k]
        if own[1] == s and rec.get(0x0D, 0) & 0x40: on |= 0x2000
        if own[7] == s: c0c = rec.get(0x0C, 0)
    return on | c0c << 14, own


def boardcheck(tag, board):
    def f():
        word, own = model(board)
        eq(f'{tag}: on/off word', hex(onoff()), hex(word))
        eq(f'{tag}: owners', list(rd(0xCE20, 12)), own)
    return C(f)


ped = lambda k: PK.index(k) + 1
B = {}
SCRIPT = [
    lcdh('boot (fresh): pedal OFF', 'OFF', 'NO KNOBS'),
    ('key', 0x0D), lcdh('ESC -> split', 'UP:PEDAL DN:RIG', 'EDIT:BOARD'),
    ('key', 0x0C), lcdh('EDIT -> board slot A1', 'A1 COMP', 'OUT'),
    C(lambda: eq('order A default WAH>DIRT (pos 0-4)', list(rd(0x9D06, 5)), [0, 2, 1, 3, 4])),
    ('key', 0x0F), lcdh('FUNC -> A2', 'A2 DIRT', 'OUT'),
    ('key', 0x0A), lcdh('GROUP -> first dirt', 'A2 DIRT', 'TUBE SCREAMER'),
    C(lambda: B.update({1: 'tubescreamer'})), boardcheck('TS', B),
    C(lambda: eq('board name', name(), 'PEDALBOARD      ')),
    ('key', 0x0A), lcdh('GROUP -> RAT', 'RAT'), C(lambda: B.update({1: 'rat'})), boardcheck('RAT (DIST, no OD bit)', B),
    ('key', 0x09), lcdh('BANK -> TS', 'TUBE SCREAMER'), C(lambda: B.update({1: 'tubescreamer'})), boardcheck('TS again', B),
    mark('TS knob 1 up'), ('key', 1),
    lcdh('TS knobs', 'DRV*TON LVL', '5.0 '),
    C(lambda: eq('DRV 5.0 -> od drive 5+85*10/20 = 47 (internal 0x16)', ib(0x16), 47)),
    C(lambda: eq('live p8 = 47, no reload', (st['live'], st['reload']), ([(8, 47)], 0))),
    ('key', 0x0F), ('key', 0x0F), ('key', 0x0F), lcdh('A5 EQ grabbed by TS', 'A5 EQ', '<TUBE SCREAMER>'),
    ('key', 0x0A), C(lambda: eq('pick refused on grabbed slot', rd(0xCF20 + 4)[0], 0)),
    lcdh('still grabbed', '<TUBE SCREAMER>'),
    *[('key', 0x0F)] * 7, lcdh('B6 amp slot', 'B6 AMP/CAB', 'OUT'),
    ('key', 0x0A), lcdh('GROUP -> clean amp', 'CLEAN'), C(lambda: B.update({11: 'clean'})), boardcheck('TS + clean', B),
    C(lambda: eq('EQ stays the TS voicing (HI f 3.5 kHz = 40, internal 0x22)', ib(0x22), P.hz_hi(3500))),
    mark('amp VOL up'), ('key', 1),
    lcdh('amp knobs', 'VOL*TRB BAS'),
    C(lambda: eq('live master p70', [p for p, v in st['live']], [70])),
    ('key', 0x0F), lcdh('ORDER page', '>A:WAH>DIRT', ' B:STOCK'),
    ('key', 1), lcdh('A preset +1', '>A:DIRT>WAH'),
    C(lambda: eq('order A stock', list(rd(0x9D06, 5)), [0, 1, 2, 3, 4])),
    ('key', 2), lcdh('B preset +1', ' A:DIRT>WAH', '>B:TREM LAST'),
    C(lambda: eq('order B trem last (pos 6-10)', list(rd(0x9D06 + 6, 5)), [6, 7, 9, 10, 8])),
    ('key', 0x0F), lcdh('OUT page', 'OUT A/B/Y BOX'),
    C(lambda: st.update({'out0': rd(0xCF2E)[0]})),
    ('key', 1), C(lambda: eq('OUT +1 -> output channel byte', ib(0x60), (st['out0'] + 1) % 3)),
    *[('key', 0x10)] * 6, lcdh('back to B2 MOD', 'B2 MOD', 'OUT'),
    *[('key', 0x09)] * 6, lcdh('BANK x6 from OUT -> Leslie (v1 list ends with 5 new mods)', 'LESLIE'),
    C(lambda: B.update({7: 'leslie'})), boardcheck('Leslie grabs trem', B),
    ('key', 0x0F), lcdh('B3 shows the grab', 'B3 TREM/PAN', '<LESLIE>'),
    ('key', 0x10), ('key', 0x09), ('key', 0x09), ('key', 0x09), ('key', 0x09),
    lcdh('BANK x4 -> first mod (pitch)', 'PITCH/OCTAVE'),
    C(lambda: B.update({7: 'octave'})), boardcheck('pitch frees trem', B),
    ('key', 1), lcdh('signed INT knob (default -12, +1)', 'INT*MIX FIN', '-11 '),
    C(lambda: eq('pitch chromatic sysex 1 -> internal 0x3B = 1*5', ib(0x3B), 5)),
    ('key', 0x0D), ('key', 0x0D), ('wait',), ('wait',),
    C(lambda: check(f'patch screen after exit: {g["lcd_text"]()!r}', 'PEDALBOARD' in g['lcd_text']())),
    ('key', 0x0E), ('key', 0x0E),
]
g['SCRIPT'][:] = []
g['SCRIPT'].extend(SCRIPT)
mu = g['mu']
from unicorn import UcError
from unicorn.x86_const import UC_X86_REG_CS, UC_X86_REG_IP
mu.reg_write(UC_X86_REG_CS, 0xE83B); mu.reg_write(UC_X86_REG_IP, 0x0088)
try:
    mu.emu_start(g['phys'](0xE83B, 0x0088), 0xFFFFFFFF, count=400_000_000)
except UcError as e:
    st['log'].append(f'UC ERROR {e} at {mu.reg_read(UC_X86_REG_CS):04X}:{mu.reg_read(UC_X86_REG_IP):04X}')
for l in st['log']:
    print(l)
print('calls:', st['calls'], ' script steps done', st['step'], '/', len(SCRIPT), ' service calls', st['svc'])
ok = st['step'] == len(SCRIPT) and not any(l.startswith(('FAIL', 'UC')) for l in st['log']) and st['calls'][-1:] == ['SYSMENU']
print('PASS' if ok else 'NOT OK')
