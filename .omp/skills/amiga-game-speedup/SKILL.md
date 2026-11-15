---
name: amiga-game-speedup
description: Method for speeding up and modernising a closed-source Amiga game by patching its executable, learned on the Atari ST Midwinter work and applied to Amiga Midwinter II on a fast A1200. Covers phase plan, deterministic Copperline measurements and gates, fixed-timestep decoupling, direct controls, rendering gains, hard-disk and floppy delivery, 68020/AGA/Kickstart traps. Use when starting or planning work on a game in gamebench/games/.
---

# Speeding up an Amiga game (method)

Reference for the behaviour and the gates: `AtariST/gamebench/games/done/midwinter2` (Atari ST). This skill records what carries over and what is genuinely Amiga-specific. The Amiga work is at `games/in_progress/Midwinter-2`. Tooling is Copperline (skill `amiga-copperline`); disk/hunk/HD-image facts are in `amiga-adf-and-hunks`.

## User preferences (carry over unless told otherwise)
- **Target:** a fast **Amiga 1200** — 68020/68030, AGA, 2 MB chip + fast RAM, Kickstart 3.1. Delivery is a **hard-disk image** (RDB, one partition per game, boots to Workbench; each game a volume you open and run) plus a fixed VHD and an install zip; the three-floppy set stays supported.
- **Fallback testing:** plain A500/A500+/A600 (68000, OCS/ECS, Kickstart 1.3/2.0x) where the original works. Copperline models them (`Machine(model="A500")`); **not yet run for Midwinter II**. Never treat an A500 run as evidence about the A1200.
- **Pixel-identical by default.** Visual tradeoffs need before/after screenshots and explicit approval.
- **Keep dithered fills:** they make the landscape readable.
- **Game speed must not depend on CPU speed.** Fixed real-time logic rate.
- **Direct controls.** Joystick/keys turn at a constant rate while held and stop on release. The mouse turns by its motion and stops when it stops. No "yoke" (input → persistent rate). Done for Midwinter II: the user confirmed it on foot and in the plane; the automated gate runs in the mission-start vehicle (a jeep); other vehicles are untested.
- **Deliverables:**
  - patched copies, never the originals modified;
  - a patch tool that verifies original bytes and applies all-or-nothing;
  - the HD image + VHD, floppy images, `dist/run_*.sh` launchers (each game "shows up and just runs");
  - an automated suite (`python3 -m pytest tests`) and `tools/test_hd_image.py IMG GAME` -> one `RESULT` line;
  - **release credit (mandatory, not yet done):** `vX.Y enhanced by dad_prg` visible at startup, in the README/PATCHES text and in the image name. Remove crack intros/slurs from the shipped startup sequence.

## Phases
1. **Harness and baseline.**
   - Boot from the real image on the A1200 (`tools/test_hd_image.py`) and record the boot path, the prompts, the title and the in-game screens as frame hashes (`tests/goldens.json`) and Copperline save states.
   - Add `games/<game>/tools/<g>cl.py`: a `Session` subclass with `boot()` (wait on a region digest), navigation to the in-game view, `locate()` for the patch sites.
   - Measure with emulated time: `Session.frame()`/`now()` and game counters read with `read_w` (**word reads** for word counters). Wall time is irrelevant and runs are exactly repeatable.
2. **Reverse-engineer, in parallel and read-only.**
   - Need: the frame loop and flip, the hot drawing routines, the logic timing (per frame or per VBL), the input pipeline (mouse/joystick/keyboard, ports and RAM counters), the loader and disk-swap logic.
   - Use `amigabin.py flat` + `m68dis.py`, read the loaded hunks through CCP (`segments.list` + `mem.read`), PC/watch/MMIO breakpoints and `last_writer` instead of dumps. Notes in `work/notes/` with evidence or `[INFERENCE]`.
   - Get the **actual load base** from `segments.list` (never assume one), per Kickstart.
3. **Patch delivery.**
   - Prefer patching the executable on disk (same-size edits or an appended blob) over runtime-only patches: a release must run without tools. Midwinter II: blob appended to CODE hunk 0 with the RELOC32 table rewritten (`tools/mw2patch.py`).
   - Verify original bytes at build time (`verify`) and, in the emulator, that the patch is the loaded code.
   - Beware the 68020 instruction cache: flush after writing code into RAM. Copperline models the icache (it is on by default for 020+).
4. **Timing.**
   - Add a free-running real-time counter from the level-3 VBL (or CIA), independent of the game's counters.
   - Run game logic at the original real rate (measure it first), wait when ahead, skip renders when behind (clamped), resync after gaps/menus.
   - Decide VBL-locked vs CPU-bound by running the same scene on a slow and a fast `Machine(cpu=..., cpu_clock=...)` and comparing world ticks per emulated frame.
5. **Display.** Profile before optimising (`profile.start`, per-frame CPU/DMA ownership, coverage — see the Copperline docs). On Amiga expect:
   - chip-RAM bandwidth and blitter/CPU contention to matter more than instruction count;
   - the blitter can help for long spans but not for many short spans; measure both paths;
   - AGA does not make OCS/ECS drawing faster by itself; do not switch screenmodes for speed without pixel-identical proof;
   - cull under opaque cockpit/HUD regions, skip cells that emit nothing, skip rendering unchanged views.
6. **Controls.** Find where the poller accumulates deltas and where the consumer reads them. Replace at the consumer, once per logic tick:
   - mouse: yaw += dx since last tick * gain, capped; clear the accumulator; no motion → no turn;
   - keys/joystick: percentage of the old full-yoke rate × held VBLs / elapsed VBLs, deadzone/clamp from the vehicle's control block.
   The Atari implementation is `patches/p5_ctl_x.s` in the ST repo; constants (MOUSE_GAIN 1.5 in 8.8, cap 1000, YAW 50%) are a starting point, not law. The Amiga gate is `tests/test_mw2_direct_controls.py` (poke acc → exact turn value, cap, consume-and-clear, real injected mouse, joystick, negative control on the unpatched volume).
7. **Regression:** every machine/ROM/RAM size that can run the original, disk swaps, save/load, campaign or data-disk creation, joystick/mouse/keyboard modes, and a cold boot to gameplay.

## Gates (every patch)
- `verify`: original bytes match in the executable image.
- A/B pixel gate against the unpatched game from the same state/frame (`capture.region_digest` of identical regions, or `copperline-ctl diverge` for lockstep); compare visible bitplanes only, with a negative control that must fail.
- FPS/frame-time before and after on the same machine, scene and emulated interval.
- Logic-rate equality: the world state at each real tick equals the unpatched game's step.
- Cold boot from the built image to gameplay through the real boot path, with the patch marker and a hash.
- LoadSeg integrity (`check_load`): every hunk equals the relocated file after load.

## Amiga-specific traps
- **Kickstart version changes the load address** of the executable and free RAM. Check each ROM (1.3, 2.0x, 3.1) with `segments.list`.
- **68020 cache and alignment.** The 68000 has none; the 68020 does. Patched-in code and self-modifying routines may need `CINVA`.
- **AGA/ECS differences.** OCS/ECS games run in compatibility modes; a "fast A1200" also means PAL 50 Hz; Kickstart 3.1's default screen is 640x256.
- **A game may need a CLI context, a volume root and a safe transfer size.** Midwinter II Gurus when started from a plain Workbench tool icon (CLI vs icon stack not isolated), only runs from the root of its volume, and the RDB `MaxTransfer` must be 0x1FE00 (see `amiga-adf-and-hunks`).
- **Copperline's default ROM is AROS, not Kickstart.** `Machine` always passes the 3.1 ROM from `os/Kickstart/`; never gate on AROS behaviour.
- **Floppy delivery:** disk swaps and `LoadSeg` overlays are part of the original design; do not break volume names or the loader. The SPL program disk has ~241 KB free.
- **Kickstart 3.1 AmigaDOS** may add assigns/patches absent on 1.3; test the exact startup sequence you ship.
- **Crack intros** (Sepultura, Quartex) add minutes to boot and contain offensive text; skip them and verify the game still initialises.
- **Cracks remove retail behaviour, not just protection.** The SPL release NOPed out the call to Midwinter II's "Press M / J / K" device selector (a MiSTer Amiga-core user saw the screen, we did not). Diff the executable against another release (`cmp -l`, here SPL vs Quartex: 59 bytes) and read every difference; a call with no callers (`m68dis --callers` empty) is the signature of a removed call. Restoring it was a 4-byte `bsr.w` (`tools/mw2patch.py`). After J or K the game drives its own menus with that device, so navigate with M.
- **Midwinter II's front end ignores quick presses** (VBL-sampled): hold the left button ~1 s emulated.

## Estimating gains
- A hot routine's share is not the gain. Chip-bus contention, blitter setup and the game's own front end stay.
- Prefer stateless rewrites to caches that need many invalidation hooks.
- Ship measured numbers only, with the machine, scene and measurement method named.
