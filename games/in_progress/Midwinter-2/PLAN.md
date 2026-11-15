# Midwinter II (Amiga): port plan

Goal: reproduce the finished Atari ST behaviour on the Amiga release, for a fast **Amiga 1200**, without source code. Delivery is a hard-disk image (see P7); the three-floppy set remains supported. (Earlier revisions of this plan said "floppy only"; the user has since moved to HD delivery, the ST precedent.)

The reference implementation and its evidence are `AtariST/gamebench/games/done/midwinter2`:
- timing: `patches/tick_vbl.s`, `p3cp_head.s`, `p3c_sim.s`, `p3c_render.s`; notes `simtiming.md`, `frameloop.md`, `tick_inventory.md`, `vehicles_p3b.md`;
- controls: `patches/p5_ctl_vbl.s`, `p5_ctl_x.s`; notes `controls.md`, `p5_controls.md`;
- rendering: `p7_*`, `p4_*`; report section 5;
- patch delivery: `tools/mw2patch.py`, `patches/README.md`.

The Amiga program is a different build of the same game: do not copy addresses, only behaviour and method.

## P0 — Bench (done)

- Repo layout, `.gitignore`, README.
- `tools/adf.py`, `tools/amigabin.py`, `tools/m68dis.py`, `tools/clharness.py` (Copperline).
- Skills: `amiga-game-speedup`, `amiga-copperline`, `amiga-adf-and-hunks`, `game-delegation`.
- Disk choice and MD5 sums: `README.md`.

## P1 — Baseline and boot path (done on A1200)

Status 2026-11-15: the game boots and plays on an emulated A1200 with Kickstart 3.1 in
Copperline, from the hard-disk image and from the three floppies (df0 starts the game, df1/df2
satisfy every "insert graphics/missions disk into any drive" prompt). The front end needs
**held** ~1 s mouse presses. Path (game coordinates 0..319 x 0..199): RAIDS (117,56) -> level
(INTERMEDIATE 120,166) -> click the CAMARGO island (155,170) -> SPACE -> briefing -> "?" (15,177)
-> thumbs-up (264,16) -> 3D cockpit (~30 s of set-up). Automated: `tools/test_hd_image.py`.


Deliverable (done, on Copperline): `games/in_progress/Midwinter-2/tools/mw2cl.py` (`MW2(Session)`):
- `boot()` waits for the hallway by region digest; `to_cockpit()` plays the front end with real mouse counts and held presses;
- cursor steering closed-loop on the game's own X/Y words (hunk 1 +0x308E/+0x3090);
- `locate()` finds the steering path in the loaded code hunk by skeleton (no RAM dump);
- reference states are Copperline save states (`work/states/`, git-ignored) and frame hashes (`tests/goldens.json`).

Facts already known:
- SPL disk 1 is OFS, volume `program`; `S/startup-sequence` runs `INTRO` then `mwII`.
- `MWII` is a 4-hunk load file (see README).
- At 15-50 s on A500 the cracktro runs; skip `INTRO` for tests.
- Copperline (CCP) gives memory, registers, breakpoints, `loadseg`/`segments.list`, region hashes and save states; see skill `amiga-copperline`.

Acceptance: a cold boot reaches the title and an in-game view with the state words recorded. Met on the A1200 with Kickstart 3.1 (Copperline, from the HD image and from floppies); **not yet run on A500/A600** (Kickstart 1.3/2.05 are in `os/Kickstart/`).

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

Settled and shipped for P5 (**variant of A**): the blob is appended to the end of
CODE hunk 0 (not a separate hunk), the sites become `jmp <blob>`, and the tool
rewrites the hunk-0 RELOC32 table so the blob's operands and the two `jmp`
operands relocate correctly. No startup-sequence changes, nothing to allocate,
and the patch survives disk swaps because it lives in the loaded code. See
`tools/mw2patch.py` and `games/in_progress/Midwinter-2/patches/p5_direct.s`.

## P4 — Timing (measurement open)

2026-11-14 (FS-UAE): both machine models presented real time (`timing_baseline.md`), which
shows only that the **emulator** is real-time; it does not distinguish VBL-locked logic from a
CPU-bound sim. The decisive number is world time per emulated frame on a slow vs a fast
machine, through the game's own VBL counters. With Copperline this is now straightforward and
free of the FS-UAE pause artefacts: `Session.run_to`/`frame()` give exact emulated time,
`read_w` gives the counters (read as WORD), and `Machine(model=..., cpu=..., cpu_clock=...)`
selects the machines. The ST scheduler ports only if the test shows CPU-bound stepping.

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

**Device selector restored (2026-11-15).** The retail game shows "Press 'M' for Mouse / 'J' for Joystick / 'K' for Keyboard" after the credits (a user running the game on a MiSTer Amiga core saw it; our build did not). Cause: the SPL crack overwrote the `bsr.w` to the selector routine, and a second call, with four NOPs at hunk-0 offset `0x1F170` (the Quartex release still has `61 00 3B CC` / `61 00 12 42` there; the first lands on the selector, the second on code the other crack also edited, left out). `tools/mw2patch.py` now restores only the first call (4 bytes, `verify` checks them). Gated by `tests/test_mw2_direct_controls.py::test_device_selector_is_offered_and_sets_the_gates` (M, J and K each pressed on the real screen reach the hallway and set the game's device gates). After J or K the game drives its own menus with that device, so the mouse-driven front-end harness only continues from M. The unpatched volume stays the unmodified SPL game (no selector), so it remains a faithful A/B control. Joystick turning after a real J selection (rather than poked gates) is not yet exercised.

## P6 — Rendering

Only after timing and controls are gated. Candidate work, in order of expected value:
1. skip the 3D render when the view inputs are unchanged (static frame skip);
2. cull polygons hidden under the opaque cockpit/HUD with an exact per-row mask;
3. skip cells/objects that emit nothing;
4. reduce chip-bus traffic (merged writes, blitter where spans are long).

Every change needs an identical-picture gate and a measured fps gain. No screenmode changes without approval.

## P7 — Release (in progress)

Delivered 2026-11-15 (Copperline; supersedes the 2026-11-14 FS-UAE build): an RDB hard-disk
image `dist/Amiga_enhanced_games_<date>.hdf` (+ fixed `.vhd`): DH0 Workbench 3.1 (boots to the
desktop), DH1 `Midwinter2` (patched), DH2 `Midwinter2Orig` (unpatched). Double-click the volume,
then `Play` (an IconX project icon: a plain tool icon Gurus, a CLI-context launch works; the game also needs the root of its volume). Launchers
`dist/run_hd.sh`, `dist/run_mw2.sh`, `dist/run_mw2_floppy.sh`. Verified by `python3 -m pytest tests`
(static, VHD, HD boot, bit-exact LoadSeg, desktop click-through, direct-controls gate on the
patched volume with the unpatched volume as negative control). Found and fixed on the way: RDB
`MaxTransfer` must be 0x1FE00 or reads past 128 KiB are wrong (the real cause of the Gurus seen
on HD). The install zip (`tools/make_amiga_zip.py`) is unchanged and not yet re-tested.
Not verified: real hardware (A1200 CF/IDE), A500/A600 paths. Still to do: the credit line,
the cold-boot matrix, single-floppy-drive swaps.


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
