# Cracking the GP-16 DSP (Toshiba TC23SC260AF-002 x3)

## What we have
- **Prior art:** github.com/ToddAWalter/roland-dsps lists our chip ("DSP", 1989, designer Naoya Nozawa; also in the
  RSP-550, JD-800, SE-50 and ME-10) with an **empty** page: nobody has cracked it.
- **Its successor is fully mapped:** the CSP (TC6088AF, 1992, same designer) has a documented format and an emulator
  verified on hardware.
  - 24-bit instruction + paired 16-bit coefficient, run once per sample.
  - Fields: b0-8 internal-RAM offset (circular buffer), b9-11 store target, b12-15 opcode (accA/accB load / accumulate
    / multiply / abs...), b16-17 multiplier shift, b19-23 external-RAM sequencer.
  - Two 30-bit accumulators; special registers for I/O and jumps.
  - Use it as the hypothesis template.
- **Our chip:**
  - 512 steps per chip; 24-bit instruction + 16-bit coefficient.
  - Coefficient **unity = 0x0800** (tap feedback and reverb measured by ear), and every stock gain tops out at 0x7FF.
    That points to a 12-bit fraction or a fixed >>11.
- **Static decode with the CSP layout fits only partly:**
  - Opcode 0 dominates; opcode 15 and store 7 are common.
  - b19 is set in about 30% of words, far too many to be the CSP's "start external-RAM access".
  - So it's an ancestor with its own layout.
  - Words with top byte 08-0B carry signed 16-bit values that look like **memory offsets**: Line Out bands -37 / -43 /
    -64, tap feedback +56, longer delays around -23000.
- **`dspdump.py`** gives the live program (all 1536 steps, instruction + coefficient + reg3 + the writing routine) from
  full-firmware emulation, in `out/dsp_program.txt`.
- **Coefficient map:** `out/coefmap.txt` says which parameter writes which step's coefficient.
- **Debug port** (SysEx cmd 01): writes any step's instruction + coefficient live on the unit.
- **`dsprig.py`:** log-sweep and impulse measurement over the OCTA-CAPTURE loop.

## Plan
### Phase 1: desk work (no hardware)
1. **Program dumps for many configurations**
   - One block at a time, parameter sweeps, each routing preset.
   - The diffs show which steps belong to which effect, the data path between blocks and chips, and how the
     firmware's routing code rewrites instructions.
2. **Label the program**
   - Per effect: coefficient steps (from the coefmap), the memory taps around them, plus recognisable structures.
   - A biquad EQ band = 5 coefficients + taps at -1 / -2 samples; a delay = a large offset + a feedback coefficient.
3. **Field hypotheses + disassembler v0**
   - Top-byte flags vs CSP opcode / store / shift.
   - Signed 16-bit memory offset in the low bits for memory ops.
   - Find the **input and output instructions** (audio in, inter-chip links, audio out).
4. **Emulator skeleton (Python)**, parameterised by those hypotheses, running the dumped program on a test signal.

### Phase 2: on the unit (needs the audio loop)
Wiring: OCTA-CAPTURE out 3-4 -> GP-16 IN, GP-16 OUT A -> OCTA in 5-6. Keep the volume low: wrong instructions can
make loud noise, but they can't damage anything (the DSP only computes).

5. **Coefficient format:** sweep a clean gain step (0, 0x100 ... 0x7FF, 0x800, 0x8000 ... 0xFFFF) to get scale, sign
   and saturation.
6. **Bit flips:** on a known step (Line Out gain, EQ band, tap), flip one instruction bit at a time and measure gain,
   delay and filter change. That maps every field.
7. **Delay offsets:** change a tap's 16-bit offset and measure the impulse delay. That gives the address unit and
   sample rate.
8. **Close the loop:** run the stock program in the emulator and on the unit with the same input; iterate the field
   semantics until the outputs match. Once they do, the ISA is cracked.

### Phase 3: new algorithms
9. **Assembler + loader:** the OS writes DSP programs at patch load, like the firmware already does.
10. **Targets:**
    - a real cab sim (multi-band or short FIR in spare steps: chip0 ~0x1C4-0x1FF, chip2 ~0x17D-0x1FF are unused);
    - cascaded gain stages (more gain than 0x7FF allows);
    - octave fuzz, ring mod, bitcrush;
    - a new reverb or freeze.

## Log
- 2026-10-13: roland-dsps found; CSP layout tested against our boot images (partial fit); `dspdump.py` written.
- 2026-10-13 (hardware, Focusrite loop: OUT 1 -> GP-16 IN, GP-16 OUT -> IN 1; debug port on the Focusrite MIDI):
  - **Loop:** clean OFF patch = -27.6 dB at 1 kHz, linear to -3 dBFS send, THD about -60 dB. Windows latency about 270 ms
    and different per stream, so all tests run inside one continuous stream (`dspscan.py` / `dspx.py` measure the tone
    onset first).
  - **Coefficient format (chip1 step 0x16E, a mix gain):** only the low 12 bits count, as a two's-complement fraction.
    - 0x7FF = +0.9995, 0x400 = +0.5, 0x000 = 0, 0x800 = -1.0, 0xC00 = -0.5.
    - The top 4 bits are ignored there: 0x1000-0x7FFF act like 0, and 0xF800 acts like 0x800.
    - "Unity 0x800" in older notes is really -1.0. Stock gains top out at 0x7FF = +1.
  - **Bus latches** (from the full firmware bus log):
    - 8000:0/1 = 16-bit field "A", 8000:2 = "B", 8000:3 = reg3, 8000:4/5 = coefficient, 8000:8/9/A = instruction.
    - Commit values seen: 0 (program load), 1 after A, 2 after B, 4 after reg3, 8 after the coefficient, 0x0C.
    - Commit 0 **also takes the coefficient latch**: rewriting a step with commit 0 and coef 0 zeroed its gain. So a
      commit probably takes every latch.
    - Writing steps with stale latches killed the audio until a pedal switch / reload.
    - Fixes: `dsplive.py` restores a step by re-sending every latch exactly as the firmware left it.
      `dspreplay.py` replays all 18,735 firmware bus writes over MIDI (about 70 s), which brought a dead unit back
      without a power cycle.
  - **Digital twin:** `ramdump.py` reads the unit's 64 KB RAM over the debug port. `dsptwin.py` boots the emulator with
    it: the edit buffer matches the unit, and it writes `out/dsp_live.json` plus `out/dsp_buslog.json`.
  - **Signal-path scan** (`dspscan.py`: each step replaced by 000000 and restored; results in `out/scan/`):
    - Full scans of all 3 chips restore exactly.
    - Path blocks:
      - chip0: 000-00F, 080-08F, 0F0-10F, 130-14F, 190-1CF;
      - chip1: 030-03F, 080-08F, 120-13F, 160-17F, 190-1BF, 1D0-1DF;
      - chip2: only 0B0-0CF and 0F0-0FF (the rest of chip2 = effects that are off).
    - chip0 step 000 `00003e` = audio input (removing it mutes everything). Low 6 bits look like a register number;
      0x3E/0x3F look like the audio I/O registers.
    - chip1 167-177 = output mix: two identical halves, 16B-16F (`0880ee c90080 c80030 14002d 00003e`) and 172-176
      (`0880f3 c90080 c80000 140032 00003f`). Each half is -6 dB of the output; 16E/167 coef 0x7DF = the mix gains.
    - Recurring pair `180000` + `00xxx1` (0:196/197, 0:1AA/1AB, 0:1B0/1B1, 1:195/196, 1:19E/19F, 1:1B9/1BA,
      1:1D6/1D7). Breaking one gives large boosts or cuts. Candidate: an external-RAM access with the address in the
      second word (bits 6-15?), like the CSP's b19-23 sequencer.
  - **Pair 1:1D6/1D7 (`180000` + `003d01`):** any change to the second word's low bits gives broadband noise
    (+40-60 dB residual), not a clean delay shift. Bit 16 (`013d01`) and `190000` change nothing. It's probably a
    memory-sequencer setup, not a tap address.
  - **Bit flips on 1:16E `14002d`** (MAC of register 0x2D into the output, coef 0x7DF; `dspx.py`):

    | Bits | Result | Reading |
    |---|---|---|
    | 0-5 | different signal | register number (0x2D -> 2C/2F/29/25/3D/0D) |
    | 6-18 | nothing | don't-care for this register op, including 0x14 -> 0x10 |
    | 19 (0x08) | gain 0 | source = memory at signed offset (low 16 bits = +45)? |
    | 20 (0x10) | step does nothing | multiply-accumulate enable / opcode bit |
    | 21 (0x20) | exactly x0.5 | shift right 1 |
    | 22 (0x40), 23 (0x80) | noise / distortion | opcode bits (0x54, 0x74, 0x94, 0xD4 all misbehave) |

    - Coefficient linearity confirmed again: coef 0x100 = 0.125 (-5.0 dB as predicted for this sum).
    - The delay readout (tone phase, 1024-frame blocks, latency 'high') is stable to +/-0.02 samples. Over/underruns
      shift it by whole blocks; `dspx.py` prints a warning when that happens.
- 2026-10-13, later (stereo loop: GP-16 CH1 A -> in 1, CH1 B -> in 2; `ir2.py` = stereo IR from one sweep):
  - **DSP sample rate = 32.0 kHz.** It falls out of the HI-EQ table at ROM 0x1CA9C: rows of 12 bytes = frequency in Hz
    (2000-8000, log) + 5 coefficients for 1:0B1/0B3/0B4/0B5/0B6.
    - It's a Butterworth HPF by bilinear transform **without prewarp**: K = pi*f/fs, a0 = 1 + sqrt2*K + K^2.
    - c0 = (1+sqrt2 K)/a0, c1 = -1/a0, c2 = (1-sqrt2 K)/a0, c3 = (1-K^2)/a0 = -a1/2, c4 = -a2.
    - All rows fit with fs = 31,980 (rounding).
    - The -a1/2 step (1:0B5) has top byte 0x49: bit 22 is probably a x2 shift.
    - HI gain (param 21) writes 1:0B9 = (sqrt(G) - 2)/8, i.e. shelving A = sqrt(G).
  - **Firmware setters:** descriptor table at ROM 0x1C396, 22 bytes per parameter: w0 = block<<8 | p, setter far ptr
    at +0x12. `coefsweep.py` calls one setter per value in the twin.
    - Unicorn caches translated code, so the stub needs a fresh address per call.
  - **Bus writes need care:**
    - The GP-16's MIDI receive ring is tiny. Bursts of debug-port writes lose bytes and give random wrong steps.
      Every tool now uses flow control (debug-port ping and wait every few writes, `dsplive.sync`).
    - Write steps the firmware's way: instruction, then the field latch ([1],[0] / [2] / [3]), then commit.
    - **Every commit takes every latch.** The coefficient latch is copied even on commit 1/4, so stale latches land in
      the step. `dsplive._send` sets all latches to the firmware's values first.
    - **Commit 1 = A replaces the instruction's 16-bit memory address.** Commit-1 steps carry their stock address in
      the ROM instruction word (2:0BD `0151a4` -> A 0x5200).
  - **Twin bug found and fixed: the timer interrupt.**
    - E83B:0C92 (ISR) bumps [A202], counts down RAM timers, then calls F2FC:3660 every tick.
    - A patch change first writes some block levels as 0: E980:05D6 calls the SDLY level setter with 0, saves the
      target in [A65E] and sets [A20A] bit 0x10. The ticks restore the level later (de-click / old-delay mute).
    - The emulator had no ticks, so the doubler level stayed 0.
    - `emu_tick.py` simulates ticks until [A20A] stays clear; `dsptwin.py` uses it.
    - Result: the twin state pushed to the unit (1,723 commits) gives exactly the real doubler (19.000 ms, -5.4 dB).
  - **Delay memory (doubler, 2:05A, `delaytest.py`):** A = absolute read address in samples @ 32 kHz.
    - Echo = A - 2100 samples exactly (+1 -> +1 sample, +-160 -> +-160).
    - That line wraps every 3,200 samples (100 ms).
    - The SDLY write address is 2100 (boot default A = 2101 = 1-sample delay).
  - **Host port:** 8000:(chip*0x400+6) is a DSP -> CPU readback (self-test E83B:0529). It reads 0x55 (the self-test's
    last value) and didn't respond to the self-test setup copied onto chip2 steps 0B/0E.
  - **Self-test (F2FC:183A, patched out in the emulator):** step 0B coef + step 0E reg3. reg3 0x28 = own value,
    0x0B = previous chip's: the chips form a ring, 0 -> 1 -> 2 -> 0.
  - **Routing:** EQ on changes 1:081 reg3 0x29 -> 0x33; doubler on changes 2:0C1/101 reg3 0x23 -> 0x25/0x27 and adds
    reg3 commits on 2:057/058/05E/061. reg3 = destination/source register, i.e. block routing.
  - **4-band EQ fully decoded** (firmware setters p20-p30 swept in the twin with `coefsweep.py`; laws checked on hw;
    `cabband.py` designs coefficients):

    | Band | Steps (chip 1) | Structure / law |
    |---|---|---|
    | HI | 0B1/0B3/0B4/0B5/0B6 + gain 0B9 | 2nd-order section (formulas above). Shelf gain = (G - 1)/4, G = 10^(dB/20). G = 0 (0xE00) makes it a **true 2nd-order low-pass**; any f and Q can be designed |
    | HM, LM | f 09C+0A0, 090+094; Q 07C, 07A; cut 089/088; boost 0A5/0A4 | Chamberlin SVF, f = 2 sin(pi fc/32k) at any frequency. Cut = (1/G - 1)/4, boost = (G - 1)/4. Q coef = 0.25/(1 + v/40) |
    | LO | f 0AC+0AF, gain 0BA | Same SVF and the same shelf law, but built as x + k*LP: G = 0 gives a dip plus a bump, not a clean high-pass |
    | OUT | 086 | 0.25*sqrt(G). Tied into the low path: x2 gave +6 dB above 1 kHz and -10..-17 dB below 200 Hz, so not a free boost |

    - Knob units: 4 per dB, v = 48 is 0 dB.
  - **Cab sim from EQ coefficients only** (GE-7 state, change vs flat):
    - Cab A (HI LP 4.5k Q1.2, LM 110 Hz +6, HM 1.4k -5, LO 70 Hz -12): +5.5 @100, -2 @1k, +2.7 @4k, -12.8 @8k,
      -34.7 @13k.
    - Cab B (5k Q1.6, 100 Hz +8, 1.2k -6): -8.2 @50, +7.9 @100, -4.3 @1k, +5.1 @4k, -32 @13k.
    - Designs must allow for the GP-16's fixed analog/chain response (about +4 dB lows, -8 dB at 10 kHz, base state)
      and leave the guitar/cable/amp-input coloration to the amp model, not the cab (user's note).
  - **Drive (RAT state):**
    - 0:110 coef = drive (4F3 stock). The instruction at 0:110 is irrelevant: replacing it with 0 changes nothing, so
      another step uses that coefficient.
    - 0x7FF gives +22 dB more distortion residual.
    - Shift-bit flips on 0:110 do nothing.
    - 0:12C/12D = tone, 0:130 (0x023) = dist output level, 0:133 = path gain.
    - A second multiply at 0:111 lowered the distortion.
    - More gain needs the pipeline/dataflow decode.
  - **Next:**
    - The pipeline: which instruction uses which step's coefficient (0:110's instruction is a don't-care).
    - Cab as an OS feature: write the coefficients after each apply via the firmware's E83B:0679 (chip 1 set_coef).
    - Map the write side of a delay line (which step writes at 2100).
    - EQ/biquad dataflow on 1:0A4-0BD with the HI band active.
    - Cab sim from custom coefficients in the existing EQ bands.
