; IE probe: bank-6 timer-0 ISR that stores its PSW at entry (pushf) and counts entries. Is IE still set inside a
; register-bank-switch ISR? (If yes, vectored ISRs can nest into the engine and run on bank 6 with its DS/SS.)
        cpu 186
        bits 16
        org 0

isr:    pushf
        pop word [cs:psw]
        inc word [cs:cnt]
        db 0x0f, 0x92                   ; FINT
        db 0x0f, 0x91                   ; RETRBI

        align 2
psw     dw 0x5555
cnt     dw 0
