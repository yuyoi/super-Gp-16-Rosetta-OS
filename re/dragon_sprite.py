#!/usr/bin/env python3
"""Deliberate 3-cell (15x8) side-view flying dragon sprite, hand-pixeled. One frame for shape approval."""
W,H=15,8
def grid(rows): return [[1 if ch=='#' else 0 for ch in r.ljust(W)[:W]] for r in rows]

# wings-up pose, head right, tail left
BASE=[
 "......#........",   # wing tip
 ".....#.#..##...",   # wing / horns
 "#...#...#.#.#..",   # tail tip / wing / head top
 ".##..#.######..",   # tail / wingroot / head
 "...#######..###",   # body back / neck / snout
 "....######.#...",   # belly / leg
 ".....#...#.....",   # legs
 "...............",
]
def render(g):
    for r in range(H): print('  '+''.join('#' if g[r][c] else '.' for c in range(W)))
def bytes3(g):
    out=[]
    for cell in range(3):
        out.append([sum((1<<(4-c)) for c in range(5) if g[r][cell*5+c]) for r in range(8)])
    return out
if __name__=='__main__':
    g=grid(BASE); render(g)
    from PIL import Image, ImageDraw
    sc=16; im=Image.new('RGB',(W*sc,H*sc),'#8ba61c'); d=ImageDraw.Draw(im)
    for r in range(H):
        for c in range(W):
            if g[r][c]: d.rectangle([c*sc,r*sc,c*sc+sc-2,r*sc+sc-2],fill='#20300a')
    im.save('sprite_preview.png'); print('saved sprite_preview.png')
