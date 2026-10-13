# GP Tone Zone

Turns existing tone captures into Roland GP-16 sounds for JSW ROSETTA OS. No neural capture of its own: it reads
the formats that already exist and translates them onto the GP-16's own blocks.

- **NAM captures** (`.nam`, Neural Amp Modeler, e.g. from TONE3000): pedals and amps, WaveNet and LSTM, both old
  (0.5.x) and new files.
- **Cab IRs** (`.wav`).

## Setup (once)

1. You need Python 3.10 with numpy, scipy, torch, soundfile, matplotlib, mido and python-rtmidi.
2. Run `setup.cmd`. It installs NAM's own runtime (MIT, Steven Atkinson) into `tonezone/_vendor` only; nothing on the
   system changes.
3. Put your downloaded `.nam` / `.wav` files in `tonezone/captures`.

## Use

Start `GP Tone Zone.cmd`, then **Open folder**, pick a capture, and **Analyse**.

**What Analyse does**
- Plays a calibrated guitar through the capture: NAM's own DI clip plus synthesized riffs, peaking at about +2 dBu
  via the capture's `input_level_dbu`. Sines at levels from 60 dB below playing level up to playing level go
  through too.
- Measures the capture:
  - **clipping type:** clean, soft (OD) or hard (DIST);
  - **gain:** how far below playing level it already compresses;
  - **voicing curve:** its tone curve with a generic clipper's own tilt removed.
- Fits the GP-16's four EQ bands to the voicing using the firmware's real frequency tables (HI 2-8 kHz, HM
  500 Hz-4 kHz, LM 125 Hz-1 kHz, LO 60-250 Hz, Q 1-5).
- Picks DIST or OD and the drive, and sets the level so it sits with the OS's fuzzes.
- Shows the plot: dots are the capture's voicing, the line is the GP-16 EQ fit.

**Results**
- A drive capture becomes a **pedal** (A2) with knobs GAN, TON, MID, VOL.
- A clean amp or an IR becomes a **RIG amp** with knobs VOL, TRB, MID, BAS.

**Buttons**

| Button | Does |
|---|---|
| Push to GP-16 | Puts the sound into the unit's edit buffer over MIDI to audition it. The GP-16 must be on its patch screen (ESC twice from the OS) and on MIDI channel 1. WRITE on the unit stores it to a patch. |
| Save to library | `tonezone/library/<name>.json` |
| Add to OS build | Copies the sound to `re/tz_sounds/`. The next `re/build_all.py` lists it after the built-in pedals and amps; flash to keep it. Each sound takes about 115 bytes of ROM (there is room for about 10 now). Adding one resets stored knobs and board memories once. |

## Limits

- The GP-16 has one dirt block, a 4-band EQ and a simple cab filter, so captures land "in the family", not identical.
- The fit cannot hear the GP-16's own dirt block yet. With the audio loop wired (OCTA-CAPTURE out 3-4 -> GP-16 in,
  GP-16 out -> in 5-6) a later version will play the same DI through both and refine the settings on the real unit.
- SlimmableContainer ("A2") NAM files are not supported yet.

## Licenses

- GP Tone Zone is MIT, like the rest of the repo. The NAM runtime is MIT.
- Captures keep their own licenses (TONE3000 shows one per tone: cc-by, cc-by-nc, cc0...). Don't redistribute them
  or sounds derived from them against those terms. The repo ignores `captures/`, `library/` and `re/tz_sounds/`.

## Files

| File | |
|---|---|
| `tonezone.pyw` | the app (tkinter + matplotlib) |
| `tz_capture.py` | loads `.nam` (NAM runtime, old-file upgrade) and `.wav` IRs, runs audio through them |
| `tz_measure.py` | test signals, gain / clipping / voicing / loudness measurement |
| `tz_fit.py` | GP-16 EQ fit, dirt type and drive, level match, knobs (uses `re/pedals.py`, `re/level_match.py`) |
| `tz_gp16.py` | MIDI push (`re/pedals.py` SysEx), library, add to OS build |
