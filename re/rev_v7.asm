; REVERSE engine v7 = v5 locked core (timer 0, register bank 6) + chunk-jump fades done in the 1 ms PEDAL TICK
; (vector 30 stub), never inside the engine's interrupt. v6 wrote the C level from the engine ISR and hung the unit
; (DSP interface stuck busy -> the firmware's untimed busy poll looped forever; battery RAM got hit).
; Why the pedal tick: the firmware masks TMIC2 (vector 30) around its own DSP writes, so the fade can never land in
; the middle of a firmware write; IE = 0 while the stub runs (FINT doesn't set IE), so the engine can't cut in either.
; Fade: each ms the tick reads the engine's A (bank 6 BW). A >= ftrig (the last NL+2 ms before the chunk jump):
; level index li steps down one per ms to 0; otherwise it steps up to NL. Each step writes ltab[li] to the C level
; MACs 2:076 and 2:07C (instruction 090038 + coefficient, commit 8: the same bytes as the firmware's set_coef
; E83B:06CC), with a TIMED busy wait (skip + count instead of looping forever) and a breadcrumb in battery RAM.
; Layout (06C0:xxxx): engine 000, tick 060, data 140 (loader offsets in rk7.py), stack 1A0-1AF, stubs 1C0 / 1D0.
; Bank 6: DS = 8000, ES = 40F0, SS = PS = 06C0, SP = 01B0; AL = 1, BX = A, BP = step, DX = amax, CX = chunk length,
; SI = 0, DI = 0x1872 (commit: chip 2 step 0x072 = C tap).
        cpu 186
        bits 16
        org 0
NL      equ 5                           ; fade steps (ms) each way: "hard" fades (user)
BW      equ 0xC0 + 0x18                 ; bank 6 BW (= the engine's A) in segment 40E0

isr:    test [si], al                   ; busy: early
        jz .late
        mov word [es:0x82], 83
        mov ah, 12
.sp:    test [si], al
        jz .go
        dec ah
        jnz .sp
        inc word [cs:nbusy]
        mov word [es:0x82], 1000        ; back off: the engine must never hog the CPU
        jmp .out
.late:  mov word [es:0x82], 82
.go:    add bx, bp                      ; A += step (2 frames)
        cmp bx, dx
        jae .wrap
.in:    test byte [es:0x9e], 0x40       ; TMIC2 masked: the firmware is writing the DSP
        jnz .fw
        mov [si + 1], bh                ; A latch high, low
        mov [si], bl
        mov byte [si + 0x0a], 0         ; commit 1 also takes the instruction latch's top byte: keep it the C tap's
        mov [di], al                    ; commit 1: C tap address = A
        inc word [cs:nwr]
.out:   db 0x0f, 0x92                   ; FINT
        db 0x0f, 0x91                   ; RETRBI
.wrap:  sub bx, cx
        jmp .in
.fw:    inc word [cs:nfw]
        jmp .out

        times 0x60 - ($ - $$) db 0x90
tick:   sti                             ; the engine (timer 0, priority 6) may preempt this routine: with IE = 0
        pusha                           ; the whole time it lost ~1 update per ms (6% slow, 1 kHz wobble)
        push ds
        push es
        cmp byte [cs:fon], 0
        je .done
        mov ax, 0x40E0
        mov es, ax
        mov bx, [es:BW]                 ; engine A
        mov al, [cs:li]
        cmp bx, [cs:ftrig]
        jae .down
        cmp al, [cs:nlv]
        jae .done
        inc al
        jmp .set
.down:  or al, al
        jz .done
        dec al
.set:   mov [cs:li], al
        xor bh, bh
        mov bl, al
        shl bx, 1
        mov dx, [cs:ltab + bx]
        mov cx, 0x1876                  ; 2:076
        call wr
        mov cx, 0x187C                  ; 2:07C
        call wr
.done:  pop es
        pop ds
        popa
        ret

wr:     mov ax, 0x8000                  ; level write: the bus is ours only for 5 latch writes + the commit (IE
        mov es, ax                      ; off ~10 us), so the engine never misses an update; its next commit
        mov ah, 40                      ; waits out ours (<= 2 frames) and resets the instruction latch itself
.t:     cli
        test byte [es:0], 1
        jz .ok
        sti                             ; busy (the engine's last commit): let it run, try again
        mov byte [cs:bc], 1
        dec ah
        jnz .t
        inc word [cs:nto]
        mov byte [cs:bc], 0
        ret
.ok:    mov byte [es:0x0a], 0x09        ; instruction 090038, high byte first (as set_coef)
        mov byte [es:9], 0x00
        mov byte [es:8], 0x38
        mov [es:5], dh                  ; coefficient
        mov [es:4], dl
        mov bx, cx
        mov byte [es:bx], 8             ; commit 8
        sti
        inc word [cs:nlw]
        mov byte [cs:bc], 0
        ret

        times 0x140 - ($ - $$) db 0x90
fon     db 0                            ; 140: fades on (the loader sets it last)
li      db NL                           ; 141: current level index (nlv = full)
bc      db 0                            ; 142: breadcrumb (battery RAM: readable after a hang)
nlv     db NL                           ; 143: fade steps each way (1 per ms), set by the loader (max 24)
ftrig   dw 0xFFFF                       ; 144: fade-down threshold on A (amax - window)
        dw 0
ltab    times 25 dw 0                   ; 148: level coefficients, ltab[0] = silent, ltab[nlv] = full
        times 0x180 - ($ - $$) db 0
nwr     dw 0                            ; 180: address writes
nbusy   dw 0                            ; 182: engine busy give-ups
nfw     dw 0                            ; 184: engine skips (firmware writing)
nlw     dw 0                            ; 186: level writes
nto     dw 0                            ; 188: level-write busy timeouts (skipped)

        times 0x1C0 - ($ - $$) db 0
s29:    db 0x0f, 0x92                   ; FINT
        jmp 0xe83b:0x0c92               ; stock counters ISR
        times 0x1D0 - ($ - $$) db 0
s30:    db 0x0f, 0x92                   ; FINT
        call tick
        jmp 0xe83b:0x0cf0               ; stock pedal tick
