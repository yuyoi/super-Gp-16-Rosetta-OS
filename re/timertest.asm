; Timer-0 probe: does writing MD0 inside the ISR restart the count (= every tick runs late)? Bank-6 ISR that only
; counts entries and, when wr != 0, writes MD0 = 82 every tick (the same value it already holds). No DSP access.
; Bank 6: ES = 40F0 (SFRs), PS = SS = 06C0.
        cpu 186
        bits 16
        org 0

isr:    inc word [cs:nent]
        cmp word [cs:wr], 0
        je .o
        mov word [es:0x82], 82
.o:     db 0x0f, 0x92                   ; FINT
        db 0x0f, 0x91                   ; RETRBI

        align 2
nent    dw 0
wr      dw 0
