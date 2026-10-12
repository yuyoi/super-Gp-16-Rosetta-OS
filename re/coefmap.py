#!/usr/bin/env python3
"""Map every DSP write: chip, step, coefficient source, calling function. Usage: coefmap.py listing.asm > coefmap.txt"""
import sys,re
L=open(sys.argv[1]).read().splitlines()
W={'0x626':('c',0),'0x679':('c',1),'0x6cc':('c',2),'0x569':('w',0),'0x5a8':('w',1),'0x5e7':('w',2)}
fn='?'; rows=[]
for k,l in enumerate(L):
    m=re.match(r'; ======== FUNCTION (\S+)',l)
    if m: fn=m.group(1)
    m=re.search(r'lcall 0xe83b, (0x[0-9a-f]+)$',l)
    if not m or m.group(1) not in W: continue
    kind,chip=W[m.group(1)]
    # walk back over pushes: last push = step (arg1), previous = coef (arg2)
    pushes=[]; 
    for b in range(k-1,max(0,k-40),-1):
        t=L[b]
        if 'push' in t:
            src=t.split('push',1)[1].strip()
            # resolve "push ax" to previous mov ax, X
            if src in ('ax','bx','cx','dx'):
                for bb in range(b-1,max(0,b-6),-1):
                    mm=re.search(rf'mov {src}, (.+)$',L[bb])
                    if mm: src=mm.group(1).strip(); break
            pushes.append(src)
            if len(pushes)==(2 if kind=='c' else 4): break
    step=pushes[0] if pushes else '?'
    rest=pushes[1:]
    rows.append((chip,step,kind,fn,' | '.join(rest),l.split()[0]))
def key(r):
    try: return (r[0],int(r[1],0))
    except: return (r[0],99999)
for r in sorted(rows,key=key):
    print(f"chip{r[0]} step {r[1]:>8} {r[2]} {r[3]:12s} @{r[5]}  coef/word: {r[4]}")
