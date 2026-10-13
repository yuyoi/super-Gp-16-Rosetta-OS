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

### Format survey (2026-10-13)

| Format | Open? | Library | Use for us |
|---|---|---|---|
| **NAM `.nam`** (Neural Amp Modeler) | yes: JSON spec, MIT code | TONE3000 (ex-ToneHunt), very large, amps **and pedals** | **primary**: run it locally, measure, fit GP-16 blocks |
| Cab IR `.wav` | yes (plain WAV) | everywhere, TONE3000 too | cab / amp EQ: fit the 4-band EQ + LINE OUT filter (B6 amps) |
| AIDA-X / GuitarML Proteus (RTNeural JSON) | yes, no formal spec | smaller | secondary; community converters exist |
| Helix `.hlx`, BOSS `.tsl` presets | JSON, undocumented | big | translate by model name + knob values (no audio), later |
| ToneX, Kemper, Quad Cortex captures | no documented open format | big | skip (vendor-locked) |

**NAM details**
- `.nam` = JSON: `version`, `architecture` (WaveNet, LSTM, SlimmableContainer "A2", Sequential), `config`, flat `weights`,
  optional `sample_rate` (default 48 kHz).
- `metadata` carries what the translator needs to route a capture:
  - `gear_type`: amp / pedal / pedal_amp / amp_cab / amp_pedal_cab / preamp / studio;
  - `tone_type`: clean / overdrive / crunch / hi_gain / fuzz;
  - `gear_make` / `gear_model` (free text, e.g. "Ibanez" / "TS808" -> our TUBE SCREAMER as the starting point);
  - `input_level_dbu` / `output_level_dbu` (calibrated levels -> correct drive and loudness).
- Runtimes:
  - Python `neural-amp-modeler` (the reference, needs PyTorch);
  - Rust `nam-rs` (loads all architectures, light);
  - C++ NeuralAudio / NAM Core;
  - or our own numpy WaveNet/LSTM from the spec (`_export_weights` layout).
- TONE3000 API v1 (`https://www.tone3000.com/api/v1`):
  - search `/tones/search` with `gears=pedal|amp`, `format=nam|ir` and `makes`; model files via `/models?tone_id=` -> `model_url`;
  - OAuth 2.0 PKCE or a secret key, 100 req/min;
  - every tone carries a `license` (t3k / cc-by / cc-by-nc / cc0);
  - free tier = non-commercial only, which fits (free, MIT, the user downloads the captures, we never redistribute them).
  - Example app: github.com/tone-3000/t3k-api.

### How a capture becomes a GP-16 sound
1. **Route by metadata.**
   - pedal -> an A2 dirt recipe (plus EQ);
   - amp / amp_cab -> a RIG pair (dirt + an amp with EQ + LINE OUT);
   - IR -> amp EQ + cab;
   - `tone_type` picks the starting block: fuzz/hi_gain -> DIST, overdrive/crunch -> OD.
2. **Measure the capture** (render offline):
   - sine sweeps at several input levels -> small-signal EQ curve + gain / clipping curve (hard vs soft) + compression;
   - a DI guitar loop -> long-term spectrum + loudness.
3. **Fit**, using the GP-16's real tables:
   - EQ bands from the firmware Hz tables (4 bands + out);
   - drive from the gain curve, DIST vs OD from the clip shape, level from loudness;
   - LINE OUT bands for cab captures.
4. **Close the loop on the real unit (most accurate, no DSP emulator needed).**
   - The PC sets the parameters over SysEx, plays the same DI through the GP-16 (OCTA loop), records, compares with the NAM output and nudges the parameters.
   - It repeats until the error stops falling.
5. **Output:** a USER pedal / amp recipe with knobs (loaded over MIDI, see 3), or baked into the ROM list.

### Recordings (fallback)

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

## Status 2026-10-13: GP Tone Zone v0.1 built (`tonezone/`)
- Reads NAM (WaveNet/LSTM, old 0.5.x files upgraded) through NAM's own vendored runtime, and cab IR WAVs.
- Measures clipping, knee gain, voicing (minus a generic clipper's tilt) and loudness; fits the GP-16 EQ from the firmware tables.
- Pushes to the unit over MIDI; saves to the library; Add to OS build (`re/tz_sounds/*.json`, merged by gen_pedal_data).
- Tested on NAM's example captures; the push was tested against a fake unit only. The hardware audition and the loop refine are next.
