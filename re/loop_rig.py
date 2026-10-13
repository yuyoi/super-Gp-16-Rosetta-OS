#!/usr/bin/env python3
"""GP-16 audio loop rig (any WASAPI interface, default Focusrite): play a log sine sweep out of one output into the
GP-16, record its output, deconvolve (Farina) -> impulse response, latency, level, frequency response.
Wiring: interface OUT 1 -> GP-16 INPUT, GP-16 OUTPUT A -> interface IN 1 or 2 (auto-detected). 48 kHz.
Usage: py -3.10 loop_rig.py check [--dev Focusrite] [--level -30]
       py -3.10 loop_rig.py measure <name> [--level -30]     -> out/loop/<name>.npz (+ .wav of the recording)"""
import argparse, os, sys, time
import numpy as np

RATE = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, 'out', 'loop')


def devices(name):
    import sounddevice as sd
    api = next(i for i, h in enumerate(sd.query_hostapis()) if 'WASAPI' in h['name'])
    dev_in = dev_out = None
    for i, d in enumerate(sd.query_devices()):
        if d['hostapi'] != api or name.lower() not in d['name'].lower():
            continue
        if d['max_input_channels'] >= 2 and dev_in is None:
            dev_in = i
        if d['max_output_channels'] >= 2 and dev_out is None:
            dev_out = i
    if dev_in is None or dev_out is None:
        raise SystemExit(f'no WASAPI in+out device matching "{name}"')
    return dev_in, dev_out


def sweep(seconds=2.0, f1=20.0, f2=20000.0, level_db=-30.0):
    t = np.arange(int(seconds * RATE)) / RATE
    k = np.log(f2 / f1)
    x = np.sin(2 * np.pi * f1 * seconds / k * (np.exp(t * k / seconds) - 1))
    fade = int(0.01 * RATE)
    x[:fade] *= np.linspace(0, 1, fade)
    x[-fade:] *= np.linspace(1, 0, fade)
    inv = x[::-1] * np.exp(-t * k / seconds)                       # Farina inverse filter (amplitude-compensated)
    D = np.abs(np.fft.rfft(np.convolve(x, inv)))                  # normalise: x * inv = 0 dB in the 200 Hz-5 kHz band
    fD = np.fft.rfftfreq(2 * len(x) - 1, 1 / RATE)
    inv /= np.median(D[(fD > 200) & (fD < 5000)])
    return x * 10 ** (level_db / 20), inv / 10 ** (level_db / 20)


def playrec(sig, dev, out_ch=0, tail=1.0):
    import sounddevice as sd
    n = len(sig) + int(tail * RATE)
    play = np.zeros((n, 2), dtype=np.float32)
    play[:len(sig), out_ch] = sig
    rec = sd.playrec(play, RATE, channels=2, device=dev, dtype='float32')
    sd.wait()
    return rec.astype(np.float64)


def analyse(rec, x, inv):
    out = {}
    pk = np.abs(rec).max(axis=0)
    ch = int(np.argmax(pk))
    y = rec[:, ch]
    ir = np.convolve(y, inv)[len(x) - 1:]
    lat = int(np.argmax(np.abs(ir[:RATE // 2])))
    seg = ir[max(0, lat - 64):lat + 8192].copy()                  # flat window, short fades (keeps the peak intact)
    w = np.ones(len(seg))
    w[:32] = np.hanning(64)[:32]
    w[-1024:] = np.hanning(2048)[1024:]
    seg *= w
    H = np.fft.rfft(seg, 16384)
    f = np.fft.rfftfreq(16384, 1 / RATE)
    mag = 20 * np.log10(np.abs(H) + 1e-12)
    ref = np.interp(1000, f, mag)
    out.update(ch=ch, peak_in=pk, latency=lat, ir=ir[:RATE], f=f, mag=mag - ref, gain_1k=ref)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['check', 'measure', 'tone'])
    ap.add_argument('name', nargs='?', default='check')
    ap.add_argument('--dev', default='Focusrite')
    ap.add_argument('--level', type=float, default=-30.0)
    ap.add_argument('--secs', type=float, default=20.0)
    a = ap.parse_args()
    dev = devices(a.dev)
    if a.cmd == 'tone':                                          # steady 440 Hz on OUT 1, per-second input peaks
        t = np.arange(int(a.secs * RATE)) / RATE
        rec = playrec(np.sin(2 * np.pi * 440 * t) * 10 ** (a.level / 20), dev, tail=0.2)
        for s in range(int(a.secs)):
            pk = 20 * np.log10(np.abs(rec[s * RATE:(s + 1) * RATE]).max(axis=0) + 1e-12)
            print(f'{s:3d}s  in1 {pk[0]:6.1f}  in2 {pk[1]:6.1f} dBFS')
        n = len(t)                                               # 440 Hz content (finds a tone buried in noise)
        ref = np.exp(-2j * np.pi * 440 * t)
        for c in range(2):
            amp = 2 * np.abs(np.dot(rec[:n, c], ref)) / n
            print(f'in{c + 1} 440 Hz component {20 * np.log10(amp + 1e-12):6.1f} dBFS (sent {a.level:.0f})')
        return
    x, inv = sweep(level_db=a.level)
    rec = playrec(x, dev)
    r = analyse(rec, x, inv)
    pk = 20 * np.log10(r['peak_in'] + 1e-12)
    print(f'device in/out {dev}; peaks: in1 {pk[0]:.1f} dBFS, in2 {pk[1]:.1f} dBFS -> GP-16 on input {r["ch"] + 1}')
    if pk.max() < -60:
        print('  no signal back: check OUT 1 -> GP-16 INPUT, GP-16 OUTPUT -> interface input, GP-16 not muted')
    elif pk.max() > -1:
        print('  WARNING: recording near clipping, lower the input gain or GP-16 output')
    print(f'latency {r["latency"]} samples ({1000 * r["latency"] / RATE:.2f} ms), loop gain at 1 kHz {r["gain_1k"]:.1f} dB')
    for fq in (50, 100, 200, 500, 1000, 2000, 5000, 10000, 15000):
        print(f'  {fq:5d} Hz {np.interp(fq, r["f"], r["mag"]):+6.1f} dB')
    if a.cmd == 'measure':
        os.makedirs(OUT_DIR, exist_ok=True)
        np.savez(os.path.join(OUT_DIR, a.name + '.npz'), ir=r['ir'], f=r['f'], mag=r['mag'], latency=r['latency'],
                 gain_1k=r['gain_1k'])
        print('saved', os.path.join(OUT_DIR, a.name + '.npz'))


if __name__ == '__main__':
    main()
