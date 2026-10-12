# GP-16 mod OS - UI + 4-OUT pedal mode design (draft 2026-10-12)

## Hardware facts this is built on
- Panel: LCD, patch display, Number buttons 1-8, BANK, GROUP, EDIT, SYSTEM, FUNCTION up/down, a-Dial,
  ESCAPE, WRITE, output-channel LEDs. Rear: RRC IN (FC-100 footswitch bus), CONTROL PEDAL, EXP pedal.
- Outputs: 4 unbalanced jacks = 2 signals (A, B) x 2 jack pairs (CH1, CH2), plus XLR A/B.
  CH select = latch 0x60001 (1 = CH1, 2 = CH2, 3 = both) + relay bits 0x60006 (firmware E980:3F27). Switchable instantly.
  A vs B = DSP left/right. Only one jack: CH select + DSP sends signal to A only or B only (pan/output gains).
  At most 2 different signals at once (A and B): hardware limit.
- Space: 12.7 KB free at ROM 0720-38FF (v0.3) + ~1.7 KB scattered. Backdoor stays.

## 1. PEDAL MODE (1 in -> 4 outs)
- 4 slots on Number buttons 1-4 (and FC-100 switches 1-4). Each slot = output jack (CH1-A, CH1-B, CH2-A, CH2-B)
  + one FX (any stock effect, or FX LAB: FREEZE, INF DLY, FLANGER RES+) + level.
- Press a slot: signal moves to that jack with that slot's FX. LED/LCD shows the active jack.
- Buttons 5-8: momentary actions (5 = FREEZE hold, 6 = INF repeat, 7 = mute, 8 = tap tempo later).
- SPLIT option: A = dry (to amp), B = wet (to FX amp/desk) at the same time.
- Slot setup stored in the patch's spare bytes (or a global table in battery RAM above 0x4800).

## 2. Navigation (EDIT)
- Number buttons jump straight to an effect page: 1 COMP/DRIVE, 2 FILTER, 3 PHASER, 4 EQ, 5 NOISE, 6 DELAY/MOD,
  7 TAP/REVERB, 8 CAB (line out). Press the same number again = effect on/off.
- FUNCTION up/down = next/prev parameter inside the page, dial = value, ESCAPE = back to play.
- LCD line 1: page + param, line 2: value bar + on/off. No more scrolling through ~80 params.

## 3. SYSTEM menu (replaces the 12 stock functions, same features kept)
- MIDI (channel, filter, mapping), PEDALS (control pedal: MUTE/BYPASS/FREEZE, exp), OUTPUT (pedal mode setup),
  FX LAB (beyond-limits ranges), UTIL (factory presets, bulk dump), INFO (version, credits).

## Build order
- v0.4: PEDAL MODE + FREEZE on control pedal + FX LAB entry (hooks: System button, key handler, output latch).
- v0.5: EDIT navigation (number-button pages).
- v0.6: full SYSTEM menu rewrite.

## RE still needed (all host-side, no DSP ISA needed)
- Key scan codes + key handler dispatch (port P2 strobes / PT read at boot, then the main-loop key routine).
- LCD text routines (F94B printf-style, 0x20000 HD44780) + current screen state.
- System menu dispatcher (F6A1, 12-entry handler table F6A1:1D78) to hook/replace.
- DSP A-only / B-only output control (pan or output gain steps; measure with the rig).
- FC-100 / RRC message format on serial 1 (vectors 16-18).
