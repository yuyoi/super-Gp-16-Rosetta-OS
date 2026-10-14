#!/usr/bin/env python3
"""How the REVERSE engine stretches (Focusrite loop: OUT 1 -> GP-16 IN, GP-16 OUT -> IN 1/2), for the pedal design.
Clean measurement patch (tap delay only, C 100, feedback 0), engine v6 with fades off. For each speed / chunk:
  pitch: a steady 440 Hz tone -> the wet's pitch (the strongest peak that isn't the dry 440)
  picture: a 3-note pluck phrase (A3, C#4, E4) -> spectrogram of the GP-16 output
Then the user's REVERSE DELAY base patch and the 300 ms / -1 engine go back on.
Usage: py -3.10 stretchtest.py   -> out/stretch_grid.png, printed pitch table"""
import time
import numpy as np
import revload as RL
import revlock as RK
import revtest as RT

R = RT.R
P = RT.P
OUT = 'out/stretch_grid.png'


def pluck(f, dur, t0, total):
    x = np.zeros(int(total * R)); n = int(dur * R); t = np.arange(n) / R
    env = np.exp(-t * 5.0) * np.minimum(1, t / 0.003)
    note = sum(np.sin(2 * np.pi * f * k * t) / k ** 1.3 for k in range(1, 6)) * env
    x[int(t0 * R):int(t0 * R) + n] += note
    return x


def phrase():
    total = 3.0
    x = pluck(220.0, 0.9, 0.10, total) + pluck(277.2, 0.9, 0.45, total) + pluck(329.6, 1.2, 0.80, total)
    return 0.12 * x / np.abs(x).max()


def tone():
    n = int(1.6 * R); t = np.arange(n) / R
    return 0.1 * np.sin(2 * np.pi * 440 * t) * np.minimum(1, np.minimum(t, t[::-1]) / 0.01)


def wet_pitch(y):
    seg = y[int(0.5 * R):int(1.5 * R)]
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))); f = np.fft.rfftfreq(len(seg), 1 / R)
    m = (f > 60) & (f < 4000) & (np.abs(f - 440) > 12)
    i = np.argmax(np.where(m, S, 0))
    return f[i], 20 * np.log10(S[i] / (S[np.argmin(np.abs(f - 440))] + 1e-12))


def spec(y):
    from scipy.signal import spectrogram
    f, t, Z = spectrogram(y, R, nperseg=2048, noverlap=1536)
    keep = f < 2000
    return t, f[keep], 10 * np.log10(Z[keep] + 1e-14)


def engine(io, chunk, speed):
    RK.start(io, chunk, speed, 1, fade=False)
    time.sleep(0.4)


def main():
    io = RL.ports(); RL.stop(io); io[0].close(); io[1].close()
    RT.T.push({'recipe': P.R(P.on('dly'), P.TAP(10, 100, fb=0)), 'name': 'STRETCH TEST'}, RT.MIN, RT.MOUT,
              progress=lambda s: None)
    time.sleep(1.2)
    runs = [(300, -1.0), (300, -0.5), (300, -1.5), (300, -2.0), (300, 0.5), (150, -1.0), (580, -1.0)]
    rows = []
    x_ph = phrase()
    for chunk, speed in runs:
        io = RL.ports()
        try:
            engine(io, chunk, speed)
        finally:
            io[0].close(); io[1].close()
        fp, lv = wet_pitch(RT.playrec(tone()))
        y = RT.playrec(x_ph)
        rows.append((chunk, speed, fp, lv, y))
        print(f'chunk {chunk:4d} ms speed {speed:+.1f}: wet pitch {fp:7.1f} Hz (x{fp / 440:.2f} of 440), '
              f'{lv:+.1f} dB vs dry', flush=True)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(len(rows) + 1, 1, figsize=(10, 2.1 * (len(rows) + 1)), sharex=True)
    t, f, Z = spec(np.concatenate([np.zeros(int(0.27 * R)), x_ph]))   # input, shifted by the loop latency guess
    ax[0].pcolormesh(t, f, Z, vmin=Z.max() - 70, vmax=Z.max(), shading='auto', cmap='magma')
    ax[0].set_title('input: A3, C#4, E4 plucks', fontsize=9, loc='left')
    for a, (chunk, speed, fp, lv, y) in zip(ax[1:], rows):
        t, f, Z = spec(y)
        a.pcolormesh(t, f, Z, vmin=Z.max() - 70, vmax=Z.max(), shading='auto', cmap='magma')
        a.set_title(f'GP-16 out: chunk {chunk} ms, speed {speed:+.1f} (wet x{fp / 440:.2f} pitch)', fontsize=9, loc='left')
    for a in ax:
        a.set_ylabel('Hz', fontsize=8)
    ax[-1].set_xlabel('s')
    plt.tight_layout(); plt.savefig(OUT, dpi=90)
    print('wrote', OUT)
    # back to the user's sound
    io = RL.ports(); RL.stop(io); io[0].close(); io[1].close()
    RT.T.push({'recipe': RK.base_patch(), 'name': 'REVERSE DELAY'}, RT.MIN, RT.MOUT, progress=lambda s: None)
    time.sleep(1.2)
    io = RL.ports()
    try:
        RK.start(io, 300, -1, 1, fade=False)
    finally:
        io[0].close(); io[1].close()
    print('REVERSE DELAY + engine 300 ms / -1 back on')


if __name__ == '__main__':
    main()
