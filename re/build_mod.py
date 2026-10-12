#!/usr/bin/env python3
"""Build a modded GP-16 ROM from the stock dump.
Usage: py -3.11 -I build_mod.py <stock.bin> <out_dir> [version: 0.1 | 0.2 (default)]
v0.2 = v0.1 + DSP debug port (see backdoor.py, gp16poke.py).
v0.3 = v0.2 + only 16 factory presets kept (reset repeats them), ROM 0x0720-0x38FF freed (FF) for new code.
v0.4 = v0.3 + debug port v3: general memory read/write (cmds 05/06) for live button-map / jack-routing / LCD tests.
v0.5 = boot dragon. v0.6 = PEDAL/RIG menu (buggy). v0.7 = menu on the real SYSTEM key + firmware DT1 setter apply.
v0.8 = rack as one pedal: per-pedal knobs (buttons 1-4 up / 5-8 down, dial follows last knob), boots into it.
v0.9 = BOARD mode. v2.0 = v1 + every voicing redone from the original circuits with real EQ Hz (firmware tables).
v1.0 = JSW ROSETTA OS v1: macro knobs, 6-knob screen, board memories, 66 sounds; only 1 factory
       preset kept, boot dragon moved to ROM 0x0080 (E008:0000) and the OS to ROM 0x0200 (E020:0000), 14 KB room.
Writes <out_dir>/gp16_mod_v0_1.bin (128 KB) and gp16_mod_v0_1_sst512k.bin (4 copies, for SST39SF040).
Every patch checks the original bytes first, so it refuses to patch the wrong ROM version.

v0.1:
 - boot banner "Super GP Ver 1.0" -> "Super GP mod 0.1" (proof the new ROM runs)
 - LINE OUT FILTER knob law: stock coef = v*20+47 (linear, never fully off).
   New: lookup table, 0 = band off, even dB steps, same as stock at 50 (1047) and 100 (2047).
   Patched in the 4 setters (E980:3E36/3E5A/3E7E/3EA2) and the 4 patch-load blocks in E980:0A78.
"""
import sys, os, math, hashlib

STOCK_MD5 = 'ac5f56bcb3d8c30ddf3f1ffe88b13556'
VERSION = sys.argv[3] if len(sys.argv) > 3 else '0.2'   # '0.1' rebuilds the first test image
V1 = VERSION >= '1.0'
PRESETS_KEEP = 1 if V1 else 16
PRESETS_KEEP_END = PRESETS_KEEP * 114  # 0x0720 for 16
DRAGON_ROM = 0x0080 if V1 else 0x0720  # paragraph aligned: segment E000 + ROM/16
MENU_ROM = 0x0200 if V1 else 0x0A00
PRESETS_END = 128 * 114              # 0x3900
TABLE_ROM = 0x1FC00                # inside the 1 KB zero run 1FBBE-1FFEF
TABLE_DS = TABLE_ROM - 0x1A000      # DS=FA00 -> offset 0x5C00


def knob_table():
    lo_db = -40.0                                   # v=1
    mid_db = 20 * math.log10(1047 / 2047)           # v=50, stock value
    t = [0]
    for v in range(1, 101):
        if v <= 50:
            db = lo_db + (mid_db - lo_db) * (v - 1) / 49
        else:
            db = mid_db * (100 - v) / 50
        t.append(min(2047, round(2047 * 10 ** (db / 20))))
    assert t[50] == 1047 and t[100] == 2047
    return t


def setter_patch():
    # mov bx,[bp+6]; cmp bx,100; jbe +3; mov bx,100; shl bx,1; mov ax,[bx+TABLE]; nop  (18 bytes)
    return bytes([0x8B, 0x5E, 0x06, 0x83, 0xFB, 0x64, 0x76, 0x03, 0xBB, 0x64, 0x00, 0xD1, 0xE3,
                  0x8B, 0x87, TABLE_DS & 0xFF, TABLE_DS >> 8, 0x90])


def load_patch(mem):
    # mov al,[mem]; cmp al,100; jbe +2; mov al,100; mov ah,0; mov bx,ax; shl bx,1; mov ax,[bx+TABLE]; nop (20 bytes)
    return bytes([0xA0, mem & 0xFF, mem >> 8, 0x3C, 0x64, 0x76, 0x02, 0xB0, 0x64, 0xB4, 0x00, 0x8B, 0xD8,
                  0xD1, 0xE3, 0x8B, 0x87, TABLE_DS & 0xFF, TABLE_DS >> 8, 0x90])


STOCK_SETTER = bytes.fromhex('8b4606d1e0d1e08bd0d1e2d1e203c2052f00')


def stock_load(mem):
    return bytes([0xA0, mem & 0xFF, mem >> 8]) + bytes.fromhex('b400d1e0d1e08bd0d1e2d1e203c2052f00')


def main():
    rom = bytearray(open(sys.argv[1], 'rb').read())
    out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    md5 = hashlib.md5(rom).hexdigest()
    if md5 != STOCK_MD5:
        sys.exit(f'not the known stock dump (md5 {md5}), refusing')
    here = os.path.dirname(os.path.abspath(__file__))
    patches = []
    # banner (v0.5 shortens line 2 to leave 3 cells for the boot dragon)
    if V1:
        # boot line 1 "Guitar Processor" (only read by the boot banner, F6A1:0018) -> "JSW ROSETTA OS",
        # line 2 -> version, both centred (the dragon eats both lines)
        patches.append((0x1F671, b'Guitar Processor', b'JSW ROSETTA OS'.center(16)))
        banner_new = ('v' + (VERSION[:-2] if VERSION.endswith('.0') else VERSION)).encode().center(16)
    elif VERSION >= '0.5':
        banner_new = f'Super GP {VERSION}'.encode() + b'\x00   '
    else:
        banner_new = f'Super GP mod {VERSION}'.encode().ljust(16)[:16]
    assert len(banner_new) == 16
    patches.append((0x1F682, b'Super GP Ver 1.0', banner_new))
    # setters: body starts 3 bytes into each function (after push bp; mov bp,sp)
    for fn_rom in (0x0D636, 0x0D65A, 0x0D67E, 0x0D6A2):
        patches.append((fn_rom + 3, STOCK_SETTER, setter_patch()))
    # patch-load blocks in E980:0A78 (PRESENCE, TREBLE, MIDDLE, BASS)
    for at, mem in ((0x0AC39, 0x9D5A), (0x0AC5A, 0x9D5B), (0x0AC7B, 0x9D5C), (0x0AC9C, 0x9D5D)):
        patches.append((at, stock_load(mem), load_patch(mem)))
    # table
    tab = b''.join(v.to_bytes(2, 'little') for v in knob_table())
    patches.append((TABLE_ROM, bytes(len(tab)), tab))
    # v0.2: DSP backdoor (SysEx F0 7D 47 ...), code in the FF block at 19C00, hook on EE11:0D84
    if VERSION >= '0.2':
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import backdoor
        code, _ = backdoor.assemble()
        assert len(code) <= 0x400
        patches.append((backdoor.BASE_ROM, b'\xff' * len(code), code))
        patches.append((backdoor.HOOK_ROM, backdoor.HOOK_OLD, backdoor.HOOK_NEW))
    # v0.3: keep 16 factory presets (A1-1..A2-8). The only two readers (boot init F2FC:0186, preset-load menu
    # F6A1:27DA) compute src = E000:index*114; patch both to index&15 via imul. Frees ROM 0x0720-0x38FF (12.7 KB).
    if VERSION >= '0.3':
        for at, bpoff in ((0x13499, 0xFC), (0x1921E, 0xFE)):
            old = bytes([0x8B, 0x46, bpoff]) + bytes.fromhex('d1e08bd0d1e2d1e2d1e203c2d1e203c2d1e203c2')
            new = bytes([0x8B, 0x46, bpoff, 0x25, PRESETS_KEEP - 1, 0x00]) + bytes.fromhex('6bc072')  # and ax,N-1; imul ax,ax,114
            patches.append((at, old, new + b'\x90' * (len(old) - len(new))))
        patches.append((PRESETS_KEEP_END, rom[PRESETS_KEEP_END:PRESETS_END], b'\xff' * (PRESETS_END - PRESETS_KEEP_END)))

    # v0.5: boot dragon animation. Replace the banner-draw call at F6A1:0020 (ROM 0x16A30)
    # with a far call to the animation routine at E072:0000 (ROM 0x0720). Routine + 192-byte
    # frame table are written after the patch loop (into the freed/zero regions).
    if VERSION >= '0.5':
        patches.append((0x16A30, bytes.fromhex('9a0000fcf2'),
                        bytes([0x9a, 0x00, 0x00]) + (0xE000 + DRAGON_ROM // 16).to_bytes(2, 'little')))   # lcall E072/E008:0000
        # kill the stock running-man boot walk (F6A1:0040 -> lcall F6A1:0156), leave the dragon only
        patches.append((0x16A50, bytes.fromhex('9a5601a1f6'), b'\x90' * 5))
    # v0.6/0.7: PEDAL/RIG menu at E0A0:0000 (ROM 0x0A00). Main loop SYSTEM key (key 0xE, F6A1:012C: lcall F6A1:1530)
    # -> lcall E0A0:0000. The menu offers the stock System menu (SYSTEM again at the split screen).
    # (The burned v0.6 hooked F6A1:0106 = key 0xC = EDIT by mistake, and hand-mapped the buffer wrong; fixed in 0.7.)
    if VERSION >= '0.6':
        patches.append((0x16B3C, bytes.fromhex('9a3015a1f6'),
                        bytes([0x9a, 0x00, 0x00]) + (0xE000 + MENU_ROM // 16).to_bytes(2, 'little')))   # lcall E0A0/E020:0000
    # v0.8: boot as the pedal. Main init F6A1:0063 `mov byte [a312],0` (runs once, right before the main loop)
    # -> lcall E0A0:0003, which redoes that store and enters the last PEDAL/RIG mode.
    if VERSION >= '0.8':
        patches.append((0x16A73, bytes.fromhex('c60612a300'),
                        bytes([0x9a, 0x03, 0x00]) + (0xE000 + MENU_ROM // 16).to_bytes(2, 'little')))   # lcall E0A0/E020:0003

    for off, old, new in patches:
        assert len(old) == len(new), hex(off)
        if rom[off:off + len(old)] != old:
            sys.exit(f'original bytes differ at {off:05X}: {rom[off:off+len(old)].hex()} != {old.hex()}')
        rom[off:off + len(new)] = new
        print(f'patched {off:05X} ({len(new)} bytes)')
    # v0.5: drop the boot dragon routine + frame table into the free regions
    if VERSION >= '0.5':
        code = open(os.path.join(here, 'dragon_boot.bin'), 'rb').read()
        tbl = open(os.path.join(here, 'dragon_frames.bin'), 'rb').read()
        assert len(tbl) == 192
        at = DRAGON_ROM
        assert at + len(code) <= MENU_ROM
        if set(rom[at:at + len(code)]) != {0xFF}:
            sys.exit('dragon routine region not free (need v0.3+ preset trim)')
        rom[at:at + len(code)] = code
        if set(rom[0x1FCCA:0x1FCCA + len(tbl)]) != {0x00}:
            sys.exit('dragon frame-table region not zero')
        rom[0x1FCCA:0x1FCCA + len(tbl)] = tbl
        print(f'dragon routine {len(code)} B @{at:05X}, frame table 192 B @1FCCA')
    if VERSION >= '0.6':
        menu = open(os.path.join(here, 'pedal_menu.bin'), 'rb').read()
        at = MENU_ROM
        if at + len(menu) > PRESETS_END or set(rom[at:at + len(menu)]) != {0xFF}:
            sys.exit(f'pedal menu ({len(menu)} B) does not fit in the free region {at:05X}-{PRESETS_END - 1:05X}')
        rom[at:at + len(menu)] = menu
        print(f'pedal menu {len(menu)} B @{at:05X} (E{at // 16:03X}:0000), {PRESETS_END - at - len(menu)} B left')
    name = f'gp16_mod_v{VERSION.replace(".", "_")}'
    p128 = os.path.join(out, name + '.bin'); p512 = os.path.join(out, name + '_sst512k.bin')
    open(p128, 'wb').write(rom)
    open(p512, 'wb').write(bytes(rom) * 4)
    print(p128, hashlib.md5(rom).hexdigest())
    print(p512, hashlib.md5(bytes(rom) * 4).hexdigest())
    print('knob table:', knob_table()[::10])


if __name__ == '__main__':
    main()
