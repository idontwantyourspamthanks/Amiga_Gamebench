# Timing baseline: the Amiga build is already VBL-locked (2026-11-14)

## Measurement (FS-UAE, `warp=False`, `video_sync=0`, unpatched `d1_skipintro.adf`)

Presented frames over a 10 s wall sleep, 40 s after boot (same script for both models):

| machine | frames | wall | fps | emulated time / wall |
|---|---:|---:|---:|---:|
| A1200 (KS 3.1) | 525 | 11.46 s | 45.8 | **1.03** |
| A500 (KS 1.3)  | 525 | 11.46 s | 45.8 | **1.03** |

Identical on both: the emulator's vertical-blank clock runs at real-time rate
regardless of CPU model, so a faster CPU buys rendering headroom, not game
speed. Reproduce with the snippet in this file's git history or:

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

## Consequence for the port

The ST project's fixed-rate scheduler (`tick_vbl`, `p3cp_head`, `p3c_sim`)
solved a CPU-bound frame loop; **that problem does not exist in this Amiga
build** and has no counterpart to port. Speed work here is only about drawing
fewer/cheaper frames (P6), which raises fps while the 50 Hz logic keeps game
speed exact. Warp mode *does* fast-forward the game (more VBLs per wall
second) — that is emulator behaviour, useful for automated tests, not evidence
about real hardware, where the vertical blank stays at 50 Hz.

Baseline rendering in the cockpit: ~25 fps presented while driving (the
`h.fps()` figure of ~23 used the unreliable warp `time_us`; treat 45.8 fps as
the real-time figure outside the cockpit, ~25 inside).
