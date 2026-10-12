; GP-16 boot dragon: flies left->right across BOTH lines, eating each line's text and leaving a dot trail.
; Lives at ROM 0x0720 = E072:0000. Replaces the banner-draw call at F6A1:0020. The stock running-man walk
; (F6A1:0156) is NOP'd by build_mod. Draws the banner, flies a dragon across line 1 and line 2 in sync,
; then restores the stock glyphs so the play screen is unchanged.
        cpu 186
        bits 16
        org 0

F2FC_SEG  equ 0xf2fc
F2FC_BAN  equ 0x0000
E93C_SEG  equ 0xe93c
E93C_CUR  equ 0x0238          ; set cursor(col,line)  push col; push line
E93C_CC   equ 0x00cc          ; set addr(mode,val)    push val; push mode (8=CGRAM)
E93C_DATA equ 0x03ae          ; write data byte        push byte
E93C_PUTC equ 0x0000          ; putc(char)             push char
E93C_DLY  equ 0x0422          ; spin delay(count)      push count

TABLE_DS  equ 0x5cca          ; frame table (ROM 0x1FCCA)
STOCK1_DS equ 0x2a46          ; stock glyph char1 (ROM 0x1CA46); char2 -8, char3 -16
NAME1_DS  equ 0x5671          ; line 1 "Guitar Processor" (ROM 0x1F671)
NAME2_DS  equ 0x5682          ; line 2 "Super GP 0.5"      (ROM 0x1F682)
COLS      equ 16
POS0      equ -2
POSEND    equ 18
DOT       equ 0x2e
DLYCNT    equ 0x4000
DLYREP    equ 1              ; 3x faster than the first version

%macro farcall 2
        db 0x9a
        dw %2
        dw %1
%endmacro

start:
        push bp
        mov bp, sp
        sub sp, 10            ; -2 frame  -4 step  -6 pos  -8 line  -10 name_ds
        push si
        push di
        push word [bp+0x0c]
        push word [bp+0x0a]
        push word [bp+0x08]
        push word [bp+0x06]
        farcall F2FC_SEG, F2FC_BAN
        add sp, 8
        mov word [bp-4], 0
        ; --- pass 1: fly across line 1 (ends as dots, which persist) ---
        mov word [bp-8], 1
        mov word [bp-10], NAME1_DS
        mov word [bp-6], POS0
.fly1:
        mov ax, [bp-4]
        and ax, 7
        mov [bp-2], ax
        call load_frame
        call drawrow
        call delay
        inc word [bp-6]
        inc word [bp-4]
        mov ax, [bp-6]
        cmp ax, POSEND
        jl .fly1
        ; --- pass 2: fly across line 2 (line 1 stays dotted) ---
        mov word [bp-8], 2
        mov word [bp-10], NAME2_DS
        mov word [bp-6], POS0
.fly2:
        mov ax, [bp-4]
        and ax, 7
        mov [bp-2], ax
        call load_frame
        call drawrow
        call delay
        inc word [bp-6]
        inc word [bp-4]
        mov ax, [bp-6]
        cmp ax, POSEND
        jl .fly2
        call restore_stock
        pop di
        pop si
        mov sp, bp
        pop bp
        retf

; drawrow: draw one 16-col line. [bp-8]=line, [bp-10]=name DS offset, [bp-6]=pos
drawrow:
        xor ax, ax
        push ax
        push word [bp-8]
        farcall E93C_SEG, E93C_CUR
        add sp, 4
        xor di, di
.col:
        mov ax, di
        sub ax, [bp-6]                ; cellidx = col - pos
        cmp ax, 0
        jl .behind
        cmp ax, 2
        jg .ahead
        inc ax                        ; dragon cell -> code 1..3
        jmp .put
.behind:
        mov ax, DOT                   ; passed -> dot trail
        jmp .put
.ahead:
        mov bx, di
        add bx, [bp-10]
        mov al, [bx]                  ; name char
        mov ah, 0
        cmp al, 0
        jne .put
        mov ax, 0x20                  ; past end of name -> blank
.put:
        call putc
        inc di
        cmp di, COLS
        jb .col
        ret

; putc(al)
putc:
        push ax
        mov ah, 0
        push ax
        farcall E93C_SEG, E93C_PUTC
        add sp, 2
        pop ax
        ret

; delay
delay:
        mov di, DLYREP
.d1:
        mov ax, DLYCNT
        push ax
        farcall E93C_SEG, E93C_DLY
        add sp, 2
        dec di
        jnz .d1
        ret

; load_frame: define CGRAM chars 1,2,3 from table[frame=[bp-2]]
load_frame:
        mov ax, [bp-2]
        mov bx, 24
        mul bx
        mov si, ax
        add si, TABLE_DS
        xor di, di
.lf:
        mov ax, di
        and ax, 7
        jnz .nocc
        mov ax, di
        mov cl, 3
        shr ax, cl
        inc ax
        shl ax, cl
        push ax
        mov ax, 8
        push ax
        farcall E93C_SEG, E93C_CC
        add sp, 4
.nocc:
        mov al, [si]
        mov ah, 0
        push ax
        farcall E93C_SEG, E93C_DATA
        add sp, 2
        inc si
        inc di
        cmp di, 24
        jb .lf
        ret

; restore_stock: chars 1,2,3 from stock glyphs (base STOCK1_DS - cell*8)
restore_stock:
        xor di, di
.rs:
        mov ax, di
        and ax, 7
        jnz .nocc
        mov ax, di
        mov cl, 3
        shr ax, cl
        inc ax
        shl ax, cl
        push ax
        mov ax, 8
        push ax
        farcall E93C_SEG, E93C_CC
        add sp, 4
.nocc:
        mov ax, di
        mov cl, 3
        shr ax, cl
        shl ax, cl
        mov si, STOCK1_DS
        sub si, ax
        mov ax, di
        and ax, 7
        add si, ax
        mov al, [si]
        mov ah, 0
        push ax
        farcall E93C_SEG, E93C_DATA
        add sp, 2
        inc di
        cmp di, 24
        jb .rs
        ret
