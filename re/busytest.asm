; Commit timing probe: when inside the DSP frame does a commit 1 get taken? One-shot from the REVERSE engine's bank-6
; slot (busytest.py). For 16 delays: wait for a P0.0 (EOS candidate) rising edge, spin i*2 LOOPs, write the CURRENT
; tap address (BX = A, no sound change) + commit 1 on 2:072, poll busy (8000:0 bit 0) until clear. Logs TM1 (1.3333 MHz,
; counts down) at the edge, at the write and at busy clear: 16 x 3 words in tab. DS = 40F0, ES = 8000, CS = 06C0.
        cpu 186
        bits 16
        org 0x100

meas:   pusha
        mov byte [0x9c], 0x47           ; TMIC0 masked: one shot
        xor di, di                      ; table index (bytes)
        xor bp, bp                      ; delay step i
.next:  mov cx, 4000
.lo:    test byte [0x00], 1             ; wait P0.0 low
        jz .hi0
        loop .lo
        jmp .done
.hi0:   mov cx, 4000
.hi:    test byte [0x00], 1             ; then high = rising edge
        jnz .edge
        loop .hi
        jmp .done
.edge:  mov ax, [0x88]
        mov [cs:tab + di], ax
        mov cx, bp
        shl cx, 1
        jcxz .w
.s:     loop .s
.w:     mov ax, [0x88]
        mov [cs:tab + di + 2], ax
        mov [es:1], bh
        mov [es:0], bl
        mov byte [es:0x1872], 1
        mov cx, 2000
.b:     test byte [es:0], 1
        jz .clr
        loop .b
.clr:   mov ax, [0x88]
        mov [cs:tab + di + 4], ax
        add di, 6
        inc bp
        cmp bp, 16
        jb .next
.done:  mov [cs:cnt], bp
        popa
        db 0x0f, 0x92                   ; FINT
        db 0x0f, 0x91                   ; RETRBI

        align 2
cnt     dw 0x5555
tab:
