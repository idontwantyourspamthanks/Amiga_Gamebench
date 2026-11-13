# MW2 Amiga: boot path, cracktro and first timing facts

Evidence gathered on the SPL 3-disk set, FS-UAE 3.2.35, A1200 model with
Kickstart 3.1 rev 40.68 (`os/Kickstart/amiga-os-310-a1200.rom`), 2 MB chip.
A500 + Kickstart 1.3 behaves the same for the intro.

## Boot path

`S/startup-sequence` (SPL) is:

```
setpatch >nil:
binddrivers
echo ... (crack text)
FastMemFirst
INTRO
mwII
endcli >nil:
```

- `INTRO` is a single chip CODE hunk, 34952 bytes, loaded by AmigaDOS. It is a
  Sepultura cracktro; its symbol table includes `LOOP`, `WAIT`, `JOY`, `TEXT`.
- It saves the OS vectors/registers it changes (INTENA, INTREQ, DMACON,
  ADKCON, COP1LC) and restores them on exit, then returns to the CLI.
- **It exits when CIA-A PRA bit 6 is low** (left mouse button / joystick fire
  pressed): at code offset `$162` it does `btst.b #6,$bfe001` and branches back
  to the raster-wait loop at `$102` while the bit is set. Holding the left
  mouse button for about a second exits the intro. (Verified: fire held 2.5 s
  at 25 s turned the cracktro into a black screen.)
- A plain `click` is usually too short; use `mouse_down`, wait, `mouse_up`.
- The intro installs its own copper list (`move.l #$dfe,$dff080` at `$0e6`) and
  restores `COP1LC` from `$5c` on exit.

### Skipping INTRO

- Removing `INTRO` from the startup sequence makes `mwII` fail: the shell
  returns to the CLI and `mwII` does not display. So the intro is not purely
  cosmetic; for now it must run.
- A test build `work/build/d1_skipintro.adf` patches the intro's raster-wait
  instruction at code offset `$102` (`move.l $dff004,d0`) with
  `bra.w $16e` + `nop` (`60 00 00 6A 4E 71`), so its prologue still saves the
  OS state and its exit path still restores it, but the demo is skipped.
  Boot result is still being evaluated; do not ship it until mwII is seen
  running with it.

## Executable (SPL `MWII`)

- 4 hunks: CODE 217912, DATA 84432, BSS 100000, chip DATA 138204.
- Entry is `jmp $24522` at code offset 0. `$24522` opens `dos.library`, calls
  exec (offsets `-$84`, `-$126`, `-$228`), allocates `$1D000` bytes with flags
  `$10002` (chip, cleared) at `$24602`, and jumps to `$1F110`.
- If the allocation fails it hangs in `bra.w $245F4` (infinite loop).
- All addresses above are **flat image offsets**. Runtime address = load base
  + offset; the loader relocates every absolute reference. Determine the base
  per Kickstart/startup sequence; do not hard-code.

## Interrupts and frame counter

- The game replaces the level-3 autovector at `$6C` with `$16EF8` (VBL).
- VBL handler `$16EF8`: checks `$DFF01F` bit 5 (VERTB), calls `$17F34`,
  `$1723E`, `$16F60`, `$17382`, then `addq.w #1,$393AE` and
  `addq.w #1,$39AA4`, clears `$39A9E`, calls `$172A8`, clears VERTB.
  - `$393AE` is a general frame/VBL counter used as a timebase (also cleared
    by many wait loops).
  - `$39AA4` counts VBLs and is wrapped at 6 by `$172A8` — a 1/6 s tick, not
    the world rate.
- Level-2 autovector `$68` is set to `$17170`, the CIA-A keyboard/mouse
  interrupt handler: reads `$BFED01`/`$BFEC01`, decodes a key table at
  `$3A5A6`, and writes a key-state byte table at `$39A1E`.

## Display

- `$24A64` writes `COP1LC` from `$10(A6)` and restarts the copper
  (`clr.w $88(A5)`), then calls `$1D322`, `$18416`, `$2E9E6`, `$2EA20`.
  This is the display/copper setup path, not necessarily the per-frame flip.
- Screen memory is allocated in `$24602`: `AllocMem($1D000, $10002)`, then
  `addi.l #$11800,d0` and pointers are stored at `$24AA4` and `$1DA00`;
  a pointer table is relocated by `$24A92` (walks a list until a negative
  long).

## Still unknown

- Where the per-frame flip is issued and what the game waits on (VBL counter
  `$393AE` or a custom register).
- Whether the world logic runs once per presented frame, as on the ST.
- The actual load base under 1.3 and 3.1 (debugger `s "dos.library"` returned
  nothing; use `S` dumps or `Z`/`T` once the game is running).
- Why `mwII` fails when `INTRO` is skipped entirely (a resource left by the
  intro, or a protection check in the intro's prologue).

## Verified later on 2026-11-13 (A1200, Kickstart 3.1 rev 40.68)

- Kickstart 3.1 A1200 ROM is present in `os/Kickstart/amiga-os-310-a1200.rom`
  and boots the SPL disks. The game reaches its title and the hallway menu.
- **Runtime load base is `$2D8C0`.** Four independent fixed-opcode signatures
  (input consumer, VBL handler, sampler, copper flip) all resolve to the same
  base in a full 2 MB chip-RAM dump. Absolute operands in the flat image are
  relocated by that base, which is why a raw byte search of runtime code
  against the base-0 flat image fails.
- FS-UAE host menu: **F12 toggles**, **Escape closes** it; focus starts on
  PAUSE. From PAUSE, Down x7 selects the `df0` media item; Enter opens
  `INSERT INTO DF0` whose list is `EJECT, D1, DISK 2, DISK 3, ...` (current
  image highlighted). Enter on an image inserts it. The window manager (twm)
  is required for FS-UAE to take focus/grab input under Xvfb.
- Disk model in the game's own strings: START-UP (disk 1), GRAPHICS (disk 2),
  MISSIONS (disk 3), plus PERSONNEL and CAMPAIGN disks for campaign saves.
  The first prompt is `Insert Graphics Disk / Into any drive`; inserting disk 2
  clears it and the game shows its title/intro, then the hallway menu.
- At the hallway with only disk 2 in `df0`, VBL counter `$393AE` read 0 and the
  input sampler was idle. `[INFERENCE]` the game is waiting for the START-UP
  disk again; the swap-back test is in progress. Do not treat "VBL=0" as a
  verdict until the disk state is known.

### Corrections to earlier text in this note

- `$40E26` is in the DATA hunk, not BSS; its value at the menu was `$4173`.
  `tst.w $40E26` therefore tests an initialised word, not a 0/1 flag. Do not
  read it as "input enabled" without checking the surrounding code.
- `dos.library` at runtime `$2BEE4` is below the MWII base `$2D8C0`; it belongs
  to the OS/shell, not MWII. It is not a base-finding anchor.
- The "Press 'M' for Mouse" strings are in the `MWII` file but not in the
  relocated flat image; they are most likely symbol/debug or an unloaded
  section. Do not assume a control-selection prompt is live.

## Disk-wait state (2026-11-13, after graphics disk insert)

- The game reaches the hallway "WAR ROOM / RAIDS / CONTROL / TRAINING" screen
  but sits in a tight busy-wait: PC `$3EBAA`, `TST.W $00060424`, variable 0.
- The level-3 autovector at that point is `$3DFC8`, i.e. flat `$10708` when
  base `$2D8C0` — **not** `$16EF8`. The `$16EF8` handler seen earlier is a
  later/other module. So `$393AE` reading 0 does **not** prove interrupts are
  off; do not use it as a liveness indicator at this stage.
- Swapping d1/d2/d3 in `df0` does not clear the wait. The code around the wait
  is **not** found in the MWII flat image at `$11CEA` (bytes differ), so a
  module is loaded elsewhere/relocated at this stage. Next step: dump RAM in
  this state, disassemble around `$3EBAA`, and identify the owning disk file
  before assuming which disk/prompt it wants.

## Phase-dependent base (important)

The load base is **not constant across the game's phases**:
- At the hallway/disk-wait state, the level-3 vector is `$3DFC8`, which matches
  flat `$16EF8` with **code base `$270D0` and data base `$270D8`** (the VBL
  increments `$60486` = flat `$393AE` + `$270D8`; the wait routine at `$3EB72`
  matches flat `$17AA2` byte for byte).
- A later state (full 2 MB dump after further loading) resolved four signatures
  to base `$2D8C0`. Either the game relocates/reloads a module, or that dump was
  from a different phase. **Always re-derive the base for the phase under test**;
  never reuse `$2D8C0` blindly.

## The hallway wait is an input-event wait

Flat routine `$17AA2` (runtime `$3EB72` at base `$270D0`):

```
17aa4: tst.w  $40E26          ; input enabled
17aaa: bne.b  $17ADA
17aac: move.w $38600,d0       ; joystick-1 flag
17ab2: or.w   $3934C,d0       ; input flags
17ab8: beq.b  $17aac
...
17ada: tst.w  $3934C          ; wait for any input flag
17ae0: beq.b  $17ada
17ae2: move.w $3934C,$3934E
17aec: move.w #$FFFF,$39336   ; VBL semaphore
17af4: tst.w  $39336
17afa: bne.b  $17af4
17afc: move.w (a7)+,d0
17afe: rts
```

`$3934C` is written once per VBL by the sampler `$1765E` from `$39930`:
- bit 0 = right mouse button / POTGOR bit 2 (verified: right button -> 1)
- bit 1 = left mouse button / CIA-A PRA bit 6 (verified: left button -> 2)

`$40E26` is 1 at this phase, so the wait only watches `$3934C`.
The game re-enters this wait after consuming an event (many callers), so a
single click does not necessarily change the screen. Input is delivered; the
open question is which **event code/mode** the menu caller accepts and whether
the pointer is drawn from the joystick position (`$3933C/$39340`) or the mouse
accumulators (`$39344/$39348`).

## Menu navigation (2026-11-13)

- **The mouse must be on port 0.** Adding `joystick_port_0=keyboard` disconnects
  the mouse and the menu cursor freezes. With the default mouse device the
  cursor moves, and the game highlights the icon under it (RAIDS was hovered).
- FS-UAE loses the first relative motion after the pointer grab: send a
  priming `mouse_rel(1,0)` after the grab click, then the real move.
- Cursor position can be detected from screenshots: it is a 16x16 white arrow,
  connected-component area ~87, at the top of the screen; label boxes are
  excluded (see the closed-loop navigator used in testing).
- Hovering RAIDS works; **activation does not**: left click, right click, space
  (tap or hold) leave the screen unchanged.
- Decisive test: writing `4e71 4e71 4e71 4e71` over the first wait
  (`$3EBAA`) moves execution to the **second** wait at `$3EBC4`
  (`tst.w $6040E` / flat `$39336`), which never clears. So the menu routine is
  genuinely blocked in this wait pair, and the VBL semaphore `$39336` is not
  being cleared at this point.
- The sampler `$1765E` is called from `$17382` in the VBL chain
  (`$16EF8 -> $17382 -> $177B0, $1765E`), and clears `$39336` only when
  `$40E26` (input enable) is non-zero and no button bits are set.
  Next: read `INTENA`/`INTREQ` and `$40E26` at the NOP state to determine why
  the semaphore is not cleared (interrupt disabled, or input disabled during
  the wait).
