#!/usr/bin/env python3
"""3-cell (15x8) flying-dragon boot animation, 8 frames. Side view, head right, wings flap.
Fixed body/head/tail + a wing that sweeps up->down over the 8 frames.
Each frame -> 3 custom chars (cols 0-4,5-9,10-14). ROM data = 8 frames x 3 chars x 8 bytes = 192 B."""
W,H=15,8

def blank(): return [[0]*W for _ in range(H)]

def dragon(frame):
    g=blank()
    def on(c,r):
        if 0<=c<W and 0<=r<H: g[r][c]=1
    # --- tail (left), sweeps up-left ---
    on(0,2);on(0,3);on(1,3);on(2,4)
    # --- body (horizontal, cols 3-9 around row 4-5) ---
    for c in range(3,10): on(c,4)
    for c in range(4,9): on(c,5)
    # hind + front legs
    on(4,6);on(8,6)
    # --- neck + head (right) ---
    on(10,4);on(11,3);on(12,3);on(13,3)   # neck up into head
    on(12,2)                              # horn
    on(13,2)                              # head top
    on(14,3);on(14,4)                     # snout/jaw to the right
    # --- wing (cols 6-9) sweeps with frame ---
    phase=[ -3,-2,0,2,3,2,0,-2 ][frame%8]   # tip offset from body row4: - = up
    root_c=7; root_r=4
    tip_r=root_r+phase
    # strut from root up/down to tip
    lo,hi=sorted((root_r,tip_r))
    for r in range(lo,hi+1): on(root_c,r)
    # membrane: spread toward body front/back at the tip height
    on(root_c-1,tip_r); on(root_c+1,tip_r+ (1 if phase>0 else 0))
    if abs(phase)>=2:
        on(root_c-1,(tip_r+root_r)//2)
        on(root_c+1,(tip_r+root_r)//2)
    return g

def to_chars(g):
    chars=[]
    for cell in range(3):
        rows=[]
        for r in range(8):
            b=0
            for c in range(5):
                col=cell*5+c
                if g[r][col]: b|=1<<(4-c)
            rows.append(b)
        chars.append(rows)
    return chars

if __name__=='__main__':
    for f in range(8):
        g=dragon(f)
        print(f'--- frame {f} ---')
        for r in range(8):
            print('  '+''.join('#' if g[r][c] else '.' for c in range(W)))
