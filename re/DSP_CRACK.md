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

## REVERSE (2026-10-13): write forwards, read backwards
- **Pitch shifter (B2 MOD, PITCH):** one oscillator step 1:152 `008008`, coef = 2048 * (1 - ratio) (ROM table DS:355A,
  2401 entries = -12..+12 st in cents; -12 st 0x400, +12 st 0x800). Measured: coef 0x400 -> 221 Hz, 0x200 -> 331 Hz
  from 440. `008008` is an oscillator with its own phase (1:163 tremolo is the same instruction); copies elsewhere are
  idle oscillators; no shift bits (sweep of all 24 bits: only bits 0-3 and 19 matter, both stop it); coefficient top 4
  bits ignored. Read heads: depth steps 2:003 `51ffcf` and 2:01b `51fe0c` (coef 0x7FF in pitch mode; halving both
  -> 385 Hz exactly). The B2 block is ONE modulated-delay program for chorus / flanger / pitch / Dimension (0
  instruction rewrites between them). Read speed caps at 1x -> no reverse inside the DSP so far (needs 2x).
- **Tap delay C tap:** chip 2 step 0x072 `00ffff`, read address = A field, A = 0x69FF + 32 * ms (0x69FF..0xFFFE =
  0..1200 ms; 1 unit = 1 sample). Written by commit 1.
- **Commit 1 takes only the A latch:** with the instruction, coefficient, B and reg3 latches poisoned (0), A + commit 1
  moved the echo 302 -> 502 ms, level intact (`committest.py`). So an address move = 3 bus writes ([1], [0], commit).
- **CPU-driven reverse works** (`rev_isr.asm` + `revload.py`, hot-loaded into RAM 06C0:0000 over the debug port,
  timer 0 / vector 28, no burn): the read address grows 2 per DSP sample, so the read head runs backwards. v2 follows
  real time (timer 1 count * k, k = 2 * 32000 / 1333333 * 65536 = 3146), so dropped ticks don't change the speed:
  a 440 Hz tone comes back at exactly 440 (v1, tick-counted, gave 113 Hz = quarter speed). A decaying ding comes back
  as a rising swell with a hard cut (chunk 250 ms). REVERSE VERB = B order REV>DELAY (6,7,8,10,9) + hall into the tap.
- **CPU limits:** V25 8 MHz, timer clock 8 MHz / 6. Ticks delivered: 99% at 4 kHz, 93% at 7.9 kHz, 63% at 15.9 kHz
  (the ISR + busy bus). At 8-16 kHz the main loop slows enough that long debug-port messages (peek, RQ1) are lost;
  ping still answers. Next: slimmer ISR (register-bank interrupt, no mul), crossfade at the wrap (second tap), then a
  REVERSE DELAY / REVERSE VERB pedal in the OS (far code in the v2.7 free space).
- **Timer 0 is free** (TMC0 0x50 stopped, TMIC0 masked, vector 28 = dummy IRET); timer 1 = MD1 0x535 (1 kHz system tick,
  vectors 29/30, TMIC1/TMIC2 priority 7). P0 bit 0 toggles fast (candidate DSP end-of-sample line, unconfirmed).
- **REVERSE v5 "locked" (`rev_lock.asm`, `revlock.py`, `vec_stubs.asm`):** back-to-back commits complete exactly every
  2 DSP frames (`clocktest.py`: 41.69 timer counts = 31.98 kHz), so the fastest address update is every 2 frames;
  timer 0 is phase-locked to the busy flag. The firmware's 1 ms ISRs (vectors 29/30) kept their ISPR bit set for their
  whole run and the V25 then took no other interrupt at any priority: 14% of the ticks were lost (pitch sank). RAM
  stubs FINT first, then jump to the stock ISR: 16,064 ticks/s, zero loss. Remaining artifact: the read head steps
  +1/-3 -> a mirror at 16 kHz - f, ~25 dB under the signal, which no stock filter removes (the tap's cut filter sits
  before the delay line). P0.0 is not the DSP frame clock.
- **Tap delay block 0x0E params:** p53 C time (2:072 commit 1), p54/55 L/R time, p56 C level, p57 L level, p58 R level,
  p59 feedback, p60 cut filter (setter E980:34D8 writes 2:089/08A/08B from a table: those are the cut filter, NOT the
  wet return as noted above). C level writes 2:076 + 2:07C (instr 090038), coef = level * 1024 / 100.
- **On 2:076/07C the coefficient acts as 11-bit:** 0x400 (level 100) = full scale, 0x7FF wraps to ~0 (wet -32..-40 dB
  on the loop), 0xC00 == 0x400. No wet boost from that coefficient. 2:075 (R-level MAC, instr 09ffc0) feeds output A.
- **One shared commit pipeline (2026-10-14, `chippar.py`):** back-to-back commit 1 to unused steps, waiting for busy
  each time: chip 2 only, chip 2/chip 0 alternating and chip 2/chip 1 alternating all take exactly 2 frames per commit.
  The instruction/coefficient/A latches are shared by all three chips, so the gate array serializes every commit:
  no extra read heads by spreading them over chips.
- **Pitch shifter depth steps 2:003/2:01b (`pitchx2.py`, loop, PITCH -5 st = 330 Hz):** the depth coefficient is a
  linear scale on the oscillator's delay rate (0x7FF -> 330 Hz, 0x400 -> 385.6 Hz exactly). Bits 21 and 22 do nothing
  on these steps (they are x0.5 shifts in the 14 and 09 families, not here). Bit 20 or 19 breaks the modulation
  (418/242 Hz). Bit 23 splits it into two pitches (358/296 Hz at 0x7FF, 412/358 at 0x400): probably the crossfade
  window, not a gain. So the shifter's delay rate = oscillator coef (max ~1.0) x depth (max 1.0) caps at 1 sample per
  sample: no native reverse from it. The way left: a custom program in chip 2's free steps (~0x17D-0x1FF) whose read
  offset is the SUM of two oscillators (2 samples per sample). That needs the modulated-read decode (how 2:003 takes
  the oscillator output as its address offset).

## DSP-NATIVE REVERSE FOUND (2026-10-14, `pitchmap.py`, `flipscan.py`, `delayscope.py`, `twin_apply.py`)
- **Tools:** `twin_apply.py` = emulator twin of a patch pushed into the edit buffer (boot, copy buffer, call
  F00E:0764 + F6A1:0382 directly). `pitchmap.py` = write / measure / exact-restore loop (440 Hz in, wet peaks out).
  `delayscope.py` = click train in, each output click's position = each read head's delay; `seq()` changes steps
  mid-stream (Windows gives every new stream a different latency, so compare only inside one stream; audio must run
  on the main thread, MIDI writes in a helper thread).
- **Commit 8 is NOT instruction + coefficient only:** writing 1:154 with commit 8 and stale latches broke the
  oscillator path until an exact `dsplive.restore`. Always poke through `dsplive.poke/restore` (exact latches).
- **Shifter structure (PITCH, wet only):** oscillator chip 1 1:14E-1:157; 1:155 `090000` / 1:156 `880000` are
  memory ops: the phase lives in delay RAM between samples. Heads on chip 2: load phase (2:002/2:01A), x depth
  (2:003/2:01B, plain 12-bit signed, no range bits), special regs 0x3D (2:004/01C), 0x3C (2:006/01E, kills output),
  0x38 (2:00B/023, interpolation, loud garbage if changed), 4 reads 2:00C-00F / 2:024-027. reg3 of 2:003/2:01B =
  destination register (0x1F there folds head 2 into a triangle: 221 Hz component, not a real x2).
- **1:154 `01001f` bits 16-17 = scale of the stored phase increment: 01 = x1, 11 = x(-1), 00 = x0 (stops),
  10 = x(-2).** Bits 6-15 add a constant rate (+v/2^18). So rate = -2 * osc * depth with `02001f`:
  osc 0x100 -> 549 Hz, 0x400 -> 878, 0x7FF -> 1315 (rate -2). **osc 0x800 (-1.0) -> rate +2.0 = REVERSE at pitch**
  (435 Hz from 440; ~1% slow, trim via the bits 6-15 add). 0xA00 -> 216 Hz (reverse octave down), 0xC00 -> freeze.
  Delay scope confirms slope 2. Demo: `out/dsp_native_reverse_demo.wav`.
- **Limit: window W = 2048 samples (64 ms).** Address offset = phase x depth x 1024, no scale bits found on
  2:002-2:004/2:006/2:00B. Reversed grains = W/2 = 32 ms -> granular "micro reverse", not a reverse delay.
- **2:017 `0114b5` A field = shared base read address of both heads** (A +320 -> both heads +10 ms, exact). A +3200
  reads another block's memory: the B2 line is ~100 ms. A clone of 2:017 at 2:007 did nothing (base path unknown).
- **Long-grain plan:** per-head bases + the CPU hops each head's base by +W at that head's wrap (head faded out), ~60
  writes/s; grain change = hop the silent head to the new grain (native 16-32 ms crossfade); memory = point the base
  into the tap line (0x69FF+). Needs: how the base enters each head, frame-exact wrap timing (commit chain = 2
  frames), routing so the tap line holds the dry signal.
- **Long grains: BLOCKED (2026-10-14, `dspx.py` phase readout, oscillator frozen):** 2:017 is the B2 line's WRITE
  (zeroing it with commit 8 kills the wet; A +4 -> delay +4 samples exactly). The head reads (2:00C-00F,
  2:024-027) ignore their A fields (A 0 -> 4: no delay change); they use only the modulated address register
  (phase x depth, a Q23 fraction mapped to +-1024 samples, no scale bits on 2:002-2:006/2:00B). So per-head offsets
  are capped at +-W/2 and the only 16-bit address in the shifter is the shared write: no per-head base hops, no
  unbounded grains. DSP-native reverse = micro reverse (32 ms grains) only. The long reverse stays CPU-driven
  (tap 2:072). Ideas that remain: a DSP 2-sample average after the tap (zero at fs/2 kills the 16 kHz - f mirror
  ~11-20 dB under 3 kHz content), fades via the 1 ms stub + firmware set_coef.
- **Tool notes:** delayscope clicks need main-thread audio; peak thresholds must be robust (percentile) because
  write bursts make noise; with a moving head the mod-T plot aliases. `dspx.py` (tones, phase delay +-0.02 smp,
  one stream) is the reliable delay meter. `dsplive.poke` on a step whose last commit was 1 sends commit 1 (A only):
  pass commit=8 / 0 to really change the instruction.

## Borrowed memory: the reverse gets 2.05 s (2026-10-14, `mem2s.py`, `memtest.py`)
- **Memory op encoding (chip 2 only; chips 0/1 have no DRAM addresses):** address = instruction low 16 bits (commit 1
  replaces just those). **Bit 17 = write** (classes 02/03/0A/0B/12...): tap input write **2:092 `0369ff`**, doubler
  2:05D `020834` (2100), pitch line 2:039 `0314b4`, reverb 2:0B6-2:136, modulated writes 2:041/048/0C0/0CC/0D7.
  Class 00/01 = reads: tap reads 2:069 (L), 2:06C (R), 2:072 (C), all set by E980:12E8. (My first guess "01 = write"
  was wrong: 2:017 `0114b5` is a B2 step whose A moves both heads, not the write.)
- **Trick:** silence every chip-2 write into 0x0100..0xFFBF except the tap's (17 steps), move the tap write to 0x0100
  (and the L/R reads to 0x0101), engine BASE = 0x0100. Click test over the loop: echoes at 800.1 / 1150.1 / 1300.1 /
  1600.1 / 1900.1 / 2000.1 ms for 800..2000 set, level flat (-6.2 dB vs dry), no foreign content (junk = leftover
  feedback repeats, -27 dB after a pause). Kills reverb/mod/doubler in that patch; any patch push undoes it.
- Reverse at 1/4 = 92 BPM (652 ms chunks, A 0x0120-0xA411) now fits: `mem2s.rev(io, 651.77)`.
- **Dry kill attempt (2026-10-14, `drytest.py`, static C tap 300 ms, click per step, chip 2 060-0AF):** no single
  step carries the dry. Wet-only killers: 2:070/071/072 (C tap read), 2:078 `14002e`, 2:07E `14002c` (each kills
  the whole echo: in series). Dry -6.0 dB exactly when 2:075 `09ffc0`, 2:07B `09fff9` or 2:07D `090038` is zeroed
  (coef 0 on all three: the instruction, not a level). 2:073/2:079 `000023` -> any MAC/load variant: +35 dB blow-up.
  So the echo is added into a signal that already holds the dry; a wet-only mix needs the register/acc dataflow
  of 2:073-2:07E decoded. Gotcha: `D.restore` of 2:072 puts the tap back to the patch time, so scans must skip it
  or re-set the static tap after it.

## Fades round 2 (2026-10-14): what we learned the hard way
- **Commit 1 takes the instruction latch's top byte, not only A.** `committest.py` poisoned the latches with 0, which is
  the C tap's own class (00), so it looked like "A only". Any other DSP write leaves its own top byte (firmware
  setter, fade level 09, debug poke) and the engine's next commit 1 turns 2:072 into that class: the wet vanishes
  (and stays gone across patch reloads until something rewrites the latch). Fix: write [8000:A] = 00 before each
  commit 1 (engine v7/v8) or `rk7.tap_latch()` before resuming. Proven: wet -40 dB -> -6.7 dB just by that.
- **Commit 8 ignores the A latch** (2:076 rewritten with A latch 5A5A: echo unchanged).
- **Engine-ISR level writes hang the unit, latch fix or not** (v8 = v6 + latch reset hung at the first fade). The
  hang scrambled half of battery RAM; `ramrestore.py` + the 06:00 dump brought most back. MISSED first time: the system block DS 9D00-9D05 + 9D78-9E78 (MIDI ch, PC maps; boot loads it via F6A1:0006 -> F00E:1E78, F00E:22A0 masks ch &0x0F) + live PC maps A0F4/A182 + A42C: boot looked odd, MIDI ch came back 3. Added to ramrestore.py. B800-CE1F / AB19-AFFE / D000-DFFF also scrambled but = unused SRAM noise / stack: left alone. Hard rule stands.
- **Pedal-tick fades (v7, vector 30 stub, IE=0, timed busy waits) never hung** (100s of writes), but: (1) with IE=0
  for the whole tick the engine lost ~1 update/ms (6% slow, 1 kHz wobble = the user's "Zelda pitch dancing") -> STI
  first; (2) the engine keeps the bus busy almost continuously, so a fade write must wait inside an exclusive window
  and the read head stalls a few updates per write: on a sweep the fades measured worse (+21 dB bursts) than no
  fades (+9..14 dB). 1 ms level steps are also coarse (zipper). Open: a single exclusive write per step with the
  engine skipping exactly one update, or crossfading between two taps instead of ramping a level.
- Measuring traps: the loop must be in (check the dry level first); Windows latency changes per stream; drive 70
  makes a steady tone's HF floor -27 dB, which hides clicks; a steady sine hides chunk-jump clicks (use a sweep).
- **3rd hang (2026-10-14):** v7 engine running (address writes only, fades off), user pressed ESC to leave PEDAL mode
  -> hung, debug port dead. Turning a knob with the engine on had not hung (stock knob path masks TMIC2); the mod menu
  path apparently writes the DSP without masking TMIC2, so the engine commit lands inside its write. Rule: RL.stop
  before anyone touches the front panel.

## 100% WET HUNT round 2 (2026-10-14, `drytest.py` + `out/dsp_buslog_rev2.json` = old rev log + fresh apply twin)
- The first chip-2 dry scan was wrong from 2:072 on: restoring 2:072 put the patch's 10 ms C time back, so "wet" (300 ms
  window) read the floor. Rescan 2:073-08F with a valid wet: `out/dryscan_chip2b.txt`.
- Chip 1 output mix 1:160-17A (`out/dryscan_chip1.txt`): no dry-only step. 1:169/1:170 (`54002b`/`540030`) cut dry 3/5.5
  dB alone but both together blow up (+13..+19 dB, filter states). 1:179 (`180000`) zeroed = +29 dB and its restore
  left the unit +25 dB hot until re-restored (dsplive.restore 1:179 + 1:17A): avoid that pair.
- Chip 2 mixer, two halves: A = 073-078 (`000023 01ffdc 09ffc0 090038 08001d 14002e`), B = 079-07E (`000023 01ffc0
  09fff9 090038 090038 14002c`). 2:076/07C = C level (coef 0x400). 08 family = store acc to register (077 -> reg 1D;
  swapping 077 to reg 38 overwrote the tap register). 2:101 `180023` = writes the block input into reg 23.
- **Half B dry removed: 2:079 `000023` -> `000038`** (load the C tap register instead of the input): dry -6 dB, wet
  +3.5 dB (wet-dry -6 -> +3.4). Half A's dry does NOT come from any reg-23 reader in chip 2 (073/061/084/086/09A/09E/
  0A3/0A4/0C1 swapped to 38: no change) nor 074/075's registers. Source still unknown.
- 2:07D `090038` (third MAC, coef 0) -> `090023` + coef: wet +5.7..+9.2 dB more, dry unchanged (coef 0x7FF: wet-dry
  +9.3). Mechanism not understood (reg 23 at that step is not plain dry). Ear test before trusting it.
- Round 3 (`out/drywet_scanB_058.txt`, `drywet_dig1-3`, `drywet_combo3`): with 2:079 fixed, zero-scan 058-0AF: only
  2:07C NOP cuts more dry (-11.9 dB total, wet -0.1). 2:075 belongs to the SAME dry half as 079 (B + 075 nop: no change).
  07A/07B/07D NOP kill everything (chain links); 07B operand swaps do nothing; 07A r00->r38 kills everything.
  Best so far: B + 07D `090023`/7FF = wet-dry +9.1 dB (dry -5.7, wet +9.4); B + 07C nop = +5.8 dB.
  DANGER: B + 07C nop + 07D tweak = +26 dB and the restore left the unit +17 dB hot until 07D/07C/079 were
  re-restored in that order. Zero/swap tests interact nonlinearly: the ISA semantics (00/01/08/09/14 families,
  pipelining) need a real decode before the last dry half can be found.

## 100% WET FOUND (2026-10-14, `bench.py`, `wet100.py`; logs out/bench1-9.txt)
- **Coefficients are 12-bit two's complement: 0x7FF = +1.0, 0x800 = -1.0, 0xC00 = -0.5; bits 12-15 ignored.**
  CORRECTION of the old note "0x7FF wraps to ~0 on 2:076/07C" (that was the stale-latch bug): 076/07C coef 0x7FF =
  +1.0 = +6 dB wet over the firmware's max 0x400 (+0.5, "level 100"). Measured +5.9 dB.
- Each step has its own coefficient SLOT; commit 8 writes instruction + slot. Steps the firmware only commits with 00
  (instruction) keep a slot set at boot: poking them with commit 8 and the default coef 0 silently zeroes the slot
  (that was most of round 2-3's confusing "NOP"/swap results). `dsplive.py <chip> <step>` lists the commits.
- **2:07A `01ffc0` slot = chain-B dry gain (boot +1.0).** Set to 0x800 (-1.0): chain B's dry cancels chain A's dry.
  Static 300 ms tap: dry -28..-30 dB (meter floor), wet -0.1 dB. On the reverse (engine frozen for the A/B): dry
  -22 -> -53 dBFS (-31 dB), echo +3 dB with C level 0x7FF. Trim 0x800-0x830: flat (floor), so the gains match.
- On 07A: instruction bits 6-23 (incl. 16-17 and 22-23) change nothing; the low 6 bits do (operand/register).
  On 079 (`000023`, r3 field 23 via commit 4) only the low 6 bits matter (23 = block input, 38 = C tap).
- Tool: `py -3.10 wet100.py on [clevel] | off` (engine paused around the writes, C-tap latch, resume). Any OS DSP
  rewrite undoes it. Only run `on`/`off` with the reverse engine loaded (resume starts timer 0).
- **Crackle = digital clipping on the output side** (ear test 2026-10-14, guitar, wet100 on): C level 0x7FF crackles,
  0x400 better, 0x300 "almost perfect", 0x200 only barely on hard attacks. Engine counters clean meanwhile (16k
  writes/s, 0 busy/fw/timeout). Lowering C level helps, so the clip is after 2:076/07C. Suspect: the dry cancel may be
  ACROSS the L/R outputs (chain A -> one DAC, chain B -> the other, summed by the mono jack), so each DAC still carries
  full dry + wet; then the headroom fix is removing the dry inside each chain. Untested; lofilt.py: negative
  treble/presence = louder/fizzier/harsher, no help (treble 0 = the line-out's max cut).
- Ear tuning (guitar, 2026-10-14): crackle at high volume = the 16 kHz - f mirror (high strings crackle more; input
  cut 6 kHz -> 4.5 kHz better; 3 kHz darker; user KEEPS 4.5 kHz). Per-chain echo: chain A (2:076) 0x300, chain B (2:07C) 0 = cleaner
  than both 0x200. Muting output A or B (outmute.py) never brought the dry back: the cancel is inside the DSP and
  both outputs carry the reverse; the user's jack hears a mix of both. One-shot: `py -3.10 revfull.py`.
  Next idea: 2-sample average after the tap (notch at 16 kHz) in chain B's spare steps, to get brightness back.

## REVERSE DLY in ROM (v2.8 WIP, 2026-10-14)
- The tuned live setup became an OS pedal: `rev_blob.asm` (engine + setup), knob target REVT in `pedal_menu.asm`,
  recipe `pedals.py` 'revdelay', knobs BP NT MX F T L (`gen_pedal_data.py`), test `emu_v28.py`.
- Found while building: the firmware's sound change (LOADBUF) never rewrites chip-2 INSTRUCTIONS (they load once at
  boot; all 512 live chip-2 instructions = the boot table DS:14C4, 3 B per step). It rewrites tap A fields (069/06C/072,
  commit 1) and C levels (076/07C, commit 8) only. So the borrowed-memory NOPs, the moved tap write and the 07A dry
  cancel would outlive the pedal: `unborrow` writes those 19 steps back from the boot table (commit 0; resets 07A's
  coefficient slot) before every sound change. "A patch push undoes borrowed memory" in mem2s.py was only the tap times.

## v2.8 hang on REV select/exit (2026-10-14, hw)
- Symptom: with REVERSE DLY picked, navigating/exiting hung the unit (the engine ran continuously; on any menu
  action the OS also wrote the DSP and the engine's commit-1 landed inside it -> stuck busy). Same mechanism as the
  earlier ESC hang. The emulator can't reproduce it (DSP modelled as never-busy).
- Fix: a menu-hold byte FA00:CE47 (= 06C0:0247 in the engine's SS). mloop clears it before SERVICE (idle wait: the
  engine may write) and sets it after (all dispatch: the engine skips its commit, A still advances so timing holds).
  stop_core now also waits for the DSP to go idle before unborrow writes it. No DSP write from the engine can overlap
  an OS DSP write. emu_v28 checks the byte toggles 0/1.
- First fix (hold byte, skip the COMMIT) still hung on hw, but differently: controls died, sound kept playing. That
  means the engine was fine (sound) but the firmware's main loop was stuck in its own untimed DSP busy-poll. Cause:
  the engine ISR's FIRST act was `test [si],al` = a DSP STATUS READ, done every tick BEFORE the hold check. That read
  lands inside the firmware's DSP transaction and jams its poll. Real fix: check the hold byte at the very TOP of the
  ISR and, when held, touch the DSP not at all (no status read, no commit) -- freeze A, re-arm the tick, FINT/RETRBI.
- 2nd fix (hold byte at ISR top, no DSP touch) ALSO hung ("same shit"). Working theory now: the M60014 gate array
  cannot take ANY CPU interrupt in the middle of a DSP access sequence -- even a do-nothing engine interrupt inserts a
  bus cycle that corrupts the firmware's untimed poll. A flag the engine CHECKS is not enough; the engine's timer must
  be truly MASKED so it cannot fire. v2.8 rework (not yet burned): REV_HOLD/REV_GO entries mask/unmask TMIC0 (engine
  timer) around every OS dispatch (mloop brackets SERVICE); the engine runs only in the idle wait. Plus breadcrumbs:
  ST_REVPH (DS CE48) written at each setup phase (0x10-0x12 hook, 0x20-0x25 rev_now/engine) -- after a hang, dump RAM
  and read CE48 for the exact point. Reverted the unit to v2.7 meanwhile. emu_v28 checks the breadcrumb hits 0x25 and
  TMIC0 toggles 0x56/0x16.
- Masking the whole menu loop fixed the hang but was noisy -- user: "extra cascading samples". Cause: the engine
  timer kept running under the mask so A advanced, but commits were blocked; each unmask fired a commit at the
  jumped A = stray echo taps. Fix (matches the live tool, which was clean): engine runs FREE through the menu
  (redraws/keys touch the LCD, not the DSP); the truce is called only where the OS writes the DSP -- rev_now /
  hook_load / REV_STOP stop the engine, live_set masks TMIC0 around the firmware setter. Removed the mloop-wide mask.
