; Parallel-chip probe: does each TC23SC260 have its own commit pipeline, or do all three share one?
; One-shot in the engine's bank-6 slot (chippar.py loads it at 06C0:0000 with the engine stopped). Commit 1 (address
; field only) to UNUSED steps: chip 2 step 0x180 (8000:1980), chip 0 step 0x1D0 (8000:11D0), chip 1 step 0x1F0
; (8000:15F0). Never writes while busy: each commit waits for busy to clear, then TM1 (1.3333 MHz, counts down, period
; 1334) is logged. Test A: chip 2 only. Test B: chip 2 / chip 0 alternating. Test C: chip 2 / chip 1 alternating.
; One shared pipeline = 2 frames (83.4 counts) per commit in every test; separate pipelines = faster in B and C.
; Bank 6: DS = 8000 (DSP bus), ES = 40F0 (SFRs), CS = SS = 06C0, SP = 01B0.
        cpu 186
        bits 16
        org 0

meas:   pusha
        mov byte [es:0x9c], 0x47        ; TMIC0 masked: one shot
        mov byte [1], 0x80              ; A latch = 0x8000 (commit 1 takes it; unused steps)
        mov byte [0], 0x00
        mov bp, tabs
        mov dx, 0x1980                  ; A: chip 2, chip 2
        mov si, 0x1980
        call test
        mov dx, 0x1980                  ; B: chip 2, chip 0
        mov si, 0x11d0
        call test
        mov dx, 0x1980                  ; C: chip 2, chip 1
        mov si, 0x15f0
        call test
        mov word [cs:done], 1
        popa
        db 0x0f, 0x92                   ; FINT
        db 0x0f, 0x91                   ; RETRBI

test:   mov ax, [es:0x88]
        mov [cs:bp], ax
        add bp, 2
        mov cx, 16
.t:     mov bx, dx
        call one
        mov bx, si
        call one
        loop .t
        ret

one:    mov byte [bx], 1                ; commit 1 at 8000:bx
        push cx
        mov cx, 3000
.w:     test byte [0], 1                ; wait for the apply
        jz .c
        loop .w
.c:     mov ax, [es:0x88]
        mov [cs:bp], ax
        add bp, 2
        pop cx
        ret

        align 2
done    dw 0
tabs    times 3 * 33 dw 0
