#!/usr/bin/env python3
"""Fully-animated side-view flying dragon, 150x80 shapes -> 15x8 (3 LCD cells), 8 frames.
Every part moves: wing flaps, tail undulates snake-like, body bobs, legs shuffle."""
import math, numpy as np
from PIL import Image, ImageDraw
HW, HH = 150, 80


def rot(pts, cx, cy, deg):
    a = math.radians(deg); ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


def draw(frame):
    ph = 2 * math.pi * (frame % 8) / 8
    bob = 1.6 * math.sin(ph)                 # whole-body vertical bob
    wing_deg = -16 - 26 * math.cos(ph)       # flap: frame0 up, frame4 down
    legsw = 2.4 * math.sin(ph)               # leg shuffle
    im = Image.new('L', (HW, HH), 0); d = ImageDraw.Draw(im)
    B = bob

    def poly(pts): d.polygon([(x, y + B) for x, y in pts], fill=255)

    # body
    d.ellipse([30, 42 + B, 100, 52 + B], fill=255)
    # neck up, head tilted DOWN with a downward-pointing snout (not stretched forward)
    poly([(92, 44), (106, 30), (118, 29), (120, 40), (102, 50)])
    poly([(114, 28), (126, 27), (133, 33), (131, 42), (126, 48), (119, 45), (113, 36)])
    poly([(114, 28), (107, 13), (120, 26)])   # horn
    # legs (shuffle: front and hind swing opposite)
    d.polygon([(50 - legsw, 51 + B), (46 - legsw, 66 + B), (56 - legsw, 66 + B), (58 - legsw, 51 + B)], fill=255)
    d.polygon([(80 + legsw, 51 + B), (76 + legsw, 66 + B), (86 + legsw, 66 + B), (88 + legsw, 51 + B)], fill=255)
    # wing (rotates about shoulder, which also bobs)
    sh = (78, 46 + B)
    wing = [(78, 46 + B), (58, 4 + B), (70, 16 + B), (80, 8 + B), (90, 22 + B), (100, 16 + B), (104, 34 + B)]
    d.polygon(rot(wing, sh[0], sh[1], wing_deg), fill=255)
    # tail: slim tapering snake, undulates (base follows bob, tip waves most)
    N = 28
    for i in range(N + 1):
        t = i / N
        x = 36 - 34 * t
        y = 46 + B + 16.0 * t * math.sin(2 * math.pi * 0.95 * t - ph)
        rr = max(1.3, 3.0 * (1 - t) + 0.9)
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=255)
    # eye (knock out, follows bob)
    d.ellipse([121, 32 + B, 124, 35 + B], fill=0)
    return im


def frame_bytes(frame, thr=0.33):
    g = (np.array(draw(frame).resize((15, 8), Image.BOX)) / 255.0) > thr
    return g


def frames_rows():
    out = []
    for f in range(8):
        g = frame_bytes(f)
        out.append([sum((1 << (14 - c)) for c in range(15) if g[r][c]) for r in range(8)])
    return out


if __name__ == '__main__':
    rows = frames_rows()
    print(','.join('[' + ','.join(map(str, fr)) + ']' for fr in rows))
    for f in range(8):
        print(f'--- f{f} ---')
        g = frame_bytes(f)
        for r in range(8):
            print('  ' + ''.join('#' if g[r][c] else '.' for c in range(15)))
