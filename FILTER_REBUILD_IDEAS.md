# GP-16 LINE OUT FILTER rebuild - ideas (2026-10-12, nothing dumped yet)

## What's there now
- B-6 LINEOUT FILTER: PRESENCE / TREBLE / MIDDLE / BASS, each 0-100. Per patch, on/off bit 0x0D bit 4.
- Fixed at the very end of the chain (can't be moved) - that is the right spot for a cab sim, so keep it.
- Manual pitches it as a tone control for line-out recording or a power amp into monitors. It's a plain
  4-band tone stack with fixed frequencies: no speaker resonance, no steep high cut, so a direct DI sounds fizzy.

## Key unknown (answer comes from the ROM dump)
Are the 4 bands biquads whose coefficients the CPU looks up in ROM tables (likely: values 0-100 -> table),
or fixed inside the DSP microcode? If tables -> Tier 0/1 are pure ROM edits + x86 code. Find: 4 tables of
101 entries (or one per band), near the "PRESENCE"/"TREBLE" strings or the patch->DSP update routine.

## Tier 0 - table edits only (no new code)
Re-voice the existing 4 knobs into a speaker/cab response (user voices it, they build amps):
- BASS -> low resonance bump (cab thump, roughly 80-150 Hz) instead of a shelf.
- MIDDLE -> mid scoop/push centre moved to taste.
- TREBLE + PRESENCE -> together act as the speaker roll-off (high cut) instead of boosts.
Limits: still 4 bands of whatever filter type the DSP code implements (shelf/peak), so the high cut is only
as steep as two stacked bands allow.

## Tier 1 - CPU side (new x86 code + new patch bytes, same DSP filter code)
- CAB MODEL selector: each model = a preset set of coefficients for all 4 bands
  (e.g. open 1x12, closed 4x12, 2x12, small 1x10 combo, bass 1x15, "flat/off"). Knobs then trim around the model.
- MIC selector: on-axis / off-axis / room = presence-treble offsets on top of the model.
- Multiple mod sources (user wants this): expression pedal, MIDI CC, or the input envelope can move a band,
  e.g. pedal = "tilt" (dark <-> bright), play harder = more presence. Needs the CPU to rewrite coefficients live.
- Spare patch bytes: patch is ~0x76 used of a 0x80 stride - check after the dump if ~8 bytes are free.
  Otherwise a global setting (System mode) for cab model.

## Tier 2 - DSP side (new microcode, needs the TC23SC260 instruction set cracked)
- Real speaker roll-off: 12-24 dB/oct low-pass around 4-6 kHz plus a resonant low bump with Q.
- Cone breakup peaks/notches in the 2-4 kHz area.
- Short FIR "mini-IR" (16-64 taps) if the DSP budget allows; real IRs are out of reach on 1990 hardware.
- Per-output routing: cab sim on Output B only, Output A dry to a real amp (very useful live). Needs DSP routing changes.
- Must fit the instruction budget the old Line Out Filter uses (same DSP slot).

## Renaming (user's call)
Current: "LINEOUT FILTER" (14 chars). Pool: CAB SIM, SPEAKER SIM, CABINET, MIC'D CAB, CAB+MIC, DI CAB, SPEAKER.
Same length or shorter = simple string edit in the ROM.

## Order of work
1. Dump IC11 (both units). 2. Find the band tables -> Tier 0 re-voice (fast win).
3. Find the patch->DSP update routine -> Tier 1 (cab models, mod sources). 4. Tier 2 after DSP RE.
Phaser slot stays as it is (user, 2026-10-12).

## Side note: Picking Filter (A-3) - parked
Q tops out at 5.0, single envelope. Same tier approach would apply (more Q, ENV/LFO/STEP sources). Not the focus now.
