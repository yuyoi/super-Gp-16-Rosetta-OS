# GP-16 ROM reverse engineering (unit 1, IC11, "Super GP Ver 1.0")

Dump: `../dumps/gp16_u1_ic11.bin` (128 KB, MD5 ac5f56bcb3d8c30ddf3f1ffe88b13556). All addresses below are ROM offsets
(0x00000-0x1FFFF) unless written seg:off. Tools in this folder; outputs in `out/`.

## Tools
- `gp16dis.py rom out [cs:ip ...]` - recursive-descent V25 disassembler (capstone x86-16 + hand decoder for V20/V25 0F opcodes,
  BTCLR etc.). Writes `out/listing.asm`, `out/functions.txt`, `out/bad.txt`.
- `entries.py rom listing` - extra entry points: interrupt vectors, `cs:[bx+T]` jump tables, parameter-table far pointers.
- `coefmap.py listing` - every DSP write (chip, step, coefficient source, caller) -> `out/coefmap.txt`.
- Rebuild everything:
  ```
  for i in 1 2 3 4 5; do py -3.11 -I re/entries.py dumps/gp16_u1_ic11.bin re/out/listing.asm 2>re/out/jumptables.txt | sort -u > re/out/entries.txt; py -3.11 -I re/gp16dis.py dumps/gp16_u1_ic11.bin re/out $(tr '\n' ' ' < re/out/entries.txt); done
  py -3.11 -I re/coefmap.py re/out/listing.asm > re/out/coefmap.txt
  ```
- Coverage: 25.7k instructions, 67.6 KB code, 784 functions, 0 decode errors. Compiled C (large model, far calls everywhere).

## ROM layout
| ROM range | What |
|---|---|
| 00000-038FF | 128 factory presets x 114 (0x72) bytes, internal patch format (name at +0x61) |
| 03900-083AF | Reverb coefficient bank: 10 modes x 0x778 bytes, sub-tables of 76 words indexed by DECAY (0-75). Segment E390 |
| 083B0-0843F | Interrupt vector table image (36 far ptrs, copied to 0000:0000 at boot) |
| 08438 | Reset entry (E83B:0088). Reset vector at 1FFF0 = JMP E83B:0088 |
| 08440-19B24 | Code. Segments E83B (boot, HW drivers), E93C (test/LCD), E980 (DSP effect driver), EE11 (MIDI/SysEx),
F00E (edit/params), F2FC (patch/routing loader), F6A1 (UI/system menu), F94B (printf/LCD text) |
| 1A000-1FFFF | DGROUP const area (DS=FA00, offsets 0000-5FFF): strings, tables, DSP boot programs |
| 1A750 / 1ADC8 / 1B4C4 | DSP boot program images chip 0 / 1 / 2 (24-bit words, 3 bytes each, low byte first) |
| 1BAC7 | Hidden credits + demo text (English/Japanese) |
| 1C396 | Parameter table: 71 x 22-byte records (see below) |
| 1EF71-1F6xx | Parameter/effect name strings ("L.O.FIL-PRESENCE" 1F4F9, "LINEOUT FILTER" 1F618, "Super GP Ver 1.0" 1F682) |
Free ROM (verified, v0.2 image): 19DC4 572 B (after backdoor), 1FCCA 806 B (after knob table, to 1FFEF), 19B25 219 B (after last code), maybe 1FA5A 205 B -> ~1.6-1.8 KB. NOT free: 065EC/06D64 (zeros are reverb PLATE coefficient sub-tables), 1AC9C/1B93B (tails of the chip0/chip2 DSP images = unused DSP steps: chip0 ~0x1C4-0x1FF, chip2 ~0x17D-0x1FF, room for new DSP code). Reclaimable: demo/credits text ~1.1 KB at 1BAC7, System menu code if replaced, unreferenced funcs at 090D4 / 19826 (unverified).
No ROM checksum found (no code reads segments E000/F000 except via DS) -> patching should be safe.

## CPU memory map (physical)
| Address | Device |
|---|---|
| 00000-07FFF | 32 KB battery S-RAM (IC12). Vectors at 0, stack top 07FFE (SS=0700). |
| DS=FA00 | DGROUP: DS offsets 0000-5FFF -> ROM 1A000-1FFFF, offsets 6000-FFFF wrap to RAM 00000-09FFF |
| 20000 | LCD (HD44780-type, 0x30/0x38 init), reg 0 = command, 1 = data |
| 40E00 / 40F00 | V25 internal RAM / SFRs (IDB set to 0x40 at boot, writes FFFFF=0x40) |
| 60000 | Control latch: +3 = master/output volume (value*vol/50), +4/+5 = mute, +1, +0x10 |
| 80000 | DSP host interface (M60014 "BOSS-017"), see below |
| E0000-FFFFF | This ROM |

## V25 setup (boot E83B:0088)
- Serial 0 and 1: SCM=0x49, SCC=0, BRG=0x80 (MIDI rate for the board's clock). Vectors: 13/14 = serial 0 RX/TX,
  16/17/18 = serial 1 err/RX/TX, 24 = INTP0 (external), 29/30 = timer units. Others -> dummy IRET.
- Panel keys: port P2 strobes (0xFE, 0xFD...) read back on port T (PT, 0x38).

## DSP interface (segment 8000)
- `[0]` bit0 = busy (poll until 0). `[8]`,`[9]`,`[0xA]` = 24-bit instruction latch (low, mid, high).
  `[4]`,`[5]` = 16-bit coefficient latch (low, high). `[6]` read-back / control.
- Commit: write to `0x1000 + chip*0x400 + step` (step 0-0x1FF): value 0 = store instruction only, value 8 = store instruction + coefficient.
- 3 DSPs (TC23SC260), 512 steps each. Each step = 24-bit instruction + 16-bit coefficient (same idea as the later CSP chip).
- Host routines (all far, args on stack):
  - E83B:0323 init/handshake, E83B:0444 upload the 3 boot images, E83B:0529 read chip status
  - E83B:0569 / 05A8 / 05E7 `write_instr(chip0/1/2, step, b0, b1, b2)`
  - E83B:0626 / 0679 / 06CC `set_coef(chip0/1/2, step, coef16)` (re-sends the step's instruction from the boot image)
- Chip split (from which chip each parameter's setter writes):
  chip 0 = COMP, DIST, OD, PICKING FILTER;
  chip 1 = STEP PHASER, PARAMETRIC EQ, NOISE SUPP, LINE OUT FILTER (+ parts of chorus/flanger/pitch/space-D/pan);
  chip 2 = SHORT DELAY, CHORUS, FLANGER, PITCH, SPACE-D, PAN, TAP DELAY, REVERB.
- Patch change / effect order: F2FC functions rewrite instruction words (F2FC:1A52, 1CCA, 214C, 22EC, 19E4) = routing.
  Whole-patch apply = E980:0A78 (pushes every coefficient).

## Parameter table (ROM 1C396 = FA00:2396), 71 records x 22 bytes, index = expression-assign number (0-70)
`+0 index, +1 effect id (1-17), +2 min (word), +4 max (word), +6 far ptr long name, +10 far ptr short name,
+14 far ptr display formatter, +18 far ptr DSP setter (called with the value as one word arg)`.
Full dump with chip map: run the snippet in GP16_RE history or see `out/` (params 66-69 = Line Out Filter, 70 = master vol).

## Patch format
- Internal patch (RAM + presets): 114 bytes. Current edit buffer in RAM at DS:9D06 (RAM 03D06).
- SysEx address = internal offset + 3 from 0x56 up (2-byte params are expanded in SysEx). Line Out: internal 0x54 PRESENCE,
  0x55 TREBLE, 0x56 MIDDLE, 0x57 BASS, 0x58 MASTER.
- EE11:123E + table EE11:170A (117 entries) = read patch byte by SysEx address; EE11:1EDC (118) = write; 0x75 = sound change request.
- F00E tables 0B24 / 0FB4 (77 entries) = panel edit get/set by parameter number.
- SysEx receive = byte state machine, jump table EE11:1046 (11 states): 0D99 checks 0x41, 0DAA device ID, 0DBF model 0x2A,
  0DD2 command 0x11 (RQ1) / 0x12 (DT1), then address/data states.

## LINE OUT FILTER - how it works
- Setters E980:3E36 / 3E5A / 3E7E / 3EA2: `coef = value*20 + 0x2F` (0..100 -> 47..2047), written with set_coef to **chip 1**:
  PRESENCE step 0x148, MIDDLE 0x149, BASS 0x14A, TREBLE 0x14B. Also written in E980:0A78 at patch load.
- So each knob is only a linear gain on a fixed band. The band filters (frequencies/slopes) are NOT set by the CPU:
  only 43 chip-1 steps ever get CPU coefficients, the rest are fixed in the boot image (ROM 1ADC8 + 3*step).
  The 24-bit words carry 16-bit fields (e.g. step 0x13C = 09 F9C0, 0x140 = 0A BDDE, 0x145 = 0B D619) that look like
  embedded coefficients or delay addresses -> re-voicing the bands = editing chip-1 microcode, needs the TC23SC260 instruction set.
- What the host side alone can change today: knob law (curve, range, sign), the names, adding new control sources
  (pedal/LFO/MIDI can already drive params 66-69 via expression assign).

## Hidden stuff
- Credits screen + "Super GP DEMO" (English and Japanese) and a Factory Preset single-patch reload, in the init/test menus
  around 1BAC7. Test mode: hold FUNCTION down + WRITE + BANK(VALUE down) at power-on, ID 5218.

## Next steps
1. DSP backdoor: small SysEx handler in free ROM (hook the model-ID state EE11:0DBF or an unused DT1 address) that writes
   raw instruction/coefficient words to any chip/step. Then crack the TC23SC260 ISA on hardware (send words, listen),
   like roland-dsps did for the CSP. ~150-300 bytes of x86.
2. With the ISA known: rewrite chip-1 steps ~0x138-0x150 into a cab-sim (speaker resonance, steep roll-off), rename strings.
3. Dump unit 2 and diff.

## Mod builds (`build_mod.py`, outputs in `build/`)
| Version | Contents | 512 KB flash image MD5 |
|---|---|---|
| v0.1 | banner "Super GP mod 0.1"; Line Out knob table at ROM 1FC00 (0 = band off, dB taper, = stock at 50/100), patched in 4 setters + 4 patch-load blocks | 20fd2383b3d12711217f6eb88dd359b0 (burned + verified 2026-10-12) |
| v0.2 | v0.1 + DSP backdoor: `backdoor.py` code at ROM 19C00 (F9C0:0000, 452 B), hook EE11:0D84 -> jmp far | b065c2b813e19236ed0368bd163686e3 (not burned yet) |
| v2.7 | **Kill old stock parts, 24 KB freed**: patch-screen EDIT key (F6A1:0106) -> OS split (stock Edit menu gone); F6A1:0037 `lcall F2FC:0186` -> `jmp 0045` (power-on hold modes gone: credits [9E7A]=55, init menu [9E7B]=E0 = factory 1-patch/all-patch load + System Data Init + 2 demos, test mode [9E7B]=0B ID 5218 = battery/INIT ALL/DSP/DRAM/tri wave/thru/gain/MIDI/RRC/key tests). `reach.py` = call graph over the stock listing (roots: reset, 34 vectors, 71 descriptor ptrs, every stock entry the OS/backdoor/dragon call): 51 functions + their jump tables + 1-byte pads (22107 B) and the credits/demo/test text DS 1AC7-22DA minus the banner's two %s (2060 B) -> `dead_ranges.txt`, wiped to FF by build_mod. Kept: all MIDI/SysEx (RQ1/DT1, bulk dump, data load, debug port), stock System menu (12 pages byte-identical to v2.6 in emulation), patch screen, setters. Lost: no on-unit system-data/patch init any more (debug port can write RAM). Free now: far 0x1300E-0x147F9 (~6 KB, seg F301), 0x16F30-0x17F3E (~4 KB, F6F3), 0x10C04-0x112A1 (1.7 KB), 0x1BAC7-0x1C2DA text (2 KB), more small; near (OS CS E020 can call): 0x09F3E-0x0A277 826 B, 0x0DDFE-0x0E072 ~0.6 KB. emu_v11.py (v10 script + tripwire on every wiped byte + real System menu walk + EDIT check) + emu_v10 + emu_v09 PASS. | 460f778fbc841922a29b4864498eed53 / sst512k 1f6282b312dd040e45d2b21180039157 (not burned yet) |
| v2.6 | **More ROM + finer HOT**: new **far blob** (far_blob.asm) at ROM 0x1FD90 = FFD9:0000, in the stock end-of-ROM zero run (after the dragon frames; ends before the reset vector at 1FFF0). It holds the dial scaling, the HOT stage write and the cab coefficient writer + tables (far_data.inc from gen_pedal_data), reached via a jump table (+0 dial_set, +3 dial_val, +6 hot, +9 cab); the OS keeps far-call wrappers. HOT on 0-10 knobs (halves) = 10+ / 11 / 11+ / 12 (x2 stage + drive 50 / 62 / 80 / 100 = about +0 / +2 / +4 / +6 dB); whole-step knobs keep 11 / 12. Checked first: the zero runs at ROM 0x65EC/0x6D64 are NOT free (reverb param 62 reads them). Still unused: 0x19E51 FF x431, the demo/credits text (~1.1 KB at 0x1BAC7..), and the rest of the 1FBBE zero run. pedal_menu.bin 13752 B (328 B left), far blob 309 B (299 B left). Knobs reset (structure). emu_v10 + emu_v09 PASS. | 5c7fbdfb4e92bdbe2adb96c5d1da5091 / sst512k 628fe38cab71b9446a07de555c95fee8 (burned + verified 2026-10-13) |
| v2.5 | **DRIVE PAST 10 (HOT)**: the 15 DIST pedals' drive knob gets positions 11 and 12. They switch on a x2 stage inside the DIST clipper by rewriting DSP chip 0 step 10B 1204a7 -> 9204a7 (bit 23; measured on hw: odd harmonics +12..+27 dB, noise floor unchanged, more than stock max drive). 11 = drive 70 + x2 (about +3 dB over 10), 12 = drive 100 + x2 (+6 dB). The OS writes the step from mloop after the sound change (ST_HOTP; commit 0, other latches 0, timer masked); every apply resets to stock. Compact knob target (HOTT 0xFD + base steps, 2 B); drive/macro targets converted to exact tables, defaults unchanged. pedal_menu.bin 13982 B, **98 B left**. Structure changed -> knobs reset. emu_v10 (+ HOT checks) + emu_v09 PASS. | 82b4219f0f3061769443441e0980d37e / sst512k b8c45874e264ce64e7154fbf8e4f4bab (burned + verified 2026-10-13) |
| v2.4 | **CAB sim** (first DSP-level feature): every amp but DI gets a CAB knob, OFF / 4X (4x12 closed, 4.5 kHz Q1.4) / 2X (2x12 open, 5.5 kHz Q1.0) / 1X (1x12, 3.8 kHz Q1.7). The OS writes custom HI-band coefficients (2nd-order low-pass, design formulas from DSP_CRACK.md, measured on the unit) through the firmware's chip-1 set_coef E83B:0679, from mloop once the sound change is done (ST_CABP), timer masked; again after any live knob move; CAB off restores the amp's shelf through its setters (p20/p21). Amps reaching 5 knobs use the 5-knob screen (whole steps). Controls (user feedback): RIG FUNCTION up = pedal side, down = amp side, same side again = pick <-> knobs; 5-6 knob pages: 1-6 pick in a row, 7/8 = CURSOR prev/next, value = dial or VALUE (GROUP/BANK). The alpha dial is a smooth encoder (many counts per turn): dial_set gives short ranges S counts per position (>=10 steps 1, 5-9 2, 2-4 4, switch 6), VALUE step = S, all dial reads via dial_val. pedal_menu.bin 13216 B, 864 B left. Structure changed -> knobs + boards reset. emu_v10 (+ cab checks) + emu_v09 PASS. | 599b8b91dc0c256a299846f1e80087c4 / sst512k a429c93bf07cd97f118ccfd91d078ce5 (burned + verified 2026-10-13; earlier burns b9edb8a0 = old keys, 5b3af638 = no dial scaling) |
| v2.3 | v2.2 + 4 signature pedals (A2): DETROIT (Ace Frehley, Detroit Rock City solo: plexi OD + double-track B1 + plate B5), FLOOD 1 (Dimebag rhythm: 750 Hz V scoop, tight gate), FLOOD 2 (Floods outro solo: mids back + delay B4 + hall B5), HOLYWAR (Mustaine RIP: boosted JCM800, tight, 1.2 kHz bark); level-matched to the fuzzes. + 3 signature amps for RIG mode (the amp's EQ replaces the pedal's there): SUPER LEAD (Ace), RANDALL (Dime), JCM800 RIP (Mustaine). 60 pedals, 12 amps. pedal_menu.bin 12700 B, 1380 B ROM left. Structure changed -> knobs + boards reset once (user OK'd). emu_v10 + emu_v09 PASS. | 673d37a862b0110a28402a65a2b3a8e7 / sst512k 7c3add8abd33e2ab9f52e3d2d78c27c6 (burned + verified 2026-10-13) |
| v2.2 | v2.1 + Funeral VOL = boost knob (fuzz level 20-100 + comp makeup level 40-100 + EQ OUT +2..+12 dB; default 6.0, 10 = all max, ~+17 dB over v2.1 if the levels are linear); Funeral TRIM dropped (its VOL owns EQ OUT). KMAGIC now hashes STRUCTURE only (entry names, knob counts + steps, stores, homes, slot lists) via SIG, pinned 0x89 -> 0x0d so v2.1 knobs + boards carry over. emu_v10 + emu_v09 PASS. | cdd9045d598d9d664513bd66f0c3103c / sst512k ed5cb9c5f192e95e8403a4a4f0657bdd (burned + verified 2026-10-13) |
| v2.1 | v2 + level trims via EQ OUT (pedals.py TRIM; user: fuzz levels are RIGHT, raise the rest): Funeral +7, SD-1 +6, OD-1 +5.5, TS +5, Klon +5, Rangemaster +4.5, Iron Man +4 -> overdrives + Funeral sit at the fuzz level (re/level_match.py loudness model, DIST clip density calibrated by ear). Fuzzes untouched (user: Fuzz Factory 'genius'). KMAGIC now hashes the table LAYOUT only, so voicing tweaks keep knob positions + board memories. emu_v10 + emu_v09 PASS. | 7d12d1842bf2a7167ce28f1441bea8d4 / sst512k 34adcce974712cdc2b7484f55469c8d8 (burned + verified 2026-10-13) |
| v2.0 | **JSW ROSETTA OS v2** = v1 (incl. Funeral path) + every voicing redone from the original circuits in REAL units: pedals.py helpers EQ(Hz, dB, Q) / COMP / DIST / OD / PICK / TAP / REVERB / EXP use the firmware's own display tables (EQ HM 500-4k DS:304C, LM 125-1k DS:31E0, LO 60-250 DS:3374, all log over 0-100; HI 2-8 kHz assumed log; delay/reverb CUTOFF 500 Hz x 16^(i/200), 200 = THRU, DS:481C stride 8). The v0.6-v1 EQ freqs were mis-placed (TS 'hump' sat at ~320 Hz). Creative but faithful: RE-201 = 3 taps as heads 1:2:3 + MODE table + its spring (grabs B5); Leslie = pan + doppler chorus + preamp OD (grabs A2), SLOW/FAST switch; shimmer = pitch +12 with feedback into hall; cave = room + rock echoes (B4); Phase 90 script/block switch; wah TOP/BOT = exp sweep range. pedal_menu.bin 11822 B. emu_v10 + emu_v09 PASS. | 3f4d13d4f5b2abddfce19a87554574a8 / sst512k ddaac92f1ca965440590bd8f47232d0e (burned + verified 2026-10-13) |
| v1.0 | **JSW ROSETTA OS v1** (boot: " JSW ROSETTA OS " / "v1", line 1 replaces "Guitar Processor" @1F671). Only 1 factory preset kept (readers `and ax,0`), dragon moved to ROM 0x0080 (E008:0000), OS to ROM 0x0200 (E020:0000), 14 KB room (11368 B used). New table format (macro knobs: any number of targets, linear or value table with FF = skip, deps mask re-applies knobs sharing a param after a live move; up to 6 knobs; ainfo 3 B/addr), knob stores at DS B000 (per entry), 8 board memories at DS B400 (96 B each; WRITE = save prompt, page 15 BOARD MEMORY 1-8 = load). 6-knob names-over-numbers screen (LO HM LM H  G  L) + 5-knob variant with the HD44780 underline cursor (E93C:01CA 1/2); Dimension C mode buttons; OFF/ON + LO/HI switches. Expression pedal: apply writes 0x5C=127 (off) first, recipes claim it (Whammy #45, wahs #12), BOARD = first pedal in chain. 16 picks + Small Clone + Dim C (55 pedals, 9 amps). DS A800-CDFF has no stock refs; emu_v10 watches B000-B6FF. emu_v10.py (164 steps) + emu_v09.py PASS; emu_boot_banner.py shows the boot text. Funeral = Funeralopolis path: Muff > cocked wah (picking filter parked, WAH knob) > comp as the loud amp; pedals may carry A-chain order bytes (PEDAL/RIG; default WAH>DIRT written first), ORDER page has a 4th A preset DIRT>WAH>COMP. | df3a35be95f87d5ad1b482e3c1f6f41a / sst512k d1f54032715d9bb829b24ea4da48f5da (first v1 build 41c30707... burned + verified 2026-10-13) |
| v0.9 | BOARD mode (split: EDIT=BOARD): 12 block slots + ORDER + OUT; pedals sit in their home block and grab free extra blocks their voicing uses (OWN table, chain order, own pedal first); 9 new slot pedals (Dyna Comp, CS-3, Touch Wah, Slicer, GE-7, NS-2, Doubler, Pitch/Octave, Autopan); chain presets A (WAH>DIRT / DIRT>WAH / PHASE>DIRT) + B (STOCK / TREM LAST / REV>DELAY); OUT = A/B/Y (SysEx 0x63); boot re-sends LCD contrast. pedal_menu.bin 9539 B. emu_v09.py + emu_v08.py PASS. | 1c146b5f48025b4432f2ebb0775380b0 (128K 09766403...) |
| v0.8 | RACK AS ONE PEDAL: boots into the last PEDAL/RIG mode (F6A1:0063 `mov [a312],0` @ROM 0x16A73 -> lcall E0A0:0003); per-pedal/amp knobs (<=4, real labels, 0-10 in 0.5 steps), buttons 1-4 up / 5-8 down per column, dial follows the last knob, FUNCTION = page (pedal: knobs/pick; rig: P knobs/A knobs/pick P/pick A); knob positions in battery RAM; live knob moves via the param descriptor setters (no reload). pedal_menu.bin 6420 B. emu_v08.py PASS. | 63915ffb368552a6826e0b4e3a276db5 (128K d4ed320e...) |
| v0.7 | v0.6 FIXED: menu on the real SYSTEM key (key 0xE, F6A1:012C `lcall F6A1:1530` @ROM 0x16B3C -> E0A0:0000; EDIT untouched); apply = recipes as raw SysEx pairs through the DT1 setter EE11:17F4 + stock sound-change service (F00E:0764 + F6A1:0382). pedal_menu.bin 2584 B. Verified by FULL-firmware emulation (re/emu_menu.py: real boot, real setter/DSP load, only keytest scripted). | 735cdb9494fa3d7c9eccc2117778a1b6 (128K fac76471...) |
| v0.6 | **BUGGY on hw (2026-10-12): opened on EDIT, applies did nothing audible -- see v0.7.** v0.5 (dragon 3x faster, sequential two-line eat w/ dot trail, man NOP'd) + PEDAL/RIG MENU: SYSTEM key -> E0A0:0000 (ROM 0x0A00, pedal_menu.asm 2473 B incl. 31 pedal + 8 amp voicing tables). Emulated clean. | 276fe7c5a14a99d3bfd1e6babfafb233 |
| v0.5 | v0.4 + boot DRAGON animation: 8-frame Toothless-style flying dragon on 3 CGRAM cells (chars 1-3) on boot line 2, routine at E072:0000 (ROM 0x0720, 273 B, dragon_boot.asm), 192-B frame table at 1FCCA; banner->"Super GP 0.5"; banner-draw call at F6A1:0020 (0x16A30) redirected to the routine, which draws the banner then animates then restores stock glyphs. Emulated clean (halts, restores chars 1-3). | 4a4bd1ac9864439408d29039e3649bc8 / sst512k b88ddee8... (burned+verified 2026-10-12; speed = spin-loop guess, tune DELAYREP) |
| v0.4 | v0.3 + debug port v3 (memory read/write cmds 05/06, 593 B) -> live button-map / jack-routing / LCD tests over MIDI | 7ded0480bd8fa0e4d79d4fad80c01705 / sst512k e7377d80... (not burned yet) |
| v0.3 | v0.2 + 16 factory presets kept (F2FC:0186 boot init + F6A1:27DA preset load patched at 13499/1921E to `and ax,15; imul ax,ax,114`), ROM 0720-38FF = 12.7 KB freed (FF, segment E000) | 0bd623ec898d73ff62fd37166cbf58c2 (burned + verified 2026-10-12) |
Burn: the "SST39SF040" chips here read ID 0x3786 = AMIC A29040 -> `minipro -p A29040 -w <file>_sst512k.bin`. No wiring needed (socket pin 31 already high).

## Backdoor protocol (v0.2) - PC tool `gp16poke.py` (py -3.10, mido, OCTA-CAPTURE)
- `F0 7D 47 01 chip s2 s1 s0 i5..i0 c3..c0 m1 m0 F7` write DSP step (instr 24 + coef 16, commit m to 8000:1000+chip*400+step)
- `F0 7D 47 02 o3..o0 v1 v0 F7` raw write 8000:o; `03 o3..o0` raw read -> `F0 7D 47 43 o3..o0 v1 v0 F7`; `04` ping -> `44 03`
- v3 adds general memory access (any segment): `05 g3..g0 o3..o0 n1 n0` read n bytes seg:off -> `F0 7D 47 45 g3..g0 o3..o0 <2 nib/byte> F7`;
  `06 g3..g0 o3..o0 v1 v0` write byte v to seg:off. PC: `gp16poke.py mr/mw/keys/jack`. Scratch RAM DS:CF1A-CF1E.
  Lets you read key strobes FA00:A310/A311, drive output latch 6000:1 (1/2/3) + relay 6000:6, poke LCD 2000:0/1 -- all live, no burn.
- Runs in the main loop (SysEx is queued by the serial ISR, parsed by EE11:0C82 -> 0D84), DSP writes under CLI.
- RAM DS:CF00-CF1B (RAM 6F00) for parser state. Messages are swallowed, never reach the Roland parser.
- Serial ISR only queues SysEx data when F0's low nibble (0) matches the basic channel (unless flag [9F30]&10) -> GP-16 on MIDI channel 1.
- The firmware re-sends stock instructions for a step whenever it sets that step's coefficient (param changes, patch load), so pokes get overwritten by knob moves.

## Hardware log
- 2026-10-12: v0.1 boots on the unit. v0.2 backdoor answers ping (version 2). Live write confirmed by ear:
  chip0 step 0x110 (DIST drive, stock instr 01CCC0) coef 0 -> distortion goes clean.
- 8000 reads: [0]=00 (not busy), chip status [+6]: chip0 00, chip1 FF, chip2 E8; others read back open-bus junk (7D/78/08).
- Known coefficient laws: DIST drive 0x110 = v*20+47; DIST level 0x130 = v*64/100 (instr 002000); OD level 0xEE = v*128/100;
  REVERB E.LEVEL chip2 0x157 = v*2047/100; Line Out chip1 0x148-0x14B = v*20+47 (v0.1: table).

## Patch I/O over SysEx (works with v0.2)
- RQ1 F0 41 00 2A 11 00 00 00 00 00 76 cs F7 returns the whole 118-byte edit buffer in one DT1.
- DT1 writes: 8-byte blocks with ~0.1 s gaps + SOUND CHANGE REQUEST (00 00 75 = 0) work and read back exactly.
  One 116-byte DT1 is ignored (too long for the receive ring).
- DT1 writes are ignored while the panel is in a System/Edit menu: flag [A430] bit0 (set by F6A1 menu code, cleared on
  return to play) routes data to a path that needs [9E9A]!=0. Reads still work there. -> exit to the play screen first.
- Files: backup_tempbuf_before_dimebag.json (user's "Bypass"), dimebag_dist_tempbuf.json (loaded 2026-10-12, verified).

## DSP instruction format - first look (out/instrmap.txt)
- `instrmap.py` = stack tracker over listing.asm: 144 constant instruction rewrites (routing code F2FC:1A52 x30 init/mute set,
  1CCA x55 chip2, 22EC x40, 214C x19) with stock word + XOR at the same step.
- Stock words: top byte behaves like flags. Families 00-03 (op 00 = 720 of 1536 words), 08-0B (large signed low16,
  e.g. -23488 / -16930 -> look like delay-RAM offsets), 10-1C, 48-56, 88-97, C4-D6. Low 2 bits vary inside each family.
- Each step = 24-bit instruction + separate 16-bit coefficient (CSP-style).

## Measurement rig (`dsprig.py`, py -3.10, WASAPI 48 kHz)
- OCTA out 3-4 (L) -> GP-16 IN, GP-16 OUT A -> OCTA in 5-6 (L). Log sweep 20 Hz-20 kHz -20 dBFS, Farina deconvolution.
- Offline check vs a known 2nd-order 1 kHz lowpass: -3.2/-24.7 dB measured vs -3.0/-24.5 true.
- Commands: measure, poke (baseline/poke/restore overlay), coefsweep (one curve per coefficient).

## ISA experiment plan
1. Coefficient format: coefsweep on a clean gain step (Line Out PRESENCE chip1 0x148, or DIST level chip0 0x130):
   0, 0x100, 0x200, 0x400, 0x7FF, 0x800, 0xF800, 0xFFFF, 0x4000, 0x7FFF -> scale, sign, saturation.
2. Line Out bands: measure each knob alone (others 0, v0.1 table) -> the 4 band shapes (centre, Q, slope) = target for rewrite.
3. Instruction fields: on chip1 steps 0x138-0x150 flip one bit at a time in the top byte / low16, measure, restore.
4. Delay taps: change low16 of an 08-0B word on a delay effect, measure IR delay shift -> confirms address field.
- 2026-10-12: TAP DELAY F.BACK beyond stock (chip2 step 0x7D, instr 090038): coef 0x0800-0x0FFF -> repeats go INFINITE (user, by ear).
  Stock max 0x07FF = just under unity -> coefficient unity is likely 0x0800 (12-bit fraction). First beyond-limits FX candidate.
- DSP interface, more: E83B:08BF writes chip2 with reg [3] = 8-bit extra field ([9FE4], set by routing: 0x27/0x2B/0x33..),
  coef [4]/[5], commit 0x0C. Commit values seen: 0 instr only, 8 instr+coef, 0x0C coef + reg3. (08BF writes [8] twice, skips [9].)
- 2026-10-12: FLANGER RES beyond stock (chip2 step 0x34, instr 080023, commit 0x0C keeps the latched reg3): coef 0x0700-0x0880
  "sounded better" (0x0700-0x07C0) and "went real crazy" toward 0x0800-0x0880 (user). Stock max 0x0665. Candidate: RES range extended to 0x0880 with a CRAZY zone above unity.
- 2026-10-12: REVERB = 6 comb pairs on chip2. Feedback gains steps 0E8 0F5 108 115 122 12F (decay 75 ~ 2010-2027),
  damping steps 0E7 0F4 107 114 121 12E (fall to ~3-10; PLATE modes 0). Unity = 0x0800 (matches tap delay).
  FREEZE test (HALL1): all feedback 0x0800 + damping 0 -> held tail, user: "nasty" (= good). Restore = SOUND CHANGE REQUEST.

## Host-side system map (traced 2026-10-12, Opus)
- **Main loop** F6A1:0000 -> inits, then loops at F6A1:006B..0143. Each pass calls: F6A1:03BC (MIDI+expr service),
  F6A1:00AA patch-change check ([A6B4]!=[9FCA] -> F6A1:031E loads patch [9FCA]), EE11:0 (RRC rx when [9F30]&80),
  EE11:14A (when [A43C]&8), F00E:1C42 (get next panel key event 1-10, 0 = none) -> F6A1:2446 play-key handler.
- **Key scan** F00E:1EE0 (called inside F6A1:03BC). Strobe P2 via 40F0:[0x10]=0xFE then 0xFD, read PT 40F0:[0x38].
  Row0 (0xFE) -> not() -> [A310], events XORed into [A42E]; Row1 (0xFD) -> [A311], events into [A431].
  So **live button state = FA00:A310 (row0) / A311 (row1)**, bit set = pressed. (mr fa00 a310 2 to map them.)
- **Key decode** F00E:1C42 returns 1..10 from the A42E/A431 event bytes (then masks them to low 3 bits):
  row0 bits 10/20/40/80 -> keys 1/2/3/4 ; row1 bits 10/20/40/80/08 -> keys 5/6/7/8/9 ; row0 bit08 -> key 10.
  (Number buttons 1-8 = keys 1-8; the two extra bits = bank/group-ish. Confirm on hardware with `keys`.)
- **Play-key handler** F6A1:2446: key9 toggles a mode bit [9F30]&4 (the 8-slot vs patch view); key8 in that mode
  xors [9FCA]&40; otherwise sets patch select bits in [9FCA] and flags redraw ([9F30]|80, [A43C]|8).
- **Timer ISR** E83B:0C92 (vector 29): increments [A202], decrements a bank of countdown words (9E7C, 9F36, A434,
  A6BC, A6C0, A65C, 9FD4). [A202]&40 toggles ~ms tick used for pedal/LED debounce.
- **Pedal tick** F2FC:3660 (called from vector-30 ISR E83B:0CF0): reads expression pedal (serial/ADC into 9FDA/9FDE),
  slews current value [A31F] toward target, and when assign byte [9D5F]==0x46 computes a scaled param and calls the
  assigned setter via far ptr [A662]; control-pedal switch handled in F2FC:35CC (reads 40F0:[8]&0x20, toggles 40F0:[0x40]&4).
- **Output routing** E980:3EC6 (called by F6A1:0144 on patch load) + F6A1:26CE. Channel latch **6000:1** (1=CH1,2=CH2,
  3=both), relay/mute byte **6000:6** built in RAM [A43B] (bit2/3 = CH1/CH2 enable, bit0/1 = mute A/B). Source = patch
  OUTPUT CHANNEL [9D66]. LED strip also via 6000:4 from [A0F3]. -> `jack` cmd drives 6000:1 + 6000:6 directly.
- **LCD** physical 0x20000 = seg 2000: [0]=command reg, [1]=data reg (HD44780; busy = data bit7 via E93C:03EA).
  putc = E93C:0010 (handles 08 BS / 09 tab-to-col / 0A home-line2 / 0C clear / 0D CR, else E93C:03AE writes data).
  printf = F94B:0000 (%s %d %c, into a stack buffer then E93C:0000 per char). Cursor addr set by E93C:024x (+0x80 line1,
  +0xC0 line2). -> poke a char with `mw 2000 1 <ascii>` after positioning, or just watch via the normal redraw.
- **MIDI rx** EE11:0C82 walks the serial ring [a30d..a65b], per byte calls EE11:0D84 (our entry patch sits here).
  F0 sets [A430]&40 + [A314]=0; F7 clears [A430]&60. MIDI **tx one byte** = EE11:11BA (used by the port's `send`).
- **DSP writers**: write_instr chip0/1/2 = E83B:0569/05A8/05E7; set_coef chip0/1/2 = E83B:0626/0679/06CC (re-sends the
  step's boot instruction from ROM image 14C4/.. then coef, commit 8); chip2+reg3 = E83B:08BF (commit 0x0C, keeps [9FE4]).

## Boot dragon (v0.5) — FINAL on hw 2026-10-12
- Dragon flies L->R across LINE 1, EATING the name "Guitar Processor" (name stays ahead, blank behind) with a
  trailing '.' one cell behind the tail — mimics the stock running-man wipe. 8-frame full-body anim (wings/head/tail/legs).
- Stock running-man boot walk = F6A1:0156 (called at F6A1:0040); NOP'd that call (build_mod v0.5, ROM 0x16A50) so only
  the dragon plays. Dragon routine replaces the banner-draw call at F6A1:0020 (0x16A30 -> lcall E072:0000).
- Routine dragon_boot.asm (NASM) @ROM 0x0720; 192-B frame table @0x1FCCA (DS 0x5CCA); name read from DS:0x5671.
  Speed = DLYCNT/DLYREP spin; POS0=-2..POSEND=18. Emulated (unicorn): wipe+dot correct, halts, restores stock glyphs.
- design tools: dragon_vec.py (shapes->15x8->bytes) + dragon_frames.bin. To retune art/speed: edit + reassemble + rebuild.

## Boot dragon (v0.5) [superseded notes]
- Art: traced a CC0 side-view dragon then hand-refined to a 15x8 (3-cell) sprite; every part animates over 8 frames
  (wings flap, head/body bob, tail undulates, legs shuffle). Design tools: re/dragon_vec.py (shapes->downsample->bytes),
  re/dragon_frames.bin (8x3x8 = 192 CGRAM bytes). Frame table stored at ROM 0x1FCCA (DS 0x5CCA).
- Routine re/dragon_boot.asm (NASM, cpu 186) at ROM 0x0720 (E072:0000): wraps the boot banner draw, prints char codes
  1/2/3 at line2 col13, loops 3x8 frames rewriting CGRAM chars 1-3 (E93C:00CC mode8 + E93C:03AE), delay E93C:0422,
  then restores stock glyphs (ROM 0x1CA46/3E/36 = DS 0x2A46/3E/36) so the play screen's char-3 icon is unchanged.
- The 8 stock boot glyphs (incl. the 'running man' frames) live at ROM 0x1CA16, 8 B each, loaded by F00E:1F6E.
- To change speed: DELAYREP in dragon_boot.asm (reassemble + rebuild). To change art: edit dragon_vec.py, regen dragon_frames.bin.

## PEDAL / RIG menu (v0.7; v0.6 was buggy) -- pedal_menu.asm + gen_pedal_data.py (from pedals.py)
- Hook: main loop SYSTEM key = key 0xE: F6A1:012C (ROM 0x16B3C) `lcall F6A1:1530` (stock System menu) -> `lcall E0A0:0000`.
  SYSTEM again at the split calls F6A1:1530, so nothing stock is lost. EDIT (key 0xC -> F6A1:0520 = stock Edit menu) untouched.
  v0.6 BUG: hooked F6A1:0106 = key 0xC = EDIT (I had 0xC/0xE labels swapped). Proof: the "Escape ?" prompt F00E:11C2
  prints "Y=ESCAPE N=SYS" and takes key 0xD = yes, 0xE = no.
- Nav: split " UP = PEDAL / DOWN = RIG"; FUNCTION key 0xF -> PEDAL mode, 0x10 -> RIG mode (">P:name" / " A:name",
  UP/DOWN toggles the row); dial scrolls; BANK/GROUP = -/+ (service(1) enables F00E:0176); ESC steps back.
  0xF/0x10 confirmed FUNCTION: stock page-step helper F00E:0454 (0xF = [9FD8]+1 next page, 0x10 = -1 previous).
- Key codes (F00E:1CD2(n), consumes the event; 0xFF clears): 1-8 numbers, 9 BANK (value -), 10 GROUP (value +),
  0xB WRITE, 0xC EDIT, 0xD ESCAPE, 0xE SYSTEM, 0xF FUNCTION next, 0x10 FUNCTION previous.
  Main loop: 0xC -> F6A1:0520 (Edit), 0xE -> F6A1:1530 (System). Stock exit check F6A1:1D90 (WRITE confirm, ESC prompt).
- Dial: INTP0 ISR E83B:09C0 -> F2FC:35CC quadrature, inc/dec word [A654] clamped 0..[A6BE], wraps when byte [A318]!=0.
- INTERNAL EDIT BUFFER != SysEx layout (v0.6 BUG #2: hand-mapped wrong). The DT1 receiver's per-byte setter
  EE11:17F4(buf far, sysex_addr, value) (jump table cs:1EDC, 0x76 cases) is the ground truth:
  * SysEx 0x0C/0x0D/0x0E -> ONE 16-bit word at +0x0C (DS:9D12): 0x0C<<14 (B2 type), (0x0D<<7)&0x2F80, 0x0E&0x7F.
    bit n = block n on (table DS:2326 = 1<<n); bit13 = A2 OD/DIST; bit12 not settable by SysEx. +0x0E = SysEx 0x0F.
  * SysEx 0x0F..0x3A -> +0x0E..0x39 (-1), several SCALED: 0x18/0x1D/0x41/0x44/0x52 x10, 0x3D x5,
    0x1C/0x24/0x26/0x27/0x29/0x2A/0x2C/0x2D x2. 0x3B/3C -> byte +0x3A. 0x3D..0x44 -> -2. 0x45/47/49 pairs -> LE words
    +0x44/46/48. 0x4B..0x4E -1, 0x4F/50 -> byte +0x4E, 0x51/52 -2, 0x53/54 -> byte +0x51, 0x55..0x5E -3 (0x5C also
    -> [A657]), 0x5F-0x62 -> words [A444]/[A64E] (exp min/max), 0x63 -> +0x60, 0x64..0x73 name -> +0x61..0x70,
    0x05/0x0B/0x74 ignored, 0x75 = SOUND CHANGE REQUEST ([A43C] |= 0x20).
  * The reader for RQ1 is EE11:123E(buf far, addr). RULE: never hand-map; call 17F4/123E.
- Apply (v0.7): ST_ON (CF33..35) = OR of the entries' SysEx 0C/0D/0E; every other pair -> EE11:17F4(FA00:9D06, a, v)
  (pedal then amp, amp wins); then 0C/0D/0E through 17F4; name -> DS:9D67; then the main loop's sound-change service:
  [A43C]|=0x20, if !([9FCC]&0x40) { clear; F00E:0764(FA00:9D06, 1) (order check); F6A1:0382 (buffer -> DSPs via E980:0A78) }.
  E980:023E(FF) (v0.6's choice) is NOT a patch load: it skips everything unless [9FD6]==0/1.
- State: DS:CF30 pedal idx, CF31 amp idx, CF32 rig row, CF33-35 on/off scratch (battery RAM, no stock refs).
  Data entry layout: name[16], count, count x (sysex addr, value). Tables ped_off[31]/amp_off[8].
- Patch load path for reference: F6A1:031E = copy patch DS:6400+n*114 -> 9D06 (F00E:2DDA), F00E:23D8 (globals),
  E83B:02DD, E980:0A78, E83B:02A8, E980:00B8. Play screen = F00E:2DF6 (name + chain "A-12345 6B-123456" from the word).
- Test: `py -3.11 -I re/emu_menu.py build/gp16_mod_v0_7.bin` = full-firmware unicorn run: boots from reset to the main
  loop (stubs only: spin delay E93C:0422, DSP self-test F2FC:183A; DSP status 8000:0 reads 0; LCD modeled incl. read-back
  test), presses SYSTEM, scrolls pedals/amps, checks on/off word, scaled bytes, DSP writes, LCD text, play screen after
  exit, SYSTEM-again -> stock System menu. Same script on v0.6 (EDIT entry) reproduces the hw failure (word 0x0000 etc.).
- Rebuild chain: edit pedals.py -> py -3.11 gen_pedal_data.py -> nasm pedal_menu.asm -> build_mod.py ... 0.7 -> emu_menu.py.

## v0.8 knobs ("rack as one pedal")
- Param descriptor table DS:2396 (ROM 1C396): 71 x 22 B = the ASSIGNABLE params (exp pedal list). Fields: w0 = block<<8|p,
  w1/w2 = internal min/max, w3:w4 name ptr, w5:w6 name2, w7:w8 display fn, **w9:w10 (+0x12) = live setter far ptr**.
  p = SysEx 0x0F..0x5B in order, skipping the lsb byte of 2-byte params (0x3C 0x46 0x48 0x4A 0x50 0x54); p66-69 =
  line-out PRES/TREB/MID/BASS (E980:3E36..), p70 = master (E980:0672).
- Stock edit menu live path (F6A1:0B10..0C04): F00E:0BBE(buf, editnum, val) writes the buffer, then (if p != [9D5F]
  exp assign) 40F0:9E |= 0x40, push val (INTERNAL units), call desc[p].setter via E83B:1006 (push dx; push ax; retf),
  40F0:9E &= ~0x40. F00E:0812 / F00E:0BBE = get/set by edit number (77, plain buffer, no DSP).
- SysEx DT1 path has NO live per-param update: 17F4 only writes the buffer; sound only changes on 0x75 (full reload).
- Menu knob move = dt1set (buffer, firmware scaling) + read the internal value back (offset parsed from 17F4's jump
  table by gen_pedal_data.py) + desc[p] setter. Pedal/amp change = full apply (recipes + knob positions + sound change).
- RAM: CF36 boot mode, CF37 knob magic (KMAGIC from the knob tables; mismatch -> defaults), CF38 page, CF39 dial knob,
  CF3A far-ptr scratch, CF3E state, CF3F tmp, CF40 pedal knobs 31x4, CFC0 amp knobs 8x4.
- Exit flushes all key events (F00E:1CD2(0xFF)): v0.7 leaked number presses into the patch keys after ESC.
- Test: `py -3.11 -I re/emu_v08.py build/gp16_mod_v0_8.bin` (boots into the pedal, knob/dial/page/rig/persist checks).
  emu_menu.py is the v0.7 test (SYSTEM entry).

## v0.9 BOARD mode
- Slots = the 12 blocks in chain order (A1 COMP, A2 DIRT, A3 WAH/FILTER, A4 PHASER, A5 EQ, A6 GATE, B1 SHORT DELAY,
  B2 MOD, B3 TREM/PAN, B4 DELAY, B5 REVERB, B6 AMP/CAB) + ORDER + OUT. RAM: BRD CF20 (12, pedal idx; slot 11 = amp idx),
  ORDA CF2C, ORDB CF2D, OUTSEL CF2E, VIEW CF2F, FILT CF32, OWN CE20 (12), OACT CE2C; amp knob store moved to CE00.
- Ownership (compute_owners): own pedal wins its slot; then slots in chain order give their pedal's EXTRA blocks
  (gen_pedal_data.extras = recipe on-bits minus home, minus the gate for non-gate pedals) if still free. A grabbed slot
  shows <NAME> and refuses picks. Apply writes each pedal's pairs/knob targets only for blocks it owns (blk_of table,
  knob target flags hi nibble = block, 0xF global = exp params); OD type bit follows the dirt owner, 0x0C follows the
  mod owner; on bits = blocks with an owner; order bytes SysEx 0-4 / 6-10 (0x05/0x0B are fixed: gate + line out stay
  last); 0x63 output channel; name "PEDALBOARD"; sound change (E980:0A78 also re-applies the output routing).
- Order positions hold block indices (position -> block), checked by F00E:0764. Only within A and within B.
- LCD contrast: saved in 9D04 (system block 9D00-9D05, saved by F00E:1E1C on WRITE in stock menus, restored by F00E:1E78
  at boot F6A1:0006), working copy 9FD2 (boot clears DS 9E7E-AB17), DAC latch 6000:2 written by F6A1:1DFA (boot F6A1:000B).
  Board/pedal code never writes them (emulation trace). v0.9 boot entry re-sends 1DFA (user saw low contrast ~1 in 5
  boots, cleared by a proper power cycle -> looks like power-on timing; VR1 on the main board trims the range).
- Bug caught in emulation: knob_apply must keep si/di (knobs_all loops on si).

## v1.0 notes
- Gain/level ceiling: every stock gain-type coefficient tops out at 0x7FF (drive E980:1EF0 = v*20+0x2F to chip0 step 0x110; line-out knobs the same) = max of a 12-bit signed field, so a bigger coefficient probably does nothing (testable live: debug port write to chip0 step 0x110). More drive is a gain-staging job: EQ (+12 dB bands, +12 dB EQ OUT) and/or COMP in front of the dirt block via the A-chain order bytes. Beyond that = DSP microcode (shift fields), i.e. the ISA work.
- Emulator scripts: a key right after a dial move is seen in the same loop pass (before dial_check); put two ('wait',) between a dial move and the next key.
