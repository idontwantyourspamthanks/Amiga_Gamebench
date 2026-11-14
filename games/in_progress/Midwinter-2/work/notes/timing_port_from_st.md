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
