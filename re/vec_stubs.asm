; Vector stubs for the firmware's two 1 ms timer ISRs (vector 29 = counters E83B:0C92, vector 30 = pedal tick
; E83B:0CF0, both priority 7). Their in-service (ISPR) bit stays set for the whole ISR, and while it is set the V25
; accepts NO other maskable interrupt, at any priority (STI inside doesn't help): the REVERSE engine's timer 0 lost
; ~2.3 ticks per ms (timertest.py: 13,810 of 16,064/s; with these stubs 16,054/s). FINT first clears that bit.
; The pedal tick writes the DSP only when the expression pedal moves (setters, commits 0/8 = instruction/coefficient:
; they don't take the A latch, so an engine write landing between their latch writes and their commit is harmless,
; unless the pedal is assigned to an address parameter). Masking TMIC2 for the pedal tick instead (engine skips while
; masked) cost 40% of the engine's updates: the pedal tick stretches to ~400 us/ms with the engine running inside it.
; In RAM at 06C0:01C0 (DS FA00:CDC0; keep below 06C0:0200 = DS CE00, the OS state starts at CE20).
        cpu 186
        bits 16
        org 0x1c0

s29:    db 0x0f, 0x92                   ; FINT
        jmp 0xe83b:0x0c92               ; stock ISR (STI, counters, FINT, IRET)

        align 16
s30:    db 0x0f, 0x92                   ; FINT
        jmp 0xe83b:0x0cf0               ; stock ISR (pedal tick, FINT, IRET)
