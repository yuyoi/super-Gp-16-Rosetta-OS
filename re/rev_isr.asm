; REVERSE engine prototype v2, loaded into RAM over the debug port (revload.py), no burn.
; Timer 0 interrupt (vector 28) moves the tap delay's C tap (DSP chip 2 step 0x072) read address. The write head
; moves 1 sample per DSP sample, the read address grows 2 per DSP sample, so the read head runs backwards through the
; stored audio: write forwards, read backwards. At amax it wraps to amin (chunk = (amax - amin) / 2 samples).
; v2: the address follows real time, not the tick count. Each tick reads timer 1 (the firmware's free-running 1 kHz
; system timer: 1.3333 MHz, counts down MD1..0) and adds elapsed counts * k (k = 2 * 32000 / 1333333 * 65536). A
; dropped or skipped tick no longer changes the speed. No busy-wait: if the DSP bus is busy the tick only advances.
; A commit 1 takes only the A latch (measured: committest.py): a write is 3 bus writes. Skipped while TMIC2 is masked
; (the firmware and the OS mask it around their own DSP writes).
        cpu 186
        bits 16
        org 0

isr:    push ax
        push bx
        push dx
        push es
        mov ax, 0x40f0
        mov es, ax
        mov ax, [es:0x88]               ; TM1 now (counts down)
        mov bx, [cs:last]
        mov [cs:last], ax
        sub bx, ax                      ; elapsed = last - now
        jae .pos
        add bx, [cs:period]             ; timer 1 reloaded in between
.pos:   mov ax, bx
        mul word [cs:k]                 ; dx:ax = counts * k -> dx samples, ax fraction
        add [cs:frac], ax
        adc [cs:addr], dx
        mov ax, [cs:addr]
        cmp ax, [cs:amax]
        jb .in
        sub ax, [cs:amax]               ; wrap, keep the overshoot
        add ax, [cs:amin]
        mov [cs:addr], ax
.in:    cmp byte [cs:run], 0
        je .out
        test byte [es:0x9e], 0x40       ; TMIC2 masked: a DSP write is in progress elsewhere
        jnz .out
        mov dx, 0x8000
        mov es, dx
        test byte [es:0], 1             ; DSP bus busy: skip, the next tick catches up
        jnz .out
        mov [es:1], ah                  ; A latch high, low
        mov [es:0], al
        mov byte [es:0x1872], 1         ; commit 1: chip 2 step 0x072 (C tap) address = A
        mov byte [es:0x1869], 1         ; the same A into the L tap (2:069) and the R tap (2:06C): all three taps
        mov byte [es:0x186c], 1         ; read the same backwards position = more wet over the same dry
        inc word [cs:count]
.out:   pop es
        pop dx
        pop bx
        pop ax
        db 0x0f, 0x92                   ; FINT
        iret

        align 2
vars:
addr    dw 0
frac    dw 0
k       dw 3146                         ; 2 * 32000 / 1333333 * 65536
period  dw 1334                         ; MD1 + 1
last    dw 0
amin    dw 0
amax    dw 0
count   dw 0
run     db 0
