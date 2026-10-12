#!/usr/bin/env python3
"""Flying-dragon custom-char frames for the GP-16 boot screen.
Replaces the 7 built-in icons (chars 1-7) at ROM 0x1CA16 (8 bytes each, 5x8 CGRAM).
Each frame is a side-view winged dragon; the set reads as a wing-flap when the firmware cycles chars.
Edit the ASCII, run to preview, then build_mod bakes the bytes (v0.5)."""

FRAMES = {
 # char: 8 rows of 5 ('#'/'.'), top to bottom
 1: ["..#..",   # wings UP, tail low
     ".#.#.",
     "#.#..",
     ".###>",   # '>' = head/snout to the right (drawn as ..##. etc below)
     ".###.",
     "...#.",
     "..#..",
     ".#..."],
 2: [".....",   # wings MID
     "..#..",
     "#.#.#",
     ".####",
     ".###.",
     "...#.",
     "..#..",
     ".#..."],
 3: [".....",   # wings DOWN (downstroke)
     ".....",
     "..#..",
     "#####",
     ".###.",
     "...#.",
     ".#.#.",
     "#...#"],
 4: [".....",   # glide
     ".....",
     "##.##",
     ".###.",
     ".####",
     "...#.",
     "..#..",
     "....."],
 5: ["#...#",   # big flap up
     ".#.#.",
     "#.#.#",
     ".###.",
     ".###.",
     "...#.",
     "..#..",
     ".#..."],
 6: [".....",   # small dragon (distant)
     ".....",
     ".....",
     ".#.#.",
     "..#..",
     ".###.",
     ".....",
     "....."],
 7: [".....",   # fire puff / dragon head close
     "..#..",
     ".###.",
     "####.",
     ".####",
     ".###.",
     "..#..",
     "....."],
}

def to_bytes(rows):
    out=[]
    for r in rows:
        r=r.replace('>','##').ljust(5)[:5]
        out.append(sum((1<<(4-k)) for k,c in enumerate(r) if c=='#'))
    return out

def render():
    chars=sorted(FRAMES)
    print('      '+'   '.join(f'c{c}' for c in chars))
    for row in range(8):
        line=[]
        for c in chars:
            rows=FRAMES[c]; r=rows[row].replace('>','##').ljust(5)[:5]
            line.append(''.join('#' if x=='#' else '.' for x in r))
        print('      '+'  '.join(line))
    print()
    for c in chars:
        print(f' char{c}: '+' '.join(f'{b:02x}' for b in to_bytes(FRAMES[c])))

if __name__=='__main__':
    render()
