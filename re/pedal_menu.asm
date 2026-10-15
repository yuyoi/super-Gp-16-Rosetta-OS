; JSW ROSETTA OS v1 -- GP-16 PEDAL / RIG / BOARD modes: the rack as one pedal, or a whole pedalboard.
; Position independent (org 0, tables via CS); build_mod places it at ROM 0x0200 = E020:0000. Far functions, DS=FA00.
;   +0  SYSTEM key entry (main loop F6A1:012C: lcall F6A1:1530 -> here). Starts at the split screen.
;   +3  power-on entry (F6A1:0063: mov byte [a312],0 -> lcall here). Starts in the last mode.
; split:  FUNCTION UP -> PEDAL, DOWN -> RIG, EDIT -> BOARD, SYSTEM -> stock System menu, ESC -> patch screen.
; PEDAL pages: 0 knobs, 1 pick pedal.     RIG pages: 0 pedal knobs, 1 amp knobs, 2 pick pedal, 3 pick amp.
;   FUNCTION UP/DOWN = next/previous page; RIG: UP = the pedal (top row), DOWN = the amp (bottom row), the same side
;   again = pick <-> knobs. ESC = back to split. BANK/GROUP = dial -/+ (VALUE down/up).
;   Knob page: buttons 1-4 = knob 1-4 up, 5-8 = knob 1-4 down; the dial follows the knob touched last ('*').
;   5-6 knobs: names over numbers, 1-6 pick a knob (underline cursor), 7/8 = CURSOR previous/next knob,
;   dial or VALUE up/down (GROUP/BANK) turns it. CAB knob (amps): OFF / 4X / 2X / 1X cab sim in the HI EQ band.
;   Mode-button pedals (Dimension C): buttons 1-4 = mode, the lit one again = off.
;   Knobs are macros: one knob may drive several params, linearly or by a value table.
; BOARD: 15 pages = 12 block slots (A1 COMP .. B6 AMP) + ORDER + OUT (A/B/Y box) + BOARD MEMORY (1-8 = load).
;   WRITE on any board page = save the board to memory 1-8. The expression pedal goes to the first pedal that wants it.
;   FUNCTION = next/previous slot, BANK/GROUP = previous/next pedal for the slot, buttons + dial = its knobs.
;   A pedal sits in its home slot and grabs the extra blocks its voicing uses (Muff: comp + EQ, amps: EQ, Leslie: trem)
;   when those slots are empty; a grabbed slot shows <NAME> and can't take a pedal until that pedal changes.
;   ORDER: buttons 1/5 = A chain preset (4), 2/6 = B chain preset (3). OUT: 1/5 = output channel (CH1 / CH2 / both).
; Knob moves are live (DT1 setter EE11:17F4 + the param's descriptor setter, as the stock edit menu does).
; Pedal/amp/board change = full apply through EE11:17F4, then the stock sound-change service.
; (Older sources: pedal_menu_v07.asm, pedal_menu_v08.asm, pedal_menu_v09.asm.)
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
UCUR     equ 0x01ca          ; underline cursor: 1 on, 2 off ([9E82] bit 1)

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
OWN      equ 0xce20          ; 12 B: BOARD owner slot per block (FF = none)
ST_OACT  equ 0xce2c          ; ORDER page: 0 = A row active, 1 = B row
ST_BTN   equ 0xce2d          ; button pressed (0-7)
ST_WH    equ 0xce2e          ; which (0 pedal / 1 amp / 2 board) for the knob being edited
ST_N     equ 0xce2f          ; knob count of that entry
ST_SPTR  equ 0xce30          ; word: its knob store
ST_DEPS  equ 0xce32          ; knobs to re-apply after a live move
ST_SAVE  equ 0xce33          ; 1 = "save board to 1-8" prompt
ST_EXPW  equ 0xce34          ; BOARD: slot that owns the expression pedal (FF = none yet)
ST_DIR   equ 0xce35          ; +1 / -1
ST_LMEM  equ 0xce36          ; board memory loaded / saved last (FF = none)
ST_MPTR  equ 0xce38          ; word: board memory pointer
                             ; knob stores: KS_BASE.. (per entry, address in the table); no stock refs in DS A800-CDFF
BMEM     equ 0xb400          ; 8 board memories
BMSZ     equ 96              ; KMAGIC, BRD[12], ORDA, ORDB, OUTSEL, knob positions 12 x 6

K_BANK   equ 0x09
K_GROUP  equ 0x0a
K_WRITE  equ 0x0b
K_EDIT   equ 0x0c
K_ESC    equ 0x0d
K_SYS    equ 0x0e
K_UP     equ 0x0f            ; FUNCTION (stock page step: 0xF = next, 0x10 = previous)
K_DN     equ 0x10
K_CLR    equ 0xff
NSLOT    equ 15              ; BOARD pages
NORDA    equ 4               ; A chain presets
D_MODE   equ 5               ; knob disp: mode buttons
D_CAB    equ 6               ; knob disp: cab names (OFF / 4X / 2X / 1X)
CABT     equ 0xfe            ; knob table target = cab type (0 off, 1-3 = cab_t0..2), not a SysEx address
ST_CAB   equ 0xce3a          ; cab in use (0 = off): its coefficients go into the HI EQ band (chip 1 0B1-0B9)
ST_CABP  equ 0xce3b          ; 1 = cab coefficients due (written by mloop once the sound change is done)
ST_DSC   equ 0xce3c          ; dial counts per position (dial_set: short ranges, smooth encoder)
HOTT     equ 0xfd            ; knob table target = DIST x2 stage (drive past 10): 0 stock / 1 hot
ST_HOT   equ 0xce3d          ; 1 = DSP chip 0 step 10B = 9204a7 (x2 into the DIST clipper), 0 = stock 1204a7
ST_HOTP  equ 0xce3e          ; 1 = step 10B due (written by mloop once the sound change is done)
E83B_SEG equ 0xe83b
SETC1    equ 0x0679          ; chip 1 set_coef(step, coef): boot instruction + coefficient, commit 8
FARSEG   equ 0xffd9          ; far_blob.bin at ROM 0x1FD90 (end-of-ROM zero run): overflow routines + tables
FAR_DIALSET equ 0
FAR_DIALVAL equ 3
FAR_HOT  equ 6
FAR_CAB  equ 9
REVSEG   equ 0xf301          ; v2.8 rev_blob.bin at ROM 0x13010 (dead stock range wiped by v2.7): REVERSE DELAY
REV_NOW  equ 0
REV_STOP equ 3
REV_HOLD equ 9               ; mask the engine timer while the OS touches the DSP
REV_GO   equ 12             ; unmask it for the idle wait
REV_SETTLE equ 15           ; mloop calls it every pass: counts down ST_REVGO and unmasks the engine at 0
REVT     equ 0xfc            ; knob table target = reverse setting (2 B: REVT, which) -> ST_RV[which], mloop sets up
D_BPM    equ 7               ; knob disp: BPM = 40 + k, 3 digits
D_NOTE   equ 8               ; knob disp: note value name (s_note)
ST_RV    equ 0xce40          ; 4 B: BPM-40, note, mix, level (rev_blob.asm reads them)
ST_REVP  equ 0xce44          ; 1 = reverse (re)start due (written by mloop once the sound change is done)

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

mloop:                               ; the engine runs free through the menu (redraws/keys/dial touch the LCD, not the
        xor ax, ax                   ; DSP). The truce is called only at the few spots that DO write the DSP: rev_now,
        cmp byte [ST_STATE], 3       ; hook_load and REV_STOP stop the engine; live_set masks it around the firmware
        je .svc                      ; setter. Masking it across the whole loop instead jumped the tap every tick =
        inc ax                       ; "extra cascading samples" of noise.
.svc:   push ax
        farcall F6A1_SEG, SERVICE
        add sp, 2
        cmp byte [ST_CABP], 0        ; cab coefficients due, and the sound change is done
        je .ncab
        test byte [SNDREQ], 0x20
        jnz .ncab
        mov byte [ST_CABP], 0
        call cab_now
.ncab:  cmp byte [ST_HOTP], 0        ; DIST x2 stage due
        je .nhot
        test byte [SNDREQ], 0x20
        jnz .nhot
        mov byte [ST_HOTP], 0
        call hot_now
.nhot:  cmp byte [ST_REVP], 0        ; REVERSE DELAY due: memory, dry cancel, engine (rev_blob checks the pedal)
        je .nrev
        test byte [SNDREQ], 0x20
        jnz .nrev
        mov byte [ST_REVP], 0
        farcall REVSEG, REV_NOW
.nrev:  farcall REVSEG, REV_SETTLE   ; startup settle: unmasks the engine a few passes after it started (masked),
        cmp byte [ST_SAVE], 0        ; once the firmware's post-select redraw burst is done (rev_blob owns the count)
        je .nsv
        jmp .save
.nsv:   mov ax, K_ESC
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

.mode:  mov ax, K_SYS                ; ---- pedal / rig (SYSTEM/EDIT/WRITE do nothing here; eat them)
        call keyt
        mov ax, K_EDIT
        call keyt
        mov ax, K_WRITE
        call keyt
        mov ax, K_UP
        call keyt
        jz .m1
        mov al, 1
        cmp byte [ST_STATE], 2
        jne .mu
        call rig_up
        jmp mloop
.mu:    call page_step
        jmp mloop
.m1:    mov ax, K_DN
        call keyt
        jz .m2
        mov al, -1
        cmp byte [ST_STATE], 2
        jne .md
        call rig_dn
        jmp mloop
.md:    call page_step
        jmp mloop
.m2:    call numbers
        jnz .mx
        call dial_check
.mx:    jmp mloop

.board: mov ax, K_SYS                ; ---- board
        call keyt
        mov ax, K_EDIT
        call keyt
        mov ax, K_WRITE
        call keyt
        jz .b0
        mov byte [ST_SAVE], 1        ; WRITE -> "save board to 1-8"
        call redraw
        jmp mloop
.b0:    mov ax, K_UP
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

.save:  mov ax, K_ESC                ; ---- save prompt: 1-8 = memory, ESC = cancel
        call keyt
        jnz .sv_x
        mov si, 1
.sv_n:  mov ax, si
        call keyt
        jnz .sv_do
        inc si
        cmp si, 8
        jbe .sv_n
        jmp mloop
.sv_do: mov ax, si
        dec ax
        mov [ST_LMEM], al
        call mem_save
        mov byte [ST_PAGE], 14       ; show BOARD MEMORY with the new board
        mov byte [ST_VIEW], 0
.sv_x:  mov byte [ST_SAVE], 0
        mov ax, K_CLR
        call keyt
        call sync_dial
        call redraw
        jmp mloop

.exit:  farcall REVSEG, REV_STOP     ; leaving the OS: no engine on the patch screen
        call cur_off
        mov ax, K_CLR                ; drop queued presses so nothing reaches the patch keys
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
.v4:    call board_check
        mov byte [ST_ACT], 0
        mov byte [ST_VIEW], 0
        mov byte [ST_OACT], 0
        mov byte [ST_SAVE], 0
        mov byte [ST_FILT], 0xff
        mov byte [ST_LMEM], 0xff
        jmp compute_owners

board_check:                         ; BRD / ORDA / ORDB / OUTSEL in range (after a reset or a memory load)
        cmp byte [ORDA], NORDA-1
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
        ret

knobs_reset:                         ; every store <- its table defaults
        mov si, ped_off
        mov cx, NPED+1
        call .tab
        mov si, amp_off
        mov cx, NAMP+1
.tab:   push cx
        push si
        mov si, [cs:si]              ; entry
        mov bx, [cs:si+16]           ; knob block: n, def[n]
        mov di, [cs:si+20]           ; its store
        mov cl, [cs:bx]
        mov ch, 0
        jcxz .n
.c:     inc bx
        mov al, [cs:bx]
        mov [di], al
        inc di
        loop .c
.n:     pop si
        pop cx
        add si, 2
        loop .tab
        ret

to_split:
        farcall REVSEG, REV_STOP     ; the split screen never runs the engine
        mov ax, K_CLR
        call keyt
        mov byte [ST_STATE], 0
        mov byte [ST_SAVE], 0
        jmp redraw

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

rig_up:                              ; RIG FUNCTION up = the pedal (top row): amp side -> same layer on the pedal side,
        mov al, [ST_PAGE]            ; pedal side -> toggle pick <-> knobs. Pages: 0 P knobs, 1 A knobs, 2 pick P, 3 pick A
        mov ah, 2
        cmp al, 0
        je .s
        mov ah, 0
        cmp al, 2
        je .s
        cmp al, 1
        je .s
        mov ah, 2
.s:     jmp rig_set
rig_dn:                              ; RIG FUNCTION down = the amp (bottom row), same scheme
        mov al, [ST_PAGE]
        mov ah, 3
        cmp al, 1
        je rig_set
        mov ah, 1
        cmp al, 3
        je rig_set
        cmp al, 0
        je rig_set
        mov ah, 3
rig_set:
        mov [ST_PAGE], ah
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
        mov si, ax
        shl si, 1
        mov si, [cs:ped_off+si]
        mov di, [cs:si+20]
        ret
.a:     xor ax, ax                   ; amp counts only in RIG mode
        cmp byte [ST_STATE], 2
        jne .amp
        mov al, [ST_AMP]
.amp:   mov ah, 0
        mov si, ax
        shl si, 1
        mov si, [cs:amp_off+si]
        mov di, [cs:si+20]
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
        mov si, ax
        shl si, 1
        cmp bl, 11
        je .a
        mov si, [cs:ped_off+si]
        jmp .s
.a:     mov si, [cs:amp_off+si]
.s:     mov di, [cs:si+20]
        ret

nknobs:                              ; si = entry -> al = knob count (bx clobbered)
        mov bx, [cs:si+16]
        mov al, [cs:bx]
        ret

knob_rec:                            ; si = entry, al = knob idx -> bx = record (cs). ax, cx kept.
        push cx                      ; record: rlen, label[3], steps, disp, ntg, deps, targets
        push ax
        mov bx, [cs:si+16]
        mov cl, [cs:bx]
        mov ch, 0
        add bx, cx
        inc bx                       ; skip n + defaults
        pop ax
        push ax
        mov cl, al
        jcxz .d
.l:     mov al, [cs:bx]
        mov ah, 0
        add bx, ax
        loop .l
.d:     pop ax
        pop cx
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
        sub sp, 14                   ; -2 k, -4 steps, -6 targets left, -8 live, -10 target, -12 value, -14 ainfo
        mov [bp-8], dl
        mov cl, al
        mov ch, 0
        add di, cx
        call knob_rec
        mov cl, [di]
        cmp cl, [cs:bx+4]
        jbe .kok
        mov cl, [cs:bx+4]
        mov [di], cl
.kok:   mov ch, 0
        mov [bp-2], cx
        mov al, [cs:bx+4]
        mov ah, 0
        mov [bp-4], ax
        mov al, [cs:bx+6]
        mov [bp-6], ax
        add bx, 8
        mov [bp-10], bx
.t:     cmp word [bp-6], 0
        jne .t1
        jmp .done
.t1:    mov bx, [bp-10]
        cmp byte [cs:bx], CABT       ; cab: remember the type, mloop writes the coefficients
        jne .nc
        mov si, [bp-2]
        mov al, [cs:bx+si+1]
        mov [ST_CAB], al
        test al, al                  ; off: only a live move needs the amp's shelf back (an apply reloads it anyway)
        jnz .cabp
        cmp byte [bp-8], 0
        jne .cabp
        jmp .next
.cabp:  mov byte [ST_CABP], 1
        jmp .next
.nc:    cmp byte [cs:bx], HOTT       ; hot (2 bytes: HOTT, base steps): knob past its base range = x2 DIST stage;
        jne .nh                      ; mloop rewrites the stage instruction
        mov al, [bp-2]
        cmp al, [cs:bx+1]
        mov al, 0
        jbe .hs
        inc al
.hs:    mov [ST_HOT], al
        mov byte [ST_HOTP], 1
        mov ax, 2
        jmp .adv
.nh:    cmp byte [cs:bx], REVT       ; reverse (2 bytes: REVT, which): position -> ST_RV[which], mloop sets up
        jne .nr
        mov al, [cs:bx+1]
        mov ah, 0
        mov si, ax
        mov al, [bp-2]
        mov [si+ST_RV], al
        mov byte [ST_REVP], 1
        mov ax, 2
        jmp .adv
.nr:    mov al, [cs:bx]
        and al, 0x7f
        sub al, 0x0c
        mov ah, 3
        mul ah
        add ax, ainfo
        mov [bp-14], ax
        mov si, ax
        mov al, [ST_FILT]            ; BOARD: skip targets in blocks this pedal does not own
        cmp al, 0xff
        je .use
        mov ah, [cs:si]
        and ah, 0x0f
        cmp ah, 0x0f
        je .use
        mov bl, ah
        mov bh, 0
        cmp al, [bx+OWN]
        je .use
        jmp .next
.use:   mov bx, [bp-10]
        test byte [cs:bx], 0x80
        jz .lin
        mov si, [bp-2]               ; table: value per step, FF = leave alone
        mov al, [cs:bx+si+1]
        mov ah, 0
        cmp al, 0xff
        jne .have
        jmp .next
.lin:   test byte [cs:si], 0x10      ; v = v0 + (v10 - v0) * k / steps
        jz .lb
        mov ax, [cs:bx+3]            ; 2-byte param: word v0 / v10
        sub ax, [cs:bx+1]
        imul word [bp-2]
        idiv word [bp-4]
        mov bx, [bp-10]
        add ax, [cs:bx+1]
        jmp .have
.lb:    mov al, [cs:bx+2]
        mov ah, 0
        mov cl, [cs:bx+1]
        mov ch, 0
        sub ax, cx
        imul word [bp-2]
        idiv word [bp-4]
        mov bx, [bp-10]
        mov cl, [cs:bx+1]
        mov ch, 0
        add ax, cx
.have:  mov [bp-12], ax
        mov bx, [bp-10]
        mov si, [bp-14]
        test byte [cs:si], 0x10
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
        and bl, 0x7f
        call dt1set
.live:  cmp byte [bp-8], 0
        je .next
        mov si, [bp-14]
        mov al, [cs:si+1]            ; p
        cmp al, 0xff
        je .next
        cmp al, [EXPASG]
        je .next                     ; the expression pedal owns this param
        mov cl, [cs:si+2]            ; internal value from the buffer (the setters take internal units)
        mov ch, 0
        mov bx, cx
        test byte [cs:si], 0x20
        jz .ib
        mov cx, [bx+BUF]
        jmp .iv
.ib:    mov cl, [bx+BUF]
.iv:    call live_set
.next:  mov bx, [bp-10]              ; next target
        test byte [cs:bx], 0x80
        jz .nl
        mov ax, [bp-4]
        add ax, 2                    ; addr + steps+1 values
        jmp .adv
.nl:    mov si, [bp-14]
        mov ax, 3
        test byte [cs:si], 0x10
        jz .adv
        mov ax, 5
.adv:   add [bp-10], ax
        dec word [bp-6]
        jmp .t
.done:  mov sp, bp
        pop bp
        pop di
        pop si
        ret

live_set:                            ; al = param p, cx = internal value -> descriptor setter (firmware tick + the
        mov ah, 22                   ; reverse engine both masked around it, so neither writes the DSP mid-setter)
        mul ah
        mov bx, ax
        mov ax, [bx+PDESC+0x12]
        mov [ST_FP], ax
        mov ax, [bx+PDESC+0x14]
        mov [ST_FP+2], ax
        farcall REVSEG, REV_HOLD     ; reverse engine timer masked (only if it is running); the firmware setter writes
        mov ax, 0x40f0               ; the DSP untimed, so the engine must not fire inside it
        mov es, ax
        or byte [es:TMIC], 0x40
        push cx
        call far [ST_FP]
        add sp, 2
        mov ax, 0x40f0
        mov es, ax
        and byte [es:TMIC], 0xbf
        farcall REVSEG, REV_GO
        ret

cab_now:                             ; [ST_CAB] -> HI EQ band: the cab's low-pass coefficients, or (0) the buffer's shelf
        mov al, [ST_CAB]
        test al, al
        jnz .on
        mov bl, 0x23                 ; cab off: HI freq + gain back from the edit buffer through their own setters
        call live_addr
        mov bl, 0x24
        jmp live_addr
.on:    cmp al, 3
        ja .x
        farcall FARSEG, FAR_CAB      ; al = cab 1-3
.x:     ret

hot_now:                             ; chip 0 step 10B <- x2 DIST stage or stock (far_blob)
        farcall FARSEG, FAR_HOT
        ret

live_addr:                           ; bl = SysEx addr -> its param's live setter with the edit buffer's value
        mov bh, 0
        sub bx, 0x0c
        mov ax, bx
        add bx, bx
        add bx, ax                   ; ainfo: 3 B per address
        add bx, ainfo
        mov al, [cs:bx+1]            ; p
        cmp al, 0xff
        je .r
        mov cl, [cs:bx+2]            ; internal offset
        mov ch, 0
        test byte [cs:bx], 0x20
        mov bx, cx
        jz .b
        mov cx, [bx+BUF]
        jmp live_set
.b:     mov cl, [bx+BUF]
        mov ch, 0
        jmp live_set
.r:     ret

knobs_all:                           ; bl = which (0/1): every knob -> buffer (no live setters), in order
        push si
        push bx
        call ent_ptr
        call nknobs
        pop bx
        mov ah, 0
        mov cx, ax
        xor si, si
.l:     cmp si, cx
        jae .d
        push cx
        push bx
        mov ax, si
        mov dl, 0
        call knob_apply
        pop bx
        pop cx
        inc si
        jmp .l
.d:     pop si
        ret

set_knob:                            ; cl = knob idx, al = new k; si = entry, di = store, [ST_WH], [ST_N] set.
        mov ch, 0                    ; stores it and re-applies it live with every knob sharing a param. ZF = no change
        mov bx, di
        add bx, cx
        cmp al, [bx]
        je .same
        mov [bx], al
        mov al, cl
        call knob_rec
        mov al, [cs:bx+7]            ; deps (includes itself)
        mov [ST_DEPS], al
        xor cx, cx
.l:     cmp cl, [ST_N]
        jae .d
        mov al, [ST_DEPS]
        shr al, cl
        test al, 1
        jz .n
        push cx
        mov al, cl
        mov dl, 1
        mov bl, [ST_WH]
        call knob_apply              ; keeps si/di
        pop cx
.n:     inc cx
        jmp .l
.d:     cmp byte [ST_CAB], 0         ; a live setter may have rewritten the HI band: cab again
        je .d1
        mov byte [ST_CABP], 1
.d1:    or al, 1                     ; ZF = 0
        ret
.same:  xor al, al                   ; ZF = 1
        ret

knob_press:                          ; ax = button 1..8
        dec ax
        mov [ST_BTN], al
        mov cl, al
        and cl, 3                    ; column
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
        cmp al, 14
        jae .mem
        test cl, cl                  ; OUT page: column 1 only
        jnz .ret
        mov al, ch
        jmp out_change
.mem:   mov al, [ST_BTN]             ; BOARD MEMORY: 1-8 = load
        jmp mem_load
.ord:   cmp cl, 2                    ; ORDER page: column 1 = A, column 2 = B
        jae .ret
        mov [ST_OACT], cl
        mov al, ch
        jmp order_change
.ret:   ret
.bk:    mov byte [ST_VIEW], 1        ; board slot: show its knobs
        jmp .kp
.nb:    call page_which
        test bh, bh
        jnz .kp                      ; on a pick page: jump to that thing's knob page
        mov al, bl
        cmp byte [ST_STATE], 2
        je .rg
        mov al, 0
.rg:    mov [ST_PAGE], al
.kp:    call page_which
        mov [ST_WH], bl
        call ent_ptr                 ; si = entry, di = store
        call nknobs
        mov [ST_N], al
        test al, al
        jnz .k0
        jmp .redr                    ; no knobs on this pedal
.k0:    xor ax, ax
        call knob_rec
        cmp byte [cs:bx+5], D_MODE
        je .mode
        cmp byte [ST_N], 5
        jae .six
        mov al, [ST_BTN]             ; 4 knobs: column = knob, top row up, bottom row down
        mov cl, al
        and cl, 3
        mov ch, 1
        cmp al, 4
        jb .dir
        mov ch, -1
.dir:   cmp cl, [ST_N]
        jae .redr
        mov [ST_ACT], cl
        mov [ST_DIR], ch
        jmp .step
.six:   mov al, [ST_BTN]             ; 5-6 knobs: 1-6 pick, 7/8 = CURSOR < > (previous / next knob);
        cmp al, 6                    ; the value: dial or VALUE up/down (GROUP / BANK)
        jb .s_pk
        mov ah, [ST_ACT]
        jne .s_nx
        dec ah                       ; 7 = previous (wraps)
        jns .s_set
        mov ah, [ST_N]
        dec ah
        jmp .s_set
.s_nx:  inc ah                       ; 8 = next (wraps)
        cmp ah, [ST_N]
        jb .s_set
        mov ah, 0
.s_set: mov al, ah
.s_pk:  cmp al, [ST_N]
        jae .redr
        mov [ST_ACT], al
        jmp .redr
.step:  mov al, [ST_ACT]
        call knob_rec                ; bx = record
        mov cl, [ST_ACT]
        mov ch, 0
        push bx
        mov bx, di
        add bx, cx
        mov al, [bx]
        pop bx
        add al, [ST_DIR]
        js .lo
        cmp al, [cs:bx+4]
        jbe .st
        mov al, [cs:bx+4]
        jmp .st
.lo:    xor al, al
.st:    mov cl, [ST_ACT]
        call set_knob
        jmp .redr
.mode:  mov al, [ST_BTN]             ; mode buttons: 1-4 = mode, the lit one again = off
        cmp al, 4
        jae .redr
        inc al
        cmp al, [di]
        jne .m1
        xor al, al
.m1:    mov byte [ST_ACT], 0
        xor cl, cl
        call set_knob
.redr:  call sync_dial
        jmp redraw

dial_check:                          ; PEDAL / RIG
        call page_which
        test bh, bh
        jz .pick
        jmp dial_knob
.pick:  call dial_val
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
        mov [ST_WH], bl
        call ent_ptr
        call nknobs
        mov [ST_N], al
        cmp [ST_ACT], al
        jae .r
        call dial_val
        mov cl, [ST_ACT]
        call set_knob
        jz .r
        mov byte [ST_VIEW], 1
        jmp redraw
.r:     ret

; ---------------------------------------------------------------- board
board_dial:
        mov al, [ST_PAGE]
        cmp al, 12
        jb .k
        cmp al, 14
        jae .r                       ; BOARD MEMORY: buttons only
        mov si, OUTSEL
        ja .s
        mov si, ORDA
        cmp byte [ST_OACT], 0
        je .s
        mov si, ORDB
.s:     call dial_val
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
        cmp ah, 13
        je out_change
        ret
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

write_order:                         ; al = A preset, ah = B preset -> SysEx 0..4 (A) and 6..10 (B)
        push ax
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
        pop ax
        mov al, ah
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
        ret

order_change:                        ; al = -1 / +1 on the active chain preset (A: 4, B: 3)
        mov si, ORDA
        mov cl, NORDA
        cmp byte [ST_OACT], 0
        je cycn
        mov si, ORDB
        mov cl, 3
        jmp cycn
out_change:                          ; al = -1 / +1 on the output channel
        mov si, OUTSEL
        mov cl, 3
cycn:                                ; [si] = ([si] + al) mod cl, then rebuild the board
        add al, [si]
        cmp al, 0x80
        jb .a
        mov al, cl
        dec al
.a:     cmp al, cl
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
        mov byte [ST_CAB], 0         ; the amp slot's CAB knob may set one
        mov byte [ST_HOT], 0
        mov byte [ST_HOTP], 1
        call compute_owners
        mov byte [ST_EXPW], 0xff     ; expression pedal: unassigned until a pedal claims it
        mov bl, 0x5c
        mov al, 127
        call dt1set
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
        mov [ST_N], al
        xor cx, cx                   ; knobs in order (later ones override shared params)
.k:     cmp cl, [ST_N]
        jae .kd
        push cx
        push si
        push di
        mov al, cl
        mov dl, 0
        call knob_core
        pop di
        pop si
        pop cx
        inc cx
        jmp .k
.kd:    pop bx
.sn:    inc bx
        cmp bx, 12
        jb .s
        mov byte [ST_FILT], 0xff
        mov al, [ORDA]
        mov ah, [ORDB]
        call write_order
        mov bl, 0x63                 ; output channel = the A/B/Y box
        mov al, [OUTSEL]
        call dt1set
        call write_on
        mov si, s_board
        jmp name_snd

board_pairs:                         ; cs:si -> entry; writes the pairs in blocks owned by slot [ST_FILT]
        add si, 22
        mov cl, [cs:si]
        mov ch, 0
        inc si
        jcxz .done
.p:     push cx
        mov bl, [cs:si]
        mov al, [cs:si+1]
        add si, 2
        cmp bl, 0x0c
        jb .nx                       ; a pedal's own chain order: the ORDER page decides on the board
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
.blk:   mov dl, al
        mov al, bl
        sub al, 0x0c
        mov ah, 3
        mul ah
        mov di, ax
        mov al, [cs:di+ainfo]
        and al, 0x0f
        cmp al, 0x0f                 ; global (exp pedal) params: the first pedal in the chain that has them
        je .glob
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
.glob:  mov al, [ST_EXPW]
        cmp al, 0xff
        je .gown
        cmp al, [ST_FILT]
        jne .nx
.gown:  mov al, [ST_FILT]
        mov [ST_EXPW], al
        jmp .set

; ---------------------------------------------------------------- apply (PEDAL / RIG)
apply_cur:
        mov al, [ST_PED]
        mov ah, 0
        xor dx, dx
        cmp byte [ST_STATE], 2
        jne apply
        mov dl, [ST_AMP]
apply:                               ; ax = pedal idx, dx = amp idx
        mov byte [ST_CAB], 0         ; no cab unless the amp's CAB knob sets one (knobs_all below)
        mov byte [ST_HOT], 0         ; stock DIST stage unless a drive knob is past 10
        mov byte [ST_HOTP], 1
        push dx
        push ax
        mov bl, 0x5c                 ; expression pedal unassigned unless the pedal claims it
        mov al, 127
        call dt1set
        xor ax, ax                   ; default chain WAH>DIRT / stock B; a pedal may bring its own (Funeral)
        call write_order
        pop ax
        pop dx
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

apply_entry:                         ; cs:si -> entry (name16, kptr, extras, kstore, count, count x (sysex addr, value))
        add si, 22
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
        cmp al, 14
        jae .none
        mov si, OUTSEL
        ja .set3
        mov si, ORDA
        mov cx, NORDA-1
        cmp byte [ST_OACT], 0
        je .set4
        mov si, ORDB
.set3:  mov cx, 2
.set4:  mov al, [si]
        mov ah, 0
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
        mov cl, [cs:bx+4]
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
dial_set:                            ; ax = value, cx = max, dl = wrap (far_blob: smooth-encoder scaling)
        farcall FARSEG, FAR_DIALSET
        ret

dial_val:                            ; -> ax = dial position
        farcall FARSEG, FAR_DIALVAL
        ret

; ---------------------------------------------------------------- screens
redraw:
        call cur_off                 ; only the 6-knob screen shows the underline cursor
        cmp byte [ST_SAVE], 0
        je .r0
        jmp draw_saveq
.r0:    mov al, [ST_STATE]
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
        jb .slot
        je draw_order
        cmp al, 13
        je draw_out
        jmp draw_mem
.slot:
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
        add ah, NORDA
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

draw_knobs:                          ; bl = which. 1-4 knobs: labels + values; 5-6: names over numbers; modes
        mov [ST_WH], bl
        call ent_ptr
        mov [ST_SPTR], di
        call nknobs
        mov [ST_N], al
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
        jmp puts
.has:   xor ax, ax
        call knob_rec
        cmp byte [cs:bx+5], D_MODE
        jne .nm
        jmp draw_modes
.nm:    cmp byte [ST_N], 5
        jb draw_four
        jmp draw_six

draw_four:                           ; row 1 labels (+'*' on the dial's knob), row 2 values
        xor ax, ax
        mov cx, 1
        call cursor
        xor di, di                   ; di = knob idx (survives far calls)
.l1:    mov ax, di
        cmp al, [ST_N]
        jae .b1
        call knob_rec
        mov al, [cs:bx+1]
        call putc
        mov al, [cs:bx+2]
        call putc
        mov al, [cs:bx+3]
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
.l2:    mov ax, di
        cmp al, [ST_N]
        jae .b2
        call knob_rec
        mov ah, [cs:bx+5]            ; disp
        mov dl, [cs:bx+4]            ; steps
        mov bx, [ST_SPTR]
        mov al, [bx+di]              ; k
        call put_val
        mov al, ' '
        call putc
        jmp .n2
.b2:    call put4sp
.n2:    inc di
        cmp di, 4
        jb .l2
        ret

draw_six:                            ; 5-6 knobs: 2-char names over 2-digit values, underline cursor on the active one
        xor ax, ax
        mov cx, 1
        call cursor
        call put16sp
        xor ax, ax
        mov cx, 2
        call cursor
        call put16sp
        mov word [ST_FP], six_col    ; column table: 6 knobs (LO HM LM H  G  L) or 5 (evenly spaced)
        cmp byte [ST_N], 6
        je .t6
        mov word [ST_FP], six_col5
.t6:    xor di, di
.l:     mov ax, di
        cmp al, [ST_N]
        jae .cur
        mov bx, [ST_FP]
        mov al, [cs:bx+di]
        mov ah, 0
        mov cx, 1
        call cursor
        mov ax, di
        call knob_rec
        mov al, [cs:bx+1]
        call putc
        mov al, [cs:bx+2]
        call putc
        mov bx, [ST_FP]
        mov al, [cs:bx+di]
        mov ah, 0
        mov cx, 2
        call cursor
        mov ax, di
        call knob_rec                ; cab knob: 2-char name instead of the number
        cmp byte [cs:bx+5], D_BPM    ; reverse BPM: 3 digits (the column after knob 0 is free)
        jne .nbp
        mov bx, [ST_SPTR]
        mov al, [bx+di]
        mov ah, 0
        add ax, 40
        call put3
        jmp .nx
.nbp:   cmp byte [cs:bx+5], D_NOTE   ; reverse note value: 2-char name
        jne .ncb
        mov bx, [ST_SPTR]
        mov al, [bx+di]
        mov ah, 0
        add ax, ax
        mov bx, ax
        mov al, ' '                  ; one column right (the free one): the BPM's 3rd digit sits before it
        call putc
        mov al, [cs:bx+s_note]
        call putc
        mov al, [cs:bx+s_note+1]
        jmp .d2
.ncb:   cmp byte [cs:bx+5], D_CAB
        jne .num
        mov bx, [ST_SPTR]
        mov al, [bx+di]
        mov ah, 0
        add ax, ax
        mov bx, ax
        mov al, [cs:bx+s_cab2]
        call putc
        mov al, [cs:bx+s_cab2+1]
        jmp .d2
.num:   mov bx, [ST_SPTR]
        mov al, [bx+di]
        cmp al, 10
        jb .d1
        sub al, 10 - '0'             ; 10, 11, 12 (DIST hot)
        push ax
        mov al, '1'
        call putc
        pop ax
        jmp .d2
.d1:    push ax
        mov al, ' '
        call putc
        pop ax
        add al, '0'
.d2:    call putc
.nx:    inc di
        jmp .l
.cur:   mov bl, [ST_ACT]
        cmp bl, [ST_N]
        jb .c1
        mov bl, 0
.c1:    mov bh, 0
        add bx, [ST_FP]
        mov al, [cs:bx]
        inc al                       ; under the value's last digit
        mov ah, 0
        mov cx, 2
        call cursor
        mov ax, 1
        jmp lcd_ucur
six_col: db 0, 3, 6, 8, 11, 14       ; LO HM LM H  G  L
six_col5: db 0, 3, 6, 9, 12          ; VL GT CP DR SB

put3:                                ; ax = 0-255 -> 3 chars, leading blank
        mov cl, 100
        div cl                       ; al = hundreds, ah = rest
        mov ch, ah
        add al, '0'
        cmp al, '0'
        jne .h
        mov al, ' '
.h:     call putc
        mov al, ch
        mov ah, 0
        mov cl, 10
        div cl
        add ax, '00'
        call putc
        mov al, ah
        jmp putc

draw_modes:                          ; mode buttons: row 1 name, row 2 " 1   2  [3]  4  "
        xor ax, ax
        mov cx, 1
        call cursor
        mov cx, 16
        call puts
        xor ax, ax
        mov cx, 2
        call cursor
        mov bx, [ST_SPTR]
        mov dl, [bx]                 ; lit mode (0 = off)
        mov dh, 1
.l:     mov al, ' '
        cmp dh, dl
        jne .a
        mov al, '['
.a:     call putc
        mov al, dh
        add al, '0'
        call putc
        mov al, ' '
        cmp dh, dl
        jne .b
        mov al, ']'
.b:     call putc
        mov al, ' '
        call putc
        inc dh
        cmp dh, 4
        jbe .l
        ret

draw_mem:                            ; BOARD MEMORY: " 1 2 - 4..." ('-' empty, '>' = loaded/saved last)
        xor ax, ax
        mov cx, 1
        call cursor
        mov si, s_slots + 14*16
        mov cx, 16
        call puts
        xor ax, ax
        mov cx, 2
        call cursor
        xor dx, dx
        mov bx, BMEM
.m:     mov al, ' '
        cmp dl, [ST_LMEM]
        jne .a
        mov al, '>'
.a:     call putc
        mov al, '-'
        cmp byte [bx], KMAGIC
        jne .b
        mov al, dl
        add al, '1'
.b:     call putc
        add bx, BMSZ
        inc dl
        cmp dl, 8
        jb .m
        ret

draw_saveq:
        xor ax, ax
        mov cx, 1
        call cursor
        mov si, s_saveq
        mov cx, 16
        call puts
        xor ax, ax
        mov cx, 2
        call cursor
        mov cx, 16
        jmp puts                     ; puts left si at the second line

put16sp:
        call put4sp
        call put4sp
        call put4sp
put4sp:
        mov al, ' '
        call putc
        call putc
        call putc
        jmp putc

put_val:                             ; al = k, ah = disp, dl = steps -> 3 chars
        cmp ah, D_CAB
        jne .ncab
        mov ah, 3
        mul ah
        mov bx, ax
        mov al, [cs:bx+s_cab3]
        call putc
        mov al, [cs:bx+s_cab3+1]
        call putc
        mov al, [cs:bx+s_cab3+2]
        jmp putc
.ncab:  cmp ah, 3
        jb .nsw
        sub ah, 3                    ; 3 = OFF/ON, 4 = LO/HI
        shl ah, 1
        test al, al
        jz .s0
        inc ah
.s0:    mov al, ah
        mov ah, 3
        mul ah
        mov bx, ax
        mov al, [cs:bx+s_sw]
        call putc
        mov al, [cs:bx+s_sw+1]
        call putc
        mov al, [cs:bx+s_sw+2]
        jmp putc
.nsw:   cmp ah, 1
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
.h:     cmp al, 20                   ; 0-10 in halves; past 10 (DIST hot): 21-24 = 10+ 11 11+ 12
        jb .n
        sub al, 20
        mov ah, ' '
        shr al, 1
        jnc .h1
        mov ah, '+'
.h1:    add al, '0'
        push ax
        mov al, '1'
        call putc
        pop ax
        call putc
        mov al, ah
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

; ---------------------------------------------------------------- board memories
mem_save:                            ; al = memory 0-7 <- board + its pedals' knob positions
        mov ah, BMSZ
        mul ah
        add ax, BMEM
        mov [ST_MPTR], ax
        mov di, ax
        mov byte [di], KMAGIC
        xor bx, bx
.b:     mov al, [bx+BRD]             ; BRD[12], ORDA, ORDB, OUTSEL are contiguous
        mov [bx+di+1], al
        inc bx
        cmp bx, 15
        jb .b
        xor bx, bx
.s:     call mem_knobs
        jcxz .n
.c:     mov al, [si]
        mov [di], al
        inc si
        inc di
        loop .c
.n:     inc bx
        cmp bx, 12
        jb .s
        ret

mem_load:                            ; al = memory 0-7 -> board (empty memory: nothing)
        mov ah, BMSZ
        mul ah
        add ax, BMEM
        mov [ST_MPTR], ax
        mov si, ax
        cmp byte [si], KMAGIC
        jne .r
        mov al, [ST_BTN]
        mov [ST_LMEM], al
        xor bx, bx
.b:     mov al, [bx+si+1]
        mov [bx+BRD], al
        inc bx
        cmp bx, 15
        jb .b
        call board_check
        xor bx, bx
.s:     call mem_knobs
        xchg si, di                  ; memory -> store
        jcxz .n
.c:     mov al, [si]
        mov [di], al
        inc si
        inc di
        loop .c
.n:     inc bx
        cmp bx, 12
        jb .s
        mov byte [ST_ACT], 0
        call board_apply
        call sync_dial
.r:     jmp redraw

mem_knobs:                           ; bx = slot -> si = its pedal's knob store, di = its copy in [ST_MPTR], cx = count
        push bx
        mov al, [bx+BRD]
        call ent_slot                ; si = entry, di = store
        push di
        call nknobs
        mov ah, 0
        mov cx, ax
        pop si
        pop bx
        mov al, bl
        mov ah, 6
        mul ah
        add ax, [ST_MPTR]
        add ax, 16
        mov di, ax
        ret

; ---------------------------------------------------------------- helpers
cur_off:                             ; LCD underline cursor off
        mov ax, 2
lcd_ucur:                            ; ax = 1 on / 2 off (E93C:01CA)
        push ax
        farcall E93C_SEG, UCUR
        add sp, 2
        ret

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
s_saveq:  db "SAVE BOARD TO   ", "1-8   ESC=CANCEL"
s_sw:     db "OFFON LO HI "
s_cab3:   db "OFF4X 2X 1X "
s_cab2:   db "--4X2X1X"
s_ordn:   db "WAH>DIRT     ", "DIRT>WAH     ", "PHASE>DIRT   ", "DIRT>WAH>COMP", "STOCK        ", "TREM LAST    "
          db "REV>DELAY    "
s_outn:   db "AMP 1  (CH1)    ", "AMP 2  (CH2)    ", "BOTH  (A/B/Y)   "
orda_t:   db 0, 2, 1, 3, 4,  0, 1, 2, 3, 4,  0, 2, 3, 1, 4      ; COMP WAH DIRT PHAS EQ | stock | COMP WAH PHAS DIRT EQ
          db 1, 2, 0, 3, 4                                     ; DIRT WAH COMP PHAS EQ (Funeral path: comp = loud amp)
ordb_t:   db 6, 7, 8, 9, 10,  6, 7, 9, 10, 8,  6, 7, 8, 10, 9   ; stock | trem after reverb | reverb before delay
%include "pedal_data.inc"
