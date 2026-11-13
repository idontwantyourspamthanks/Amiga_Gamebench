---
name: amiga-game-speedup
description: Method for speeding up and modernising a closed-source Amiga game by patching RAM or disk images, learned on the Atari ST Midwinter work and applied to Amiga Midwinter II on a fast A1200. Covers phase plan, benchmarks, fixed-timestep decoupling, direct controls, rendering gains, floppy-only delivery, 68020/AGA/Kickstart traps, gates and packaging. Use when starting or planning work on a game in gamebench/games/.
---

# Speeding up an Amiga game (method)

Reference for the behaviour and the gates: `AtariST/gamebench/games/done/midwinter2` (Atari ST). This skill records what carries over and what is genuinely Amiga-specific. The Amiga work is at `games/in_progress/Midwinter-2`.

## User preferences (carry over unless told otherwise)
- **Target:** a fast **Amiga 1200** — 68020/68030, AGA, 2 MB chip + fast RAM, Kickstart 3.1. Booting from **floppy only** (no hard disk for now).
- **Fallback testing:** plain A500/A500+ (68000, OCS/ECS, Kickstart 1.3/2.04) where the original works. Never treat an A500 run as evidence about the A1200.
- **Pixel-identical by default.** Visual tradeoffs need before/after screenshots and explicit approval.
- **Keep dithered fills:** they make the landscape readable.
- **Game speed must not depend on CPU speed.** Fixed real-time logic rate.
- **Direct controls.** Joystick/keys turn at a constant rate while held and stop on release. The mouse turns by its motion and stops when it stops. No "yoke" (input → persistent rate). This is the user's fixed Atari behaviour, to be reproduced on the Amiga.
- **Deliverables:**
  - patched copies, never the originals modified;
  - a patch tool that verifies original bytes and applies all-or-nothing;
  - floppy images (and, later, a hard-disk build);
  - `play.sh`-style launchers;
  - **release credit (mandatory):** `vX.Y enhanced by dad_prg` visible at startup, in the README/PATCHES text and in the image name. Remove crack intros/slurs from the shipped startup sequence.

## Phases
1. **Harness and baseline.**
   - Boot the chosen disks on A500 (fast loop) and A1200 as soon as a 3.1 ROM exists.
   - Record the boot path (`S/startup-sequence`, `INTRO`, `mwII`), the disk prompts, the title and the in-game screens as reference images.
   - Add a game-specific `FSUAE` subclass in `games/<game>/tools/` with `boot_to_game()` and RAM-state checks (not just screenshots).
   - Measure baseline fps (debugger frame counters) at stock A1200, at accelerated speeds and at A500 7.09 MHz.
2. **Reverse-engineer, in parallel and read-only.**
   - Need: the frame loop and flip, the hot drawing routines, the logic timing (per frame or per VBL), the input pipeline (mouse/joystick/keyboard, ports and RAM counters), the loader and disk-swap logic.
   - Use `amigabin.py flat` + `m68dis.py`, plus debugger RAM dumps (`S`) from live gameplay. Notes in `work/notes/` with evidence or `[INFERENCE]`.
   - Establish the **actual load base** on each Kickstart from the debugger (`dm`, register/stack inspection, or a unique code signature search).
3. **Patch delivery.**
   - Prefer patching the executable on disk (same-size edits or an appended hunk) over runtime-only patches: a floppy release must boot without tools.
   - Verify original bytes at build time and at startup (all-or-nothing + marker word).
   - Beware 68020 instruction cache: after writing code/patches into RAM, flush it (`CINVA`/`CacheClearU`). Code that was never executed is usually safe, but self-modifying originals may not be.
4. **Timing.**
   - Add a free-running real-time counter from the level-3 VBL (or CIA), independent of the game's counters.
   - Run game logic at the original real rate (Midwinter II: 5 Hz), wait when ahead, skip renders when behind (clamped), resync after gaps/menus.
   - Optional smooth motion: run the original step unchanged once per group, render extrapolated poses in between, restore state before the next real step.
5. **Display.** Profile before optimising. On Amiga expect:
   - chip-RAM bandwidth and blitter/CPU contention to matter more than instruction count;
   - the blitter can help for long spans but not for many short spans; measure both paths;
   - AGA does not make OCS/ECS drawing faster by itself; do not switch screenmodes for speed without pixel-identical proof;
   - cull under opaque cockpit/HUD regions, skip cells that emit nothing, skip rendering unchanged views (compare the inputs of the render or a dirty flag).
6. **Controls.** Find where the IKBD/port deltas are accumulated and where the consumer reads them. Replace at the consumer, once per logic tick:
   - mouse: yaw += dx since last tick * gain, capped; clear the accumulator; no motion → no turn.
   - keys/joystick: yaw = percentage of the old full-yoke rate × (held VBLs) / (elapsed VBLs), deadzone/clamp from the vehicle's control block.
   The Atari implementation is `patches/p5_ctl_x.s` in the ST repo; constants (MOUSE_GAIN 1.5 in 8.8, cap 1000, YAW 50%) are a starting point, not law.
7. **Regression:** every machine/ROM/RAM size that can run the original, disk swaps, save/load, campaign or data-disk creation, joystick/mouse/keyboard modes, and a cold boot to gameplay.

## Gates (every patch)
- `verify`: original bytes match in the executable image.
- A/B pixel gate against the unpatched game from the same state/frame; compare visible bitplanes only, with a negative control that must fail.
- FPS/frame-time measurement, before and after, on the same machine and scene (debugger frame counters, not host stopwatch).
- Logic-rate equality: the world state at each real tick equals the unpatched game's step.
- Cold boot from the built ADF set to gameplay, with the patch marker set and a screenshot.
- `adf.py diff` shows only intended sectors changed.

## Amiga-specific traps
- **Kickstart version changes the load address** of the executable and the amount/placement of free RAM. Never hard-code an address without checking on each ROM (1.3, 2.04, 3.1).
- **68020 cache and alignment.** The 68000 has no instruction cache; the 68020 does. Patched-in code and self-modifying routines may need `CINVA`. Unaligned long accesses work on 68000 but trap/slow on 68020 (the 68020 supports them, at a cost; the 68030 with MMU can fault).
- **AGA/ECS differences.** OCS/ECS games run in compatibility modes but may read `DENISEID`/`VPOSR` or use ECS registers; a "fast A1200" also means 50 Hz vs 60 Hz (PAL/NTSC), and Kickstart 3.1's default screen is 640x256.
- **Floppy-only:** disk swaps and `LoadSeg` overlays are part of the original design; do not break volume names or the loader. Free space is ~19 KB on the program disk; plan payload size.
- **Kickstart 3.1 AmigaDOS** may add assigns/patches absent on 1.3; test the exact startup sequence you ship.
- **AROS is not Kickstart.** FS-UAE falls back to AROS when no ROM exists; never gate on it.
- **FS-UAE's debugger `m` cannot read `$DFFxxx`.** Use `e`/`c`.
- **Crack intros** (Sepultura, Quartex) add minutes to boot and contain offensive text; skip them in the shipped startup sequence and verify the game still initialises.

## Estimating gains
- A hot routine's share is not the gain. Chip-bus contention, blitter setup and the game's own front end stay.
- Prefer stateless rewrites to caches that need many invalidation hooks.
- Ship measured numbers only, with the machine, scene and measurement method named.
