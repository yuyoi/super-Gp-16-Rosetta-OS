; REVERSE engine v3e ("compressed"): timer 0 at ~31.7 kHz through V25 REGISTER BANK SWITCHING (TMIC0 ENCS = 1,
; priority 6 = bank 6). Bank layout confirmed on the unit (v3d left DS0 = 40F0 at +08, DS1 = 8000 at +0E), so the
; segments are set once by the loader and persist.
; Bank 6 registers: BX = read address A, CX = fraction, BP:DX = step per tick (int:frac), SI = amin, DI = amax,
; AL = ticks until the next resync. DS = 40F0 (SFRs), ES = 8000 (DSP bus).
; Every tick (cheap): A += step, wrap, 3 bus writes (A latch high, low, commit 1 on chip 2 step 0x072), skipped
; while TMIC2 is masked (a DSP write elsewhere).
; Every 8th tick (exact): elapsed timer-1 counts * k - 8 * step is added to A, so lost ticks never change the speed
; (k = (1 - speed) * 32000 / 1333333 * 65536, step = (1 - speed) * 32000 / tick rate). FINT + RETRBI.
        cpu 186
        bits 16
        org 0

isr:    add cx, dx
        adc bx, bp
        cmp bx, di
        jb .in
        sub bx, di
        add bx, si
.in:    test byte [0x9e], 0x40          ; TMIC2 masked: someone else is writing the DSP
        jnz .sk
        mov [es:1], bh
        mov [es:0], bl
        mov byte [es:0x1872], 1         ; commit 1: chip 2 step 0x072 address = A
.sk:    dec al
        jz .sync
.out:   db 0x0f, 0x92                   ; FINT
        db 0x0f, 0x91                   ; RETRBI

.sync:  mov [cs:sdx], dx                ; keep the step fraction
        mov ax, [0x88]                  ; TM1 now (counts down, period MD1 + 1)
        mov dx, [cs:last]
        mov [cs:last], ax
        sub dx, ax                      ; elapsed counts since the last resync
        jae .p
        add dx, [cs:period]
.p:     mov ax, dx
        mul word [cs:k]                 ; dx:ax = true advance (16.16)
        sub ax, [cs:applf]              ; minus what 8 ticks applied
        sbb dx, [cs:appli]
        add cx, ax                      ; correction (signed)
        adc bx, dx
        cmp bx, di                      ; wrap both ways
        jb .w1
        sub bx, di
        add bx, si
.w1:    cmp bx, si
        jae .w2
        add bx, di
        sub bx, si
.w2:    mov dx, [cs:sdx]
        mov ax, 8
        jmp .out

        align 2
k       dw 3146                         ; true advance per timer-1 count (16.16): speed -1
period  dw 1334                         ; MD1 + 1
last    dw 0
sdx     dw 0
applf   dw 0                            ; 8 * step per tick, fraction / integer
appli   dw 16
