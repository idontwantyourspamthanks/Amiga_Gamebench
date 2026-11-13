# Midwinter II (Amiga): port plan

Goal: reproduce the finished Atari ST behaviour on the Amiga release, for a fast **Amiga 1200**, **floppy only**, without source code.

The reference implementation and its evidence are `AtariST/gamebench/games/done/midwinter2`:
- timing: `patches/tick_vbl.s`, `p3cp_head.s`, `p3c_sim.s`, `p3c_render.s`; notes `simtiming.md`, `frameloop.md`, `tick_inventory.md`, `vehicles_p3b.md`;
- controls: `patches/p5_ctl_vbl.s`, `p5_ctl_x.s`; notes `controls.md`, `p5_controls.md`;
- rendering: `p7_*`, `p4_*`; report section 5;
- patch delivery: `tools/mw2patch.py`, `patches/README.md`.

The Amiga program is a different build of the same game: do not copy addresses, only behaviour and method.

## P0 — Bench (done)

- Repo layout, `.gitignore`, README.
- `tools/adf.py`, `tools/amigabin.py`, `tools/m68dis.py`, `tools/amigaharness.py`.
- Skills: `amiga-game-speedup`, `amiga-fs-uae-harness`, `amiga-adf-and-hunks`, `game-delegation`.
- Disk choice and MD5 sums: `README.md`.

## P1 — Baseline and boot path

Deliverable: `games/in_progress/Midwinter-2/tools/mw2harness.py`, a `FSUAE` subclass with:
- `boot_to_title()` and `boot_to_game()` using game-state checks (RAM words), not only screenshots;
- reference screenshots in `work/ref/` (git-ignored): Kickstart screen, startup text, title, cockpit, on-foot;
- the exact disk-swap sequence, and whether the game runs with `INTRO` skipped;
- baseline fps on A500 1.3 (fast loop) and on A1200 3.1 when the ROM exists, stock and accelerated (`A1200/1230`);
- a RAM dump and flat-image map with the **actual load base** on each ROM.

Facts already known:
- SPL disk 1 is OFS, volume `program`; `S/startup-sequence` runs `INTRO` then `mwII`.
- `MWII` is a 4-hunk load file (see README).
- At 15-50 s on A500 the cracktro runs; skip `INTRO` for tests.
- FS-UAE debugger works: `m`, `r`, `S <file> <addr> <n>`, `W`, `f`, `c`, `e`, `dm`.

Acceptance: a cold boot reaches the title and an in-game view, with a screenshot and the state words recorded, on A500 1.3. A1200 blocked until a Kickstart 3.1 ROM is supplied.

## P2 — Reverse engineering (parallel, read-only)

One agent per slice, notes in `work/notes/`; every claim cites disassembly or raw tool output.

1. **Frame loop and flip.** Find the main loop, the VBL/interrupt handler, the screen flip (which pointer write marks a presented frame), and whether logic runs per frame or per VBL. This decides the timing design.
2. **Input pipeline.** CIA-A PRA fire button, JOY0DAT/JOY1DAT, the mouse/joystick interrupt handler, the accumulators, and the consumer that turns them into yaw. Compare with the ST findings (`$6fb6` there). Identify the per-vehicle control block and its clamp/deadzone fields if the structure matches.
3. **Hot drawing routines.** Profile by instrumentation or by targeted measurement; read the terrain/object/cockpit routines. Establish whether the blitter is used and whether an OCS/ECS→AGA path exists.
4. **Loader and disk-swap logic.** How `mwII` finds `grafix`/`missions` (volume names, `Lock`, `Open`, directory cache), how prompts are shown, and where a patch can hook a file load.
5. **68020/AGA/Kickstart 3.1 compatibility.** What the game does at startup (chipset detection, `DENISEID`, `VPOSR`, CIA timers, `movec`, cache assumptions, `LoadSeg` base). List anything that would break on an A1200 or under 3.1.

Acceptance for each note: addresses plus routine text, and at least one live check via the debugger (`m`/`S`/`f`), not static reading alone.

## P3 — Patch delivery

Deliverable: `tools/mw2patch.py`-equivalent for the Amiga build:
- verify every site's original bytes against the chosen ADF's `MWII` (and any other patched file);
- build patched ADFs from the originals; never modify the originals;
- all-or-nothing application, with a marker word in RAM;
- a boot-time installer, or patches written directly into the executable;
- `adf.py diff` output as proof of changed sectors.

Design choice to settle in P1/P2:
- **A. In-place + appended hunk.** Add a CODE hunk to `MWII` and patch the entry/sites to jump to it. Keeps a single executable and no startup changes beyond the credit; needs a hunk writer and correct relocation of new hunk addresses.
- **B. Separate payload file** loaded by a replaced `S/startup-sequence`, copied to a fixed free RAM area, then `mwII` started with patches applied. Simpler byte-wise, but needs an `AllocMem` or fixed-address proof and must survive disk swaps (df0 is swapped; the payload must already be in RAM).
- **C. Live-only patches** for experiments via the debugger (`W`); never shipped.

Recommended: **B** for iteration, **A** for the release if the hunk writer is clean; both gated by cold boots.

## P4 — Timing

Mirror the ST design:
- free-running real-time counter from the level-3 VBL (50 Hz PAL; handle 60 Hz NTSC), independent of the game's counters;
- run the game's logic at its original real rate (measure it first; assume 5 Hz only as a hypothesis);
- wait when ahead; skip a render when behind (clamped, e.g. 3 steps); resync after menus/disk swaps;
- optional per-group extrapolated render passes for smooth motion, with exact state restore at group end.

Gates:
- world state at each real step equals the unpatched game's step (positions, heading, altitude, NPC table, RNG, clock);
- fps before/after at A500 and A1200, stock and accelerated;
- input latency measurement (first visible change after an impulse).

## P5 — Direct controls

Port the consumer-side replacement:
- mouse: yaw change proportional to `dx` accumulated since the last logic tick, capped; clear the accumulator; no motion → no turn;
- keys/joystick: constant rate while held, proportional to held/elapsed VBLs, from the vehicle's own clamp/deadzone; zero on release;
- no persistent "yoke" accumulator.

Start from the ST constants (`MOUSE_GAIN 1.5` in 8.8, cap 1000, `YAW_PCT 50`) and tune only with before/after traces. Acceptance: hold right → constant turn; release → stop at once; mouse nudge → one small turn, then no further rotation; all vehicle types that steer on X.

## P6 — Rendering

Only after timing and controls are gated. Candidate work, in order of expected value:
1. skip the 3D render when the view inputs are unchanged (static frame skip);
2. cull polygons hidden under the opaque cockpit/HUD with an exact per-row mask;
3. skip cells/objects that emit nothing;
4. reduce chip-bus traffic (merged writes, blitter where spans are long).

Every change needs an identical-picture gate and a measured fps gain. No screenmode changes without approval.

## P7 — Release

- ADF set (3 disks) built from the SPL originals; startup sequence replaced: credit line `vX.Y enhanced by dad_prg`, `INTRO` skipped, `mwII` started.
- No hard-disk dependency; test with a single floppy drive and the required disk swaps.
- Cold-boot matrix: A500 1.3, A500+ 2.04, A600, A1200 3.1 stock, A1200/1230 — as far as ROMs allow.
- `README.md` / `PATCHES.TXT` / zip names carry the version.
- A final report in this folder with pasted gate outputs.

## Open questions

1. Does the game initialise without `INTRO` (does the cracktro install anything the game needs)?
2. Does it run correctly on A1200/AGA/Kickstart 3.1 at all before patching? **Needs a 3.1 ROM.**
3. Is the logic rate per frame (speedup with CPU) as on the ST? Measure on A500 vs accelerated A1200.
4. Which program owns the level-3 vector, and can we hook it without breaking the game?
5. Is the executable loaded at a fixed address under 1.3 and under 3.1, or must patches be PC-relative?
6. Does the game use the blitter, and does it use an ECS/AGA screenmode on A1200?
