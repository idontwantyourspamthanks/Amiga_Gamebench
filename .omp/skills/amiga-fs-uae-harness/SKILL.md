---
name: amiga-fs-uae-harness
description: Run, drive and measure Amiga games in headless FS-UAE with gamebench/tools/amigaharness.py. Covers private Xvfb displays, screenshots, keyboard/mouse input, the UAE console debugger for memory/dumps/breakpoints, frame statistics, and the traps that silently break automation. Use for any emulator test, measurement or UI navigation of a game under gamebench/games/.
---

# Amiga games: FS-UAE harness

`tools/amigaharness.py` (class `FSUAE`) is the only way to drive FS-UAE here.
- Each instance gets its own scratch dir (`/tmp/amigrun-*`), its own Xvfb display and its own floppy overlay dir. Supplied ADFs are never written (`writable_floppy_images=0`).
- It writes the exact FS-UAE config it used to `<scratch>/test.fs-uae`; keep it when a run misbehaves.
- Always `h.close()` (or `with`): it frees the display and kills the emulator.

```python
import sys; sys.path.insert(0, 'tools')
from amigaharness import FSUAE
h = FSUAE(machine='A500', disks=[d1, d2, d3])
try:
    h.wait(20)
    h.screenshot('shot.png')
    print(h.frame_stats())
finally:
    h.close()
```

## Machines and ROMs

- `machine`: `A500`, `A500+`, `A600`, `A1200`, `A1200/020`, `A1200/1230`, `A1200/1240`, `A4000`.
  - `A1200` is a stock 68EC020 with 24-bit addressing; `A1200/020` is a full 68020; `A1200/1230` is a Blizzard 1230-IV with 8 MB fast RAM by default.
- ROM lookup: explicit `rom=`, else `<gamebench>/kickstarts/` then `<gamebench>/os/Kickstart/`, by machine.
- Present: 1.3 (A500), 2.05 (A600), 3.1 rev 40.68 (A1200, **the target**) and 3.1 rev 40.63 (A600). `python3 tools/amigaharness.py roms` prints what is present and what is missing.
- **Missing Kickstart = AROS.** FS-UAE ships `aros-amiga-m68k-rom.bin`; it boots, but it is not Kickstart. `FSUAE.using_aros` is True and such runs must not be used as compatibility or performance evidence. The A1200 target uses the 3.1 rev 40.68 ROM; an A500 run on 1.3 is the fallback regression loop, not proof of A1200 behaviour.
- Add `extra=['fast_memory=64']`, `chip_kb=`, `fast_mb=` to override.
- `warp=True` runs the emulator as fast as possible; screenshots are fine, but timing is meaningless.

## Display and input

- FS-UAE's own screenshot (PrintScrn / F12+S) reads the OpenGL frame buffer and returns a **white image under Xvfb**. Use `h.screenshot()`, which runs `import -window <id>`; it captures the real window.
- The harness starts FS-UAE with `automatic_input_grab=0`/`initial_input_grab=0`, so input only goes to the game after `h.grab_mouse()` (a click) or a key. Keys: `h.key('Return', 'space', 'F1')` (X keysym names). Mouse: `h.mouse_to(x, y)`, `h.mouse_rel(dx, dy)`, `h.mouse_click()`.
- No window manager runs under Xvfb, so `xdotool windowactivate` fails. Use `xdotool key --window <id>` (the harness does); do not depend on focus.
- The window is 720x568 by default and the Amiga picture is inside it. `h.screenshot()` captures that whole window.

## Frame statistics

`h.frame_stats()` parses the debugger's `c` output:

```
Average frame time: 22081.62 ms [frames: 191 time: 4217590]
```

`time` is in microseconds (191 frames / 4.217590 s = 45.3 fps). It is cumulative since reset, so measure a delta:
1. `h.resume()` and sleep for an emulated interval (the emulator runs in real time when `cpu_speed=real`, which is the default for all models except accelerated ones);
2. take another sample; `fps = delta_frames / (delta_time_us / 1e6)`.
Entering the debugger stops the emulator, so the delta measures emulated time, not wall time. This is the primary FPS measurement; there is **no cycle profiler** in FS-UAE.

For a CPU-time profile, instrument the emulator or the game (counters read via `read_mem`/`save_mem`), or use `H <n>` PC history for short bursts. Don't claim a profile from `frame_stats()` alone.

## The console debugger

`console_debugger=1` is set by default. `h.debugger(...)` sends `F12+D` once, then writes commands to FS-UAE's stdin. It works only because FS-UAE is started with piped stdin/stdout (the upstream docs say "run it from a terminal").

| Command | Use |
|---|---|
| `r` | CPU registers |
| `m <addr> [<lines>]` | memory dump, 16 bytes/line (RAM only) |
| `d <addr> [<lines>]` | disassembly |
| `f <addr>` / `fl` / `fd` | add / list / remove breakpoints |
| `g` | resume |
| `S <file> <addr> <n>` | save Amiga memory to a host file (**no spaces in path**) |
| `W <addr> <words...>` / `W <addr> 'string'` | write memory |
| `s "str"` / `s <values>` | search memory |
| `c` | CIA/disk/custom registers + frame stats |
| `e` | all custom registers with names |
| `dm` | address-space map (find free RAM) |
| `T`, `Tl`, `Td` | tasks, libraries, devices |
| `H <n>` | last n PCs |
| `?` | full help |

Traps:
- **`m` cannot read the custom chip range.** `m dff000` prints `**** Custom chipset ****` and no data; use `e` (all registers) or `c`.
- **`S` and `W` paths/values are whitespace-separated**: put dumps in the scratch dir, no spaces.
- **The debugger stops emulation.** Any `read_mem`/`save_mem`/`registers` freezes the game; call `h.resume()` (`g`) afterwards if you need it to keep running.
- **`g` at a breakpoint resumes the game**, which can immediately hit the same breakpoint again.

## Snapshots and determinism

FS-UAE save states exist (`save_states=1`, `F12` menu) but are not exposed by the harness yet. Restoring a state restores unpatched RAM, so patches applied at boot need a cold boot. Prefer cold boots from the disk images; they are reproducible when the same ROM and machine options are used.

## Concurrency

Keep to 2-3 emulator instances at once. Each costs a core; a machine under load misses input clicks and alters wall-clock-based measurements. Measure FPS with the debugger frame counters (emulated time), not host stopwatches.

## Disk swapping (verified)

FS-UAE has no CLI/remote disk swap in this build; drive the on-screen menu:
- **F12 opens/closes** the menu; **Escape also closes** it. Focus starts on
  PAUSE each time the menu opens.
- From PAUSE, **Down x7** reaches the `df0` media item (with one drive and the
  default input rows). Enter opens `INSERT INTO DF0`, whose list is
  `EJECT, d1, d2, d3, ...`, current image highlighted. Enter inserts; the menu
  closes.
- The layout shifts with the number of input rows, so `amigaharness.swap_floppy`
  locates the `REMOVABLE MEDIA` section by the menu's blue selection bars
  (x=540): the last blue section bar is the header, and the first item below it
  is `df0`. Do not hard-code y coordinates.
- A window manager (twm) is required for FS-UAE to take focus and grab input
  under Xvfb; the harness starts one if `GAMEBENCH_WM` is set or `twm` is in
  `PATH`.
- `writable_floppy_images=0` keeps the supplied ADFs read-only (writes go to
  overlays); the game's disk prompts still work.
