# Timing baseline: what is measured, and what is still open (2026-11-14)

## Measurement (FS-UAE, `warp=False`, `video_sync=0`, unpatched `d1_skipintro.adf`)

Presented frames over a 10 s wall sleep, 40 s after boot (same script for both models):

| machine | frames | wall | fps | emulated time / wall |
|---|---:|---:|---:|---:|
| A1200 (KS 3.1) | 525 | 11.46 s | 45.8 | **1.03** |
| A500 (KS 1.3)  | 525 | 11.46 s | 45.8 | **1.03** |

**What this proves and what it does not.** It proves FS-UAE runs both machine
models at real time. It does **not** prove the game's logic is VBL-locked: a
CPU-bound sim also presents 50 frames/s on both models, it just advances more
world state per frame. The discriminator is **game time per emulated frame**
(the game's own VBL/frame counters, or HUD minutes between fixed numbers of
emulated frames) measured on A500 vs A1200 - still open, see below. Reproduce
the frame numbers with:

```python
h = mw.FSUAE(machine='A1200', disks=[mw.D1,mw.D2,mw.D3], images=[...], warp=False)
h.wait(40); f0=h.frame_stats(); h.resume(); time.sleep(10); f1=h.frame_stats()
```

`frame_stats` `time_us` does not track wall time in warp mode; only use it with
`warp=False`, and remember `h.resume()` before the sleep (every debugger call
pauses the emulator).

## Game clock

The VBL handler increments the game's own counters (file: `addq.w #1,$393AE`
frame counter, `addq.w #1,$39AA4` wrapped at 6 = a 1/6 s tick, plus a
`clr.w $39A9E`). Live operand addresses move per run: locate them in the
session's RAM dump (`direct_controls_howto.md` §8).

## Consequence for the port (pending the VBL-lock test)

If the counters show the world clock advancing per VBL at the same rate on
A500 and A1200, the ST fixed-rate scheduler has no Amiga counterpart and all
remaining speed work is P6 rendering. If instead the A1200 advances more world
state per VBL, the tick patch is needed. Measurement protocol (the one that
works): locate the VBL handler's counters in the session's dump, then
**`h.resume()` before every wall window** - `pr.dump`/`read` pause the
emulator, and three earlier readings of "0 VBL/s" were that artifact, not the
game. Warp mode *does* fast-forward the game (more VBLs per wall
second) — that is emulator behaviour, useful for automated tests, not evidence
about real hardware, where the vertical blank stays at 50 Hz.

Baseline rendering in the cockpit: ~25 fps presented while driving (the
`h.fps()` figure of ~23 used the unreliable warp `time_us`; treat 45.8 fps as
the real-time figure outside the cockpit, ~25 inside).
