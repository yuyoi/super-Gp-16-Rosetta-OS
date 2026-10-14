; JSW ROSETTA OS v2.8 WIP -- REVERSE DELAY pedal: the reverse engine + its setup, in ROM.
; Lives in a dead stock-code range wiped by v2.7 (ROM 0x1300E-0x147FA): build_mod places it at ROM 0x13010 = F301:0000.
; Far functions (retf), DS = FA00 like the OS. Entry points = the jump table below (pedal_menu.asm REV_*).
; What it does (all proven live with the Python tools first, see DSP_CRACK.md):
;  - borrowed memory (mem2s.py): the 17 other chip-2 memory writes become NOPs, the tap's input write 2:092 moves to
;    WBASE, the L/R tap reads go next to it: the C tap gets 0x0120..0xFFBF = 2 s of line;
;  - 100% wet (wet100.py): 2:07A slot = the dry gain of mixer chain B, 12-bit signed: MIX 10 = -1.0 cancels chain A's
;    dry; LVL = chain A's C level 2:076 (0..+0.5), chain B's 2:07C = 0 (headroom: less clipping on hard attacks);
;  - the engine (rev_v7.asm core, phase-locked, no counters so it runs from ROM): timer 0, register bank 6, one C-tap
;    address write (2:072, commit 1) every 2 DSP frames, chunk = BPM x note value (auto-halved to fit the memory);
;  - safety: the firmware's sound-change entry LOADBUF F6A1:0382 jumps to hook_load first, which stops the engine
;    (a sound change with the engine running hung the unit). Only rev_now (the pedal's own knobs / apply) restarts it.
        cpu 186
        bits 16
        org 0

%include "rev_data.inc"              ; REV_PED (gen_pedal_data.py)

ST_STATE equ 0xcf3e                  ; pedal_menu.asm: 1 pedal, 2 rig
ST_PED   equ 0xcf30
ST_RV    equ 0xce40                  ; 4 B: knob positions BPM-40, note, mix 0-10, level 0-10
ST_REVON equ 0xce45                  ; 1 = engine running
ST_REVMEM equ 0xce46                 ; 1 = borrowed memory / dry cancel written: unborrow before anything else plays
ST_REVHOLD equ 0xce47                ; OS view (DS FA00): 1 = OS busy, engine must not touch the DSP this tick
HOLD_SS  equ 0x0247                  ; same byte in the engine's SS = 06C0 (FA00:CE47 == 06C0:0247): menu-hold flag
BOOTI    equ 0x14c4                  ; DS: chip 2 boot instructions, 3 B per step (set_coef E83B:06CC reads them)
REVSEG   equ 0xf301
WBASE    equ 0x0100                  ; tap write address (borrowed memory)
AMIN     equ 0x0120                  ; shortest read offset (1 ms)
SPANMAX  equ 0xffbf - AMIN           ; longest chunk x 2 (1019 ms)
BANK6    equ 0xc0                    ; bank 6 registers in segment 40E0
MD0      equ 82                      ; 83 counts = 62.25 us; the PLL toggles 82 / 83 (2 DSP frames = 83.38)

        jmp near rev_now             ; +0
        jmp near rev_stop            ; +3
        jmp near hook_load           ; +6  (F6A1:0382 jumps here)

; ---------------------------------------------------------------- the engine (bank 6: DS = 8000, ES = 40F0,
; AL = 1, BX = A, BP = step, DX = amax, CX = span, SI = 0, DI = 0x1872 = commit address of chip 2 step 0x072)
isr:    cmp byte [ss:HOLD_SS], 0     ; OS busy (any menu dispatch): touch the DSP NOT AT ALL -- not even the status
        jz .run                      ; read below -- or the read lands inside the firmware's own DSP poll and jams it
        mov word [es:0x82], MD0      ; (sound kept playing, controls died). Freeze A, keep the tick steady, leave.
        jmp .out
.run:   test [si], al                ; busy: early
        jz .late
        mov word [es:0x82], MD0 + 1
        mov ah, 12
.sp:    test [si], al
        jz .go
        dec ah
        jnz .sp
        mov word [es:0x82], 1000     ; back off: the engine must never hog the CPU
        jmp .out
.late:  mov word [es:0x82], MD0
.go:    add bx, bp                   ; A += step (2 frames)
        cmp bx, dx
        jae .wrap
.in:    test byte [es:0x9e], 0x40    ; TMIC2 masked: the firmware is writing the DSP
        jnz .out
        mov [si + 1], bh             ; A latch high, low
        mov [si], bl
        mov byte [si + 0x0a], 0      ; commit 1 also takes the instruction latch's top byte: the C tap's (00)
        mov [di], al                 ; commit 1: C tap address = A
.out:   db 0x0f, 0x92                ; FINT
        db 0x0f, 0x91                ; RETRBI
.wrap:  sub bx, cx
        jmp .in

s29:    db 0x0f, 0x92                ; 1 ms ISRs FINT first, so the engine's ticks get through (else 14% lost)
        jmp 0xe83b:0x0c92
s30:    db 0x0f, 0x92
        jmp 0xe83b:0x0cf0

; ---------------------------------------------------------------- stop
stop_core:                           ; engine off: timer 0 masked + stopped (all regs kept)
        push ax
        push es
        mov ax, 0x40f0
        mov es, ax
        mov byte [es:0x9c], 0x47     ; TMIC0 masked (no more engine interrupts)
        mov byte [es:0x90], 0x50     ; TMC0 as the firmware leaves it
        mov ax, 0x8000               ; wait for any in-flight engine commit to finish before the caller writes the DSP
        mov es, ax
        push cx
        mov cx, 4000
.w:     test byte [es:0], 1
        jz .idle
        loop .w
.idle:  pop cx
        pop es
        pop ax
        mov byte [ST_REVON], 0
        ret

rev_stop:
        call stop_core
        call unborrow
        retf

hook_load:                           ; LOADBUF entry (patched to jmp far here): engine off, the program back to stock
        call stop_core               ; (the sound change rewrites tap times + C levels itself, not instructions),
        call unborrow                ; then the 8 bytes we replaced
        push bp
        mov bp, sp
        db 0x9a
        dw 0x0098, 0xe980            ; lcall E980:0098
        jmp 0xf6a1:0x038a

unborrow:                            ; the 17 memory writes, the tap write 2:092 and the dry gain 2:07A back to the
        cmp byte [ST_REVMEM], 0      ; boot program (= the live program: chip 2's never changes after boot)
        je .r
        push si
        push bx
        push cx
        push ax
        push es
        mov ax, 0x8000
        mov es, ax
        mov si, unb
.l:     mov bx, [cs:si]
        cmp bx, 0xffff
        je .d
        mov cx, 4000
.w:     test byte [es:0], 1          ; timed busy wait: skip, never hang
        jz .ok
        loop .w
        jmp .n
.ok:    pushf
        cli
        xor al, al
        mov [es:3], al
        mov [es:2], al
        mov [es:1], al
        mov [es:0], al
        mov [es:5], al
        mov [es:4], al
        push bx
        mov ax, bx
        shl bx, 1
        add bx, ax                   ; 3 B per step
        mov al, [bx + BOOTI + 2]
        mov [es:0x0a], al
        mov al, [bx + BOOTI + 1]
        mov [es:9], al
        mov al, [bx + BOOTI]
        mov [es:8], al
        pop bx
        add bx, 0x1800               ; chip 2 commit address
        mov byte [es:bx], 0          ; commit 0 = instruction (resets 07A's coefficient slot too)
        popf
.n:     add si, 2
        jmp .l
.d:     mov byte [ST_REVMEM], 0
        pop es
        pop ax
        pop cx
        pop bx
        pop si
.r:     ret
unb:    dw 0x039, 0x041, 0x048, 0x05d, 0x0b6, 0x0c0, 0x0c4, 0x0cc, 0x0d0, 0x0d7, 0x0db, 0x0ec, 0x0f9, 0x10c, 0x119
        dw 0x126, 0x136, 0x092, 0x07a, 0xffff

; ---------------------------------------------------------------- DSP writes
dspw:                                ; cs:si -> record: dw commit address, db commit, db instr hi, dw instr lo, dw coef,
        push es                      ; dw A. Timed busy wait (skip, never hang), latches + commit with IE off.
        push cx
        push ax
        mov ax, 0x8000
        mov es, ax
        mov cx, 4000
.w:     test byte [es:0], 1
        jz .ok
        loop .w
        jmp .x
.ok:    pushf
        cli
        xor al, al
        mov [es:3], al               ; r3, B
        mov [es:2], al
        mov ax, [cs:si + 8]          ; A
        mov [es:1], ah
        mov [es:0], al
        mov ax, [cs:si + 6]          ; coefficient
        mov [es:5], ah
        mov [es:4], al
        mov al, [cs:si + 3]          ; instruction, high byte first
        mov [es:0x0a], al
        mov ax, [cs:si + 4]
        mov [es:9], ah
        mov [es:8], al
        mov bx, [cs:si]
        mov al, [cs:si + 2]
        mov [es:bx], al              ; commit
        popf
.x:     pop ax
        pop cx
        pop es
        ret

%macro W 6                           ; chip, step, commit, instr, coef, A
        dw 0x1000 + %1 * 0x400 + %2
        db %3, (%4) >> 16
        dw (%4) & 0xffff, %5, %6
%endmacro
RECSZ    equ 10

memw:                                ; borrowed memory (mem2s.py): the other chip-2 memory writes -> NOP (program-load
        W 2, 0x039, 0, 0, 0, 0       ; style: commit 0, all latches 0), the tap write to WBASE, L/R reads beside it
        W 2, 0x041, 0, 0, 0, 0
        W 2, 0x048, 0, 0, 0, 0
        W 2, 0x05d, 0, 0, 0, 0
        W 2, 0x0b6, 0, 0, 0, 0
        W 2, 0x0c0, 0, 0, 0, 0
        W 2, 0x0c4, 0, 0, 0, 0
        W 2, 0x0cc, 0, 0, 0, 0
        W 2, 0x0d0, 0, 0, 0, 0
        W 2, 0x0d7, 0, 0, 0, 0
        W 2, 0x0db, 0, 0, 0, 0
        W 2, 0x0ec, 0, 0, 0, 0
        W 2, 0x0f9, 0, 0, 0, 0
        W 2, 0x10c, 0, 0, 0, 0
        W 2, 0x119, 0, 0, 0, 0
        W 2, 0x126, 0, 0, 0, 0
        W 2, 0x136, 0, 0, 0, 0
        W 2, 0x092, 0, 0x030000 | WBASE, 0, 0
        W 2, 0x069, 1, 0x009c00, 0, WBASE + 1
        W 2, 0x06c, 1, 0x01ce00, 0, WBASE + 1
NMEMW    equ ($ - memw) / RECSZ

; mix / level records: the coefficient comes from the knob (dspc, dx), the record's coef field is unused
mixw:   W 2, 0x07a, 8, 0x01ffc0, 0, 0    ; chain B dry gain (12-bit signed: 0x7FF = +1, 0x800 = -1)
levw:   W 2, 0x076, 8, 0x090038, 0, 0    ; chain A C level
lvbw:   W 2, 0x07c, 8, 0x090038, 0, 0    ; chain B C level = 0

dspc:                                ; like dspw, with the coefficient from dx instead of the record
        push es
        push cx
        push ax
        mov ax, 0x8000
        mov es, ax
        mov cx, 4000
.w:     test byte [es:0], 1
        jz .ok
        loop .w
        jmp .x
.ok:    pushf
        cli
        xor al, al
        mov [es:3], al
        mov [es:2], al
        mov [es:1], al
        mov [es:0], al
        mov [es:5], dh
        mov [es:4], dl
        mov al, [cs:si + 3]
        mov [es:0x0a], al
        mov ax, [cs:si + 4]
        mov [es:9], ah
        mov [es:8], al
        mov bx, [cs:si]
        mov al, [cs:si + 2]
        mov [es:bx], al
        popf
.x:     pop ax
        pop cx
        pop es
        ret

; note values: 2 * 31980 (measured fs) * 60 * (quarters) = A-units span x BPM. Order = the NOTE knob.
notes:  dd 959400, 1279200, 1918800, 2558400, 2878200, 3837600, 5756400, 7675200   ; 16 8T 8 4T 8. 4 4. 2
NNOTE   equ 8

; ---------------------------------------------------------------- start / restart
rev_now:                             ; mloop, once the sound change is done: (re)start if the REV pedal is up
        push si
        push di
        push bx
        call stop_core
        mov al, [ST_STATE]
        cmp al, 1
        je .p
        cmp al, 2
        je .p
        jmp .x
.p:     cmp byte [ST_PED], REV_PED
        je .go
        jmp .x
.go:    mov byte [ST_REVMEM], 1      ; set first: whatever got written is undone on the next stop
        mov si, memw                 ; 1. borrowed memory
        mov di, NMEMW
.m:     call dspw
        add si, RECSZ
        dec di
        jnz .m
        mov al, [ST_RV + 2]          ; 2. MIX k 0-10 -> chain B dry gain 2047 - 4095 k / 10 (k 10 = -2048 = -1.0)
        cmp al, 10
        jbe .mx
        mov al, 10
.mx:    mov ah, 0
        mov cx, 4095
        mul cx
        mov cx, 10
        div cx
        mov dx, 2047
        sub dx, ax
        and dx, 0x0fff
        mov si, mixw
        call dspc
        mov al, [ST_RV + 3]          ; 3. LVL k 0-10 -> chain A C level k * 0x400 / 10, chain B 0
        cmp al, 10
        jbe .lv
        mov al, 10
.lv:    mov ah, 0
        mov cx, 0x400
        mul cx
        mov cx, 10
        div cx
        mov dx, ax
        mov si, levw
        call dspc
        xor dx, dx
        mov si, lvbw
        call dspc
        mov bl, [ST_RV + 1]          ; 4. chunk: span = notes[n] / BPM, halved until it fits the memory
        cmp bl, NNOTE - 1
        jbe .nt
        mov bl, NNOTE - 1
.nt:    mov bh, 0
        shl bx, 2
        mov ax, [cs:bx + notes]
        mov dx, [cs:bx + notes + 2]
        mov bl, [ST_RV]
        mov bh, 0
        add bx, 40                   ; BPM 40-240
        cmp bx, 240
        jbe .h
        mov bx, 240
.h:     cmp dx, bx                   ; quotient must fit 16 bits
        jb .dv
        shr dx, 1
        rcr ax, 1
        jmp .h
.dv:    div bx                       ; ax = span
.f:     cmp ax, SPANMAX
        jbe .sp
        shr ax, 1
        jmp .f
.sp:    mov cx, ax                   ; cx = span
        call engine_start
.x:     pop bx
        pop di
        pop si
        retf

engine_start:                        ; cx = span. Vectors 29/30 -> the FINT stubs, bank 6 registers, timer 0 on.
        push es
        push ax
        push bx
        pushf
        cli
        xor ax, ax
        mov es, ax
        mov word [es:29 * 4], s29
        mov word [es:29 * 4 + 2], REVSEG
        mov word [es:30 * 4], s30
        mov word [es:30 * 4 + 2], REVSEG
        popf
        mov ax, 0x40e0
        mov es, ax
        mov bx, BANK6
        mov word [es:bx + 0x02], isr     ; VPC
        mov word [es:bx + 0x08], 0x8000  ; DS0
        mov word [es:bx + 0x0a], 0x06c0  ; SS (scratch RAM 06C0:0000-01FF; the ISR pushes nothing)
        mov word [es:bx + 0x0c], REVSEG  ; PS
        mov word [es:bx + 0x0e], 0x40f0  ; DS1 (ES)
        mov word [es:bx + 0x10], 0x1872  ; IY = DI: commit address of 2:072
        mov word [es:bx + 0x12], 0       ; IX = SI
        mov word [es:bx + 0x14], 4       ; BP = step: speed -1 = 2 (1 - speed) per 2 frames
        mov word [es:bx + 0x16], 0x01b0  ; SP
        mov word [es:bx + 0x18], AMIN    ; BW = A
        mov ax, AMIN
        add ax, cx
        mov [es:bx + 0x1a], ax           ; DW = amax
        mov [es:bx + 0x1c], cx           ; CW = span
        mov word [es:bx + 0x1e], 1       ; AW: AL = 1 (busy bit / commit 1)
        mov ax, 0x40f0
        mov es, ax
        mov word [es:0x82], MD0
        mov byte [es:0x90], 0x80     ; TMC0: start, fCLK/6, interval
        mov byte [es:0x9c], 0x16     ; TMIC0: register bank switching, priority 6 = bank 6, unmasked
        mov byte [ST_REVON], 1
        pop bx
        pop ax
        pop es
        ret
