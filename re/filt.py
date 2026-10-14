#!/usr/bin/env python3
"""REVERSE DELAY filter ear session (engine keeps running: revlock.push stops it, pushes, resumes).
EQ + tap cut filter sit BEFORE the reverse (they shape what gets reversed); LINE presence/treble sit AFTER (fizz).
Usage: py -3.10 filt.py <flavour>"""
import sys
import revlock as RK
import revtest as RT

P = RT.P
OD = P.OD(0, 40, 60)
FLAVOURS = {
    'base':  ('your current: band-pass 250 Hz-2.5 kHz, +8 dB at 1 kHz',
              P.EQ(hi=(2500, -12), hm=(1000, +8, 1.5), lm=(200, -6, 1.0), lo=(250, -12)), 3000, (0, 0)),
    'wide':  ('wide open: lows and highs back, small mid bump',
              P.EQ(hi=(6000, -3), hm=(1000, +3, 1.0), lm=(200, 0, 1.0), lo=(80, 0)), 8000, (0, 0)),
    'dark':  ('dark: everything above ~1.5 kHz rolled off, warm 600 Hz',
              P.EQ(hi=(2000, -12), hm=(600, +6, 1.0), lm=(200, 0, 1.0), lo=(100, 0)), 1500, (0, 0)),
    'phone': ('telephone: narrow, honky 1.2 kHz',
              P.EQ(hi=(2000, -12), hm=(1200, +12, 3.0), lm=(300, -12, 1.0), lo=(300, -12)), 3000, (0, 0)),
    'wah':   ('fixed wah: sharp resonant peak at 800 Hz',
              P.EQ(hi=(2500, -12), hm=(800, +12, 5.0), lm=(200, -6, 1.0), lo=(200, -12)), 3000, (0, 0)),
    'air':   ('your band-pass, but presence/treble up after the reverse (more air, more fizz)',
              P.EQ(hi=(2500, -12), hm=(1000, +8, 1.5), lm=(200, -6, 1.0), lo=(250, -12)), 3000, (35, 35)),
}

if __name__ == '__main__':
    what, eq, cut, (pres, treb) = FLAVOURS[sys.argv[1]]
    RK.push(P.R(P.on('dirt', 'dly', 'eq', 'amp', od=True), OD, eq, P.TAP(10, 100, fb=45, cutf=cut),
                P.LINE(pres, treb, 50, 55, 80)))
    print(f'{sys.argv[1]}: {what}')
