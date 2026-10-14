; Clock probe: is P0.0 the DSP frame clock? One-shot from the REVERSE v4 bank-6 slot (clocktest.py).
; Part A: TM1 at 64 P0.0 rising edges. Part B: TM1 at 64 commit-complete events (commit 1 of the CURRENT tap address
; on 2:072 = no sound change, poll busy until clear, repeat): those are tied to DSP frames. Comparing the two periods
; (in TM1 counts) says whether P0.0 runs on the DSP clock. Bank 6 (v4): DS = 8000, ES = 40F0, BX = tap address.
        cpu 186
        bits 16
        org 0x100

meas:   pusha
        mov byte [es:0x9c], 0x47        ; TMIC0 masked: one shot
        xor di, di
.a:     mov cx, 4000
.lo:    test byte [es:0], 1
        jz .h0
        loop .lo
        jmp .done
.h0:    mov cx, 4000
.hi:    test byte [es:0], 1
        jnz .edge
        loop .hi
        jmp .done
.edge:  mov ax, [es:0x88]
        mov [cs:taba + di], ax
        add di, 2
        cmp di, 128
        jb .a
        xor di, di
.b:     mov [1], bh
        mov [0], bl
        mov byte [0x1872], 1
        mov cx, 3000
.bz:    test byte [0], 1
        jz .clr
        loop .bz
        jmp .done
.clr:   mov ax, [es:0x88]
        mov [cs:tabb + di], ax
        add di, 2
        cmp di, 128
        jb .b
        mov word [cs:ok], 1
.done:  popa
        db 0x0f, 0x92                   ; FINT
        db 0x0f, 0x91                   ; RETRBI

        align 2
ok      dw 0
taba    times 64 dw 0
tabb    times 64 dw 0
