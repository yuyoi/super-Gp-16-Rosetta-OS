"""GP Tone Zone: the real GP-16 in the audio loop -- calibrate, then refine a fitted sound on the unit itself.
Wiring (as re/loop_rig.py): interface OUT 1 -> GP-16 INPUT, GP-16 OUTPUT A -> interface IN 1 or 2, MIDI both ways on
the same interface. GP-16 on its patch screen (ESC twice from the OS), MIDI channel 1. Don't change the GP-16 output
volume or the interface gains between Calibrate and Refine.
- Levels are absolute, like the captures: NAM files say what their 0 dBFS is in dBu, and the interface output is known in
  dBu (OUT_DBU, Scarlett 6i6 OUT 1 on a TS cable). The test guitar peaks at +2 dBu on both sides, and the sine ladder runs
  from 60 dB under to 6 dB over that (a boost in front), so the unit is matched over the range pedals in front cover.
- calibrate(): clean loop gain + where the GP-16 input clips (information), then the OS Big Muff recipe plays the
  guitar DI once: its loudness is the level reference (the user's fuzz level).
- Unit.play(): a whole test program in one stream (one latency), found again by a sync chirp, cut back into pieces.
- refine(): push the sound (Roland DT1), play the capture's own test program through the unit, measure it the same
  way, then correct: EQ by the tone-curve residual (the EQ sits after the dirt, so it adds straight on), drive by
  lining the unit's input->output curve up with the capture's (drive coefficient is linear: v*20+47), level by EQ OUT
  against the reference. Repeat, keep the best pass."""
import json, os, sys, time
import numpy as np
from scipy.signal import fftconvolve

from tz_capture import HERE, SR
import tz_measure as M
import tz_fit as F
import tz_gp16 as T

sys.path.insert(0, os.path.join(HERE, '..', 're'))
import loop_rig as L                                        # noqa: E402  (WASAPI device pick + playrec)

CAL = os.path.join(HERE, 'loopcal.json')
_t = np.arange(int(0.25 * SR)) / SR
SYNC = 0.05 * np.sin(2 * np.pi * (300 * _t + (3000 - 300) / (2 * 0.25) * _t ** 2)) * np.hanning(len(_t))
REF_PEDAL = 'bigmuff'
OUT_DBU = 10.0      # Scarlett 6i6 2nd gen OUT 1: +16 dBu balanced at 0 dBFS, -6 dB on a TS (guitar) cable. Spec, not measured


def load_cal():
    try:
        with open(CAL) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


class Unit:
    def __init__(self, audio='Focusrite', midi_in=None, midi_out=None):
        self.dev = L.devices(audio)
        if not midi_in or not midi_out:
            _, _, midi_in, midi_out = T.midi_ports()
        self.min, self.mout = midi_in, midi_out
        self.cal = load_cal()
        self.ch = None

    def push(self, recipe, name='TONE ZONE'):
        T.push({'recipe': recipe, 'name': name}, self.min, self.mout, progress=lambda s: None)
        time.sleep(0.4)                                     # sound change + the DSP's deferred un-mutes

    def play(self, sigs, gap=0.12):
        """dict of signals (interface full scale) -> dict of what the GP-16 sent back, same lengths"""
        z = lambda s: np.zeros(int(s * SR))
        parts, starts, pos = [z(0.1), SYNC, z(0.25)], {}, int(0.35 * SR) + len(SYNC)
        for k, v in sigs.items():
            starts[k] = pos
            parts += [v, z(gap)]
            pos += len(v) + int(gap * SR)
        prog = np.concatenate(parts)
        if np.abs(prog).max() > 0.99:
            raise RuntimeError(f'test program peaks at {20 * np.log10(np.abs(prog).max()):+.1f} dBFS: would clip the interface output')
        rec = self._playrec(prog, tail=0.6)
        if self.ch is None:
            self.ch = int(np.argmax(np.sqrt(np.mean(rec ** 2, axis=0))))
        y = rec[:, self.ch]
        pk = np.abs(y).max()
        if pk > 0.98:
            raise RuntimeError('the GP-16 return clips the interface input: lower the interface input gain (then Calibrate again)')
        if pk < 1e-3:
            raise RuntimeError('nothing came back from the GP-16: check the loop cables and that it is not muted')
        n = int(2.0 * SR)
        c = np.abs(fftconvolve(y[:n], SYNC[::-1], mode='valid'))
        if c.max() < 8 * np.median(c):
            raise RuntimeError('sync chirp not found in what came back: the tone is not reaching the GP-16 '
                               '(interface output / cable / GP-16 input)')
        off = int(np.argmax(c)) - int(0.1 * SR)
        return {k: y[off + s:off + s + len(sigs[k])] for k, s in starts.items()}

    def _playrec(self, x, tail=0.6):
        """separate input and output streams: the Focusrite's full-duplex WASAPI stream sometimes opens with a dead
        output (silent until another stream wakes the endpoint); the sync chirp finds the offset anyway"""
        import sounddevice as sd
        buf = []
        out = np.zeros((len(x) + int(tail * SR), 2), dtype=np.float32)
        out[:len(x), 0] = x
        with sd.InputStream(device=self.dev[0], samplerate=SR, channels=2, dtype='float32', blocksize=1024,
                            latency='high', callback=lambda d, f, t, s: buf.append(d.copy())):
            time.sleep(0.1)
            with sd.OutputStream(device=self.dev[1], samplerate=SR, channels=2, dtype='float32', blocksize=1024,
                                 latency='high') as o:
                o.write(out)
            time.sleep(0.3)
        return np.concatenate(buf).astype(np.float64)


def _sine(level_dbfs, secs=0.3, f=220.0):
    t = np.arange(int(secs * SR)) / SR
    return 10 ** (level_dbfs / 20) * np.sin(2 * np.pi * f * t)


def _save(cal):
    with open(CAL, 'w') as f:
        json.dump(cal, f, indent=1)


def calibrate(unit, out_dbu=None, progress=print):
    """Interface on the GP-16 input: clean loop gain, input clip point (if reachable), then the level reference."""
    out_dbu = OUT_DBU if out_dbu is None else out_dbu
    peak = M.GUITAR_PEAK_DBU - out_dbu
    top = peak + M.LEVELS[-1]
    if top > -1:
        raise RuntimeError(f'the test program would peak at {top:+.1f} dBFS: interface output too quiet for it')
    progress('Calibrate: clean patch, sine ladder into the GP-16...')
    unit.push(F.P.R(F.P.on('eq'), F.P.EQ()), 'TZ CLEAN')       # flat EQ (all blocks off = silent)
    levels = np.arange(-50, -1, 2)                         # up to -2 dBFS (interface output headroom)
    out = unit.play({int(lv): _sine(lv) for lv in levels})
    o, thd = [], []
    for lv in levels:
        yy = out[int(lv)]
        h = M.harmonics(yy, 220)
        o.append(M.db(M.rms(yy[len(yy) // 4:])))
        thd.append(np.sqrt(np.sum(h[1:] ** 2)) / max(h[0], 1e-12))
    o, thd = np.array(o), np.array(thd)
    noise = float(np.min(o))                                # quietest rung ~ the return's noise floor
    good = o > noise + 25                                   # enough SNR for THD and gain to mean anything
    if good.sum() < 4:
        raise RuntimeError('too little signal back from the GP-16: raise the interface input gain, then Calibrate again')
    g0 = float(np.median((o - levels)[good][:6]))            # clean gain from the quiet good rungs
    comp = (o - levels) < g0 - 1.0                          # compressed by more than 1 dB
    rising = np.r_[False, False, False, thd[3:] > 2 * thd[:-3]]
    bad = np.where(good & (comp | ((thd > 0.03) & rising)))[0]
    clip = float(levels[bad[0]]) if len(bad) else None
    where = f'clips at {clip + out_dbu:+.0f} dBu' if clip is not None else f'clean up to {levels[-1] + out_dbu:+.0f} dBu'
    progress(f'Clean loop gain {g0:+.1f} dB; GP-16 input {where} (interface OUT 1 = {out_dbu:+.1f} dBu at 0 dBFS)')
    unit.cal = {'out_dbu': out_dbu, 'peak_dbfs': peak, 'gain_db': g0, 'clip_dbu': None if clip is None else clip + out_dbu,
                'ch': unit.ch, 'levels': [int(x) for x in levels], 'out_db': [round(float(x), 2) for x in o],
                'thd': [round(float(x), 4) for x in thd], 'when': time.strftime('%Y-%m-%d %H:%M')}
    progress(f'Level reference: the OS {REF_PEDAL} recipe plays the test guitar (+{M.GUITAR_PEAK_DBU:.0f} dBu peaks)...')
    unit.push(F.P.PEDALS[REF_PEDAL], 'TZ REF')
    ref_db = float(M.db(M.rms(unit.play({'di': M.guitar_di() * 10 ** (peak / 20)})['di'])))
    unit.cal.update(ref_pedal=REF_PEDAL, ref_db=ref_db)
    with open(CAL, 'w') as f:
        json.dump(unit.cal, f, indent=1)
    progress(f'Calibrated: guitar peaks at {peak:+.1f} dBFS, {REF_PEDAL} plays it at {ref_db:.1f} dBFS.')
    return unit.cal


def _knee6(m):
    """input level (dB re playing level) where the output is 6 dB under its playing-level output (interpolated)"""
    o = np.asarray(m['outs_db']) - m['outs_db'][M.I0]
    lv = M.LEVELS
    k = np.where(o >= -6)[0]
    if not len(k) or k[0] == 0:
        return float(lv[0])
    i = k[0]
    return float(np.interp(-6, [o[i - 1], o[i]], [lv[i - 1], lv[i]]))


def _gain_shift(mu, mc):
    """dB of extra input gain that lines the unit's in->out curve up best with the capture's, up to an output offset
    (least squares over the rungs where the unit is above its noise floor)"""
    lv = M.LEVELS.astype(float)
    u, c = np.asarray(mu['fund_db']), np.asarray(mc['fund_db'])          # fundamental: post-EQ only offsets it
    ok = (u > mu.get('noise_fund_db', -400) + 10).astype(float)        # same units: 220 Hz bin of the quiet part
    best = (np.inf, 0.0)
    for d in np.arange(-30, 30.01, 0.5):
        q = lv + d
        m = (q >= lv[0]) & (q <= lv[-1])
        okq = np.interp(q[m], lv, ok) > 0.99
        if okq.sum() < 4:
            continue
        diff = (np.interp(q[m], lv, u) - c[m])[okq]
        best = min(best, (float(np.var(diff)), float(d)))
    return best[1]


def _drive_for(v, d_db):
    """GP DIST/OD drive coefficient = v*20+47 (linear): +d_db of gain -> new knob value"""
    return float(np.clip(((v * 20 + 47) * 10 ** (d_db / 20) - 47) / 20, 5, 100))


def refine(cap, m_cap, r, unit, iters=3, progress=print):
    """Phase 1: drive only, until the unit's clipping curve lines up with the capture's (<= 1.5 dB, max 3 passes).
    Phase 2: drive fixed, `iters` passes of EQ (tone-curve residual) + level (EQ OUT vs the reference).
    Measured without the gate; the kept pass gets it back."""
    if not unit.cal or 'ref_db' not in unit.cal or 'out_dbu' not in unit.cal:
        raise RuntimeError('Calibrate the loop first.')
    scale = 10 ** (unit.cal['peak_dbfs'] / 20)               # the same +2 dBu guitar the capture got
    sig = M.program(scale)
    fq = M.FREQS
    w = (fq >= 100) & (fq <= 6000)
    target = m_cap['curve'] - np.interp(1000, fq, m_cap['curve'])
    fitd = r['fit']
    kind = fitd.get('dirt') or ('amp' if r['kind'] == 'amp' else ('od' if 0x17 in r['recipe'] else 'dist'))
    p, e = list(fitd['eq']), fitd.get('rms_err_db', 0.0)
    drive, trim = fitd.get('drive', 50), fitd.get('trim', 0.0)
    name = r['name']
    base = [l for l in r['report'] if not l.startswith(('EQ fit', '-> ', 'unit pass', 'refined'))]
    hist, best = [], None

    def run(tag):
        nonlocal best
        rr = F.make(name, kind, p, e, drive, base, m_cap, trim, gate=False)
        progress(f'Refine {tag}: pushing + playing the test program through the GP-16...')
        unit.push(rr['recipe'], name)
        mu = M.features(sig, unit.play(sig), scale)
        cu = mu['curve'] - np.interp(1000, fq, mu['curve'])
        resid = target - cu
        err = float(np.sqrt(np.mean(resid[w] ** 2)))
        dl = mu['out_rms_db'] - unit.cal['ref_db']
        gap = _gain_shift(mu, m_cap) if kind != 'amp' else 0.0
        line = (f'unit {tag}: tone error {err:.1f} dB rms (100 Hz-6 kHz), THD {100 * mu["thd"]:.0f}% '
                f'(capture {100 * m_cap["thd"]:.0f}%), gain gap {gap:+.1f} dB at drive '
                f'{drive if kind != "amp" else "-"}, level {dl:+.1f} dB vs {unit.cal["ref_pedal"]}')
        progress(line)
        hist.append({'err': err, 'curve': cu.tolist(), 'thd': mu['thd'], 'level': dl, 'line': line, 'gap': gap,
                     'fund': np.asarray(mu['fund_db']).tolist(), 'outs': np.asarray(mu['outs_db']).tolist(),
                     'noise_fund': mu.get('noise_fund_db'), 'noise': mu.get('noise_db'),
                     'drive': drive if kind != 'amp' else None, 'eq': list(p), 'trim': trim})
        if best is None or err < best[0]:
            best = (err, len(hist) - 1, list(p), e, drive, trim)
        return resid, dl, gap

    if kind != 'amp':                                   # phase 1: drive
        for k in range(5):
            resid, dl, gap = run(f'drive pass {k}')
            if abs(dl) > 3 and abs(trim - dl) <= 12.5:      # level first: a hot output clips further down the chain
                trim = float(np.clip(trim - dl, -12, 12))  # (D/A, line out) and fakes a softer clipper
                best = None
                continue
            nd = int(round(_drive_for(drive, gap)))
            if abs(gap) <= 1.5 or nd == drive:
                if nd == drive and gap > 3:
                    progress(f'  drive maxed: the capture has ~{gap:.0f} dB more gain than DIST/OD 100 (needs HOT / a boost)')
                break
            drive = nd
            best = None                                 # earlier drives don't count as a result
    else:
        resid, dl, gap = run('pass 0')
    for k in range(iters):                              # phase 2: EQ + level at the found drive
        p, e = F.fit_eq(fq, F.eq_db(fq, p) + 0.6 * resid)   # damped: the EQ also moves the clipping a little
        trim = float(np.clip(trim - dl, -12, 12))
        resid, dl, gap = run(f'tone pass {k + 1}')
    err, it, p, e, drive, trim = best
    r = F.make(name, kind, p, e, drive, base, m_cap, trim)        # the kept pass, gate back on
    r['report'] = list(r['report']) + [h['line'] for h in hist] + [f'refined on the unit: kept pass {it} ({err:.1f} dB)']
    r['refine'] = {'target': target.tolist(), 'passes': hist, 'best': it,
                   'cap_fund': np.asarray(m_cap['fund_db']).tolist(), 'cap_outs': np.asarray(m_cap['outs_db']).tolist()}
    return r


def main():
    """py -3.10 tz_loop.py calibrate [out_dbu] | synth [iters] | <capture.nam> [iters]"""
    import tz_capture as C
    a = sys.argv[1:] or ['calibrate']
    unit = Unit()
    print(f'audio {unit.dev}, MIDI {unit.min} / {unit.mout}')
    if a[0] == 'calibrate':
        calibrate(unit, float(a[1]) if len(a) > 1 else None)
        return
    if a[0] == 'synth':
        import tz_synth
        cap = tz_synth.SynthCapture()
    else:
        cap = C.Capture(a[0])
    m = M.measure(cap)
    r = F.fit(cap, m)
    print('\n'.join(r['report']))
    r = refine(cap, m, r, unit, iters=int(a[1]) if len(a) > 1 else 3)
    print('\n'.join(r['report'][-2:]))
    with open(os.path.join(HERE, 'last_refine.json'), 'w') as f:
        json.dump(r['refine'], f)


if __name__ == '__main__':
    main()
