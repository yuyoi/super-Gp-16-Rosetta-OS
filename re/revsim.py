#!/usr/bin/env python3
"""Offline model of the GP-16 reverse-delay engine's pointer arithmetic (rev_blob.asm), so the two crackle
artifacts can be seen and HEARD without the hardware. Not cycle-accurate DSP; it reproduces exactly the thing
that matters: how the C-tap read position moves, where it splices, and the feedback that cascades the clicks.

  py -3.10 revsim.py            # render engine / fullrate / xfade WAVs + print metrics

Model (see DSP_CRACK.md):
  - hardware write pointer Wptr advances +1 every frame (fs). The delay line is a ring.
  - read position = Wptr - A, A = the C-tap offset the engine writes.
  - ENGINE  : A += 4 every 2 frames (the real firmware). abs read = -1/frame avg + a +/-1 sample
              square-wave JITTER at fs/2  -> the bright fizz (artifact B).
  - FULLRATE: A += 2 every frame. abs read = clean -1/frame, no fs/2 jitter -> fizz gone.
  - both wrap the grain with A -= span (no crossfade) -> a step = a click every grain (artifact A),
    recirculated by feedback -> the cascade.
  - XFADE   : two reversed grains offset by span/2, raised-cosine crossfade -> no splice step.
  read uses zero-order hold on the integer position (what the gate array does); +0.5-sample linear
  interp is offered too, to show it is the JITTER not the quantisation that fizzes.
"""
import math, wave, struct, os
import numpy as np

FS = 31980
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'revsim_out')
os.makedirs(OUT, exist_ok=True)


def test_input(sec=3.0):
    """A guitar-ish test: repeated plucked notes (sharp attack + decaying tone + a bit of bright harmonic),
    so both the transient pops and the HF fizz have something to bite on."""
    n = int(sec * FS)
    t = np.arange(n) / FS
    x = np.zeros(n)
    notes = [196.0, 196.0, 392.0, 587.33, 392.0, 196.0]      # G plucks, one up high to show the fizz
    spacing = sec / len(notes)
    for i, f in enumerate(notes):
        t0 = i * spacing
        s = int(t0 * FS)
        env = np.exp(-(t - t0) * 7.0)
        env[t < t0] = 0.0
        tone = (np.sin(2 * np.pi * f * (t - t0))
                + 0.5 * np.sin(2 * np.pi * 2 * f * (t - t0))
                + 0.3 * np.sin(2 * np.pi * 3 * f * (t - t0))
                + 0.15 * np.sin(2 * np.pi * 5 * f * (t - t0)))   # bright, lots to alias
        x += env * tone
        if s < n:
            x[s:s + 6] += 1.4                                    # pick click = a broadband transient
    return 0.5 * x / (np.max(np.abs(x)) + 1e-9)


def lp1(x, fc):
    """one-pole low-pass, like the tap CUTOFF."""
    a = math.exp(-2 * math.pi * fc / FS)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def run(x, mode, span, fb=0.36, fb_cut=4500, interp=False):
    """Render one reverse-delay pass. span in samples (grain length). fb = feedback, fb_cut = 1-pole LPF in
    the feedback path (the tap CUTOFF). fb_cut >= FS/2 disables it. Returns the wet output (not extra-filtered,
    so the fs/2 jitter image stays visible)."""
    n = len(x)
    N = span + 8                      # ring just big enough for one grain + guard
    buf = np.zeros(N)
    out = np.zeros(n)
    W = 0
    A = float(span // 2)              # start mid-grain
    A2 = A + span / 2                 # 2nd grain for xfade
    fb_state = 0.0                    # the low-passed feedback return
    fa = math.exp(-2 * math.pi * min(fb_cut, FS / 2 - 1) / FS)
    use_fblp = fb_cut < FS / 2
    fprev = 0.0

    def rd(pos):
        pos = pos % N
        if not interp:
            return buf[int(pos) % N]
        i0 = int(pos) % N
        frac = pos - math.floor(pos)
        return buf[i0] * (1 - frac) + buf[(i0 + 1) % N] * frac

    for i in range(n):
        buf[W % N] = x[i] + fb_state          # write input + feedback
        # advance the read offset per the mode
        if mode == 'engine':
            if i % 2 == 0:
                A += 4
        elif mode == 'fullrate':
            A += 2
        elif mode == 'xfade':
            A += 2
            A2 += 2
        if A >= span:
            A -= span
        # read
        if mode == 'xfade':
            if A2 >= span:
                A2 -= span
            # raised-cosine crossfade between the two grains by grain phase
            ph = A / span
            g1 = 0.5 - 0.5 * math.cos(2 * math.pi * ph)     # 0 at the splice, 1 mid-grain
            s1 = rd(W - A)
            s2 = rd(W - A2)
            s = g1 * s1 + (1 - g1) * s2
        else:
            s = rd(W - A)
        out[i] = s
        # feedback return, low-passed by the tap cutoff (1-pole) in the loop, then scaled
        if use_fblp:
            fprev = (1 - fa) * s + fa * fprev
            fb_state = fb * fprev
        else:
            fb_state = fb * s
        W += 1
    return out


def hf_fizz(y):
    """crude HF-energy proxy above ~5 kHz = the fizz metric (RMS of a high-passed copy)."""
    hp = y - lp1(y, 5000)
    return float(np.sqrt(np.mean(hp ** 2)))


def click_pops(y, span):
    """count big sample-to-sample jumps near grain boundaries = the splice pops."""
    d = np.abs(np.diff(y))
    thr = 6 * np.median(d[d > 0]) if np.any(d > 0) else 1.0
    return int(np.sum(d > thr))


def save(name, y):
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.9
    p = os.path.join(OUT, name)
    with wave.open(p, 'w') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(FS)
        w.writeframes(b''.join(struct.pack('<h', int(v * 32767)) for v in y))
    return p


def tone(f, sec, fade=True):
    n = int(sec * FS)
    t = np.arange(n) / FS
    y = np.sin(2 * np.pi * f * t)
    if fade:
        r = int(0.01 * FS)
        y[:r] *= np.linspace(0, 1, r); y[-r:] *= np.linspace(1, 0, r)
    return 0.5 * y


def bin_db(y, f):
    """level (dB) at frequency f from the FFT of y."""
    Y = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    k = int(round(f / FS * len(y)))
    k = max(0, min(len(Y) - 1, k))
    peak = np.max(Y) + 1e-12
    return 20 * math.log10((Y[k] + 1e-12) / peak)


if __name__ == '__main__':
    print('=== Artifact B (fizz): fs/2 position-jitter image. 6 kHz sine in, no feedback, no extra LPF.')
    print('    A clean reverse would show only 6 kHz. The engine adds a mirror at fs/2-6k = %.0f Hz.\n' % (FS / 2 - 6000))
    ft = tone(6000, 1.0)
    bigspan = int(0.9 * FS)                       # grain long enough that no splice in the window
    print(f'    {"mode":10} {"6kHz(want)":>12} {"9990Hz(img)":>12} {"image below want by":>22}')
    for mode in ('engine', 'fullrate'):
        y = run(ft, mode, bigspan, fb=0.0, fb_cut=FS)   # fb_cut>=FS/2 -> no LPF, image stays bare
        w = bin_db(y, 6000); im = bin_db(y, FS / 2 - 6000)
        print(f'    {mode:10} {w:12.1f} {im:12.1f} {w - im:19.1f} dB')

    print('\n=== Artifact A (pops): splice clicks. 200 Hz sine in, feedback 0.36, grain 0.55 s, no tap LPF.')
    print('    The only thing above ~1 kHz is splice-click energy. xfade should collapse it.\n')
    st = tone(200, 3.0)
    span = int(0.55 * FS)
    base = None
    hdr = 'peak step (2nd diff)'
    print(f'    {"mode":12} {hdr:>22} {"vs engine":>12}')
    for mode in ('engine', 'fullrate', 'xfade'):
        y = run(st, mode, span, fb=0.36, fb_cut=FS)
        d2 = np.abs(np.diff(y, 2))          # a splice = a slope break = a spike in the 2nd difference;
        e = float(np.max(d2))               # a smooth 200 Hz sine barely registers here
        if base is None:
            base = e
        print(f'    {mode:12} {e:22.5f} {20 * math.log10((e + 1e-9) / (base + 1e-9)):9.1f} dB')

    print('\n=== Musical renders (guitar plucks, feedback 0.36, tap LPF 4.5 kHz) -> revsim_out/*.wav')
    x = test_input(3.0)
    save('00_dry.wav', x)
    for mode in ('engine', 'fullrate', 'xfade'):
        save(f'{mode}.wav', run(x, mode, span, fb=0.36, fb_cut=4500))
    save('engine_lp2500.wav', run(x, 'engine', span, fb=0.36, fb_cut=2500))   # cheap no-engine-change fix
    print(f'    WAVs in {OUT}')
