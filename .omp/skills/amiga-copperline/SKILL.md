---
name: amiga-copperline
description: Run, drive, debug and regression-test Amiga games with the Copperline emulator (headless, deterministic, JSON-RPC control) via gamebench/tools/clharness.py. Covers install, machine configs, one-shot scheduled-input runs, CCP sessions (run-to-time, memory, breakpoints, screenshots, region digests, save states, input), the HD-image test flow, and the traps found so far. Use for any emulator test, measurement, UI navigation or reverse-engineering run of a game under gamebench/games/. Replaces the FS-UAE harness.
---

# Amiga games: Copperline

Copperline (https://copperline.dev, GPL-3, Rust, v1.1.0) is a cycle-driven Amiga emulator. Everything here uses it through `tools/clharness.py`.

## Why it replaced FS-UAE (all verified here)
- **Headless needs no display server.** `--screenshot-after` runs open no window and run unthrottled: 30 emulated s of A1200 Workbench boot = ~6 s wall.
- **Deterministic.** Same config + same inputs = same frames, memory and timings. Seed the clock (`Machine.rtc_time`, on by default). So delays in a navigation script are exact, not guesses, and a frame hash is a valid regression oracle.
- **Time is emulated.** Input is scheduled on emulated timestamps; the machine advances only while a `run_*` call is in progress. There are **no pause artefacts** (FS-UAE paused on every debugger call and blacked the screen).
- **Real debugger over a protocol.** Memory read/write, registers, PC/watch/MMIO/exception/`loadseg` breakpoints, run to time/frame/PC, reverse stepping, save states, per-region frame hashes, `segments.list` (the loaded hunks of the running program).
- Also in the docs (not yet used here): `copperline-ctl diverge` (A/B lockstep finder), `profile.start` + lcov coverage, `copperline-ctl --mcp` (MCP server for agents), `--run PROG` (boot a host executable), `COPPERLINE_DBG_*` env tracing, VCD waveforms, `disk.fault.*` fault injection.

## Install
`tools/fetch_copperline.sh` downloads the release, verifies SHA256, extracts the AppImage (no FUSE) into `tools/bin/` (git-ignored): `tools/bin/copperline`, `tools/bin/copperline-ctl`. `COPPERLINE_BIN` overrides. Vulkan is **not** needed for headless runs.

## The three layers in `tools/clharness.py`
```python
from clharness import Machine, Schedule, capture, Session
m = Machine(model="A1200", ide="dist/Amiga_enhanced_games_<date>.hdf")   # A1200, KS 3.1 ROM from os/Kickstart, 8 MB fast
```
- `Machine`: renders the TOML (`.toml()`). Fields: `model` (A1200/A600/A500/A500Plus; ROM picked from `os/Kickstart/`), `fast`, `chip`, `cpu`, `cpu_clock`, `floppies` (df0..), `ide` (RDB/bare HDF, VHD, gz HDF or a **host directory**), `filesys` (live host-folder volumes, optional `bootpri`), `rtc_time`, `extra` raw TOML. Write the config to a file to reproduce a run.
- `capture(m, Schedule()...)`: one-shot headless run with scheduled input (`press/hold/type/click/double_click/mouse/mouse_to/joy`), `shot(t, png)` and `expect(t, png, tol)` (golden compare, exit status 3). Returns `RunResult(returncode, log, wall)`. The run must contain a capture flag or it never ends.
- `Session(m)`: CCP session on a headless server that **starts paused at power-on**. `with Session(m) as s:`.
  - time: `run_to(sec)` (absolute), `run_for(dt)`, `run_frames(n)`, `run_to_pc`, `now()`, `frame()`.
  - memory: `read(addr,n)`, `read_w/l`, `write`, `write_w`, `find(pattern, lo, hi)`, `regs()`.
  - control: `break_pc`, `watch`, `mmio`, `unbreak()`; raw `s.call("method", **params)` for anything in the CCP list (`catch`, `loadseg` via `break.add kind=...`).
  - capture: `shot(path)`, `digest()`, `region_digest(x,y,w,h)`, `wait_region(region, want_digest)` (the navigation sync primitive), `save_state/load_state`.
  - input: `mouse(dx,dy,left=..)`, `click(hold=)`, `double_click()`, `mouse_to(x,y)`, `key(rawkey)`, `type(text)`, `joy(...)`.

## Facts and traps (observed in this repo unless marked "docs")
- **Coordinates.** `Session.shot()` / `capture.digest` use the unframed field (716x285 on a PAL A1200 desktop; hires px wide, scan lines tall). The CLI `--screenshot-after` PNG is aspect-corrected (716x540) and `--mouse-to-after` uses *its* pixels. Never mix them. Midwinter's 320x200 screen sits at field x = 62+2*gx, y = 16+gy.
- `input.mouse_to` steers the **sprite-0 pointer** (Workbench pointer): works for Workbench. A game with its own cursor logic (Midwinter: deadzone, eased, 0.5 px/count) will not converge; steer closed-loop on the game's own cursor words with `input.mouse` counts instead (`mw2cl.MW2.goto`).
- Double-click on Workbench: `click` twice with `hold=0.08`, gap 0.12 emulated s (`Session.double_click`). Exact in emulated time.
- `state.load` needs the machine **paused** and does not roll back hard-disk or host-folder writes. Save states are git-ignored (`*.clstate` is local); rebuild them, do not commit.
- `segments.list` returns the hunks of the program the scheduled process runs (works after `state.load` too). `break.add {kind:"loadseg", name:"mwII"}` stops at LoadSeg *before the first instruction*: the right moment to check a loaded image against the file (relocate with real bases, diff; `tools/test_hd_image.py` does this).
- `break.add {kind:"catch", vector:11}` fires at 0.28 s in Kickstart's own CPU/FPU probe. Arm exception catches after ~1 s of emulated time.
- Sprite registers (`SPR0POS`) read back 0: the sprite DMA does not write them. Find a pointer from game RAM, or use `input.mouse_to` for the Workbench pointer.
- `mem.read` returns `{"data": hex}`; `status` has `seconds`, `frame`, `pc`; `capture.digest` returns a dict (`digest` is the hash).
- The game reads `$BFEC01` in its own handler: an injected key arrives (verified with an MMIO watch). If a key "does nothing", the game state is wrong, not the injection.
- Cursor/`hold`: Midwinter's front end ignores quick clicks; hold the left button ~1 s emulated.
- Boot/cycle cost: unpaced; a full autorun boot + front end + cockpit is a few minutes wall. Use a save state for repeated experiments.
- `run_until {"stable_frames": N}` fires on **any** static screen, including a loading screen or a still Workbench drawer (it fired at 38 s on the drawer while the game was still loading). Wait for a *specific* region hash instead (`wait_region`).
- Amiga raw key codes for `input.key` (standard map; only space `0x40` was exercised here): keypad 4 / 6 `0x2D` / `0x2F`, return `0x44`, esc `0x45`. A joystick on port 2 (`s.joy(port=2, left=True)`) is what Midwinter's J mode reads (verified: turn value -200/+200 per tick).
- Finding a game's own variables without symbols: snapshot its data hunks at 3-4 input states (e.g. cursor moved 8 counts per step), keep words that change by a constant step. Offsets inside a hunk are stable per build (Midwinter cursor: data hunk +0x308E/+0x3090); bases move, so re-read `segments.list` each session. (`mw2cl.py` has the working example.)
- `capture.screenshot` has an `overlays: ["sources"]` mode that tints pixels by origin (playfield/sprite N); the reply gives a legend of ids, not colours, so it is not a ready-made pointer finder.
- Reading registers: `regs()["d"]`/`["a"]` are lists of 8 ints; `pc`, `sr` are plain.
- (from the docs, not exercised here) `[ide] slave` only works with Kickstart 3.1.4+. Boot partition priority is in the RDB; `bootpri` applies to bare HDFs and host folders only.
- HOSTFS (`filesys`) volumes boot Workbench (`bootpri=6`) and are handy for experiments, but they are not the shipped path; test the real RDB image.
- Pick one mode per run: a `--control` session (`Session`) owns the run loop and cannot be combined with `--screenshot-after`/`--expect-screenshot`/scheduled input flags (use `capture.screenshot`, `input.*`, `state.*` instead); the one-shot `capture()` cannot be driven interactively. (docs, consistent with how both layers behave here)
- (docs) Never use `[cpu] jit` / `--jit` for gates or timing: it is not cycle-exact or reproducible, and any debug hook drops it back to the precise loop. For a "fast A1200" use `Machine(cpu="68030", cpu_clock=...)` (the clock is rounded to a whole multiple of the colour clock; fast RAM runs at the CPU clock, chip RAM stays chip-bus bound). Not exercised yet here.

## Test suite and launchers
- `python3 -m pytest tests -m "not emu"` (static, seconds); `python3 -m pytest tests` (everything, ~5 min). The `cockpit(game)` fixture boots a scratch copy once, saves a state, and each test restores it into a fresh emulator: results are exact and tests independent. `--bless` rewrites `tests/goldens.json` (frame hashes only).
- `tools/test_hd_image.py IMG GAME` mirrors the ST bench: scratch copy + autorun, game harness to the in-game view, one `RESULT` line, non-zero exit on failure.
- `dist/run_hd.sh [GAME]`, `dist/run_mw2.sh`, `dist/run_mw2_floppy.sh` call `tools/clrun.py`. `clrun.py ... --shot SECS out.png` runs the same configuration headless: use it to check a launcher without a display. The windowed path itself (Vulkan window) is unverified here: only `--print-config` and the headless run were exercised.

## Hard-disk images: MaxTransfer is not optional
RDB partitions must set `MaxTransfer` to 0x1FE00 (`rdbtool add ... max_transfer=0x1fe00`). With amitools' default (0xFFFFFF) the A1200 IDE path returned wrong data for every read beyond the first 128 KiB of a transfer: `mwII`'s 218 KB code hunk was corrupt after LoadSeg and the game died with Gurus whose code changed with memory layout (`80000003`, `8000000B`, `80000004`). `tools/make_amiga_hd.py` sets it; `tools/test_hd_image.py` proves it (hunk diff = 0).

## Workflow for a new game or patch
1. Put the game on its own partition (`tools/make_amiga_hd.py`: add a `Part` + a `Play` script/icon) and boot the real image: `tools/test_hd_image.py IMG GAME` prints one `RESULT` line.
2. Write `games/<g>/tools/<g>cl.py` (a `Session` subclass): `boot()` waiting on a region digest, `to_<view>()`, cursor/input helpers. Verify every step with a screenshot once, then rely on determinism.
3. For a patch: locate it in RAM by skeleton (read the code hunk via `segments.list`, search), poke state, assert tick-exact results; compare against the unpatched volume (`mw2orig`).
4. Record numbers with the machine, scene and method named (`now()`/`frame()` are emulated; wall time is irrelevant).

## Docs worth reading before using a feature
Config https://copperline.dev/docs/configuration , headless https://copperline.dev/docs/headless , CCP https://copperline.dev/docs/control , console commands https://copperline.dev/docs/console , `COPPERLINE_DBG_*` https://copperline.dev/docs/headless-1 , reverse https://copperline.dev/docs/reverse , diverge https://copperline.dev/docs/diverge , profiling https://copperline.dev/docs/profiling , `--run` https://copperline.dev/docs/run , timing model https://copperline.dev/docs/timing .
