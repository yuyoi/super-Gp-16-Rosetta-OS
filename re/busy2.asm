; Pipelining probe: can a second commit be written while the first is still busy (one commit per frame)?
; One-shot from the REVERSE v4 bank-6 slot (busy2.py). Bank 6 here: DS = 8000 (DSP bus), ES = 40F0 (SFRs), BX = the
; current tap address (written back = no sound change). Per row: wait for a P0.0 rising edge, commit 1 on 2:072, wait
; D timer counts (dtab, 0 = no second write) after the edge, sample busy, commit again, poll busy until clear.
; Row = TM1 at edge, after commit 1, at commit 2, at clear, busy before commit 2 (5 words).
        cpu 186
        bits 16
        org 0x100

meas:   pusha
        mov byte [es:0x9c], 0x47        ; TMIC0 masked: one shot
        xor si, si
        xor di, di
.next:  mov dx, [cs:dtab + si]
        cmp dx, 0xffff
        je .done
        mov cx, 4000
.lo:    test byte [es:0], 1
        jz .h0
        loop .lo
        jmp .done
.h0:    mov cx, 4000
.hi:    test byte [es:0], 1
        jnz .edge
        loop .hi
        jmp .done
.edge:  mov bp, [es:0x88]
        mov [1], bh
        mov [0], bl
        mov byte [0x1872], 1
        mov ax, [es:0x88]
        mov [cs:tab + di + 2], ax
        mov word [cs:tab + di + 4], 0
        mov word [cs:tab + di + 8], 0
        or dx, dx
        jz .poll
.wt:    mov ax, bp
        sub ax, [es:0x88]
        jae .p1
        add ax, 1334
.p1:    cmp ax, dx
        jb .wt
        mov ax, [es:0x88]
        mov [cs:tab + di + 4], ax
        mov al, [0]
        mov [cs:tab + di + 8], ax
        mov [1], bh
        mov [0], bl
        mov byte [0x1872], 1
.poll:  mov cx, 3000
.b:     test byte [0], 1
        jz .clr
        loop .b
.clr:   mov ax, [es:0x88]
        mov [cs:tab + di + 6], ax
        mov [cs:tab + di], bp
        add di, 10
        add si, 2
        jmp .next
.done:  mov [cs:rows], di
        popa
        db 0x0f, 0x92                   ; FINT
        db 0x0f, 0x91                   ; RETRBI

        align 2
dtab    dw 0, 0, 20, 20, 35, 35, 42, 42, 50, 50, 60, 60, 80, 80, 0xffff
rows    dw 0x5555
tab:
