; GP-16 PEDAL / RIG menu (v0.7). Lives at ROM 0x0A00 = E0A0:0000. Replaces the main loop's SYSTEM-key call
; (F6A1:012C: lcall F6A1:1530 -> lcall E0A0:0000). Far function, no args, DS=FA00.
; (v0.6 hooked F6A1:0106 = the EDIT key by mistake: key 0xC is EDIT, 0xE is SYSTEM.)
;   split screen: FUNCTION UP -> PEDAL mode (pick 1 of 30, pedal only)
;                 FUNCTION DOWN -> RIG mode (pedal + amp; UP/DOWN toggles the active row)
;                 SYSTEM again -> the stock System menu
;                 ESC -> back one level (mode -> split -> play)
;   dial (and BANK/GROUP = -/+) scrolls the active list; every change is applied to the edit buffer immediately.
; Apply = the SysEx path: each recipe pair (SysEx addr, value) goes through the DT1 receiver's setter EE11:17F4,
; then the SOUND CHANGE REQUEST service the main loop runs (F00E:0764 + F6A1:0382).
        cpu 186
        bits 16
        org 0

F00E_SEG equ 0xf00e
KEYT     equ 0x1cd2          ; keytest(n) -> ax (consumes the key); 0xff clears all
VALIDATE equ 0x0764          ; (buf far, flag): effect-order check, part of the stock sound-change service
F6A1_SEG equ 0xf6a1
SERVICE  equ 0x03bc          ; service(arg): keys, MIDI, dial; arg=1 enables BANK/GROUP as -/+
SYSMENU  equ 0x1530          ; stock System menu
LOADBUF  equ 0x0382          ; edit buffer -> DSPs (stock sound-change service)
EE11_SEG equ 0xee11
DT1SET   equ 0x17f4          ; (buf far, sysex addr, value): DT1 per-byte setter
E93C_SEG equ 0xe93c
CUR      equ 0x0238          ; cursor(col,line)  push col; push line
PUTC     equ 0x0000          ; putc(ch)

BUF      equ 0x9d06          ; internal edit buffer (114 B)
BUF_NAME equ 0x9d67          ; +0x61, 16 chars (play screen shows it)
SNDREQ   equ 0xa43c          ; bit 0x20 = sound change pending (SysEx 0x75 sets it, main loop serves it)
SNDHOLD  equ 0x9fcc          ; bit 0x40 = main loop defers sound changes
DIAL     equ 0xa654          ; dial value (word), kept 0..DIALMAX by the encoder ISR
DIALMAX  equ 0xa6be
DIALSTEP equ 0xa6b8
DIALWRAP equ 0xa318
ST_PED   equ 0xcf30          ; persisted selections (battery RAM, validated on entry)
ST_AMP   equ 0xcf31
ST_ROW   equ 0xcf32
ST_ON    equ 0xcf33          ; 3 B scratch: merged SysEx 0x0C/0x0D/0x0E (B2 type, on/off hi, on/off lo)

K_ESC    equ 0x0d
K_SYS    equ 0x0e
K_UP     equ 0x0f            ; FUNCTION (stock page step: 0xF = next, 0x10 = previous)
K_DN     equ 0x10
K_CLR    equ 0xff
NPED     equ 30              ; max pedal index (0 = OFF)
NAMP     equ 7               ; max amp index   (0 = OFF)

%macro farcall 2
        db 0x9a
        dw %2
        dw %1
%endmacro

menu:
        push bp
        mov bp, sp
        sub sp, 2                    ; [bp-2] = state: 0 split, 1 pedal, 2 rig
        push si
        push di
        cmp byte [ST_PED], NPED
        jbe .okp
        mov byte [ST_PED], 0
.okp:   cmp byte [ST_AMP], NAMP
        jbe .oka
        mov byte [ST_AMP], 0
.oka:   and byte [ST_ROW], 1
        mov ax, K_CLR
        call keyt
        mov word [bp-2], 0
        call draw_split
.loop:
        mov ax, 1
        push ax
        farcall F6A1_SEG, SERVICE
        add sp, 2
        mov ax, K_ESC
        call keyt
        jz .noesc
        cmp word [bp-2], 0
        je .exit                     ; ESC at split -> play
        mov word [bp-2], 0           ; ESC in a mode -> split
        call draw_split
        jmp .loop
.noesc:
        mov ax, K_SYS
        call keyt
        jz .nosys
        cmp word [bp-2], 0
        jne .loop
        farcall F6A1_SEG, SYSMENU    ; SYSTEM at split -> stock System menu
        jmp .exit
.nosys:
        cmp word [bp-2], 0
        jne .notsplit
        mov ax, K_UP
        call keyt
        jz .chkdn
        mov word [bp-2], 1           ; -> PEDAL mode
        mov al, [ST_PED]
        mov ah, 0
        mov cx, NPED
        call dial_set
        call draw_pedal
        call apply_pedal_only
        jmp .loop
.chkdn: mov ax, K_DN
        call keyt
        jz .loop
        mov word [bp-2], 2           ; -> RIG mode
        call rig_dial
        call draw_rig
        call apply_rig
        jmp .loop
.notsplit:
        cmp word [bp-2], 1
        jne .rig
        mov ax, [DIAL]               ; PEDAL mode: dial = selection
        cmp al, [ST_PED]
        je .loop
        mov [ST_PED], al
        call draw_pedal
        call apply_pedal_only
        jmp .loop
.rig:
        mov ax, K_UP
        call keyt
        jnz .togg
        mov ax, K_DN
        call keyt
        jz .rigdial
.togg:  xor byte [ST_ROW], 1         ; UP/DOWN toggles the active row
        call rig_dial
        call draw_rig
        jmp .loop
.rigdial:
        mov ax, [DIAL]
        cmp byte [ST_ROW], 0
        jne .rigamp
        cmp al, [ST_PED]
        je .loop
        mov [ST_PED], al
        jmp .rigchg
.rigamp:
        cmp al, [ST_AMP]
        je .loop
        mov [ST_AMP], al
.rigchg:
        call draw_rig
        call apply_rig
        jmp .loop
.exit:
        pop di
        pop si
        mov sp, bp
        pop bp
        retf

; ---------------------------------------------------------------- apply
apply_pedal_only:
        mov al, [ST_PED]
        mov ah, 0
        xor dx, dx
        jmp apply
apply_rig:
        mov al, [ST_PED]
        mov ah, 0
        mov dl, [ST_AMP]
        mov dh, 0
apply:                               ; ax = pedal idx, dx = amp idx
        push dx
        push ax
        mov byte [ST_ON], 0          ; all blocks off, then OR in each entry's blocks
        mov byte [ST_ON+1], 0
        mov byte [ST_ON+2], 0
        mov bx, ax
        shl bx, 1
        mov si, [cs:ped_off+bx]
        call apply_entry
        pop ax
        pop dx
        push dx
        push ax
        mov bx, dx
        shl bx, 1
        mov si, [cs:amp_off+bx]
        call apply_entry             ; amp last: its EQ/cab wins
        mov bl, 0x0c                 ; block type + on/off (firmware packs them into the 16-bit word)
        mov al, [ST_ON]
        call dt1set
        mov bl, 0x0d
        mov al, [ST_ON+1]
        call dt1set
        mov bl, 0x0e
        mov al, [ST_ON+2]
        call dt1set
        pop ax
        pop dx
        mov bx, ax                   ; name = pedal, else amp, else OFF
        test ax, ax
        jnz .pn
        mov bx, dx
        test dx, dx
        jnz .an
        mov si, ped_e0
        jmp .cp
.pn:    shl bx, 1
        mov si, [cs:ped_off+bx]
        jmp .cp
.an:    shl bx, 1
        mov si, [cs:amp_off+bx]
.cp:    mov di, BUF_NAME
        mov cx, 16
.cl:    mov al, [cs:si]
        mov [di], al
        inc si
        inc di
        loop .cl
                                     ; SOUND CHANGE REQUEST, served now (= main loop F6A1:007E..00A5)
        or byte [SNDREQ], 0x20
        test byte [SNDHOLD], 0x40
        jnz .defer                   ; main loop serves it after we return
        and byte [SNDREQ], 0xdf
        mov ax, 1
        push ax
        mov ax, 0xfa00
        push ax
        mov ax, BUF
        push ax
        farcall F00E_SEG, VALIDATE
        add sp, 6
        farcall F6A1_SEG, LOADBUF
.defer: ret

apply_entry:                         ; cs:si -> entry (name16, count, count x (sysex addr, value))
        add si, 16
        mov cl, [cs:si]
        mov ch, 0
        inc si
        jcxz .done
.p:     push cx
        mov bl, [cs:si]
        mov al, [cs:si+1]
        add si, 2
        cmp bl, 0x0c
        jb .set
        cmp bl, 0x0e
        ja .set
        mov bh, 0
        or [bx+ST_ON-0x0c], al       ; on/off + type: merge, written once at the end
        jmp .nx
.set:   call dt1set
.nx:    pop cx
        loop .p
.done:  ret

dt1set:                              ; bl = SysEx addr, al = value -> EE11:17F4(FA00:9D06, addr, value)
        push si
        push di
        mov ah, 0
        push ax
        mov bh, 0
        push bx
        mov ax, 0xfa00
        push ax
        mov ax, BUF
        push ax
        farcall EE11_SEG, DT1SET
        add sp, 8
        pop di
        pop si
        ret

; ---------------------------------------------------------------- dial
rig_dial:
        cmp byte [ST_ROW], 0
        jne .amp
        mov al, [ST_PED]
        mov ah, 0
        mov cx, NPED
        jmp dial_set
.amp:   mov al, [ST_AMP]
        mov ah, 0
        mov cx, NAMP
dial_set:                            ; ax = value, cx = max
        mov [DIAL], ax
        mov [DIALMAX], cx
        mov word [DIALSTEP], 1
        mov byte [DIALWRAP], 1
        ret

; ---------------------------------------------------------------- screens
draw_split:
        xor ax, ax
        mov cx, 1
        call cursor
        mov si, s_split1
        mov cx, 16
        call puts
        xor ax, ax
        mov cx, 2
        call cursor
        mov si, s_split2
        mov cx, 16
        jmp puts

draw_pedal:
        xor ax, ax
        mov cx, 1
        call cursor
        mov si, s_pedal
        mov cx, 16
        call puts
        xor ax, ax
        mov cx, 2
        call cursor
        mov al, [ST_PED]
        mov ah, 0
        mov bx, ax
        shl bx, 1
        mov si, [cs:ped_off+bx]
        mov cx, 16
        jmp puts

draw_rig:
        xor ax, ax
        mov cx, 1
        call cursor
        mov al, ' '
        cmp byte [ST_ROW], 0
        jne .m1
        mov al, '>'
.m1:    call putc
        mov al, 'P'
        call putc
        mov al, ':'
        call putc
        mov al, [ST_PED]
        mov ah, 0
        mov bx, ax
        shl bx, 1
        mov si, [cs:ped_off+bx]
        mov cx, 13
        call puts
        xor ax, ax
        mov cx, 2
        call cursor
        mov al, ' '
        cmp byte [ST_ROW], 1
        jne .m2
        mov al, '>'
.m2:    call putc
        mov al, 'A'
        call putc
        mov al, ':'
        call putc
        mov al, [ST_AMP]
        mov ah, 0
        mov bx, ax
        shl bx, 1
        mov si, [cs:amp_off+bx]
        mov cx, 13
        jmp puts

; ---------------------------------------------------------------- helpers
cursor:                              ; ax = col, cx = line
        push ax
        push cx
        farcall E93C_SEG, CUR
        add sp, 4
        ret

putc:                                ; al
        push ax
        mov ah, 0
        push ax
        farcall E93C_SEG, PUTC
        add sp, 2
        pop ax
        ret

puts:                                ; cs:si, cx chars (di = counter, survives far calls)
        mov di, cx
.l:     mov al, [cs:si]
        call putc
        inc si
        dec di
        jnz .l
        ret

keyt:                                ; ax = key -> ax, ZF
        push ax
        farcall F00E_SEG, KEYT
        add sp, 2
        test ax, ax
        ret

s_split1: db " UP  = PEDAL    "
s_split2: db " DOWN= RIG      "
s_pedal:  db "PEDAL MODE      "
%include "pedal_data.inc"
