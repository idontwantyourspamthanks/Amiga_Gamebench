# MW2 Amiga: boot path, cracktro and first timing facts

Evidence gathered on the SPL 3-disk set, FS-UAE 3.2.35, A1200 model with
Kickstart 3.1 rev 40.68 (`os/Kickstart/amiga-os-310-a1200.rom`), 2 MB chip.
A500 + Kickstart 1.3 behaves the same for the intro.

> 2026-11-15: measured with FS-UAE, which has been replaced by Copperline (`tools/clharness.py`,
> skill `amiga-copperline`). The boot-path facts stand; the FS-UAE commands and the wall-clock
> measurements are historical. Copperline numbers are in emulated time and reproducible.

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
  Verified 2026-11-14: this disk boots to the hallway and reaches the in-game
  cockpit on A1200 Kickstart 3.1 (every front-end test in the 2026-11-14
  session used it). The launcher and harness fall back to the original start-up
  disk if the build file is absent.

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

## Correction: the wait is not deadlocked

A breakpoint on the sampler's clear (`$3E79E`, `CLR.W $6040E`) **hits every
VBL**: the VBL counter `$60486` was 0x118B and the semaphore is cleared by the
VBL chain. Reading `$6040E` as 0xFFFF only samples the moment between the wait
routine setting it and the next VBL; the wait pair is normal.

Remaining front-end problem: the menu is static and activation does nothing
(left click, right click, space tap/hold, port-1 fire, Return), even though the
mouse moves and RAIDS is under the pointer. All three disks mounted, one drive
with swaps, mouse-only and keyboard-joystick-on-port-1 configs all behave the
same. This points at the game's **menu state/disk condition** (likely a
campaign/personnel disk or a control-method state), not at the wait code.
Next options: (a) supply/confirm a campaign or personnel disk; (b) bypass the
menu by seeding the game's mission state via the debugger and entering a 3D
view directly, which is acceptable for a measurement harness.

## Front-end menu model (static, verified addresses)

- Hover hit test: `sub_013EA8` reads `$39338/$3933A` (cursor at the last button
  edge), walks 6-byte items at `$5E(a6)`, compares against `$42414`, and writes
  the item index to `$3749C` (-1 = no hit).
- Button flags: sampler `$1765E` sets `$383A8` on right-button press (bit 0) and
  `$383A6` on left-button press (bit 1), copying `$3933C/$39340` into
  `$39338/$3933A`. `sub_017D86` consumes `$383A6|$383A8` for a click event;
  `sub_017E7E` clears the flags and `$3934C`.
- Hallway loop `$14AC4`: wait `$17AA2` -> hit test -> `$3749C`; index 2 has a
  separate path, other indices call `$14050` (selection wrap/`$449FE`) then
  `$149C2` (screen rebuild) and store the selected index in `$44992`.
- `sub_0131CA` (index 0/RAIDS path in the `$1199A` variant) sets a flag byte in
  `$446D8+` and redraws; it is a selection, not a mission start.
- Live state on RAIDS with the left button held: `$383A6=$FFFF`,
  `$3934C=$D`, `$3749C=0`, `$40E26=1`, `$382E0=0`. So the click event and hit
  test are correct; the remaining step is the confirm that consumes the
  selection (likely a second click/fire or a key), not another input mapping.
- The `$382E0=0` screen is the hallway; `$11900` (sets `$382E0=5`) is a later
  screen, not the hallway.

## Corrected activation test (verified cursor)

- `amiganav.move_to` now converges and `find_cursor` keeps the arrow over labels.
  The RAIDS click was repeated only after `find_cursor` reported (273,131),
  i.e. the pointer was genuinely on the label. The screen still does not change
  (hashes differ only by cursor position).
- Mounting blank OFS `campaign` and `personnel` disks as df2/df3 (startup in
  df0, graphics in df1) also changes nothing.
- PERSONNEL and WAR ROOM were tested the same way (verified positions
  531,55 and 198,55): no transition.
- Selection state is definitely being set: `$3749C=0`, `$383A6=$FFFF`,
  `$3934C=$D`, `$40E26=1`, `$382E0=0`.
- **Next static target:** `$44992` is written from `$40E4E` at `$14A0E`
  (`$149C2`) and read by other screen handlers at `$111A8`, `$12994`,
  `$12B0C`, `$12C1E`, `$135B4`, `$13672`. Trace those consumers and the
  screen dispatcher; the hallway's transition gate is among them.
  `$4495C`/`$44960` are per-screen flags set/cleared in `$149C2`.

## Traced click (verified cursor, 2026-11-14)

- Cursor verified at (281,139) (arrow tip on RAIDS), breakpoint set at the
  hallway activation branch `$14AE2` (runtime `$3BBB2`), one click sent.
- **The breakpoint never fired.** After the click the CPU was still in the
  `$17AA2` wait (`PC $3EBAA`). So the active hallway loop is not the `$14AC4`
  path (or the click is consumed/cleared before that wait sees it).
- Next diagnostic: read the return address of the `$17AA2` call at the wait
  (`A7=$614B0`; caller return is in the stack frame) or set a breakpoint on
  `$17AA2` entry and walk back to its caller. That identifies the real active
  screen loop without any further guessing.

## REAL hallway loop and the agent gate (2026-11-14)

The loop is at flat `$1F226` / runtime `$462F6` (found via the `$17AA2` caller):

```
1f220: jsr $17ED4          ; restore input mode
1f226: jsr $17AA2          ; wait for a click event
1f22c: jsr $181E0          ; hit test (uses $3933C/$39340, current cursor)
1f232: tst.w $3749C
1f238: bmi $1F226          ; no hit -> wait again
1f23a: bra $1F19C          ; hit -> activation path
1f19c: tst.w $40AA6
1f1a2: bmi $1F21A          ; NEGATIVE gate -> skip mission setup, wait
1f1a4..1f212               ; mission setup (calls $17EDC, $1A8FA, $25B5E, ...)
```

- Live at hover: `$3749C=0` (RAIDS), `$3933C/$39340 = $76/$38` (game coords;
  screen ≈ ×2.4), `$39338/$3933A` stale at 0 (not used by `$181E0`).
- `$40AA6` runtime `$67B7E` was **0** in our session, so the gate is open; a
  click with a hit should run the mission setup. The remaining variable is
  whether that setup needs a particular disk in df0.

## Breakthrough: the front end runs on A1200 (2026-11-14)

The menu is driven by **held** mouse presses, not clicks. With a 1 s hold:

1. boot d1 (A1200) -> "insert graphics disk" -> swap df0 to d2 -> hallway.
2. Hold-press **RAIDS** (281,140) -> **"SELECT LEVEL OF PLAY"**.
3. Hold-press **INTERMEDIATE** (295,385) -> **the raid map** (AGORA, DHAFRA,
   LOBOS, SAMARGO, AFRICA, skulls).
4. Hover an island + press **space** -> **"Insert Missions Disk Into any
   drive"** -> swap in d3 (missions).

A quick click is missed by the front end's VBL sampler (`$17B1E`); a 1 s press
always registers. All of this is now scripted in
`games/done/Midwinter-2/tools/mw2harness.py`.

## No disk swapping needed: mount all three drives (2026-11-14)

The game accepts the graphics and missions disks in **any drive**. With
`FSUAE(disks=[d1, d2, d3])` (df0/d1, df1/d2, df2/d3) every "insert X disk
into any drive" prompt is satisfied automatically: boot from d1, hold-press
RAIDS, hold-press INTERMEDIATE, click an island, press space, and the CAMARGO
briefing appears with the question and book icons - no swaps at all.
