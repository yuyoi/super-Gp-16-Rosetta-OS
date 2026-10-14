#!/usr/bin/env python3
"""The user's REVERSE as tuned by ear 2026-10-14: v7 engine (fades off), borrowed 2 s memory, 1/4 @ 92 BPM,
input cut 4.5 kHz (crackle = the 16 kHz - f mirror, scales with HF content), 100% wet (2:07A = -1.0) with all the echo
on chain A at 0x300 and chain B echo off (headroom: less clipping on hard attacks). Re-run after any patch push,
knob or menu change. Hands off the front panel while it runs.
Usage: py -3.10 revfull.py [chain-A level hex, default 300]"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
lev = sys.argv[1] if len(sys.argv) > 1 else '300'
for args in (['rev7setup.py', '0'], ['gain.py', '4f', '1', '50', '30'], ['wet100.py', 'on', lev, '000']):
    subprocess.run([sys.executable, os.path.join(HERE, args[0])] + args[1:], cwd=HERE, check=True)
