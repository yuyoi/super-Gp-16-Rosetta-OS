; JSW ROSETTA OS -- far overflow blob: routines + tables moved out of the full E020 region (ROM 0x0200-0x38FF).
; Lives in the stock end-of-ROM zero run at ROM 0x1FD90 (FFD9:0000, up to 0x1FFEF; the reset vector follows).
; Far functions (retf), DS = FA00 like the OS. Entry points = the jump table below (pedal_menu.asm FAR_*).
        cpu 186
        bits 16
        org 0

DIAL     equ 0xa654          ; same equates as pedal_menu.asm
DIALMAX  equ 0xa6be
DIALSTEP equ 0xa6b8
DIALWRAP equ 0xa318
ST_DSC   equ 0xce3c
ST_HOT   equ 0xce3d
TMIC     equ 0x9e
E83B_SEG equ 0xe83b
SETC1    equ 0x0679

%macro farcall 2
        db 0x9a
        dw %2
        dw %1
%endmacro

        jmp near f_dial_set          ; +0
        jmp near f_dial_val          ; +3
        jmp near f_hot               ; +6
        jmp near f_cab               ; +9

f_dial_set:                          ; ax = value, cx = max, dl = wrap. The alpha dial is a smooth (no detent) encoder
        push bx                      ; that sends many counts per turn: short ranges get S counts per position
        mov bl, 1                    ; (DIAL = v*S + S/2, max = (max+1)*S - 1; VALUE up/down step S = one position)
        cmp cx, 10
        jae .s
        mov bl, 2
        cmp cx, 5
        jae .s
        mov bl, 4
        cmp cx, 2
        jae .s
        mov bl, 6
        cmp cx, 1
        je .s
        mov bl, 1                    ; max 0: nothing to turn
.s:     mov [ST_DSC], bl
        mov bh, 0
        push dx
        mul bx
        mov dx, bx
        shr dx, 1
        add ax, dx
        mov [DIAL], ax
        mov ax, cx
        inc ax
        mul bx
        dec ax
        mov [DIALMAX], ax
        mov [DIALSTEP], bx
        pop dx
        mov [DIALWRAP], dl
        pop bx
        retf

f_dial_val:                          ; -> ax = dial position (DIAL / counts per position)
        mov ax, [DIAL]
        push dx
        push cx
        mov cl, [ST_DSC]
        mov ch, 0
        cmp cx, 1
        jbe .r
        xor dx, dx
        div cx
.r:     pop cx
        pop dx
        retf

f_hot:                               ; chip 0 step 10B (DIST stage) <- 9204a7 if [ST_HOT] else stock 1204a7. Written like
        mov ax, 0x40f0               ; the firmware's program load (commit 0, all other latches 0), timer masked
        mov es, ax
        or byte [es:TMIC], 0x40
        mov ax, 0x8000
        mov es, ax
.w:     test byte [es:0], 1
        jnz .w
        xor al, al
        mov [es:3], al
        mov [es:2], al
        mov [es:1], al
        mov [es:0], al
        mov [es:5], al
        mov [es:4], al
        mov al, 0x12
        cmp byte [ST_HOT], 0
        je .st
        mov al, 0x92
.st:    mov [es:0x0a], al
        mov byte [es:9], 0x04
        mov byte [es:8], 0xa7
        mov byte [es:0x110b], 0
        mov ax, 0x40f0
        mov es, ax
        and byte [es:TMIC], 0xbf
        retf

f_cab:                               ; al = cab 1-3 -> its 6 HI-band coefficients through the firmware's chip-1 set_coef
        dec al
        mov ah, 12
        mul ah
        add ax, cab_t0
        mov si, ax
        xor di, di
        mov ax, 0x40f0
        mov es, ax
        or byte [es:TMIC], 0x40      ; timer masked: its ISR writes the DSP too (shared latches)
.l:     mov bx, si                   ; (set_coef clobbers bx)
        push word [cs:bx+di]         ; coef
        push word [cs:di+cab_steps]  ; step
        farcall E83B_SEG, SETC1
        add sp, 4
        add di, 2
        cmp di, 12
        jb .l
        mov ax, 0x40f0
        mov es, ax
        and byte [es:TMIC], 0xbf
        retf

%include "far_data.inc"              ; cab_steps, cab_t0..2 (gen_pedal_data.py)
