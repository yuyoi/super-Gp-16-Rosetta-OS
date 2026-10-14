; EOS probe: is V25 P0 bit 0 the DSP end-of-sample line? One-shot, run from the REVERSE engine's bank-6 timer-0 slot
; (eostest.py points the bank's VECTOR PC here). Masks TMIC0 first (runs once), then samples the whole P0 byte 256 times
; in a tight loop into buf, with timer 1 (TM1, counts down, MD1 + 1 = 1334) read before and after for the time base.
; DS = 40F0 (SFRs), CS = 06C0. Registers saved (they are the engine's state).
        cpu 186
        bits 16
        org 0x100

meas:   pusha
        push es
        mov byte [0x9c], 0x47           ; TMIC0 masked: one shot
        mov ax, cs
        mov es, ax
        mov di, buf
        mov cx, 256
        xor bx, bx
        mov dx, [0x88]
.l:     mov al, [bx]                    ; P0
        stosb
        loop .l
        mov ax, [0x88]
        mov [cs:t0], dx
        mov [cs:t1], ax
        pop es
        popa
        db 0x0f, 0x92                   ; FINT
        db 0x0f, 0x91                   ; RETRBI

        align 2
t0      dw 0x5555
t1      dw 0x5555
buf:
