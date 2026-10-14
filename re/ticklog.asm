; Tick log probe: bank-6 timer-0 ISR that stores TM1 (1.3333 MHz, counts down MD1..0, period 1334) at every entry
; into a 128-word ring at 06C0:0200-02FF (0300+ = RAM 6F00 = debug parser state, keep out) (DI = write pointer). Gaps show when and how often the CPU blocks interrupts.
; Bank 6: ES = 40F0 (SFRs), PS = SS = 06C0. No DSP access.
        cpu 186
        bits 16
        org 0

isr:    mov ax, [es:0x88]
        mov [cs:di], ax
        add di, 2
        and di, 0xff
        or di, 0x200
        db 0x0f, 0x92                   ; FINT
        db 0x0f, 0x91                   ; RETRBI
