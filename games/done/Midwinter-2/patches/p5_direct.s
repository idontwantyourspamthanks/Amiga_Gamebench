; name: p5_direct
; Direct steering for Midwinter II (Amiga), the counterpart of the ST p5_ctl_vbl + p5_ctl_x.
; Assembled by tools/mw2patch.py (vasmm68k_mot, 68000 code) into a blob that is appended to
; CODE hunk 0 of MWII. Two sites jump into it:
;
;   handler  site: the in-game (mode 2) accumulate routine of the input poller
;                  (file skeleton d3b9 <ACC> 4480 d1b9 <ACCY> 4e75, 16 bytes).
;                  It is called once per VBL by the active device poller (mouse, joystick or
;                  keyboard, each gated off unless selected with M/J/K).
;   cons     site: the X-axis consumer, once per logic tick (50 bytes, `move.w <ACC>,d0` first).
;
; Accumulator ACC (long):
;   M mode   hi word = sum of mouse counts/2 since the last tick (the poller's own units),
;            lo word unused.
;   J/K mode hi word = VBLs "right held" minus VBLs "left held" since the last tick,
;            lo word = VBLs elapsed (handler calls) since the last tick.
; The consumer reads and clears ACC with interrupts masked, so nothing is lost or kept.
;   M mode   OUT = MOUSE_GAIN/256 * hi word, capped at +-MOUSE_CAP. Mouse stops -> hi word 0 ->
;            OUT 0 on the next tick. The persistent "yoke" (clamped ACC written back) is gone,
;            and the deadzone is not applied.
;   J/K mode OUT = +-YAW_PCT % of (clamp - deadzone) of the vehicle block * |net|/elapsed:
;            a constant turn rate while held, zero after release, pro rata for a tap.
;            No VBL since the last tick (elapsed 0): OUT keeps the previous value.
; The Y axis (throttle/pitch) is untouched except that its accumulate is re-emitted here.
;
; Operands marked .l are absolute and are relocated by the loader: the tool finds every one by
; assembling twice with different DB and records it as a RELOC32 entry to hunk 1 (DATA).
; The tool passes (with -D) DB and the DATA-hunk offsets it read out of the original file:
;   DB       added to every DATA-hunk offset (the tool assembles with two values to find them)
;   ACC_OFF  X accumulator            (operand of the consumer's first instruction)
;   ACCY_OFF Y accumulator            (second operand of the poller's mode-2 accumulate)
;   OUT_OFF  X rate handed to the per-type rate handler (operand of the consumer's store)
;   GATE_OFF mouse gate, nonzero = M (mouse) selected   (operand of the poller's first tst.w)
ACC     equ     DB+ACC_OFF
ACCY    equ     DB+ACCY_OFF
OUT     equ     DB+OUT_OFF
GATE    equ     DB+GATE_OFF

MOUSE_GAIN equ  768                     ; 8.8 fixed on the poller's half-count units: 1.5 per count
MOUSE_CAP  equ  1000                    ; |OUT| cap (keeps OUT*scale inside a word)
YAW_PCT    equ  50                      ; J/K yaw rate, % of the old full-yoke rate
YAW_NUM    equ  YAW_PCT*256/100

        org     0
handler:                                ; d0 = y delta (long), d1 = x delta (long); rts to the poller
        tst.w   GATE.l
        bne.s   .mouse
        addq.w  #1,ACC+2.l              ; VBLs elapsed (lo word of ACC)
        tst.l   d1
        beq.s   .y
        bmi.s   .left
        addi.l  #$10000,ACC.l           ; right held this VBL
        bra.s   .y
.left:  subi.l  #$10000,ACC.l           ; left held this VBL
        bra.s   .y
.mouse: add.l   d1,ACC.l                ; original behaviour: dx counts
.y:     neg.l   d0                      ; original Y accumulate, unchanged
        add.l   d0,ACCY.l
        rts

        cnop    0,64
cons:                                   ; a0 = vehicle block (preserved); uses d0-d2 only
        move.w  sr,d2
        ori.w   #$700,sr                ; the VBL poller adds to ACC: read+clear atomically
        move.l  ACC.l,d0
        clr.l   ACC.l
        move.w  d2,sr
        tst.w   GATE.l
        bne.s   .mouse
        ; ---- joystick / keyboard: d0 = net<<16 | elapsed
        tst.w   d0
        beq.s   .keep                   ; no VBL since the last tick: keep the previous yaw
        move.w  d0,d2                   ; d2 = elapsed
        swap    d0                      ; d0.w = net (R - L)
        move.w  d0,-(a7)                ; remember the sign
        bpl.s   .abs
        neg.w   d0
.abs:   cmp.w   d2,d0
        bls.s   .nok
        move.w  d2,d0                   ; |net| <= elapsed by construction; belt and braces
.nok:   move.w  $16(a0),d1              ; full = (clamp - deadzone) * YAW_PCT / 100
        sub.w   $12(a0),d1
        ble.s   .zero                   ; vehicle has no yaw on X (type 4)
        mulu.w  #YAW_NUM,d1
        lsr.l   #8,d1
        mulu.w  d0,d1                   ; * |net|
        divu.w  d2,d1                   ; / elapsed
        move.w  d1,d0
        tst.w   (a7)+
        bpl.s   .out
        neg.w   d0
        bra.s   .out
.zero:  addq.l  #2,a7
        moveq   #0,d0
        bra.s   .out
        ; ---- mouse: heading change = gain * dx since the last tick
.mouse: swap    d0
        ext.l   d0                      ; d0 = summed dx (half counts)
        muls.w  #MOUSE_GAIN,d0
        moveq   #0,d1
        tst.l   d0
        bpl.s   .mp
        neg.l   d0
        moveq   #1,d1
.mp:    lsr.l   #8,d0                   ; magnitude, truncated toward zero
        cmpi.l  #MOUSE_CAP,d0
        bls.s   .mc
        move.l  #MOUSE_CAP,d0
.mc:    tst.b   d1
        beq.s   .out
        neg.w   d0
.out:   move.w  d0,OUT.l
.keep:  rts
