# GP-16 PC tone app: emulator VST + tone matcher + loader (idea, 2026-10-13)

**Goal:** record a tone, have the PC turn it into a GP-16 sound, audition it in a DAW as a VST, then load it into the unit.

```
 tone recording ──► TONE MATCHER ──► GP-16 patch / OS pedal recipe ──► LOADER (MIDI SysEx) ──► GP-16
 (DI + target)          │  ▲                                              │
                        ▼  │ fits params by listening                    ▼
                    GP-16 EMULATOR (core) ──► VST3 in Cubase       library: save / push / pull
```

## 1. GP-16 emulator (the core)

The GP-16 can only make what its blocks can do, so the matcher needs a model of the GP-16 itself, not a neural capture.

**Model A: block model (first, usable soon)**
- Each block is written as DSP code in C++/JUCE, with a Python prototype first: comp, dist/OD, picking filter, step phaser, 4-band EQ, gate, short delay, chorus/flanger/pitch/SPACE-D, pan/trem, tap delay, reverb, line-out filter. Routing follows the order bytes.
- **Known exactly from the ROM:**
  - EQ centre frequencies (tables at DS:304C/31E0/3374), Q 1.0–5.0, ±12 dB in 0.5 dB steps.
  - Delay times in ms.
  - The drive and line-out knob laws (value × 20 + 47).
- **Calibrated against the real unit** with the loop rig (`re/dsprig.py`, OCTA-CAPTURE out 3-4 → GP-16 → in 5-6). Sweeps, noise and impulses per parameter fit the clipping curves, comp timing and filter shapes.

**Model B: exact emulator (research path)**
- Run the GP-16's real microcode: 3 × TC23SC260 DSPs, 512 steps each, boot images in ROM at 1A750/1ADC8/1B4C4.
- The coefficients come from running the real V25 firmware. `re/emu_v10.py` already boots it in unicorn.
- Needs the TC23SC260 instruction set. Prior art: giulioz/roland-dsps (same chip family as the SE-50, RSP-550 and JD-800).
- **Payoff:** a bit-exact GP-16 VST. The same work also unlocks new algorithms on the hardware (a real cab sim, gain beyond 0x7FF).

## 2. Tone matcher: translate existing formats (user: do NOT reinvent neural capture)
- Inputs are premade, existing formats: NAM captures (.nam, e.g. ToneHunt), cab IRs (.wav), modeler presets (e.g. Helix .hlx JSON).
- NAM / IR: run test signals through them on the PC (NAM's own runtime), measure EQ curve, gain/clip curve and dynamics, then fit GP-16 blocks.
- Presets: map model names + knob values onto our pedal recipes (e.g. a TS model -> TUBE SCREAMER knobs).
- Recordings (fallback):

- **Best input:** a matched pair, your DI plus the target played the same way (re-amp, or play along with the record).
- **Recording only:** match the long-term spectrum, dynamics and harmonic profile against your own DI of the same riff.
- **Search:**
  - Patch bytes are discrete (on/off, order, 0–100 values), so it uses CMA-ES or a genetic search over the emulator.
  - If the block model is written differentiably, gradient descent refines the result.
- **Loss:**
  - multi-resolution STFT plus loudness and envelope (comp/sag);
  - an optional "keep it musical" penalty (no extreme EQ);
  - search space can be locked to chosen blocks.
- **Output:**
  - a stock GP-16 patch (114 bytes);
  - or an OS pedal recipe (SysEx pairs plus macro knobs), so it becomes a real pedal with knobs.

## 3. Loader / librarian ("PC-based translator")

- **Stock patches:** RQ1/DT1 SysEx, already working on hardware (`re/pedals.py`, `re/gp16poke.py`). The app gets push, pull, a library, and A/B against the VST.
- **New sounds into the OS without burning:** add a USER 1-8 pedal area in battery RAM (DS B700+ is free and verified unused by stock).
  - The PC writes recipes there through the debug port's memory-write command (06), which is already in the firmware.
  - The OS lists them as USER pedals in PEDAL, RIG and BOARD mode.
- The ROM pedal list stays for the curated sounds; USER slots are for matched or experimental ones.

## Phases

| # | What | Needs | Size |
|---|---|---|---|
| 0 | done: SysEx read/write, full-firmware emulation, patch map, EQ tables | | |
| 1 | Librarian + loader GUI (Python), USER 1-8 slots in the OS | small OS change, burn once | small |
| 2 | Block-model emulator (Python prototype, then JUCE VST3), calibrated on the unit | audio loop wired | medium |
| 3 | Tone matcher (CLI, then in the app) | phase 2 | medium |
| 4 | Exact emulator (TC23SC260 interpreter + V25 firmware) | instruction-set decode | large / research |
| 5 | New DSP algorithms back to the hardware | phase 4 | research |

## Limits

- One dirt block, one 4-band EQ and a simple cab filter cap how close a match can get. Big amp-stack tones will be "in the family", not identical.
- Phases 4-5 are what lift that ceiling.
- No IR or neural model runs on the GP-16 itself; the PC does the heavy lifting and the unit gets parameters.

## Notes
- SysEx is parsed while the OS screens run: service F6A1:03BC calls the parser EE11:0C82, so the debug port (memory write cmd 06) can fill USER slots without leaving the OS.
- Build order agreed: v2 voicings first (stable, not over-modernized), then loader + USER slots.
