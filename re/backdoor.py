#!/usr/bin/env python3
"""GP-16 DSP backdoor: x86-16 code for the free ROM block at 0x19C00 (CS=F9C0, IP=0).
Hand-encoded (keystone's 16-bit mode emits 0x66 prefixes the V25 can't run); checked with capstone.

Hook: EE11:0D84 (SysEx byte handler, main loop, DS=FA00) -> jmp far F9C0:0000.
Messages (data as nibbles 0-F), never passed on to the Roland parser:
  F0 7D 47 01 chip s2 s1 s0  i5 i4 i3 i2 i1 i0  c3 c2 c1 c0  m1 m0  F7   (18 data bytes after 7D)
        write DSP chip 0-2, step 0-1FF, 24-bit instruction, 16-bit coefficient, then commit value m
        to 8000:(0x1000 + chip*0x400 + step)  (firmware uses m=0 instruction only, m=8 with coefficient)
  F0 7D 47 02 o3 o2 o1 o0 v1 v0 F7      raw write byte v to 8000:o
  F0 7D 47 03 o3 o2 o1 o0 F7            raw read 8000:o -> F0 7D 47 43 o3 o2 o1 o0 v1 v0 F7
  F0 7D 47 04 F7                        ping -> F0 7D 47 44 <version> F7
RAM: DS:CF00 active flag, CF01 count, CF02.. buffer (RAM 0x6F00-0x6F1B, not used by the firmware).
"""
import capstone

VERSION = 3
BASE_ROM = 0x19C00
CS, IP = 0xF9C0, 0x0000
HOOK_ROM = 0x0EE94                      # EE11:0D84
HOOK_OLD = bytes.fromhex('558bec83ec01')
HOOK_NEW = bytes([0xEA, IP & 0xFF, IP >> 8, CS & 0xFF, CS >> 8, 0x90])


def w(v): return f'{v & 0xFF:02x}{(v >> 8) & 0xFF:02x}'


ACTIVE, COUNT, BUF = 0xCF00, 0xCF01, 0xCF02
SEGSV, OFFSV, CNTSV = 0xCF1A, 0xCF1C, 0xCF1E   # v3 scratch for the seg:off memory commands

# ('L', name) label | ('b', hex) bytes | ('j8', opcode, label) short jcc/jmp/loop | ('j16', opcode, label) near jmp/call
P = [
 ('L', 'entry'),
 ('b', 'f606' + w(0xA430) + '40'),        # test byte [A430],40   (inside a SysEx?)
 ('j8', 0x74, 'orig'),                    # jz orig
 ('b', '55 8bec 8a4606'),                 # push bp; mov bp,sp; mov al,[bp+6]
 ('b', '803e' + w(0xA314) + '00'),        # cmp byte [A314],0     (first byte after F0?)
 ('j8', 0x75, 'notfirst'),
 ('b', '3c7d'),                           # cmp al,7D
 ('j8', 0x75, 'notmine'),
 ('b', 'c606' + w(ACTIVE) + '01'),        # active = 1
 ('b', 'c606' + w(COUNT) + '00'),         # count = 0
 ('b', 'fe06' + w(0xA314)),               # inc byte [A314]  (so later bytes are not "first")
 ('j8', 0xEB, 'done'),
 ('L', 'notmine'),
 ('b', 'c606' + w(ACTIVE) + '00'),        # active = 0
 ('b', '5d'),                             # pop bp
 ('j8', 0xEB, 'orig'),
 ('L', 'notfirst'),
 ('b', '803e' + w(ACTIVE) + '01'),        # cmp active,1
 ('j8', 0x74, 'mine'),
 ('b', '5d'),
 ('j8', 0xEB, 'orig'),
 ('L', 'mine'),
 ('b', '30ff'),                           # xor bh,bh
 ('b', '8a1e' + w(COUNT)),                # mov bl,[count]
 ('b', '80fb18'),                         # cmp bl,24
 ('j8', 0x73, 'done'),                    # jae done (buffer full: swallow)
 ('b', '8887' + w(BUF)),                  # mov [bx+BUF],al
 ('b', 'fec3'),                           # inc bl
 ('b', '881e' + w(COUNT)),                # mov [count],bl
 ('b', '56'),                             # push si
 ('j16', 0xE8, 'check'),                  # call check
 ('b', '5e'),                             # pop si
 ('L', 'done'),
 ('b', '5d 33c0 cb'),                     # pop bp; xor ax,ax; retf
 ('L', 'orig'),
 ('b', '55 8bec 83ec01'),                 # displaced prologue: push bp; mov bp,sp; sub sp,1
 ('b', 'ea8a0d11ee'),                     # jmp far EE11:0D8A

 # ---- check: bl = bytes received (incl. 0x47 + cmd)
 ('L', 'check'),
 ('b', '803e' + w(BUF) + '47'),           # cmp [BUF],47
 ('j8', 0x75, 'chk_ret'),
 ('b', 'a0' + w(BUF + 1)),                # mov al,[BUF+1] (cmd)
 ('b', 'be' + w(BUF + 2)),                # mov si,BUF+2
 ('b', '3c01'), ('j8', 0x75, 'd2'), ('j16', 0xE9, 'c_write'), ('L', 'd2'),
 ('b', '3c02'), ('j8', 0x75, 'd3'), ('j16', 0xE9, 'c_raww'), ('L', 'd3'),
 ('b', '3c03'), ('j8', 0x75, 'd4'), ('j16', 0xE9, 'c_rawr'), ('L', 'd4'),
 ('b', '3c04'), ('j8', 0x75, 'd5'), ('j16', 0xE9, 'c_ping'), ('L', 'd5'),
 ('b', '3c05'), ('j8', 0x75, 'd6'), ('j16', 0xE9, 'c_peek'), ('L', 'd6'),
 ('b', '3c06'), ('j8', 0x75, 'chk_ret'), ('j16', 0xE9, 'c_poke'),
 ('L', 'chk_ret'),
 ('b', 'c3'),

 # ---- cmd 5: read <n> bytes at seg:off -> 47 45 <seg4> <off4> <2 nibbles per byte>
 ('L', 'c_peek'),
 ('b', '80fb0c'),                         # cmp bl,12
 ('j8', 0x74, 'pk_go'), ('b', 'c3'), ('L', 'pk_go'),
 ('j16', 0xE8, 'get4'), ('b', '8916' + w(SEGSV)),   # call get4; mov [SEGSV],dx
 ('j16', 0xE8, 'get4'), ('b', '8916' + w(OFFSV)),   # call get4; mov [OFFSV],dx
 ('j16', 0xE8, 'get2'), ('b', 'a2' + w(CNTSV)),     # call get2; mov [CNTSV],al
 ('b', 'b0f0'), ('j16', 0xE8, 'send'),
 ('b', 'b07d'), ('j16', 0xE8, 'send'),
 ('b', 'b047'), ('j16', 0xE8, 'send'),
 ('b', 'b045'), ('j16', 0xE8, 'send'),
 ('b', 'a0' + w(SEGSV + 1)), ('j16', 0xE8, 'sendhex'),   # echo seg hi
 ('b', 'a0' + w(SEGSV)),     ('j16', 0xE8, 'sendhex'),   # echo seg lo
 ('b', 'a0' + w(OFFSV + 1)), ('j16', 0xE8, 'sendhex'),   # echo off hi
 ('b', 'a0' + w(OFFSV)),     ('j16', 0xE8, 'sendhex'),   # echo off lo
 ('b', '8e06' + w(SEGSV)),                # mov es,[SEGSV]
 ('b', '8b1e' + w(OFFSV)),                # mov bx,[OFFSV]
 ('b', '8a0e' + w(CNTSV)),                # mov cl,[CNTSV]
 ('L', 'pk_loop'),
 ('b', '268a07'),                         # mov al,es:[bx]
 ('j16', 0xE8, 'sendhex'),
 ('b', '43 fec9'),                        # inc bx; dec cl
 ('j8', 0x75, 'pk_loop'),
 ('b', 'b0f7'), ('j16', 0xE8, 'send'),
 ('b', 'c3'),

 # ---- cmd 6: write byte <v> to seg:off
 ('L', 'c_poke'),
 ('b', '80fb0c'),                         # cmp bl,12
 ('j8', 0x74, 'po_go'), ('b', 'c3'), ('L', 'po_go'),
 ('j16', 0xE8, 'get4'), ('b', '8bca'),    # call get4; mov cx,dx  (seg)
 ('j16', 0xE8, 'get4'),                   # call get4  (dx = off)
 ('j16', 0xE8, 'get2'),                   # call get2  (al = value)
 ('b', '8bda 8ec1'),                      # mov bx,dx; mov es,cx
 ('b', '9c fa 268807 9d c3'),             # pushf; cli; es:[bx]=al; popf; ret

 # ---- get2: al = [si]<<4 | [si+1]; si += 2
 ('L', 'get2'),
 ('b', '8a04 d0e0 d0e0 d0e0 d0e0 0a4401 83c602 c3'),
 # ---- get4: dx = 16-bit from 4 nibbles
 ('L', 'get4'),
 ('j16', 0xE8, 'get2'), ('b', '8af0'),    # call get2; mov dh,al
 ('j16', 0xE8, 'get2'), ('b', '8ad0 c3'), # call get2; mov dl,al; ret
 # ---- wait_dsp: poll es:[0] bit0 with timeout
 ('L', 'wait_dsp'),
 ('b', 'b9ff7f'),                         # mov cx,7FFF
 ('L', 'wd_loop'),
 ('b', '26f606000001'),                   # test byte es:[0],1
 ('j8', 0x74, 'wd_ok'),
 ('j8', 0xE2, 'wd_loop'),                 # loop
 ('L', 'wd_ok'),
 ('b', 'c3'),

 # ---- cmd 1: full DSP word write
 ('L', 'c_write'),
 ('b', '80fb12'),                         # cmp bl,18
 ('j8', 0x74, 'cw_go'), ('b', 'c3'), ('L', 'cw_go'),
 ('b', '8a1c 46 83e303 d1e3 d1e3'),       # mov bl,[si]; inc si; and bx,3; shl bx,1 x2  (chip*4)
 ('b', '8afb 32db 80c710'),               # mov bh,bl; xor bl,bl; add bh,10  -> 0x1000 + chip*0x400
 ('b', '8a04 2401 0af8'),                 # mov al,[si]; and al,1; or bh,al   (step bit 8)
 ('b', '8a4401 d0e0 d0e0 d0e0 d0e0 0a4402 8ad8'),  # bl = s1<<4 | s0
 ('b', '83c603'),                         # add si,3
 ('b', '9c fa 53'),                       # pushf; cli; push bx
 ('b', 'b80080 8ec0'),                    # es = 8000
 ('j16', 0xE8, 'wait_dsp'),
 ('j16', 0xE8, 'get2'), ('b', '26a20a00'),   # es:[0A] = instr hi
 ('j16', 0xE8, 'get2'), ('b', '26a20900'),   # es:[09] = instr mid
 ('j16', 0xE8, 'get2'), ('b', '26a20800'),   # es:[08] = instr lo
 ('j16', 0xE8, 'get2'), ('b', '26a20500'),   # es:[05] = coef hi
 ('j16', 0xE8, 'get2'), ('b', '26a20400'),   # es:[04] = coef lo
 ('j16', 0xE8, 'get2'),                      # al = commit value
 ('b', '5b 268807 9d c3'),                # pop bx; mov es:[bx],al; popf; ret

 # ---- cmd 2: raw write
 ('L', 'c_raww'),
 ('b', '80fb08'),
 ('j8', 0x74, 'rw_go'), ('b', 'c3'), ('L', 'rw_go'),
 ('j16', 0xE8, 'get4'),
 ('j16', 0xE8, 'get2'),
 ('b', '8bda ba0080 8ec2 9c fa 268807 9d c3'),  # mov bx,dx; es=8000; pushf; cli; es:[bx]=al; popf; ret

 # ---- cmd 3: raw read + reply
 ('L', 'c_rawr'),
 ('b', '80fb06'),
 ('j8', 0x74, 'rr_go'), ('b', 'c3'), ('L', 'rr_go'),
 ('j16', 0xE8, 'get4'),
 ('b', '8bda b80080 8ec0 268a0f 51 52'),  # mov bx,dx; es=8000; mov cl,es:[bx]; push cx; push dx
 ('b', 'b0f0'), ('j16', 0xE8, 'send'),
 ('b', 'b07d'), ('j16', 0xE8, 'send'),
 ('b', 'b047'), ('j16', 0xE8, 'send'),
 ('b', 'b043'), ('j16', 0xE8, 'send'),
 ('b', '5a 8ac6'), ('j16', 0xE8, 'sendhex'),   # pop dx; al=dh
 ('b', '8ac2'), ('j16', 0xE8, 'sendhex'),      # al=dl
 ('b', '59 8ac1'), ('j16', 0xE8, 'sendhex'),   # pop cx; al=cl
 ('b', 'b0f7'), ('j16', 0xE8, 'send'),
 ('b', 'c3'),

 # ---- cmd 4: ping
 ('L', 'c_ping'),
 ('b', '80fb02'),
 ('j8', 0x74, 'pg_go'), ('b', 'c3'), ('L', 'pg_go'),
 ('b', 'b0f0'), ('j16', 0xE8, 'send'),
 ('b', 'b07d'), ('j16', 0xE8, 'send'),
 ('b', 'b047'), ('j16', 0xE8, 'send'),
 ('b', 'b044'), ('j16', 0xE8, 'send'),
 ('b', f'b0{VERSION:02x}'), ('j16', 0xE8, 'send'),
 ('b', 'b0f7'), ('j16', 0xE8, 'send'),
 ('b', 'c3'),

 # ---- sendhex: al as two nibbles
 ('L', 'sendhex'),
 ('b', '50 d0e8 d0e8 d0e8 d0e8'),         # push ax; shr al,1 x4
 ('j16', 0xE8, 'send'),
 ('b', '58 240f'),                        # pop ax; and al,0F
 ('j16', 0xE8, 'send'),
 ('b', 'c3'),

 # ---- send: queue al on MIDI OUT via firmware EE11:11BA(word)
 ('L', 'send'),
 ('b', '53 51 52 06 32e4 50'),            # push bx,cx,dx,es; xor ah,ah; push ax
 ('b', '9aba1111ee'),                     # call far EE11:11BA
 ('b', '83c402 07 5a 59 5b c3'),          # add sp,2; pop es,dx,cx,bx; ret
]


def size(item):
    k = item[0]
    if k == 'L': return 0
    if k == 'b': return len(bytes.fromhex(item[1].replace(' ', '')))
    if k == 'j8': return 2
    if k == 'j16': return 3


def assemble():
    labels, pc = {}, IP
    for it in P:
        if it[0] == 'L':
            assert it[1] not in labels, it[1]
            labels[it[1]] = pc
        pc += size(it)
    out = bytearray(); pc = IP
    for it in P:
        k = it[0]
        if k == 'b': out += bytes.fromhex(it[1].replace(' ', ''))
        elif k == 'j8':
            rel = labels[it[2]] - (pc + 2)
            assert -128 <= rel <= 127, f'short jump out of range to {it[2]}: {rel}'
            out += bytes([it[1], rel & 0xFF])
        elif k == 'j16':
            rel = (labels[it[2]] - (pc + 3)) & 0xFFFF
            out += bytes([it[1], rel & 0xFF, rel >> 8])
        pc += size(it)
    code = bytes(out)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    n = sum(i.size for i in md.disasm(code, IP))
    assert n == len(code), f'capstone decoded {n} of {len(code)} bytes'
    assert b'\x66' not in bytes(i.bytes[0] for i in md.disasm(code, IP)), '0x66 prefix found'
    return code, labels


if __name__ == '__main__':
    code, labels = assemble()
    inv = {v: k for k, v in labels.items()}
    print(len(code), 'bytes')
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    for i in md.disasm(code, IP):
        if i.address in inv: print(f'{inv[i.address]}:')
        print(f"  {CS:04X}:{i.address:04X} {i.bytes.hex():14s} {i.mnemonic} {i.op_str}")
