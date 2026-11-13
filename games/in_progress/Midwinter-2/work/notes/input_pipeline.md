# MW2 Amiga: input pipeline and the steering consumer

All addresses are **flat image offsets** in the SPL `MWII`; add the load base for
runtime addresses. Evidence: `tools/m68dis.py` output, quoted inline.

## Sampler (runs once per VBL)

The VBL handler `$16EF8` calls `$17F34`; the mouse/joystick sampling is
`$1765E` (joystick channel 0, the mouse port) and `$177B0` (joystick 1).

At `$1765E`:

```
01765e: tst.w    $40e26.l          ; input enabled?
01766e: btst.b   #6,$bfe001.l      ; left mouse / fire
017678: bset.b   #1,(a0)           ; flags at $39930
01767c: btst.b   #2,$dff016.l      ; POTGOR: right mouse button
017686: bset.b   #0,(a0)
01768a: move.w   $dff00a.l,d0      ; JOY0DAT
...                                 ; split into dx/dy, 2-pixel granularity
0176b6: move.w   $39398.l,d2       ; input mode
0176bc: add.w d2,d2 / add.w d2,d2  ; mode*4
0176c0: movea.l (a0,d2.w),a0       ; dispatch table at $17652
0176c4: jsr      (a0)
```

Dispatch table (mode -> handler):
- `$17652: $17768` (mode 0)
- `$17656: $17768` (mode 1)
- `$1765A: $17758` (mode 2)

`$17EDC` sets `$39398 = 2`; `$17ED4` clears it. So mode 2 is the mouse
(relative) path and 0/1 the joystick (absolute) path. `[INFERENCE: which
physical input maps to 0 vs 1; both use the same absolute handler]`

## Accumulators

Mouse handler `$17758`:

```
017758: add.l d1,$39344.l   ; X: accumulated dx (mouse), never reset here
01775e: neg.l d0
017760: add.l d0,$39348.l   ; Y: accumulated dy (inverted)
```

Joystick handler `$17768`:

```
017768: add.l $39340.l,d0
01776e: swap d0 / clamp high word to $08..$C3
017786: move.l d0,$39340.l  ; Y absolute, centred at $64
01778c: add.l $3933C.l,d1
... clamp high word to $08..$136
0177a8: move.l d1,$3933C.l  ; X absolute, centred at $A0
```

`$154B6`/`$154BE` initialise `$3933C = $A0` and `$39340 = $64` — the joystick
centre. `$39338`/`$3933A` hold the previous values; `$383A8`/`$383A6` are
button-press flags; `$3934C` is the input-state copy.

This is the same "yoke" as the Atari ST: the mouse path accumulates without a
reset, the joystick path leaves the stick deflection in place, and the game
reads it as a persistent turn rate.

## Consumer (once per logic tick)

Called at `$27D8E` and `$27E30`, with `a0` = per-vehicle control block:

```
028588: move.w $39344.l,d0        ; X accumulator
02858e: cmp.w  $14(a0),d0         ; clamp min
028594: move.w $14(a0),d0
02859a: cmp.w  $16(a0),d0         ; clamp max
0285a4: move.w d0,$39344.l
0285aa: move.w $12(a0),d1         ; X deadzone
0285ae: bsr    $285EC             ; (|v|-deadzone)*sign
0285b2: move.w d0,$3850A.l        ; final X steering

0285BA: ... $39348 with bounds $06/$08(a0), deadzone $04(a0)
0285E4: move.w d0,$3850C.l        ; final Y steering
```

Control block fields (matches the ST block layout):

| Offset | Meaning |
|---|---|
| `$04` | Y deadzone |
| `$06` | Y clamp min |
| `$08` | Y clamp max |
| `$12` | X deadzone |
| `$14` | X clamp min |
| `$16` | X clamp max |

`$3850A`/`$3850C` are what the simulation reads.

## Direct-controls patch (design)

Replace the consumer, exactly as `p5_ctl_x` does on the ST:

- **Mouse** (`$39398 == 2`): yaw = `$39344` (dx since the previous tick)
  × gain, capped; then clear `$39344` (and `$39348`). No motion → no turn.
- **Joystick** (mode 0/1): use the sign of `($3933C - $A0)` / `($39340 - $64)`
  to pick a direction; output ±(clamp − deadzone) (or a percentage), scaled by
  held VBLs / elapsed VBLs; reset `$3933C/$39340` to the centre. Zero when the
  stick is centred.
- Keep the clamp/deadzone semantics for downstream code; only the source
  changes.

The ST constants (`MOUSE_GAIN` 1.5 in 8.8, cap 1000, `YAW_PCT` 50) are a
starting point. Tune against traces, not by feel.

## Open questions

- Which mode value the game uses for mouse vs joystick in-game, and where it
  is changed (`$39398` writes are listed above).
- Whether the game calls the consumer once per presented frame or at a fixed
  rate; measured next.
- The per-vehicle control block base and stride (find the code that builds
  `a0 = base + type*stride` before `$27D8E`).

## Runtime base and verification status (2026-11-13)

- The executable loads at **`$2D8C0`** on Kickstart 3.1 A1200. Add that base to
  every flat offset above: sampler `$44F2E`, consumer `$28588` -> `$55E48`,
  VBL `$16EF8` -> `$447B8`, flip `$24A64` -> `$522E4`, `$39344` -> `$66C04`.
  Four fixed-opcode signatures agree on the base.
- `$39398`, `$39344/$39348`, `$3933C/$39340` lie in the DATA hunk (not BSS).
  Their initial file values are 0; the sampler writes them.
- At the frozen hallway menu, `$39398` read 0 and `$39344/$3933C` read 0, while
  the VBL counter `$393AE` read 0 too. If the VBL handler were running,
  `$393AE` should increment, so either the game was waiting for a disk, or the
  address is wrong. The disk-swap chain is being tested now; until it completes,
  treat the mode-table and deadzone field mapping below as `[INFERENCE]`
  (the fixed `cmp.w $14(a0)` / `$12(a0)` structure is confirmed against the
  disassembly, but not yet exercised live).
