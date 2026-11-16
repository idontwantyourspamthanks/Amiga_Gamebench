# What the ST did about speed, and what that means for the Amiga

Read from `AtariST/gamebench/games/done/midwinter2` (patches `tick_vbl.s`,
`p3cp_head.s`; notes `frameloop.md`, `simtiming.md`).

## The ST problem: the sim advances once per PRESENTED FRAME

`frameloop.md` §2 and `simtiming.md` §2 say it plainly: the in-play frame loop
(`$31486`, never returns) runs sim -> view setup -> render -> flip once per
iteration, and "nothing in the chain reads a VBL counter: every increment is a
fixed per-frame step". Game speed therefore equalled the achieved frame rate.
On a 16 MHz Mega STE the frame rate rose and the game ran ~2.3x too fast; that is
the bug P3 fixed.

So the ST was **not** VBL-locked - it was **frame-locked**, which is
CPU-speed-dependent because fps is CPU-bound. (A VBL-locked game would have been
safe on a fast machine.)

## The ST fix, in two parts

1. `tick_vbl` (site `$262d0`, blob `$b3700`): the VBL handler's two counters are
   routed through a blob that also maintains a free-running **real-time clock**
   in 1/300 s units at `$B3400`, adding 6 units on a 50 Hz frame and 5 on 60 Hz
   (read from shifter sync mode `$ff820a` bit 1). Never cleared.
2. `p3cp_head` (site `$31486`): replaces the frame loop. Per group of five 40 ms
   passes (`GRP` 60 clock units = 5 Hz, `SUBT` 12 = 40 ms):
   - **PH 1** runs the original tick completely unmodified (pre-calls, player
     sim, post-calls, render at the original pose, flip), so the world state at
     PH 1 is the unpatched game's by construction;
   - **PH 2-5** render extra frames at a predicted pose and run no game logic;
   - the live state is restored to the end-of-tick values before the next PH 1.
   - A due-time grid on the real-time clock decides when the next PH 1 runs, so
     the world tick stays at 5 Hz however fast the machine renders.

Net effect: game speed independent of CPU, and the extra headroom is spent on
smoother rendering (4 extra frames per tick) instead of on faster gameplay.

## The corresponding Amiga question

The Amiga build may be frame-locked in the same way. The discriminator is
**logic ticks per presented frame**, not frames per second:

- ticks/frame ~ 1 (or ticks/s ~ fps) -> frame-locked, the ST fix is required;
- ticks/frame constant and > 1 (e.g. ~5 Hz against 41 fps -> ~8 frames/tick), and
  the same on A500 and A1200 -> already real-time locked, nothing to port.

Measured cockpit baseline (A1200, `warp=0`): 41 presented fps. Tool: breakpoint
the X consumer entry (`locate()['consumer']`, every logic tick passes through
the sim chain `0x5b790 -> 0x5b7a6 -> 0x5be34`) and count `frame_stats` deltas
between hits; `frames/hit` is the answer. Compare with the same run on A500.

If the fix is needed, the Amiga port is the same shape: a real-time clock from
the level-3 VBL handler (the handler at live `0x4AFB0` already bumps `$4076` /
`$476C`, and its `jsr $17382` is a free slot to route through a blob), plus a
gate on the frame loop's sim call so the world steps at the original rate while
rendering keeps running.

## First probes on the Amiga (2026-11-14)

- An idle cockpit at `warp=0` produced **no consumer hits in 3 s**: the world step
  in that state is input-gated (the game sits in the `acquire_mouse` loop). Feed
  input while counting.
- A poke breaks that gate (that is why poke-based probes hit the store), but the
  poke round-trip time (~1.3 s) is not a tick period - do not read cadence from it.
- Counting method that matches the ST question: breakpoint the consumer entry,
  feed small mouse movements from a background thread, and record the
  `frame_stats` frame number at every hit. `frames/hit` is the metric:

  | frames/hit | meaning |
  |---:|---|
  | ~1 | sim runs once per presented frame -> frame-locked, ST fix needed |
  | > 1 and machine-independent | sim runs on its own clock -> nothing to port |

### Navigation must run in warp; rate ratios do not care

Every fixed `wait()` in `boot_to_cockpit` assumes warp speed. At `warp=0` the
same recipe does not reach the cockpit in the allotted time: the screenshots from
the non-warp runs show the boot/debugger overlay, not the cockpit, which is why
those sessions produced "no hits" and "0 VBL/s".

The **frames-per-tick ratio** is warp-independent (frames and ticks both scale
with emulated time), so the logic-rate test is valid in warp. Only absolute
"x per wall second" figures require `warp=0` *after* the cockpit is reached.

## Amiga static findings (live cockpit dump, addresses from that run)

The world step and its callers:

```
5b790: tst.w  $6a398        ; paused?
       bne.s  other
       bsr.w  $5b7a6        ; the world tick: movem, mulu #$3e per-type block,
                            ; bsr $5be34 -> bsr $5c640 (the X consumer)
```

Callers of `$5b790`: `$58dc8`, `$59cc6`, `$59ea8`. The first one is inside a long
sequential `jsr` block (`$58c9c` ... ) that also contains
`jsr $4bbe8` (the `acquire_mouse` wait - the reason an idle cockpit produces no
ticks: the block blocks there until the user moves the mouse) and ends with
`bra.w $58c9c` at `$58e4a`. There is **no VBL-counter comparison** guarding the
`jsr $5b790` in that block: as written, one pass of the block = one world step,
whatever the frame rate - the ST's frame-locked shape.

Two adjacent counters look like frame-timing instrumentation, not a clock:
`$6c53a` counts up by 1 per pass (capped at `$1f5` = 501, or down by 2 in the
other branch) and `$6c538` is set when it reaches `$64` = 100 (`sub_05b734`).

Where a port would attach, if the measurement confirms frame-locking:

| piece | Amiga site |
|---|---|
| real-time clock | VBL handler at `$4afb0`; its `jsr $17382` (at `$4afd0`) is a free 6-byte slot for a blob call, and `$4076`/`$476c` are the counters it bumps (operands move per load phase - take them from the session dump) |
| gate the world step | `$58dc8` (`jsr $5b790`) - replace with a blob call that runs the original step only when the accumulated clock owes a tick, and otherwise returns |
| original rate | measure first; the ST used 5 Hz (`GRP 60` units of 1/300 s) |

That is the same two-part design as `tick_vbl` + `p3cp_head`, minus the
predict-ahead rendering (PH 2-5), which is a separate, riskier change.
