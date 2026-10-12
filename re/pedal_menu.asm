; GP-16 PEDAL / RIG / BOARD modes (v0.9): the rack as one pedal, or a whole pedalboard.
; Lives at ROM 0x0A00 = E0A0:0000. Far functions, DS=FA00.
;   E0A0:0000  SYSTEM key entry (main loop F6A1:012C: lcall F6A1:1530 -> here). Starts at the split screen.
;   E0A0:0003  power-on entry (F6A1:0063: mov byte [a312],0 -> lcall here). Starts in the last mode.
; split:  FUNCTION UP -> PEDAL, DOWN -> RIG, EDIT -> BOARD, SYSTEM -> stock System menu, ESC -> patch screen.
; PEDAL pages: 0 knobs, 1 pick pedal.     RIG pages: 0 pedal knobs, 1 amp knobs, 2 pick pedal, 3 pick amp.
;   FUNCTION UP/DOWN = next/previous page. ESC = back to split. BANK/GROUP = dial -/+.
;   Knob page: buttons 1-4 = knob 1-4 up, 5-8 = knob 1-4 down; the dial follows the knob touched last ('*').
; BOARD: 14 pages = 12 block slots (A1 COMP .. B6 AMP) + ORDER + OUT (A/B/Y box).
;   FUNCTION = next/previous slot, BANK/GROUP = previous/next pedal for the slot, buttons + dial = its knobs.
;   A pedal sits in its home slot and grabs the extra blocks its voicing uses (Muff: comp + EQ, amps: EQ, Leslie: trem)
;   when those slots are empty; a grabbed slot shows <NAME> and can't take a pedal until that pedal changes.
;   ORDER: buttons 1/5 = A chain preset, 2/6 = B chain preset. OUT: 1/5 = output channel (CH1 / CH2 / both).
; Knob moves are live (DT1 setter EE11:17F4 + the param's descriptor setter, as the stock edit menu does).
; Pedal/amp/board change = full apply through EE11:17F4, then the stock sound-change service.
; (Older sources: pedal_menu_v07.asm, pedal_menu_v08.asm.)
        cpu 186
        bits 16
        org 0

F00E_SEG equ 0xf00e
KEYT     equ 0x1cd2          ; keytest(n) -> ax (consumes the key); 0xff clears all
VALIDATE equ 0x0764          ; (buf far, flag): effect-order check, part of the stock sound-change service
F6A1_SEG equ 0xf6a1
SERVICE  equ 0x03bc          ; service(arg): keys, MIDI, dial; arg=1 enables BANK/GROUP as -/+
SYSMENU  equ 0x1530          ; stock System menu
CONTRAST equ 0x1dfa          ; 6000:2 <- [9FD2] (LCD contrast DAC)
LOADBUF  equ 0x0382          ; edit buffer -> DSPs (stock sound-change service; also sets the output channel)
EE11_SEG equ 0xee11
DT1SET   equ 0x17f4          ; (buf far, sysex addr, value): DT1 per-byte setter
E93C_SEG equ 0xe93c
CUR      equ 0x0238          ; cursor(col,line)  push col; push line
PUTC     equ 0x0000          ; putc(ch)

BUF      equ 0x9d06          ; internal edit buffer (114 B)
BUF_NAME equ 0x9d67          ; +0x61, 16 chars (play screen shows it)
OUTCH    equ 0x9d66          ; +0x60 output channel (0 CH1, 1 CH2, 2 both)
EXPASG   equ 0x9d5f          ; param assigned to the expression pedal (it owns that param's setter)
PDESC    equ 0x2396          ; param descriptors, 22 B each; +0x12 = live setter far ptr
TMIC     equ 0x9e            ; 40F0:9E, masked around live setters (as the stock edit menu does)
SNDREQ   equ 0xa43c          ; bit 0x20 = sound change pending (SysEx 0x75 sets it, main loop serves it)
SNDHOLD  equ 0x9fcc          ; bit 0x40 = main loop defers sound changes
MENUFLG  equ 0xa430          ; bit 0 = in a menu (the main loop sets it around the SYSTEM/EDIT menus)
DIAL     equ 0xa654          ; dial value (word), kept 0..DIALMAX by the encoder ISR
DIALMAX  equ 0xa6be
DIALSTEP equ 0xa6b8
DIALWRAP equ 0xa318
                             ; battery RAM (no stock refs to CE00-CFFF; debug port uses CF00-CF1E)
BRD      equ 0xcf20          ; 12 B: pedal index per slot (slot 11 = amp index), 0 = OUT
ORDA     equ 0xcf2c          ; A chain preset 0-2
ORDB     equ 0xcf2d          ; B chain preset 0-2
OUTSEL   equ 0xcf2e          ; output channel 0-2
ST_VIEW  equ 0xcf2f          ; BOARD slot view: 0 name, 1 knobs
ST_PED   equ 0xcf30
ST_AMP   equ 0xcf31
ST_FILT  equ 0xcf32          ; BOARD: slot whose pedal is being applied (knob targets filtered by owner), FF = off
ST_ON    equ 0xcf33          ; 3 B scratch: merged SysEx 0x0C/0x0D/0x0E
ST_MODE  equ 0xcf36          ; 1 pedal / 2 rig / 3 board: mode to boot into
ST_MAGIC equ 0xcf37          ; == KMAGIC when the stores are valid
ST_PAGE  equ 0xcf38
ST_ACT   equ 0xcf39          ; knob the dial follows
ST_FP    equ 0xcf3a          ; far ptr scratch (4)
ST_STATE equ 0xcf3e          ; 0 split, 1 pedal, 2 rig, 3 board
ST_TMP   equ 0xcf3f
ST_KP    equ 0xcf40          ; (NPED+1) x 4 knob positions (pedals)
ST_KA    equ 0xce00          ; (NAMP+1) x 4 (amps)
OWN      equ 0xce20          ; 12 B: BOARD owner slot per block (FF = none)
ST_OACT  equ 0xce2c          ; ORDER page: 0 = A row active, 1 = B row

K_BANK   equ 0x09
K_GROUP  equ 0x0a
K_EDIT   equ 0x0c
K_ESC    equ 0x0d
K_SYS    equ 0x0e
K_UP     equ 0x0f            ; FUNCTION (stock page step: 0xF = next, 0x10 = previous)
K_DN     equ 0x10
K_CLR    equ 0xff
KREC     equ 22              ; knob record size
NSLOT    equ 14              ; BOARD pages

%macro farcall 2
        db 0x9a
        dw %2
        dw %1
%endmacro

        jmp near menu_sys            ; E0A0:0000
boot_entry:                          ; E0A0:0003
        mov byte [0xa312], 0         ; the instruction we replaced
        or byte [MENUFLG], 1
        farcall F6A1_SEG, CONTRAST   ; re-send LCD contrast (boot writes it once, very early; ~1 in 5 boots looked low)
        push bp
        mov bp, sp
        push si
        push di
        call validate
        mov al, [ST_MODE]
        call enter_mode
        jmp mloop

menu_sys:
        push bp
        mov bp, sp
        push si
        push di
        call validate
        call to_split

mloop:
        xor ax, ax
        cmp byte [ST_STATE], 3
        je .svc
        inc ax                       ; BANK/GROUP = dial -/+ except in BOARD (they pick pedals there)
.svc:   push ax
        farcall F6A1_SEG, SERVICE
        add sp, 2
        mov ax, K_ESC
        call keyt
        jz .noesc
        cmp byte [ST_STATE], 0
        jne .back
        jmp .exit                    ; ESC at split -> patch screen
.back:  call to_split
        jmp mloop
.noesc: mov al, [ST_STATE]
        cmp al, 3
        jne .nb
        jmp .board
.nb:    test al, al
        jz .split
        jmp .mode

.split: mov ax, K_SYS                ; ---- split
        call keyt
        jz .s1
        farcall F6A1_SEG, SYSMENU
        jmp .exit
.s1:    mov ax, K_UP
        call keyt
        jz .s2
        mov al, 1
        call enter_mode
        jmp mloop
.s2:    mov ax, K_DN
        call keyt
        jz .s3
        mov al, 2
        call enter_mode
        jmp mloop
.s3:    mov ax, K_EDIT
        call keyt
        jz .s4
        mov al, 3
        call enter_mode
        jmp mloop
.s4:    call eat_numbers
        jmp mloop

.mode:  mov ax, K_SYS                ; ---- pedal / rig (SYSTEM/EDIT do nothing here; eat them)
        call keyt
        mov ax, K_EDIT
        call keyt
        mov ax, K_UP
        call keyt
        jz .m1
        mov al, 1
        call page_step
        jmp mloop
.m1:    mov ax, K_DN
        call keyt
        jz .m2
        mov al, -1
        call page_step
        jmp mloop
.m2:    call numbers
        jnz .mx
        call dial_check
.mx:    jmp mloop

.board: mov ax, K_SYS                ; ---- board
        call keyt
        mov ax, K_EDIT
        call keyt
        mov ax, K_UP
        call keyt
        jz .b1
        mov al, 1
        call slot_step
        jmp mloop
.b1:    mov ax, K_DN
        call keyt
        jz .b2
        mov al, -1
        call slot_step
        jmp mloop
.b2:    mov ax, K_BANK
        call keyt
        jz .b3
        mov al, -1
        call board_pick
        jmp mloop
.b3:    mov ax, K_GROUP
        call keyt
        jz .b4
        mov al, 1
        call board_pick
        jmp mloop
.b4:    call numbers
        jnz .bx
        call board_dial
.bx:    jmp mloop

.exit:  mov ax, K_CLR                ; drop queued presses so nothing reaches the patch keys
        call keyt
        and byte [MENUFLG], 0xfe
        pop di
        pop si
        pop bp
        retf

numbers:                             ; buttons 1-8 -> knob_press. ZF clear if one was pressed.
        mov si, 1                    ; (si survives far calls)
.n:     mov ax, si
        call keyt
        jz .nx
        mov ax, si
        call knob_press
        or al, 1                     ; ZF = 0
        ret
.nx:    inc si
        cmp si, 8
        jbe .n
        xor al, al                   ; ZF = 1
        ret

; ---------------------------------------------------------------- state
validate:
        cmp byte [ST_MAGIC], KMAGIC
        je .chk
        call knobs_reset             ; new tables: defaults everywhere, empty board
        xor ax, ax
        mov [ST_PED], al
        mov [ST_AMP], al
        mov byte [ST_MODE], 1
        mov di, BRD
        mov cx, 12
.z:     mov [di], al
        inc di
        loop .z
        mov [ORDA], al
        mov [ORDB], al
        mov al, [OUTCH]              ; keep the patch's output jacks
        mov [OUTSEL], al
        mov byte [ST_MAGIC], KMAGIC
.chk:   cmp byte [ST_PED], NPED
        jbe .v1
        mov byte [ST_PED], 0
.v1:    cmp byte [ST_AMP], NAMP
        jbe .v2
        mov byte [ST_AMP], 0
.v2:    mov al, [ST_MODE]
        cmp al, 1
        jb .v3
        cmp al, 3
        jbe .v4
.v3:    mov byte [ST_MODE], 1
.v4:    cmp byte [ORDA], 2
        jbe .v5
        mov byte [ORDA], 0
.v5:    cmp byte [ORDB], 2
        jbe .v6
        mov byte [ORDB], 0
.v6:    cmp byte [OUTSEL], 2
        jbe .v7
        mov byte [OUTSEL], 2
.v7:    xor bx, bx                   ; every board slot holds OUT or a pedal that lives there
.bs:    mov al, [bx+BRD]
        test al, al
        jz .bn
        cmp bx, 11
        je .ba
        cmp al, NPED
        ja .bz
        push bx
        mov ah, bl
        mov bl, al
        mov bh, 0
        cmp ah, [cs:ped_home+bx]
        pop bx
        je .bn
.bz:    mov byte [bx+BRD], 0
        jmp .bn
.ba:    cmp al, NAMP
        ja .bz
.bn:    inc bx
        cmp bx, 12
        jb .bs
        mov byte [ST_ACT], 0
        mov byte [ST_VIEW], 0
        mov byte [ST_OACT], 0
        mov byte [ST_FILT], 0xff
        jmp compute_owners

knobs_reset:                         ; every store <- its table defaults
        mov si, ped_off
        mov di, ST_KP
        mov cx, NPED+1
        call .tab
        mov si, amp_off
        mov di, ST_KA
        mov cx, NAMP+1
.tab:   mov bx, [cs:si]
        mov bx, [cs:bx+16]           ; knob block: n, def0..3
        mov ax, [cs:bx+1]
        mov [di], ax
        mov ax, [cs:bx+3]
        mov [di+2], ax
        add si, 2
        add di, 4
        loop .tab
        ret

to_split:
        mov ax, K_CLR
        call keyt
        mov byte [ST_STATE], 0
        jmp draw_split

enter_mode:                          ; al = 1 pedal / 2 rig / 3 board
        mov [ST_STATE], al
        mov [ST_MODE], al
        mov byte [ST_PAGE], 0
        mov byte [ST_ACT], 0
        mov byte [ST_VIEW], 0
        cmp al, 3
        jne .pr
        call board_apply
        jmp .s
.pr:    call apply_cur
.s:     call sync_dial
        jmp redraw

npages:                              ; -> al
        mov al, 2
        cmp byte [ST_STATE], 2
        jne .n
        mov al, 4
.n:     ret

page_step:                           ; al = +1 / -1 (PEDAL / RIG)
        add al, [ST_PAGE]
        mov ah, al
        call npages
        cmp ah, 0x80
        jb .p1
        add ah, al                   ; -1 -> last
.p1:    cmp ah, al
        jb .p2
        mov ah, 0
.p2:    mov [ST_PAGE], ah
        mov byte [ST_ACT], 0
        call sync_dial
        jmp redraw

slot_step:                           ; al = +1 / -1 (BOARD pages 0..13)
        add al, [ST_PAGE]
        cmp al, 0x80
        jb .a
        mov al, NSLOT-1
.a:     cmp al, NSLOT
        jb .b
        xor al, al
.b:     mov [ST_PAGE], al
        mov byte [ST_VIEW], 0
        mov byte [ST_ACT], 0
        call sync_dial
        jmp redraw

page_which:                          ; -> bl = 0 pedal / 1 amp / 2 board slot, bh = 1 if knob page/view
        mov al, [ST_PAGE]
        cmp byte [ST_STATE], 3
        jne .nb
        mov bl, 2
        mov bh, [ST_VIEW]
        ret
.nb:    mov bx, 0x0100
        cmp byte [ST_STATE], 2
        jne .pw
        cmp al, 2
        jb .k
        mov bh, 0
        sub al, 2
.k:     mov bl, al
        ret
.pw:    cmp al, 0
        je .r
        mov bh, 0
.r:     ret

eat_numbers:                         ; split: consume 1-8 so they cannot leak
        mov si, 1
.e:     mov ax, si
        call keyt
        inc si
        cmp si, 8
        jbe .e
        ret

; ---------------------------------------------------------------- entries / knobs
ent_ptr:                             ; bl = 0 pedal / 1 amp / 2 board -> si = entry (cs), di = knob store (ds)
        mov byte [ST_FILT], 0xff
        cmp bl, 2
        je .brd
        test bl, bl
        jnz .a
        mov al, [ST_PED]
.ped:   mov ah, 0
        mov di, ax
        shl di, 2
        add di, ST_KP
        mov si, ax
        shl si, 1
        mov si, [cs:ped_off+si]
        ret
.a:     xor ax, ax                   ; amp counts only in RIG mode
        cmp byte [ST_STATE], 2
        jne .amp
        mov al, [ST_AMP]
.amp:   mov ah, 0
        mov di, ax
        shl di, 2
        add di, ST_KA
        mov si, ax
        shl si, 1
        mov si, [cs:amp_off+si]
        ret
.brd:   mov al, [ST_PAGE]            ; board: the pedal acting on this slot (its own, or the one that grabbed it)
        cmp al, 12
        jae .off
        mov bl, al
        mov bh, 0
        cmp byte [bx+BRD], 0
        jne .own
        mov al, [bx+OWN]
        cmp al, 0xff
        je .off
        mov bl, al
.own:   mov [ST_FILT], bl            ; its knobs act only on blocks it owns
        mov al, [bx+BRD]
        cmp bl, 11
        je .amp
        jmp .ped
.off:   xor ax, ax
        jmp .ped

ent_slot:                            ; bl = board slot, al = index -> si = entry, di = knob store (bx kept)
        mov ah, 0
        mov di, ax
        shl di, 2
        mov si, ax
        shl si, 1
        cmp bl, 11
        je .a
        add di, ST_KP
        mov si, [cs:ped_off+si]
        ret
.a:     add di, ST_KA
        mov si, [cs:amp_off+si]
        ret

nknobs:                              ; si = entry -> al = knob count (bx clobbered)
        mov bx, [cs:si+16]
        mov al, [cs:bx]
        ret

knob_rec:                            ; si = entry, al = knob idx -> bx = record (cs)
        mov ah, KREC
        mul ah
        mov bx, [cs:si+16]
        add bx, ax
        add bx, 5
        ret

knob_apply:                          ; bl = which, al = knob idx, dl = 1 live / 0 buffer only (si/di kept)
        push si
        push di
        push ax
        call ent_ptr
        pop ax
        call knob_core
        pop di
        pop si
        ret

knob_core:                           ; si = entry, di = store, al = idx, dl = live; [ST_FILT] = owner slot / FF
        push si
        push di
        push bp
        mov bp, sp
        sub sp, 12                   ; -2 k, -4 steps, -6 targets left, -8 live, -10 target ptr, -12 value
        mov [bp-8], dl
        mov cl, al
        mov ch, 0
        add di, cx
        call knob_rec
        mov cl, [di]
        cmp cl, [cs:bx+3]
        jbe .kok
        mov cl, [cs:bx+3]
        mov [di], cl
.kok:   mov ch, 0
        mov [bp-2], cx
        mov al, [cs:bx+3]
        mov ah, 0
        mov [bp-4], ax
        mov al, [cs:bx+5]
        mov [bp-6], ax
        add bx, 6
        mov [bp-10], bx
.t:     cmp word [bp-6], 0
        jne .t1
        jmp .done
.t1:    mov bx, [bp-10]
        mov al, [ST_FILT]            ; BOARD: skip targets in blocks this pedal doesn't own
        cmp al, 0xff
        je .use
        mov ah, [cs:bx+3]
        shr ah, 4
        cmp ah, 0x0f
        je .use
        mov bl, ah
        mov bh, 0
        cmp al, [bx+OWN]
        je .use
        jmp .next
.use:   mov bx, [bp-10]
        mov ax, [cs:bx+6]            ; v = v0 + (v10 - v0) * k / steps
        sub ax, [cs:bx+4]
        imul word [bp-2]
        idiv word [bp-4]
        mov bx, [bp-10]
        add ax, [cs:bx+4]
        mov [bp-12], ax
        test byte [cs:bx+3], 1
        jz .one
        shr ax, 7                    ; 2-byte SysEx: msb, then lsb
        mov bl, [cs:bx]
        call dt1set
        mov bx, [bp-10]
        mov al, [bp-12]
        and al, 0x7f
        mov bl, [cs:bx]
        inc bl
        call dt1set
        jmp .live
.one:   mov bl, [cs:bx]
        call dt1set
.live:  cmp byte [bp-8], 0
        je .next
        mov bx, [bp-10]
        mov al, [cs:bx+1]            ; p
        cmp al, 0xff
        je .next
        cmp al, [EXPASG]
        je .next                     ; the expression pedal owns this param
        mov cl, [cs:bx+2]            ; internal value from the buffer (the setters take internal units)
        mov ch, 0
        mov si, cx
        test byte [cs:bx+3], 2
        jz .ib
        mov cx, [si+BUF]
        jmp .iv
.ib:    mov cl, [si+BUF]
.iv:    call live_set
.next:  add word [bp-10], 8
        dec word [bp-6]
        jmp .t
.done:  mov sp, bp
        pop bp
        pop di
        pop si
        ret

live_set:                            ; al = param p, cx = internal value -> descriptor setter (timer masked)
        mov ah, 22
        mul ah
        mov bx, ax
        mov ax, [bx+PDESC+0x12]
        mov [ST_FP], ax
        mov ax, [bx+PDESC+0x14]
        mov [ST_FP+2], ax
        mov ax, 0x40f0
        mov es, ax
        or byte [es:TMIC], 0x40
        push cx
        call far [ST_FP]
        add sp, 2
        mov ax, 0x40f0
        mov es, ax
        and byte [es:TMIC], 0xbf
        ret

knobs_all:                           ; bl = which (0/1): every knob -> buffer (no live setters)
        push si
        push bx
        call ent_ptr
        call nknobs
        pop bx
        mov ah, 0
        mov si, ax
.l:     dec si
        js .d
        mov ax, si
        mov dl, 0
        push bx
        call knob_apply
        pop bx
        jmp .l
.d:     pop si
        ret

knob_press:                          ; ax = button 1..8
        dec ax
        mov cl, al
        and cl, 3                    ; column = knob
        mov ch, 1
        cmp al, 4
        jb .up
        mov ch, -1
.up:    cmp byte [ST_STATE], 3
        jne .nb
        mov al, [ST_PAGE]
        cmp al, 12
        jb .bk
        je .ord
        test cl, cl                  ; OUT page: column 1 only
        jnz .ret
        mov al, ch
        jmp out_change
.ord:   cmp cl, 2                    ; ORDER page: column 1 = A, column 2 = B
        jae .ret
        mov [ST_OACT], cl
        mov al, ch
        jmp order_change
.ret:   ret
.bk:    mov byte [ST_VIEW], 1        ; board slot: show its knobs
        push cx
        jmp .kp
.nb:    push cx
        call page_which
        test bh, bh
        jnz .kp                      ; on a pick page: jump to that thing's knob page
        mov al, bl
        cmp byte [ST_STATE], 2
        je .rg
        mov al, 0
.rg:    mov [ST_PAGE], al
.kp:    call page_which
        push bx
        call ent_ptr
        call nknobs
        pop bx                       ; bl = which
        pop cx                       ; cl = knob, ch = +1/-1
        cmp cl, al
        jae .redr                    ; no such knob on this pedal
        mov [ST_ACT], cl
        mov al, cl
        mov ah, 0
        add di, ax
        push bx
        call knob_rec
        mov al, [di]
        add al, ch
        js .lo                       ; below 0
        cmp al, [cs:bx+3]
        jbe .st
        mov al, [cs:bx+3]
        jmp .st
.lo:    xor al, al
.st:    pop bx
        cmp al, [di]
        je .redr
        mov [di], al
        mov al, [ST_ACT]
        mov dl, 1
        call knob_apply
.redr:  call sync_dial
        jmp redraw

dial_check:                          ; PEDAL / RIG
        call page_which
        test bh, bh
        jz .pick
        jmp dial_knob
.pick:  mov ax, [DIAL]
        mov si, ST_PED
        test bl, bl
        jz .p
        mov si, ST_AMP
.p:     cmp al, [si]
        je .r
        mov [si], al
        call apply_cur
        jmp redraw
.r:     ret

dial_knob:                           ; bl = which: dial -> the active knob
        push bx
        call ent_ptr
        call nknobs
        pop bx
        cmp [ST_ACT], al
        jae .r
        mov al, [ST_ACT]
        mov ah, 0
        add di, ax
        mov ax, [DIAL]
        cmp al, [di]
        je .r
        mov [di], al
        mov byte [ST_VIEW], 1
        mov al, [ST_ACT]
        mov dl, 1
        call knob_apply
        jmp redraw
.r:     ret

; ---------------------------------------------------------------- board
board_dial:
        mov al, [ST_PAGE]
        cmp al, 12
        jb .k
        mov si, OUTSEL
        ja .s
        mov si, ORDA
        cmp byte [ST_OACT], 0
        je .s
        mov si, ORDB
.s:     mov ax, [DIAL]
        cmp al, [si]
        je .r
        mov [si], al
        call board_apply
        jmp redraw
.k:     mov bl, 2
        jmp dial_knob
.r:     ret

board_pick:                          ; al = -1 / +1 (BANK / GROUP)
        mov ah, [ST_PAGE]
        cmp ah, 12
        jb .slot
        je order_change
        jmp out_change
.slot:  mov dl, al                   ; dir
        mov bl, ah
        mov bh, 0
        mov [ST_TMP], bl             ; slot
        mov al, [bx+BRD]
        test al, al
        jnz .free
        cmp byte [bx+OWN], 0xff
        je .free
        jmp redraw                   ; grabbed by another pedal: no pick until that pedal changes
.free:  shl bx, 1
        mov bx, [cs:slot_lists+bx]   ; bx -> count, idx...
        mov cl, [cs:bx]
        mov ch, 0
        xor di, di                   ; position: 0 = OUT, j = list[j]
        test al, al
        jz .have
.f:     inc di
        cmp di, cx
        ja .nf
        cmp al, [cs:bx+di]
        jne .f
        jmp .have
.nf:    xor di, di
.have:  mov ax, di
        add al, dl
        cmp al, 0x80
        jb .p1
        mov al, cl                   ; OUT - 1 -> last
        jmp .p2
.p1:    cmp al, cl
        jbe .p2
        xor al, al                   ; last + 1 -> OUT
.p2:    test al, al
        jz .st
        mov ah, 0
        mov di, ax
        mov al, [cs:bx+di]
.st:    mov bl, [ST_TMP]
        mov bh, 0
        mov [bx+BRD], al
        mov byte [ST_VIEW], 0
        mov byte [ST_ACT], 0
        call board_apply
        call sync_dial
        jmp redraw

order_change:                        ; al = -1 / +1 on the active chain preset (A or B)
        mov si, ORDA
        cmp byte [ST_OACT], 0
        je cyc3
        mov si, ORDB
        jmp cyc3
out_change:                          ; al = -1 / +1 on the output channel
        mov si, OUTSEL
cyc3:                                ; [si] = ([si] + al) mod 3, then rebuild the board
        add al, [si]
        cmp al, 0x80
        jb .a
        mov al, 2
.a:     cmp al, 3
        jb .b
        xor al, al
.b:     mov [si], al
        call board_apply
        call sync_dial
        jmp redraw

compute_owners:                      ; OWN[b] = slot whose pedal drives block b (own pedal first, then grabs)
        xor bx, bx
.o1:    mov al, 0xff
        cmp byte [bx+BRD], 0
        je .o2
        mov al, bl
.o2:    mov [bx+OWN], al
        inc bx
        cmp bx, 12
        jb .o1
        xor bx, bx                   ; bx = slot, in chain order: the earliest pedal gets a free block
.s:     mov al, [bx+BRD]
        test al, al
        jz .sn
        call ent_slot
        mov dx, [cs:si+18]           ; extras mask
        xor di, di
.b:     shr dx, 1
        jnc .bn
        cmp byte [di+OWN], 0xff
        jne .bn
        mov [di+OWN], bl
.bn:    inc di
        cmp di, 12
        jb .b
.sn:    inc bx
        cmp bx, 12
        jb .s
        ret

board_apply:                         ; whole board -> edit buffer -> sound change
        call compute_owners
        xor bx, bx                   ; on bits = blocks that have an owner
        mov dx, 1
        xor cx, cx
.on:    cmp byte [bx+OWN], 0xff
        je .on1
        or cx, dx
.on1:   shl dx, 1
        inc bx
        cmp bx, 12
        jb .on
        mov byte [ST_ON], 0
        mov al, cl
        and al, 0x7f
        mov [ST_ON+2], al            ; SysEx 0x0E = blocks 0..6
        shr cx, 7
        mov [ST_ON+1], cl            ; SysEx 0x0D bits 0..4 = blocks 7..11
        xor bx, bx                   ; each slot's pedal: params + knobs in the blocks it owns
.s:     mov al, [bx+BRD]
        test al, al
        jz .sn
        mov [ST_FILT], bl
        push bx
        call ent_slot                ; si = entry, di = store
        push si
        push di
        call board_pairs
        pop di
        pop si
        call nknobs                  ; al = count (bx clobbered)
        mov ah, 0
        mov cx, ax
.k:     jcxz .kd
        dec cx
        push cx
        push si
        push di
        mov al, cl
        mov dl, 0
        call knob_core
        pop di
        pop si
        pop cx
        jmp .k
.kd:    pop bx
.sn:    inc bx
        cmp bx, 12
        jb .s
        mov byte [ST_FILT], 0xff
        mov al, [ORDA]               ; chain order presets: SysEx 0..4 (A) and 6..10 (B)
        mov ah, 5
        mul ah
        mov si, ax
        add si, orda_t
        xor bx, bx
.oa:    mov al, [cs:bx+si]
        push bx
        call dt1set
        pop bx
        inc bx
        cmp bx, 5
        jb .oa
        mov al, [ORDB]
        mov ah, 5
        mul ah
        mov si, ax
        add si, ordb_t
        xor bx, bx
.ob:    mov al, [cs:bx+si]
        push bx
        add bl, 6
        call dt1set
        pop bx
        inc bx
        cmp bx, 5
        jb .ob
        mov bl, 0x63                 ; output channel = the A/B/Y box
        mov al, [OUTSEL]
        call dt1set
        call write_on
        mov si, s_board
        jmp name_snd

board_pairs:                         ; cs:si -> entry; writes the pairs in blocks owned by slot [ST_FILT]
        add si, 20
        mov cl, [cs:si]
        mov ch, 0
        inc si
        jcxz .done
.p:     push cx
        mov bl, [cs:si]
        mov al, [cs:si+1]
        add si, 2
        cmp bl, 0x0c
        jb .blk
        cmp bl, 0x0e
        ja .blk
        mov ah, [ST_FILT]
        cmp bl, 0x0d
        jne .t0c
        cmp ah, [OWN+1]              ; OD/DIST type goes with the dirt block
        jne .nx
        and al, 0x40
        or [ST_ON+1], al
        jmp .nx
.t0c:   cmp bl, 0x0c
        jne .nx
        cmp ah, [OWN+7]              ; B2 type goes with the mod block
        jne .nx
        mov [ST_ON], al
        jmp .nx
.blk:   mov bh, 0
        mov dl, al
        mov al, [cs:bx+blk_of-0x0c]
        cmp al, 0x0f                 ; global (exp pedal) params: always
        je .set
        mov ah, 0
        mov di, ax
        mov al, [di+OWN]
        cmp al, [ST_FILT]
        jne .nx
.set:   mov al, dl
        call dt1set
.nx:    pop cx
        loop .p
.done:  ret

; ---------------------------------------------------------------- apply (PEDAL / RIG)
apply_cur:
        mov al, [ST_PED]
        mov ah, 0
        xor dx, dx
        cmp byte [ST_STATE], 2
        jne apply
        mov dl, [ST_AMP]
apply:                               ; ax = pedal idx, dx = amp idx
        push dx
        push ax
        mov byte [ST_ON], 0          ; all blocks off, then OR in each entry's blocks
        mov byte [ST_ON+1], 0
        mov byte [ST_ON+2], 0
        mov bx, ax
        shl bx, 1
        mov si, [cs:ped_off+bx]
        call apply_entry
        pop ax
        pop dx
        push dx
        push ax
        mov bx, dx
        shl bx, 1
        mov si, [cs:amp_off+bx]
        call apply_entry             ; amp last: its EQ/cab wins
        mov bl, 0
        call knobs_all               ; knob positions on top of the recipes
        mov bl, 1
        call knobs_all
        call write_on
        pop ax
        pop dx
        mov bx, ax                   ; name = pedal, else amp, else OFF
        test ax, ax
        jnz .pn
        mov bx, dx
        test dx, dx
        jnz .an
        mov si, ped_e0
        jmp name_snd
.pn:    shl bx, 1
        mov si, [cs:ped_off+bx]
        jmp name_snd
.an:    shl bx, 1
        mov si, [cs:amp_off+bx]
name_snd:                            ; cs:si -> 16-char name -> buffer, then SOUND CHANGE (= main loop F6A1:007E)
        mov di, BUF_NAME
        mov cx, 16
.cl:    mov al, [cs:si]
        mov [di], al
        inc si
        inc di
        loop .cl
        or byte [SNDREQ], 0x20
        test byte [SNDHOLD], 0x40
        jnz .defer                   ; main loop serves it after we return
        and byte [SNDREQ], 0xdf
        mov ax, 1
        push ax
        mov ax, 0xfa00
        push ax
        mov ax, BUF
        push ax
        farcall F00E_SEG, VALIDATE
        add sp, 6
        farcall F6A1_SEG, LOADBUF
.defer: ret

write_on:                            ; block type + on/off (firmware packs them into the 16-bit word)
        mov bl, 0x0c
        mov al, [ST_ON]
        call dt1set
        mov bl, 0x0d
        mov al, [ST_ON+1]
        call dt1set
        mov bl, 0x0e
        mov al, [ST_ON+2]
        jmp dt1set

apply_entry:                         ; cs:si -> entry (name16, kptr, extras, count, count x (sysex addr, value))
        add si, 20
        mov cl, [cs:si]
        mov ch, 0
        inc si
        jcxz .done
.p:     push cx
        mov bl, [cs:si]
        mov al, [cs:si+1]
        add si, 2
        cmp bl, 0x0c
        jb .set
        cmp bl, 0x0e
        ja .set
        mov bh, 0
        or [bx+ST_ON-0x0c], al       ; on/off + type: merge, written once at the end
        jmp .nx
.set:   call dt1set
.nx:    pop cx
        loop .p
.done:  ret

dt1set:                              ; bl = SysEx addr, al = value -> EE11:17F4(FA00:9D06, addr, value)
        push si
        push di
        mov ah, 0
        push ax
        mov bh, 0
        push bx
        mov ax, 0xfa00
        push ax
        mov ax, BUF
        push ax
        farcall EE11_SEG, DT1SET
        add sp, 8
        pop di
        pop si
        ret

; ---------------------------------------------------------------- dial
sync_dial:                           ; point the dial at what the current page edits
        mov al, [ST_STATE]
        test al, al
        jnz .go
        ret
.go:    cmp al, 3
        jne .nb
        mov al, [ST_PAGE]
        cmp al, 12
        jb .knob2
        mov si, OUTSEL
        ja .set3
        mov si, ORDA
        cmp byte [ST_OACT], 0
        je .set3
        mov si, ORDB
.set3:  mov al, [si]
        mov ah, 0
        mov cx, 2
        mov dl, 1
        jmp dial_set
.knob2: mov bl, 2
        jmp .knob
.nb:    call page_which
        test bh, bh
        jz .pick
.knob:  call ent_ptr
        call nknobs
        test al, al
        jz .none
        cmp [ST_ACT], al
        jb .ok
        mov byte [ST_ACT], 0
.ok:    mov al, [ST_ACT]
        mov ah, 0
        add di, ax
        call knob_rec
        mov al, [di]
        mov ah, 0
        mov cl, [cs:bx+3]
        mov ch, 0
        mov dl, 0
        jmp dial_set
.none:  xor ax, ax
        xor cx, cx
        mov dl, 0
        jmp dial_set
.pick:  mov al, [ST_PED]
        mov cx, NPED
        test bl, bl
        jz .pp
        mov al, [ST_AMP]
        mov cx, NAMP
.pp:    mov ah, 0
        mov dl, 1
dial_set:                            ; ax = value, cx = max, dl = wrap
        mov [DIAL], ax
        mov [DIALMAX], cx
        mov word [DIALSTEP], 1
        mov [DIALWRAP], dl
        ret

; ---------------------------------------------------------------- screens
redraw:
        mov al, [ST_STATE]
        test al, al
        jnz .r1
        jmp draw_split
.r1:    cmp al, 3
        jne .r2
        jmp board_redraw
.r2:    call page_which
        test bh, bh
        jz .r3
        jmp draw_knobs
.r3:    cmp byte [ST_STATE], 2
        jne draw_pick
        jmp draw_rig

draw_pick:                           ; PEDAL mode pick page
        xor ax, ax
        mov cx, 1
        call cursor
        mov si, s_pedal
        mov cx, 16
        call puts
        xor ax, ax
        mov cx, 2
        call cursor
        mov al, [ST_PED]
        mov ah, 0
        mov bx, ax
        shl bx, 1
        mov si, [cs:ped_off+bx]
        mov cx, 16
        jmp puts

draw_split:
        xor ax, ax
        mov cx, 1
        call cursor
        mov si, s_split1
        mov cx, 16
        call puts
        xor ax, ax
        mov cx, 2
        call cursor
        mov si, s_split2
        mov cx, 16
        jmp puts

draw_rig:                            ; RIG pick pages: bl = 0 pedal row active / 1 amp row
        push bx
        xor ax, ax
        mov cx, 1
        call cursor
        pop bx
        push bx
        mov al, '>'
        test bl, bl
        jz .m1
        mov al, ' '
.m1:    call putc
        mov al, 'P'
        call putc
        mov al, ':'
        call putc
        mov al, [ST_PED]
        mov ah, 0
        mov bx, ax
        shl bx, 1
        mov si, [cs:ped_off+bx]
        mov cx, 13
        call puts
        xor ax, ax
        mov cx, 2
        call cursor
        pop bx
        mov al, ' '
        test bl, bl
        jz .m2
        mov al, '>'
.m2:    call putc
        mov al, 'A'
        call putc
        mov al, ':'
        call putc
        mov al, [ST_AMP]
        mov ah, 0
        mov bx, ax
        shl bx, 1
        mov si, [cs:amp_off+bx]
        mov cx, 13
        jmp puts

board_redraw:
        mov al, [ST_PAGE]
        cmp al, 12
        je draw_order
        ja draw_out
        cmp byte [ST_VIEW], 0
        je draw_slot
        mov bl, 2
        jmp draw_knobs

draw_slot:                           ; row 1 slot label, row 2 its pedal / <grabber> / OUT
        xor ax, ax
        mov cx, 1
        call cursor
        mov al, [ST_PAGE]
        mov ah, 16
        mul ah
        mov si, ax
        add si, s_slots
        mov cx, 16
        call puts
        xor ax, ax
        mov cx, 2
        call cursor
        mov bl, [ST_PAGE]
        mov bh, 0
        mov al, [bx+BRD]
        test al, al
        jz .nown
        call ent_slot
        mov cx, 16
        jmp puts
.nown:  mov al, [bx+OWN]
        cmp al, 0xff
        je .out
        mov bl, al
        mov al, [bx+BRD]
        call ent_slot
        mov cx, 13                   ; trimmed name length (<= 13)
.tr:    mov bx, cx
        cmp byte [cs:bx+si-1], ' '
        jne .tl
        loop .tr
        inc cx
.tl:    push cx
        mov al, '<'
        call putc
        call puts
        mov al, '>'
        call putc
        pop cx
        neg cx
        add cx, 14                   ; pad to 16
.pad:   mov al, ' '
        call putc
        loop .pad
        ret
.out:   mov si, s_out
        mov cx, 16
        jmp puts

draw_order:
        xor ax, ax
        mov cx, 1
        call cursor
        mov al, 'A'
        mov ah, [ORDA]
        mov dl, 0
        call ord_row
        xor ax, ax
        mov cx, 2
        call cursor
        mov al, 'B'
        mov ah, [ORDB]
        add ah, 3
        mov dl, 1
ord_row:                             ; al = 'A'/'B', ah = name index, dl = row id ('>' if active)
        push ax
        mov al, ' '
        cmp dl, [ST_OACT]
        jne .m
        mov al, '>'
.m:     call putc
        pop ax
        call putc
        mov al, ':'
        call putc
        mov al, ah
        mov ah, 13
        mul ah
        mov si, ax
        add si, s_ordn
        mov cx, 13
        jmp puts

draw_out:
        xor ax, ax
        mov cx, 1
        call cursor
        mov si, s_slots + 13*16
        mov cx, 16
        call puts
        xor ax, ax
        mov cx, 2
        call cursor
        mov al, [OUTSEL]
        mov ah, 16
        mul ah
        mov si, ax
        add si, s_outn
        mov cx, 16
        jmp puts

draw_knobs:                          ; bl = which. Row 1 labels (+'*' on the dial's knob), row 2 values.
        push bp
        mov bp, sp
        sub sp, 4                    ; -2 knob count, -4 store ptr
        call ent_ptr
        call nknobs
        mov ah, 0
        mov [bp-2], ax
        mov [bp-4], di
        test al, al
        jnz .has
        xor ax, ax                   ; no knobs (OFF): name + hint
        mov cx, 1
        call cursor
        mov cx, 16
        call puts
        xor ax, ax
        mov cx, 2
        call cursor
        mov si, s_noknob
        mov cx, 16
        call puts
        mov sp, bp
        pop bp
        ret
.has:   push si                      ; entry
        xor ax, ax
        mov cx, 1
        call cursor
        xor di, di                   ; di = knob idx (survives far calls)
.l1:    cmp di, [bp-2]
        jae .b1
        mov ax, di
        call knob_rec
        mov al, [cs:bx]
        call putc
        mov al, [cs:bx+1]
        call putc
        mov al, [cs:bx+2]
        call putc
        mov al, ' '
        mov dx, di
        cmp dl, [ST_ACT]
        jne .s1
        mov al, '*'
.s1:    call putc
        jmp .n1
.b1:    call put4sp
.n1:    inc di
        cmp di, 4
        jb .l1
        xor ax, ax
        mov cx, 2
        call cursor
        xor di, di
.l2:    cmp di, [bp-2]
        jae .b2
        mov ax, di
        call knob_rec
        mov ah, [cs:bx+4]            ; disp
        mov dl, [cs:bx+3]            ; steps
        mov bx, [bp-4]
        mov al, [bx+di]              ; k
        call put_val
        mov al, ' '
        call putc
        jmp .n2
.b2:    call put4sp
.n2:    inc di
        cmp di, 4
        jb .l2
        pop si
        mov sp, bp
        pop bp
        ret

put4sp:
        mov al, ' '
        call putc
        call putc
        call putc
        jmp putc

put_val:                             ; al = k, ah = disp, dl = steps -> 3 chars
        cmp ah, 1
        jne .sg
        add al, '1'                  ; 1-based int
        call putc
        mov al, ' '
        call putc
        jmp putc
.sg:    cmp ah, 2
        jne .h
        shr dl, 1                    ; signed: k - steps/2 (semitones)
        sub al, dl
        mov ah, ' '
        cmp al, 0
        je .z
        mov ah, '+'
        jg .z
        mov ah, '-'
        neg al
.z:     push ax
        mov al, ah
        call putc
        pop ax
        cmp al, 10
        jb .d1
        push ax
        mov al, '1'
        call putc
        pop ax
        sub al, 10
        add al, '0'
        jmp putc
.d1:    add al, '0'
        call putc
        mov al, ' '
        jmp putc
.h:     cmp al, 20                   ; 0-10 in halves
        jne .n
        mov al, '1'
        call putc
        mov al, '0'
        call putc
        mov al, ' '
        jmp putc
.n:     mov ah, '0'
        shr al, 1                    ; al = whole, carry = half
        jnc .w
        mov ah, '5'
.w:     mov [ST_TMP], ah
        add al, '0'
        call putc
        mov al, '.'
        call putc
        mov al, [ST_TMP]
        jmp putc

; ---------------------------------------------------------------- helpers
cursor:                              ; ax = col, cx = line (bx/dx kept)
        push bx
        push dx
        push ax
        push cx
        farcall E93C_SEG, CUR
        add sp, 4
        pop dx
        pop bx
        ret

putc:                                ; al (all regs kept)
        push ax
        push bx
        push cx
        push dx
        mov ah, 0
        push ax
        farcall E93C_SEG, PUTC
        add sp, 2
        pop dx
        pop cx
        pop bx
        pop ax
        ret

puts:                                ; cs:si, cx chars
        push di
        mov di, cx
.l:     mov al, [cs:si]
        call putc
        inc si
        dec di
        jnz .l
        pop di
        ret

keyt:                                ; ax = key -> ax, ZF
        push ax
        farcall F00E_SEG, KEYT
        add sp, 2
        test ax, ax
        ret

s_split1: db "UP:PEDAL DN:RIG "
s_split2: db "EDIT:BOARD      "
s_pedal:  db "PEDAL MODE      "
s_noknob: db "NO KNOBS        "
s_board:  db "PEDALBOARD      "
s_out:    db "OUT             "
s_ordn:   db "WAH>DIRT     ", "DIRT>WAH     ", "PHASE>DIRT   ", "STOCK        ", "TREM LAST    ", "REV>DELAY    "
s_outn:   db "AMP 1  (CH1)    ", "AMP 2  (CH2)    ", "BOTH  (A/B/Y)   "
orda_t:   db 0, 2, 1, 3, 4,  0, 1, 2, 3, 4,  0, 2, 3, 1, 4      ; COMP WAH DIRT PHAS EQ | stock | COMP WAH PHAS DIRT EQ
ordb_t:   db 6, 7, 8, 9, 10,  6, 7, 9, 10, 8,  6, 7, 8, 10, 9   ; stock | trem after reverb | reverb before delay
%include "pedal_data.inc"
