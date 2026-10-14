#!/usr/bin/env python3
"""REVERSE on the GP-16 DSP: write forwards, read backwards.
The B2 MOD block is one modulated-delay program; in PITCH mode chip 1 step 0x152 is the ramp that moves the read head:
coef = 2048 * (1 - ratio) (ROM table DS:355A, -12 st = 0x400, +12 st = 0x800). Reverse = ratio -1 = coef +2.0, past the
12-bit range, so the step needs a x2 multiplier shift (top-byte bit 21 = x0.5 is measured; bits 22/23 are the x2
candidates). Steps (audio loop as loop_rig.py, debug port on MIDI, GP-16 on its patch screen):
  1. pitch block 100% wet at 0 st, then pokes on 1:152 with a steady 440 Hz: law check (coef 0x400 -> 220 Hz),
     x0.5 check (bit 21), x2 check (bits 22 / 23 with coef 0x200 -> 220 Hz if x2, 330 Hz if not).
  2. reverse (x2 bit + coef 0x7FF): a rising chirp should come back as falling pieces; prints the share of falling
     frames and the piece (grain) length.
  3. leaves reverse ON for playing; `py -3.10 revtest.py restore` reloads the patch.
Usage: py -3.10 revtest.py [all | listen <bit> | restore]"""
import os, subprocess, sys, time
import numpy as np
import sounddevice as sd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'tonezone'))
import tz_gp16 as T
import tz_fit as F
import loop_rig as L

R = 48000
P = F.P
import revload as _RL
MIN, MOUT = _RL.port_names()                     # Windows renumbers them on reconnect
STOCK = 0x008008                      # 1:152 instruction as the firmware writes it
REC = P.R(P.on('mod', b2='pitch'), P.PITCH(0, 200))
dev = L.devices('Focusrite')


def poke(instr, coef, commit=8):
    r = subprocess.run([sys.executable, os.path.join(HERE, 'gp16poke.py'), 'write', '1', '152', f'{instr:06x}', f'{coef:04x}',
                        str(commit), '--port', 'Focusrite'], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-300:])
    time.sleep(0.3)


def playrec(x):
    buf = []
    with sd.InputStream(device=dev[0], samplerate=R, channels=2, dtype='float32', blocksize=1024, latency='high',
                        callback=lambda d, fr, t, s: buf.append(d.copy())):
        time.sleep(0.1)
        with sd.OutputStream(device=dev[1], samplerate=R, channels=2, dtype='float32', blocksize=1024, latency='high') as o:
            o.write(np.stack([x.astype(np.float32), np.zeros(len(x), np.float32)], 1))
        time.sleep(0.2)
    y = np.concatenate(buf).astype(float)
    return y[:, int(np.argmax((y ** 2).mean(0)))]


def peaks(y, n=3):
    Y = np.abs(np.fft.rfft(y * np.hanning(len(y)))); fr = np.fft.rfftfreq(len(y), 1 / R)
    m = (fr > 50) & (fr < 2000); out = []
    for i in np.argsort(Y[m])[::-1]:
        if all(abs(fr[m][i] - f) > 15 for f in out):
            out.append(fr[m][i])
        if len(out) == n:
            break
    return out


def tone_test(name):
    x = 0.2 * np.sin(2 * np.pi * 440 * np.arange(int(2.0 * R)) / R)
    y = playrec(x)
    pk = peaks(y[int(0.9 * R):int(1.9 * R)])
    print(f'  {name:34s} -> ' + ', '.join(f'{f:5.0f} Hz' for f in pk), flush=True)
    return pk


def chirp_test(name):
    """rising chirp 300 -> 3000 Hz over 3 s; per 4 ms frame the dominant frequency; reversed pieces fall"""
    t = np.arange(int(3.0 * R)) / R
    x = 0.2 * np.sin(2 * np.pi * (300 * t + (3000 - 300) / 6 * t ** 2))
    y = playrec(np.r_[x, np.zeros(R // 2)])
    hop, win = 192, 1024
    fr = np.fft.rfftfreq(win, 1 / R); w = np.hanning(win)
    f = np.array([fr[np.argmax(np.abs(np.fft.rfft(y[i:i + win] * w)))] for i in range(0, len(y) - win, hop)])
    lvl = np.array([np.sqrt(np.mean(y[i:i + win] ** 2)) for i in range(0, len(y) - win, hop)])
    on = lvl > 0.3 * lvl.max()
    d = np.diff(f)[on[1:]]
    d = d[np.abs(d) < 400]                                          # drop the jumps between pieces
    falling = float(np.mean(d < 0)) if len(d) else float('nan')
    jumps = np.where(np.abs(np.diff(f)) > 150)[0]                   # piece boundaries
    piece = float(np.median(np.diff(jumps))) * hop / R * 1000 if len(jumps) > 3 else float('nan')
    print(f'  {name:34s} -> falling frames {100 * falling:3.0f}%, pieces ~{piece:4.0f} ms', flush=True)
    return falling, piece


def restore():
    T.push({'recipe': REC, 'name': 'REVERSE TEST'}, MIN, MOUT, progress=lambda s: None)
    time.sleep(0.8)


def main():
    a = sys.argv[1:] or ['all']
    if a[0] == 'restore':
        restore(); print('patch reloaded (stock pitch shifter, 0 st)'); return
    if a[0] == 'listen':
        restore(); poke(int(a[1], 16) if len(a) > 1 else 0x408008, 0x7FF)
        print('reverse ON - play. `py -3.10 revtest.py restore` when done'); return
    restore()
    print('1. shift bits on 1:152 (steady 440 Hz in):')
    tone_test('stock, 0 st (440)')
    poke(STOCK, 0x400); tone_test('coef 400: law check (220)')
    poke(STOCK | 0x200000, 0x7FF); tone_test('bit 21 + 7FF: x0.5 check (220)')
    poke(STOCK, 0x200); ref = tone_test('coef 200, no shift (330)')
    x2 = None
    for bit in (0x400000, 0x800000):
        poke(STOCK | bit, 0x200)
        pk = tone_test(f'bit {bit.bit_length() - 1} + 200: x2 -> 220')
        if pk and abs(pk[0] - 220) < 12 and x2 is None:
            x2 = bit
    print('2. reverse (chirp 300 -> 3000 Hz rising):')
    poke(STOCK, 0x000); chirp_test('stock 0 st (forward)')
    for bit in ([x2] if x2 else [0x400000, 0x800000]):
        poke(STOCK | bit, 0x7FF)
        chirp_test(f'bit {bit.bit_length() - 1} + 7FF: REVERSE?')
    bit = x2 or 0x400000
    poke(STOCK | bit, 0x7FF)
    print(f'3. reverse left ON (1:152 = {STOCK | bit:06x} / 7FF) - play guitar. `py -3.10 revtest.py restore` to undo.')


if __name__ == '__main__':
    main()
