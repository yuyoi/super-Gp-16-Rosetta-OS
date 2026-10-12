#!/usr/bin/env python3
"""Extract every constant DSP instruction rewrite (write_instr calls E83B:0569/05A8/05E7) from listing.asm
by tracking pushes, and compare with the stock boot image word at the same chip/step.
Usage: instrmap.py rom.bin listing.asm > instrmap.txt"""
import sys, re, collections

rom = open(sys.argv[1], 'rb').read()
L = open(sys.argv[2]).read().splitlines()
IMG = {0: 0x1A750, 1: 0x1ADC8, 2: 0x1B4C4}
W = {'0x569': 0, '0x5a8': 1, '0x5e7': 2}


def stock(chip, step):
    o = IMG[chip] + 3 * step
    return rom[o] | rom[o + 1] << 8 | rom[o + 2] << 16


regs, stack, fn = {}, [], '?'
rows = []
for l in L:
    m = re.match(r'; ======== FUNCTION (\S+)', l)
    if m: fn = m.group(1); regs, stack = {}, []; continue
    if l.startswith('L_') or '; ---- gap' in l:
        regs = {}; stack = []          # join point: forget what we knew
        continue
    parts = l.split(None, 3)
    if len(parts) < 4: continue
    ins = parts[3].strip()
    m = re.match(r'mov (\w\w), (0x[0-9a-f]+|\d+)$', ins)
    if m: regs[m.group(1)] = int(m.group(2), 0); continue
    m = re.match(r'xor (\w\w), (\w\w)$', ins)
    if m and m.group(1) == m.group(2): regs[m.group(1)] = 0; continue
    m = re.match(r'push (\w\w)$', ins)
    if m: stack.append(regs.get(m.group(1))); continue
    m = re.match(r'push (word ptr .*)$', ins)
    if m: stack.append(None); continue
    m = re.match(r'add sp, (0x[0-9a-f]+|\d+)$', ins)
    if m:
        n = int(m.group(1), 0) // 2
        stack = stack[:-n] if n <= len(stack) else []
        continue
    m = re.match(r'lcall 0xe83b, (0x[0-9a-f]+)$', ins)
    if m and m.group(1) in W and len(stack) >= 4:
        chip = W[m.group(1)]
        step, lo, mid, hi = stack[-1], stack[-2], stack[-3], stack[-4]
        rows.append((chip, step, lo, mid, hi, fn, parts[0]))
        continue
    if re.match(r'(mov|add|sub|and|or|shl|shr|sar|xchg|pop|inc|dec|neg|not|cwde|cdq|mul|div|idiv|imul|lcall|call|les|lds|in|xor) ', ins + ' '):
        dst = re.match(r'\w+ (\w\w)\b', ins)
        if dst: regs.pop(dst.group(1), None)
        if ins.startswith(('lcall', 'call', 'mul', 'div', 'idiv', 'imul', 'cwde', 'cdq')): regs = {}

by = collections.defaultdict(list)
for chip, step, lo, mid, hi, fn, at in rows:
    if None in (step, lo, mid, hi):
        print(f'chip{chip} step {step if step is None else hex(step)} {fn} @{at}: non-constant')
        continue
    w = hi << 16 | mid << 8 | lo
    s = stock(chip, step)
    x = w ^ s
    by[(chip, step)].append((w, fn))
    print(f'chip{chip} step {step:03x} {fn} @{at}: new {w:06x} stock {s:06x} xor {x:06x}')
