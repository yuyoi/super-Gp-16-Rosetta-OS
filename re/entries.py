#!/usr/bin/env python3
"""Collect extra entry points for gp16dis.py: interrupt vectors (ROM 0x83B0, copied to 0:0 at boot) + cs:[bx+T] jump tables.
Usage: entries.py rom.bin listing.asm > entries.txt   (table report on stderr)"""
import sys,re
rom=open(sys.argv[1],'rb').read(); lst=open(sys.argv[2]).read().splitlines()
B=0xE0000; ents=set()
for v in range(34):
    o=0x83B0+v*4; ip=int.from_bytes(rom[o:o+2],'little'); cs=int.from_bytes(rom[o+2:o+4],'little')
    if B<=cs*16+ip<B+len(rom): ents.add((cs,ip))
for k,l in enumerate(lst):
    m=re.search(r'([0-9A-F]{4}):([0-9A-F]{4}).*jmp word ptr cs:\[bx \+ (0x[0-9a-f]+)\]',l)
    if not m: continue
    cs=int(m.group(1),16); tab=int(m.group(3),16); n=None
    for back in lst[max(0,k-8):k][::-1]:
        c=re.search(r'cmp (bx|ax|bl|al|cx|dx), (0x[0-9a-f]+|\d+)$',back)
        if c: n=int(c.group(2),0)+1; break
    if n is None: n=8
    for i in range(min(n,160)):
        o=cs*16+tab+2*i-B; ents.add((cs,int.from_bytes(rom[o:o+2],'little')))
    print(f"jt {cs:04X}:{tab:04X} n={n}",file=sys.stderr)
for cs,ip in sorted(ents): print(f"{cs:04X}:{ip:04X}")
# parameter table @ROM 0x1C396 (DS FA00:2396), 71 x 22-byte records: +14 formatter far ptr, +18 DSP setter far ptr
for i in range(71):
    r=rom[0x1C396+22*i:0x1C396+22*i+22]
    for k in (14,18):
        ip=int.from_bytes(r[k:k+2],'little'); cs=int.from_bytes(r[k+2:k+4],'little')
        if B<=cs*16+ip<B+len(rom): print(f"{cs:04X}:{ip:04X}")
