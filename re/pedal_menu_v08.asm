; GP-16 PEDAL / RIG mode (v0.8): the rack as one pedal. Lives at ROM 0x0A00 = E0A0:0000. Far functions, DS=FA00.
;   E0A0:0000  SYSTEM key entry (main loop F6A1:012C: lcall F6A1:1530 -> here). Starts at the split screen.
;   E0A0:0003  power-on entry (F6A1:0063: mov byte [a312],0 -> lcall here). Starts in the last mode, knob page.
; split:  FUNCTION UP -> PEDAL mode, DOWN -> RIG mode, SYSTEM -> stock System menu, ESC -> patch screen.
; PEDAL mode pages: 0 knobs, 1 pick pedal.      RIG pages: 0 pedal knobs, 1 amp knobs, 2 pick pedal, 3 pick amp.
;   FUNCTION UP/DOWN = next/previous page. ESC = back to split.
;   Knob page: buttons 1-4 = knob 1-4 up, 5-8 = knob 1-4 down (one column each); the dial (and BANK/GROUP -/+)
;   follows the knob touched last ('*'). Pick page: the dial picks the pedal/amp. Number buttons never pick patches.
; Knob positions are kept per pedal/amp in battery RAM. Knob moves are live: buffer via the DT1 setter EE11:17F4 +
; the param's own setter from the descriptor table DS:2396 (same as the stock edit menu, no patch reload).
; Pedal/amp change = full apply: recipe pairs + knob values through EE11:17F4, then the stock sound-change service.
; (v0.7 source kept as pedal_menu_v07.asm.)
        cpu 186
        bits 16
        org 0

F00E_SEG equ 0xf00e
KEYT     equ 0x1cd2          ; keytest(n) -> ax (consumes the key); 0xff clears all
VALIDATE equ 0x0764          ; (buf far, flag): effect-order check, part of the stock sound-change service
F6A1_SEG equ 0xf6a1
SERVICE  equ 0x03bc          ; service(arg): keys, MIDI, dial; arg=1 enables BANK/GROUP as -/+
SYSMENU  equ 0x1530          ; stock System menu
LOADBUF  equ 0x0382          ; edit buffer -> DSPs (stock sound-change service)
EE11_SEG equ 0xee11
DT1SET   equ 0x17f4          ; (buf far, sysex addr, value): DT1 per-byte setter
E93C_SEG equ 0xe93c
CUR      equ 0x0238          ; cursor(col,line)  push col; push line
PUTC     equ 0x0000          ; putc(ch)

BUF      equ 0x9d06          ; internal edit buffer (114 B)
BUF_NAME equ 0x9d67          ; +0x61, 16 chars (play screen shows it)
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
ST_PED   equ 0xcf30          ; battery RAM (no stock refs to CFxx; debug port uses CF00-CF1E)
ST_AMP   equ 0xcf31
ST_ON    equ 0xcf33          ; 3 B scratch: merged SysEx 0x0C/0x0D/0x0E
ST_MODE  equ 0xcf36          ; 1 pedal / 2 rig: mode to boot into
ST_MAGIC equ 0xcf37          ; == KMAGIC when the knob stores are valid
ST_PAGE  equ 0xcf38
ST_ACT   equ 0xcf39          ; knob the dial follows
ST_FP    equ 0xcf3a          ; far ptr scratch (4)
ST_STATE equ 0xcf3e          ; 0 split, 1 pedal, 2 rig
ST_TMP   equ 0xcf3f
ST_KP    equ 0xcf40          ; 31 x 4 knob positions (pedals)
ST_KA    equ 0xcfc0          ; 8 x 4 (amps)

K_ESC    equ 0x0d
K_SYS    equ 0x0e
K_UP     equ 0x0f            ; FUNCTION (stock page step: 0xF = next, 0x10 = previous)
K_DN     equ 0x10
K_CLR    equ 0xff
NPED     equ 30              ; max pedal index (0 = OFF)
NAMP     equ 7               ; max amp index   (0 = OFF)
KREC     equ 22              ; knob record size

%macro farcall 2
        db 0x9a
        dw %2
        dw %1
%endmacro

        jmp near menu_sys            ; E0A0:0000
boot_entry:                          ; E0A0:0003
        mov byte [0xa312], 0         ; the instruction we replaced
        or byte [MENUFLG], 1
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
        mov ax, 1
        push ax
        farcall F6A1_SEG, SERVICE
        add sp, 2
        mov ax, K_ESC
        call keyt
        jz .noesc
        cmp byte [ST_STATE], 0
        je .exit                     ; ESC at split -> patch screen
        call to_split
        jmp mloop
.noesc:
        cmp byte [ST_STATE], 0
        jne .mode
        mov ax, K_SYS                ; ---- split
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
.s3:    call eat_numbers
        jmp mloop

.mode:  mov ax, K_SYS                ; ---- pedal / rig (SYSTEM does nothing here; eat it)
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
.m2:    mov si, 1                    ; number buttons 1-8 (si survives far calls)
.mn:    mov ax, si
        call keyt
        jz .mnx
        mov ax, si
        call knob_press
        jmp mloop
.mnx:   inc si
        cmp si, 8
        jbe .mn
        call dial_check
        jmp mloop

.exit:  mov ax, K_CLR                ; drop queued presses so nothing reaches the patch keys
        call keyt
        and byte [MENUFLG], 0xfe
        pop di
        pop si
        pop bp
        retf

; ---------------------------------------------------------------- state
validate:
        cmp byte [ST_PED], NPED
        jbe .v1
        mov byte [ST_PED], 0
.v1:    cmp byte [ST_AMP], NAMP
        jbe .v2
        mov byte [ST_AMP], 0
.v2:    mov al, [ST_MODE]
        cmp al, 1
        je .v3
        cmp al, 2
        je .v3
        mov byte [ST_MODE], 1
.v3:    cmp byte [ST_MAGIC], KMAGIC
        je .v4
        call knobs_reset
        mov byte [ST_MAGIC], KMAGIC
.v4:    mov byte [ST_ACT], 0
        ret

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

enter_mode:                          ; al = 1 pedal / 2 rig
        mov [ST_STATE], al
        mov [ST_MODE], al
        mov byte [ST_PAGE], 0
        mov byte [ST_ACT], 0
        call apply_cur
        call sync_dial
        jmp redraw

npages:                              ; -> al
        mov al, 2
        cmp byte [ST_STATE], 2
        jne .n
        mov al, 4
.n:     ret

page_step:                           ; al = +1 / -1
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

page_which:                          ; -> bl = 0 pedal / 1 amp, bh = 1 if knob page
        mov al, [ST_PAGE]
        mov bx, 0x0100
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
ent_ptr:                             ; bl = 0 pedal / 1 amp -> si = entry (cs), di = knob store (ds)
        test bl, bl
        jnz .a
        mov al, [ST_PED]
        mov ah, 0
        mov di, ax
        shl di, 2
        add di, ST_KP
        mov si, ax
        shl si, 1
        mov si, [cs:ped_off+si]
        ret
.a:     xor ax, ax                   ; amp counts only in RIG mode
        cmp byte [ST_STATE], 2
        jne .a1
        mov al, [ST_AMP]
.a1:    mov di, ax
        shl di, 2
        add di, ST_KA
        mov si, ax
        shl si, 1
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

knob_apply:                          ; bl = which, al = knob idx, dl = 1 live / 0 buffer only
        push si
        push di
        push bp
        mov bp, sp
        sub sp, 12                   ; -2 k, -4 steps, -6 targets left, -8 live, -10 target ptr, -12 value
        mov [bp-8], dl
        push ax
        call ent_ptr
        pop ax
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
        je .done
        mov bx, [bp-10]
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

knobs_all:                           ; bl = which: every knob -> buffer (no live setters)
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
.up:    push cx
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

dial_check:
        call page_which
        test bh, bh
        jz .pick
        push bx                      ; knob page: dial = active knob
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
        mov al, [ST_ACT]
        mov dl, 1
        call knob_apply
        jmp redraw
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

; ---------------------------------------------------------------- apply (full: pedal/amp change)
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
        mov bl, 0x0c                 ; block type + on/off (firmware packs them into the 16-bit word)
        mov al, [ST_ON]
        call dt1set
        mov bl, 0x0d
        mov al, [ST_ON+1]
        call dt1set
        mov bl, 0x0e
        mov al, [ST_ON+2]
        call dt1set
        pop ax
        pop dx
        mov bx, ax                   ; name = pedal, else amp, else OFF
        test ax, ax
        jnz .pn
        mov bx, dx
        test dx, dx
        jnz .an
        mov si, ped_e0
        jmp .cp
.pn:    shl bx, 1
        mov si, [cs:ped_off+bx]
        jmp .cp
.an:    shl bx, 1
        mov si, [cs:amp_off+bx]
.cp:    mov di, BUF_NAME
        mov cx, 16
.cl:    mov al, [cs:si]
        mov [di], al
        inc si
        inc di
        loop .cl
                                     ; SOUND CHANGE REQUEST, served now (= main loop F6A1:007E..00A5)
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

apply_entry:                         ; cs:si -> entry (name16, kptr, count, count x (sysex addr, value))
        add si, 18
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
        cmp byte [ST_STATE], 0
        jne .go
        ret
.go:    call page_which
        test bh, bh
        jz .pick
        call ent_ptr
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
        jz draw_split
        call page_which
        test bh, bh
        jnz draw_knobs
        cmp byte [ST_STATE], 2
        je draw_rig
        jmp draw_pick

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

put_val:                             ; al = k, ah = disp -> 3 chars
        cmp ah, 1
        jne .h
        add al, '1'
        call putc
        mov al, ' '
        call putc
        jmp putc
.h:     cmp al, 20
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

s_split1: db " UP  = PEDAL    "
s_split2: db " DOWN= RIG      "
s_pedal:  db "PEDAL MODE      "
s_noknob: db "NO KNOBS        "
%include "pedal_data.inc"
