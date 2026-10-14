#!/usr/bin/env python3
"""Delay scope: a click every T ms through the unit; every output click's position inside the click period is plotted
against time (colour = level). Each read head of a modulated delay draws its delay trajectory: a head moving at rate
r (samples of delay per sample) climbs r*T per click; a window wrap is a jump. Offsets include the loop latency.
Used by pitchmap experiments: scope(tag, writes) -> (rows of (t, pos_ms, dB)), and plot(list) -> PNG."""
import numpy as np
import revtest as RT
import pitchmap as M

R = RT.R


def pulse():
    n = int(0.0006 * R); t = np.arange(n)
    return np.sin(2 * np.pi * 3000 * t / R) * np.hanning(n)


def capture(T=0.12, dur=4.0, amp=0.3):
    p = pulse(); x = np.zeros(int((dur + 0.6) * R))
    for k in range(int(dur / T)):
        i = int((0.3 + k * T) * R); x[i:i + len(p)] += amp * p
    y = RT.playrec(x)
    mf = np.abs(np.convolve(y, p[::-1], 'same'))
    from scipy.signal import hilbert, find_peaks
    env = np.abs(hilbert(np.convolve(y, p[::-1], 'same')))
    pk, pr = find_peaks(env, height=env.max() * 0.04, distance=int(0.0008 * R))
    t = pk / R
    pos = (t % T) * 1000
    db = 20 * np.log10(env[pk] / env.max())
    return np.stack([t, pos, db], 1)


def scope(tag, ws, **kw):
    M.write_all(ws)
    rows = capture(**kw)
    M.write_all([(c, s, None) for c, s, _ in ws])
    print(f'{tag:28s} {len(rows)} peaks', flush=True)
    return tag, rows


def plot(results, out, T=0.12):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(len(results), 1, figsize=(10, 2.3 * len(results)), sharex=True)
    ax = np.atleast_1d(ax)
    for a, (tag, rows) in zip(ax, results):
        a.scatter(rows[:, 0], rows[:, 1], c=rows[:, 2], s=6, cmap='viridis', vmin=-30, vmax=0)
        a.set_ylim(0, T * 1000); a.set_title(tag, fontsize=9, loc='left'); a.set_ylabel('ms mod T', fontsize=8)
    ax[-1].set_xlabel('s')
    plt.tight_layout(); plt.savefig(out, dpi=80)
    print('wrote', out)


def seq(stages, seg=1.6, T=0.1, amp=0.3):
    """One continuous click stream; stages = [(tag, writes), ...] applied one after another (each stage's writes go on
    top of the previous; everything is restored at the end). Returns [(tag, rows within that stage)] where rows' pos
    is comparable across stages (same stream, same latency)."""
    import threading, time
    p = pulse(); dur = seg * len(stages) + 1.0
    x = np.zeros(int((dur + 0.6) * R))
    for k in range(int(dur / T)):
        i = int((0.3 + k * T) * R); x[i:i + len(p)] += amp * p
    marks = []
    touched = []

    def writer():
        t0 = time.time()
        for k, (tag, ws) in enumerate(stages):
            while time.time() - t0 < 0.8 + k * seg:
                time.sleep(0.01)
            if ws:
                M.write_all(ws); touched.extend((c, s) for c, s, _ in ws)
            marks.append(time.time() - t0)
    th = threading.Thread(target=writer)
    th.start()
    y = RT.playrec(x)
    th.join()
    if touched:
        M.write_all([(c, s, None) for c, s in dict.fromkeys(touched)])
    from scipy.signal import hilbert, find_peaks
    env = np.abs(hilbert(np.convolve(y, p[::-1], 'same')))
    ref = np.percentile(env, 99.5)
    pk, _ = find_peaks(env, height=ref * 0.3, distance=int(0.0008 * R))
    t = pk / R
    rows = np.stack([t, (t % T) * 1000, 20 * np.log10(env[pk] / ref)], 1)
    return rows, marks


def transitions(res, T=0.1, floor=-12, maxn=6):
    """print the strong click positions whenever they change (one line per click period with a new pattern)"""
    allr = np.concatenate([r for _, r in res]); allr = allr[np.argsort(allr[:, 0])]
    prev = None
    for k in range(int(allr[:, 0].min() / T), int(allr[:, 0].max() / T) + 1):
        r = allr[(allr[:, 0] >= k * T) & (allr[:, 0] < (k + 1) * T) & (allr[:, 2] > floor)]
        cur = ' '.join(f'{p:5.1f}({d:+.0f})' for _, p, d in r[:maxn]) + (' ...' if len(r) > maxn else '')
        key = ' '.join(f'{p:4.0f}' for _, p, d in r[:maxn])
        if key and key != prev:
            print(f'{k*T:5.1f}s n={len(r):2d} {cur}'); prev = key


def timeline(rows, marks, every=0.3, top=4, T=0.1):
    print('writes at', ' '.join(f'{m:.2f}' for m in marks))
    for k in range(int(rows[:, 0].max() / every) + 1):
        t0 = k * every
        r = rows[(rows[:, 0] >= t0) & (rows[:, 0] < t0 + T)]
        r = r[np.argsort(r[:, 2])[::-1][:top]]
        if len(r):
            print(f'{t0:5.2f}s', '  '.join(f'{p:5.1f}({d:+.0f})' for _, p, d in r))
