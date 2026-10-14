; Priority probe: plain vectored timer-0 ISR (vector 28 -> 06C0:0080) that only counts entries. vectest.py runs it at
; several TMIC0 priorities to see which ones the firmware's 1 ms timer ISRs (priority 7, STI inside) let through.
        cpu 186
        bits 16
        org 0x80

isr:    inc word [cs:cnt]
        db 0x0f, 0x92                   ; FINT
        iret

        align 2
cnt     dw 0
