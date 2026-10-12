<p align="center"><img src="https://raw.githubusercontent.com/yuyoi/Rompler-RosettaRom/main/assets/logo.png" width="360" alt="Rosetta"></p>

# Super GP-16 Rosetta OS

> **Runs on real hardware.** v0.8 (pedal + rig modes) runs on a real Roland GP-16 from a flash chip in the IC11
> socket. v0.9 (board mode) passes full-firmware emulation; its first hardware burn is next. See [Status](#status).

A new OS for the Roland GP-16 guitar processor: the rack becomes **one pedal with real knobs**, a **pedal + amp rig**,
or a **12-slot pedalboard**, played from the front panel with no patch list in the way. It patches your own IC11 dump
(NEC V25 code) and runs on the stock DSPs, so the sound is the GP-16's own blocks, voiced like the classic pedals.

Part of the Rosetta family, after [Rosetta ROM](https://github.com/yuyoi/Rompler-RosettaRom) and the
[D-110 Rosetta OS](https://github.com/yuyoi/D110-rosetta-OS-v11).

## What it does

- **Boots as the pedal.** Power-on goes straight to the last mode you used (PEDAL, RIG or BOARD).
- **PEDAL mode:** pick one of 39 pedals; the GP-16 becomes that pedal.
- **RIG mode:** one pedal into one of 7 amps (amp = EQ + cab sim + comp voicing).
- **BOARD mode (v0.9):** a pedal in every GP-16 block. Each pedal grabs the extra blocks its voicing needs (a Tube
  Screamer takes the EQ, a Leslie takes the tremolo) when they are free. Chain-order presets, and an **A/B/Y box**
  for the outputs.
- **Real knobs.** Each pedal and amp shows its own knob names (`DRV TON LVL`, `VOL TRB BAS`...), 0-10 in half
  steps, up to 4 per screen. Knob moves are live, through the firmware's own parameter setters (no patch reload).
- **Boot dragon:** an 8-frame flying dragon replaces the stock running man at power-on.
- **LINE OUT FILTER knobs** get a dB law with a true OFF at 0 (stock never fully cuts a band).
- **SysEx debug port** (MIDI ch 1): DSP coefficient writes and memory read/write from a PC (`re/gp16poke.py`).

### Pedals (39) and amps (7)

| Slot | Pedals |
|---|---|
| A1 COMP | DYNA COMP, CS-3 COMP |
| A2 DIRT | TUBE SCREAMER, RAT, DS-1, BIG MUFF, METAL ZONE, SD-1, KLON, FUZZ FACE, METAL MUFF, FUNERAL, IRON MAN |
| A3 WAH/FILTER | TOUCH WAH, CRYBABY WAH, RESO WAH |
| A4 PHASER | SLICER, PHASE 90 |
| A5 EQ | GE-7 EQ |
| A6 GATE | NS-2 GATE |
| B1 SHORT DELAY | DOUBLER, SLAPBACK |
| B2 MOD | PITCH/OCTAVE, CHORUS CE-2, DIMENSION D, FLANGER, LESLIE |
| B3 TREM/PAN | AUTOPAN, TREMOLO |
| B4 DELAY | DIGITAL DLY, SPACE ECHO |
| B5 REVERB | SPRING, HALL/PLATE, SHIMMER, CATHEDRAL, CAVE, CHURCH, STAGE, AMBIENT |
| B6 AMP/CAB | CLEAN, TWIN, JCM800, AC30, DOOM, DI / FLAT, RADIO |

FUNERAL is a doom fuzz, IRON MAN is an early-Iommi voicing, RADIO is a germanium transistor radio. The voicings are
recipes in `re/pedals.py` (SysEx parameter values), the knobs in `re/gen_pedal_data.py`. Knob list per pedal:
[`PEDAL_MODES.md`](PEDAL_MODES.md).

## Controls

| Where | Key | Does |
|---|---|---|
| anywhere in play | **SYSTEM** | split screen `UP:PEDAL DN:RIG / EDIT:BOARD` |
| split screen | FUNCTION up / down / **EDIT** | PEDAL / RIG / BOARD mode |
| split screen | SYSTEM again | the stock System menu (all stock settings kept) |
| any mode | **ESC** | back to the split screen; ESC again = stock patch screen |
| knob screen | buttons **1-4** / **5-8** | knob 1-4 up / down (one column per knob: 1 and 5, 2 and 6...) |
| knob screen | dial | moves the knob touched last (marked `*`) |
| PEDAL / RIG | FUNCTION | next / previous page (knobs, amp knobs, pick pedal, pick amp) |
| pick pages | dial or BANK / GROUP | previous / next pedal or amp |
| BOARD | FUNCTION | next / previous slot: A1 COMP ... B6 AMP, then ORDER, then OUT |
| BOARD slot | BANK / GROUP | previous / next pedal for that slot (OUT = empty) |
| BOARD slot | buttons + dial | that pedal's knobs |
| BOARD ORDER | 1 / 5 | A chain: WAH>DIRT, DIRT>WAH, PHASE>DIRT |
| BOARD ORDER | 2 / 6 | B chain: STOCK, TREM LAST, REV>DELAY |
| BOARD OUT | 1 / 5 | A/B/Y box: AMP 1 (CH1), AMP 2 (CH2), BOTH |

A slot whose block is borrowed shows `<NAME>` of the pedal using it and refuses a new pedal until that pedal changes.
The gate stays last in chain A and the amp/cab last in chain B (the GP-16 fixes those positions). Board mode keeps
one live board; knob positions are remembered per pedal and amp in battery RAM.

## Build and burn

You must supply your **own IC11 dump**. It is Roland's copyrighted code and is not in this repo. The tools refuse
anything other than the "Super GP Ver 1.0" ROM (MD5 `ac5f56bcb3d8c30ddf3f1ffe88b13556`).

1. **Read IC11** (128 KB, 32-pin DIP mask ROM) on a programmer such as a T48 and keep the original chip:
   ```
   minipro -p AM27C010@DIP32 -y -r ic11.bin
   ```
2. **Build** (Python 3.11, `pip install capstone`, [NASM](https://www.nasm.us/) 2.16):
   ```
   cd re
   py -3.11 build_all.py ../ic11.bin
   ```
   This writes `re/build/gp16_mod_v0_9.bin` (128 KB) and `re/build/gp16_mod_v0_9_sst512k.bin` (the same image 4x).
3. **Burn** the `_sst512k` file to a 512 KB flash (SST39SF040, or AMIC A29040 for chips that ID as `0x3786`), read it
   back and compare:
   ```
   minipro -p SST39SF040 -w gp16_mod_v0_9_sst512k.bin
   ```
4. **Fit it in IC11** (notch the same way). The GP-16 board already ties pin 31 high, so the flash drops straight in:
   no wires, no cuts. Put the original chip back any time.

The first boot after a new version resets the stored knob positions and the board (the pedal tables changed).
Please don't share patched `.bin` files: share this repo.

### Test in emulation first (optional)

`pip install unicorn capstone`, then run the whole firmware, boot to the main loop and a scripted front-panel session:
```
py -3.11 -I emu_v08.py build/gp16_mod_v0_9.bin    # pedal + rig modes, live knobs
py -3.11 -I emu_v09.py build/gp16_mod_v0_9.bin    # board mode: grabs, order, A/B/Y
```
Both print `PASS`.

## Files

| File | |
|---|---|
| `re/build_all.py` | one-shot build from your dump |
| `re/build_mod.py` | applies every patch (each checks the original bytes first) and places the new code |
| `re/pedal_menu.asm` | the PEDAL / RIG / BOARD OS (NASM, x86-16, runs at ROM 0x0A00) |
| `re/pedals.py` | pedal and amp voicings as SysEx recipes |
| `re/gen_pedal_data.py` | knobs, board slots and the recipe -> internal-buffer mapping (read from your dump) -> `pedal_data.inc` |
| `re/dragon_boot.asm`, `re/dragon_vec.py`, `re/dragon_frames.bin` | boot dragon routine and art |
| `re/backdoor.py`, `re/gp16poke.py` | SysEx debug port (ROM side + PC tool, py -3.10 + mido) |
| `re/emu_menu.py`, `re/emu_v08.py`, `re/emu_v09.py` | full-firmware emulation tests (unicorn) |
| `re/gp16dis.py`, `re/entries.py`, `re/coefmap.py`, `re/instrmap.py` | V25 disassembler and DSP-write analysis |
| `re/dsprig.py` | audio measurement rig for the DSP instruction-set work |
| `re/GP16_RE.md` | ROM map, CPU/DSP memory map, parameter tables, key map, LCD, how each mod hooks in |
| `PEDAL_MODES.md`, `GP16_NOTES.md`, `FILTER_REBUILD_IDEAS.md`, `re/OS_DESIGN_v04.md` | design notes |

Disassembling your dump: `py -3.11 -I gp16dis.py ../dumps/gp16_u1_ic11.bin out` writes `re/out/listing.asm`. The
listing is derived from Roland's code: keep it private.

## Status

| Ver | | Hardware |
|---|---|---|
| 0.1 | boot banner + LINE OUT FILTER dB knob law | works |
| 0.2 | SysEx debug port: live DSP coefficient writes | works |
| 0.3 | 16 factory presets kept (A1-1..A2-8, a factory reset repeats them), frees 12.7 KB for new code | works |
| 0.4 | debug port: memory read/write | built |
| 0.5 | boot dragon | works |
| 0.6 | first PEDAL/RIG menu | failed (wrong key, wrong buffer map), replaced by 0.7 |
| 0.7 | PEDAL/RIG through the firmware's own setters | burned |
| 0.8 | rack as one pedal: real knobs, boots into the pedal | works |
| 0.9 | BOARD mode, 9 new pedals, A/B/Y box | emulation PASS, hardware next |

Known: on one unit the LCD contrast comes up low on about 1 in 5 boots and is fine after a proper power cycle. The
mod never writes the contrast setting; v0.9 re-sends it at the end of boot.

## TODO

- [ ] Hardware test of v0.9 board mode.
- [ ] Tune every voicing by ear into a real amp.
- [ ] Hold-to-repeat on the knob buttons.
- [ ] Save boards to slots (now one live board).
- [ ] Crack the TC23SC260 DSP instruction set: new algorithms, a real cab sim in place of the LINE OUT FILTER.

## Credits and legal

- **Made by JunkSmithWizard (JSW) together with Claude (Anthropic's AI).**
- Roland, BOSS and GP-16 are trademarks of Roland Corporation. This project is not affiliated with Roland. No ROM data
  is distributed here: you read your own chip and the tools add the new bytes to your dump.
- Pedal and amp names describe the sound each voicing aims for. They are trademarks of their owners; these are GP-16
  block settings, not models of those circuits.
- MIT licensed (see `LICENSE`).
