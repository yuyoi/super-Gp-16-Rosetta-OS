# GP-16 PEDAL MODES — candidate list (2026-10-12)

User to nix/ok each. Built modes land in `re/pedals.py` (SysEx voicings, tuned by ear) and later a
firmware PEDAL MODE menu that loads the stored voicing.

GP-16 blocks: COMP, A2=DIST|OD, PICKING FILTER, STEP PHASER, PARAM EQ (HI/HM/LM/LO), NOISE SUPP,
SHORT DELAY, B2=CHORUS|FLANGER|PITCH|SPACE-D, PANPOT/TREMOLO, TAP DELAY, LINE-OUT cab, REVERB.
Constraint: A2 is DIST or OD (one); B2 is one modulation (one). Expression pedal can drive any assign param (wah/whammy).

Legend: ✓ faithful · ~ approximation · status: [ ] pending / OK / NIX / drafted

## Dirt (A2 DIST/OD + EQ)
| # | Pedal | GP-16 realization | Fit | Status |
|---|---|---|---|---|
| 1 | Tube Screamer TS808/9 | OD, mid-hump ~720, low cut, soft top | ✓ | drafted |
| 2 | ProCo RAT | DIST, high-mid ~1.5-2k, treble roll (filter), full lows | ✓ | drafted |
| 3 | Boss DS-1 | DIST, bright buzzy, slight low-mid dip | ✓ | drafted |
| 4 | Big Muff Pi | DIST+COMP, deep mid scoop ~700, dark, sustain | ✓ | drafted |
| 5 | Boss MT-2 Metal Zone | DIST near-max, scoop + bright fizz, tight lows | ✓ | drafted |
| 6 | Boss SD-1 / BD-2 | OD asymmetric, a touch brighter than TS | ✓ | [ ] |
| 7 | Klon Centaur | transparent OD + mid push, clean lows | ✓ | [ ] |
| 8 | Marshall Guv'nor | amp-in-a-box crunch, midrange | ✓ | [ ] |
| 9 | MXR Distortion+ / DOD 250 | raw hard clip, simple | ✓ | [ ] |
| 10 | Suhr Riot / modern hi-gain | tight metal, scooped-ish | ✓ | [ ] |
| 11 | Fuzz Face (germanium) | DIST, gated splatty fuzz | ~ | [ ] |
| 12 | EHX Metal Muff / hi-gain | aggressive modern | ✓ | [ ] |

## Dynamics
| 13 | MXR Dyna Comp / Boss CS-2 | COMP squash | ✓ | [ ] |
| 14 | Clean boost | EQ + level | ✓ | [ ] |

## Modulation (B2 / phaser / pan)
| 15 | Boss CE-2 Chorus | CHORUS | ✓ | [ ] |
| 16 | Roland Dimension D | SPACE-D (native) | ✓ | [ ] |
| 17 | MXR Phase 90 | STEP PHASER | ✓ | [ ] |
| 18 | Electric Mistress / Flanger | FLANGER | ✓ | [ ] |
| 19 | Boss TR-2 / amp Tremolo | PANPOT/TREMOLO | ✓ | [ ] |
| 20 | Univibe | phaser/chorus hybrid | ~ | [ ] |
| 21 | Leslie / Rotary | chorus+trem+pan | ~ | [ ] |
| 22 | Vibrato | pitch wobble | ~ | [ ] |

## Pitch (B2 PITCH + expression)
| 23 | Octaver OC-2 | PITCH -1 oct | ~ | [ ] |
| 24 | Whammy | PITCH via expression pedal | ✓ | [ ] |
| 25 | Detune / 12-string | PITCH slight detune | ✓ | [ ] |

## Time
| 26 | Slapback / analog echo | SHORT/TAP DELAY, dark repeats | ✓ | [ ] |
| 27 | Digital delay / dotted-8th | TAP DELAY | ✓ | [ ] |
| 28 | Space Echo RE-201 | delay + mod/tone | ~ | [ ] |

## Filter / Wah (PICKING FILTER + expression)
| 29 | Auto-wah / envelope (Mu-Tron) | PICKING FILTER | ✓ | [ ] |
| 30 | Wah (Cry Baby) | PICKING FILTER swept by expression | ✓ | [ ] |

## Reverb
| 31 | Spring reverb | REVERB spring modes | ✓ | [ ] |
| 32 | Hall / Plate reverb | REVERB | ✓ | [ ] |
| 33 | Shimmer | reverb + pitch | ~ | [ ] |

## Amp / Cab
| 34 | Cab sim / amp voicing | LINE-OUT filter (cab mod) | ✓ | [ ] |

## User selections (2026-10-12)
DIRT ok: Tube Screamer, RAT, DS-1, Big Muff, Metal Zone, SD-1, Klon, Fuzz Face, Metal Muff
DIRT nix: Marshall Guv'nor, MXR Dist+/DOD250, Suhr Riot
MOD ok: CE-2 Chorus, Dimension D, Phase 90, Flanger, Tremolo, Leslie/Rotary
MOD nix: Univibe, Vibrato
(DELAY / REVERB / DYNAMICS / PITCH / FILTER / AMP: pending)
DELAY ok: Slapback, Digital/dotted-8th, Space Echo
REVERB ok: Spring, Hall/Plate, Shimmer(~), + ambient spaces: Cathedral, Cave, Church(warm), Stage, Ambient(near-freeze)
NOTE: reverse delay NOT feasible (needs TC23SC260 delay-read-direction microcode; ISA not cracked).
(DYNAMICS / PITCH / FILTER / AMP: pending)
WAH ok: Crybaby, Reso Wah (picking-filter cutoff swept by expression pedal; Reso Wah = high Q). Needs EV-5.
CUSTOM ok: "Funeral" doom fuzz (Electric Wizard "Funeralopolis": DIST max, deep low boost, dark top, woolly sustain). "Iron Man" Tony Iommi (Rangemaster treble-boost into cranked Laney: OD/DIST high drive, upper-mid/treble boost ~2-3k, lows trimmed, cutting + big sustain).
SKIP: Dynamics (comp/boost), Pitch (octaver/whammy/detune), Amp/Cab (already a separate mod). "no other needs for the gains."
FINAL = 30 pedal modes: 11 dirt (+Funeral, +Iron Man), 6 mod, 3 delay, 8 reverb, 2 wah.

## AMP selections (2026-10-12)
AMP ok: Clean(Fendery), Twin(bright clean), JCM800(hot Marshall), AC30(Vox), Doom(dark Orange/Laney), DI/flat
AMP nix: Plexi, Recto, Bassman
AMP custom: Radio = germanium transistor radio (lo-fi bandpass, honky narrow mid ~1-1.5k, lows+highs gutted, squashy comp)
= 7 amps.
MODEL: one dirt block only -> AMP = EQ(4-band) + cab(line-out) + power-amp comp, NO distortion. Gain always from the PEDAL.
  pedal+amp combo = dirt pedal's A2 + amp's EQ/cab. just-amp = clean through amp EQ/cab. just-pedal = dirt into real amp.
MENU: two selectors PEDAL(off+30) and AMP(off+7); loader MERGES pedal+amp recipes (OR on/off bits, take each block's params).

## Menu navigation (user design 2026-10-12)
SYSTEM -> PEDAL/RIG split screen:
  FUNCTION UP   -> PEDAL mode: pick 1 of 30 pedals (pedal-only, into real amp). ESC -> split.
  FUNCTION DOWN -> RIG mode:   pick PEDAL + AMP combo (amp-only = pedal OFF).   ESC -> split.
  ESC at split  -> back to play.
Shallow 2-level tree; ESC steps back one level. Build the on-unit menu to this shape.

## Build status (2026-10-12)
STEP 1 DONE: sound engine in re/pedals.py -- 30 pedal recipes + 7 amp recipes + merge loader.
  Commands: load <pedal> (pedal-only), amp <name> (amp-only), combo <pedal> <amp> (rig). Merge verified offline
  (on/off OR'd, amp EQ overrides pedal EQ in a rig). Values are starting points -> tune by ear post-FET into the amp.
STEP 2 TODO: on-unit PEDAL/RIG menu firmware (SYSTEM -> up=Pedal/down=Rig), bake voicings to ROM, apply-to-edit-buffer routine.
STEP 2 BUILT (v0.6, 2026-10-12): on-unit PEDAL/RIG menu in re/pedal_menu.asm (+ gen_pedal_data.py). SYSTEM -> split
  (UP=PEDAL, DOWN=RIG, SYSTEM again = stock menu, ESC back). Dial/BANK/GROUP scroll, applies live. Emulated OK.
  To verify on hw: UP/DOWN mapping (keys 0xF/0x10), dial direction, sounds. Voicings still ear-tune targets.
v0.6 ON HW (2026-10-12): menu opened on EDIT not SYSTEM, picks did nothing audible. Causes: wrong key (0xC = EDIT)
  and hand-mapped edit-buffer offsets (on/off word written as garbage -> blocks off). 
v0.7 (2026-10-12): fixed both -- SYSTEM key, apply through Roland's own DT1 setter. Full-firmware emulation passes
  (re/emu_menu.py). Ready to burn: build/gp16_mod_v0_7_sst512k.bin (md5 735cdb94...). Banner shows "Super GP 0.7".

## v0.8 = rack as one pedal (2026-10-12, built + emulated, gp16_mod_v0_8_sst512k.bin md5 63915ffb...)
User picks: knobs 0-10 (0.5 steps) | FUNCTION flips name/knob page | boots as the pedal | dial follows last-moved knob.
Screen: row 1 labels (3 chars, column per button pair), row 2 values. Buttons 1-4 = knob up, 5-8 = knob down.
Knobs (real pedal order; knob -> GP-16 param, defaults = the recipe values):
  Tube Screamer DRV TON LVL | RAT DST FLT VOL | DS-1 TON LVL DST | Big Muff VOL TON SUS | Metal Zone LVL HI MID DST
  SD-1 LVL TON DRV | Klon GAN TRB OUT | Fuzz Face VOL FUZ | Metal Muff VOL BOT TOP DST | Funeral VOL TON FUZ LOW
  Iron Man BST TRB VOL | CE-2 RAT DEP | Dimension D MOD 1-4 | Phase 90 SPD | Flanger MAN DEP RAT RES
  Tremolo RAT DEP | Leslie SPD DEP | Slapback TIM LVL | Digital LVL FBK TIM | Space Echo RPT INT ECH TON
  Reverbs DEC TON PRE LVL | Wahs Q
  Amps: Clean VOL TRB BAS | Twin VOL TRB MID BAS | JCM800 PRS BAS MID TRB | AC30 VOL TRB BAS CUT
        Doom VOL BAS MID TRB | DI VOL | Radio TUN VOL
Mapping ranges live in re/gen_pedal_data.py (KNOBS / AMP_KNOBS) -- retune there, rebuild.
Known limit: one EQ block on the unit. Pedal knobs that use the EQ (Metal Zone HI/MID, Klon/Iron Man TRB,
  Metal Muff BOT/TOP, Funeral LOW) share it with the amp's EQ voicing in RIG mode (knob wins). Amp knobs use the
  line-out filter + master, so they never clash.
No auto-repeat on held buttons yet (tap = 0.5; use the dial for big moves).

## v0.9 BOARD mode (2026-10-12, built + emulated, gp16_mod_v0_9_sst512k.bin md5 1c146b5f...)
User picks: pedals grab extra blocks | FUNCTION = slot, BANK/GROUP = pedal, dial + 1-8 = knobs | one live board |
  a few chain-order presets, no full routing | OUT = output jacks (A/B/Y box: CH1 / CH2 / both).
Split screen: UP = PEDAL, DOWN = RIG, EDIT = BOARD. Boots into the last mode (incl. BOARD).
Slot pedals: A1 Dyna Comp, CS-3 | A2 11 dirt | A3 Crybaby, Reso, Touch Wah | A4 Phase 90, Slicer | A5 GE-7 |
  A6 NS-2 | B1 Slapback, Doubler | B2 CE-2, Dimension D, Flanger, Leslie, Pitch/Octave | B3 Tremolo, Autopan |
  B4 Digital, Space Echo | B5 8 reverbs | B6 7 amps.
New knobs: Dyna Comp OUT SNS | CS-3 LVL TON ATK SUS | Touch Wah SNS RNG Q | Slicer RAT DEP STP | GE-7 LO LM HM HI |
  NS-2 THR DEC | Doubler TIM LVL | Pitch INT (-12..+12) MIX FIN | Autopan RAT DEP.
ORDER: A = WAH>DIRT (default) / DIRT>WAH (stock) / PHASE>DIRT ; B = STOCK / TREM LAST / REV>DELAY.
GP-16 can't run different effects per jack: OUT only picks CH1 / CH2 / both (each channel = stereo A/B pair).

## v1.0 = JSW ROSETTA OS v1 (2026-10-13, built + emulated, gp16_mod_v1_0_sst512k.bin md5 41c30707...)
User picks added (macro knobs = one knob moves several params): HM-2 (LVL LOW HI DST), Rangemaster (BST VOL), OD-1 (LVL DRV), Fuzz Factory (VL GT CP DR SB, grabs the gate), Octavia (VOL FUZ OCT TON, grabs B2 pitch), Ram's Head / Green Russian (VOL TON-tilt SUS), Electric Mistress (RAT RNG COL + FM switch), CE-1 (INT LVL GRT + VIB switch, grabs A2 for grit), Whammy (MOD 1-5 = oct up / oct down / 5th / 4th / +1, MIX; expression pedal), Memory Man (BLD FBK DLY CHO, grabs B2), Shoegaze Wash (WSH = reverb + decay + feedback + chorus, TIM, TON), Ross (LVL SUS), Orange Squeezer (SQZ LVL), Small Clone (RAT + DEP LO/HI), Dimension C (mode buttons 1-4, chorus + doubler), amps JC-120 and 5150.
Metal Zone = 6 knobs on the user's layout: `LO HM LM H  G  L` over 2-digit values (whole steps), underline cursor.
Board memories 1-8 (WRITE saves, BOARD MEMORY page loads). All voicings are ear-tune targets.

## v2.0 (2026-10-13): voicings redone from the original circuits
All recipes now written in real units (Hz / dB / Q / ms) from the firmware's own EQ tables; old EQ frequencies were off. Knobs do what the originals do (Muff/DS-1 TONE = tilt, RAT FILTER = low-pass, Klon GAIN adds mid bump, TS TONE = treble). Vintage references, not modern takes. Still ear-tune targets.

## v2.3 signature pedals (A2 DIRT)
- DETROIT: Ace Frehley, Detroit Rock City solo. Knobs DRV, TON, ROM (plate + double-track), VOL.
- FLOOD 1: Dimebag rhythm. GAN, SCP (V-scoop depth + sizzle), LOW, VOL.
- FLOOD 2: Dimebag, Floods outro solo. GAN, MID, DLY (level + feedback), AMB (hall).
- HOLYWAR: Dave Mustaine, Holy Wars. GAN, BRK (mid bark), TGT (tightness: lows + low-mids cut), VOL.
Signature amps for RIG mode: SUPER LEAD (DETROIT), RANDALL (FLOOD 1/2), JCM800 RIP (HOLYWAR).
User: no Hendrix, no Floyd.
