; REVERSE engine v8 = v6 "locked + fades" + the instruction-latch fix (2026-10-14): every address write resets the
; instruction latch's top byte, because commit 1 takes it along with A; v6 left 09 (the level MAC) there after a fade write,
; so its commit 1s turned the C tap into a 09xxxx op (wet gone, probably the hang). NLEV 16 = 4 ms fades.
; Original v6 notes: one tap-address write every 2 DSP frames (16 kHz), phase-locked to the DSP itself,
; and the wet fades out just before each chunk jump and back in just after, so the jump happens in silence.
; Why: a commit stays busy until the DSP applies it, and back-to-back commits complete exactly every 2 frames
; (clocktest.py: 41.69 timer counts per frame = 31.98 kHz, 2 frames per cycle, every cycle). So 2 frames is the fastest
; update, and the busy flag is a DSP-locked clock. v3e wrote at an unlocked 31.7 kHz: uneven updates = the buzz.
; (P0.0 is NOT the DSP frame clock: ~20-31 kHz, irregular. v4 locked to it by mistake.)
; PLL on the busy flag: at entry, busy = early (the last commit isn't applied yet): spin until it is (short when locked),
; next period 84 timer counts (63.0 us). Not busy = late: 83 counts (62.25 us). The 2-frame cycle is 83.38 counts, so
; each write lands right after the previous one is applied: every update at the same frame phase, same integer step.
; Fades (user's idea: drop out sensibly instead of crashing): the C level lives in 2:076 + 2:07C (instruction 090038,
; commit 8 = instruction + coefficient; the coefficient is 11-bit two's complement there, level 100 = 0x400 = -1.0).
; A level write costs one address slot, so while fading the ISR alternates address and level writes: the skipped head
; moves land under the dip. NLEV steps per fade, each written to both steps: 4 * NLEV ticks = 2 ms at NLEV 8.
; States: 0 full, 1 fading out, 3 silent hold (address writes only) until the wrap, 2 fading in, 4 fades off.
; CPU budget: this V25 runs ~1 us per instruction byte and a tick is 62.5 us, so the per-tick path stays as short as v5
; (the first v6 spent ~25 more bytes per tick on the fade check and lost a third of the ticks, starving the main loop):
; the wrap and the fade work sit on rarely taken branches, and "near the jump?" is one compare with ftrig (the loader
; precomputes amax - fade window).
; Timer 0, register bank 6 (TMIC0 0x16). Bank 6: DS = 8000 (DSP bus), ES = 40F0 (SFRs), PS = SS = 06C0, SP = 01B0.
; AL = 1 (commit 1 / busy bit), AH = scratch, BX = A, BP = step per update (2 * (1 - speed)), DX = amax,
; CX = chunk length (amax - amin), SI = 0 (bus base), DI = 0x1872 (commit: chip 2 step 0x072 = C tap).
        cpu 186
        bits 16
        org 0
NLEV    equ 16

isr:    test [si], al                   ; busy: early
        jz .late
        mov word [es:0x82], 83          ; next period 84 counts
        mov ah, 12
.sp:    test [si], al                   ; wait for the apply
        jz .go
        dec ah
        jnz .sp
        inc word [cs:nbusy]             ; never applied (firmware writing?): skip this update and
        mov word [es:0x82], 1000        ; back off 0.75 ms: the engine must never hog the CPU (MIDI = the off switch)
        jmp .out
.late:  mov word [es:0x82], 82          ; next period 83 counts
.go:    add bx, bp                      ; A += step (2 frames)
        cmp bx, dx
        jae .wrap
.in:    test byte [es:0x9e], 0x40       ; TMIC2 masked: the firmware is writing the DSP
        jnz .fw
        cmp byte [cs:fstate], 0
        jne .fade
        cmp bx, [cs:ftrig]              ; full level: near the jump?
        jae .fstart
.addr:  mov [si + 1], bh                ; A latch high, low
        mov [si], bl
        mov byte [si + 0x0a], 0         ; instruction latch top byte = the C tap's (00): commit 1 takes it too
        mov [di], al                    ; commit 1: C tap address = A
        inc word [cs:nwr]
.out:   db 0x0f, 0x92                   ; FINT
        db 0x0f, 0x91                   ; RETRBI

.wrap:  sub bx, cx                      ; back to the chunk start (the fade-out has the wet at 0 by now)
        cmp byte [cs:fstate], 4
        je .in
        mov byte [cs:fstate], 2         ; fade back in
        mov byte [cs:fi], 0
        jmp .in
.fw:    inc word [cs:nfw]
        jmp .out
.fstart:
        mov byte [cs:fstate], 1         ; start the fade-out
        mov byte [cs:fi], 0
        inc word [cs:nfad]
.fade:  mov ah, [cs:fstate]
        cmp ah, 3
        jae .addr                       ; 3 silent hold / 4 fades off: keep the head moving
        xor byte [cs:tog], 1            ; fading: alternate address and level writes
        jz .addr
        push bx
        mov bl, [cs:fi]
        mov bh, 0
        push bx                         ; fi: bit 0 picks 2:076 / 2:07C
        and bl, 0xfe                    ; level index * 2 = word offset
        cmp ah, 2
        je .tin
        mov bx, [cs:tout + bx]
        jmp .lv
.tin:   mov bx, [cs:tin + bx]
.lv:    mov byte [cs:bc], 1             ; breadcrumb (battery RAM: readable after a hang + power cycle)
        mov byte [0xa], 9               ; instruction 090038 (the C level MACs), HIGH byte first like the firmware's
        mov byte [9], 0                 ; set_coef (E83B:06CC): [A] [9] [8], then the coefficient [5] [4], commit 8.
        mov byte [8], 0x38              ; (low-first order wedged the DSP interface: the firmware then hung in its
        mov [5], bh                     ; busy poll, MIDI and all)
        mov [4], bl
        pop bx
        test bl, 1
        jnz .s7c
        mov byte [0x1876], 8            ; commit 8: 2:076
        jmp .nx
.s7c:   mov byte [0x187c], 8            ; commit 8: 2:07C
.nx:    pop bx
        mov byte [cs:bc], 2
        inc word [cs:nlev]
        inc byte [cs:fi]
        cmp byte [cs:fi], 2 * NLEV
        jb .out
        cmp byte [cs:fstate], 1         ; fade done: out -> silent hold, in -> full
        jne .full
        mov byte [cs:fstate], 3
        jmp .out
.full:  mov byte [cs:fstate], 0
        jmp .out

        times 0x140 - ($ - $$) db 0     ; fade block at a fixed address (revlock.py FADE)
fstate  db 4                            ; state (fst is an x87 mnemonic); 4 = fades off until the loader sets them
fi      db 0                            ; level writes done in this fade
tog     db 0
        db 0
fwin    dw 0                            ; fade window, address units (info)
ftrig   dw 0xffff                       ; start the fade-out when A >= this (amax - fwin)
tout    times NLEV dw 0                 ; fade-out coefficients (full -> 0), set by the loader from the C level
tin     times NLEV dw 0                 ; fade-in coefficients (0 -> full)
bc      db 0                            ; breadcrumb: 1 = inside a level write, 2 = level write done
        db 0
nfad    dw 0                            ; fade-outs started
nlev    dw 0                            ; level writes done
nfw     dw 0                            ; updates skipped: firmware writing (TMIC2 masked)
nwr     dw 0                            ; address updates written
nbusy   dw 0                            ; updates skipped: never applied
