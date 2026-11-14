# How to find a feature in Midwinter II (Amiga), patch it and test it — worked through the "direct controls" patch

Audience: an agent that has never seen this repo. Every step has the exact command and the output
that was seen when it was done (2026-11-14, FS-UAE 3.2.35, A1200, Kickstart 3.1, SPL 3-disk set).
Run all commands from the repo root `/home/ryan/Code/Amiga/gamebench`.

What was built: **direct steering**, the counterpart of the Atari ST `p5_ctl_*` patches.
- Mouse (`M`): the view turns in proportion to mouse motion since the previous logic tick and
  stops when the mouse stops. No persistent "yoke".
- Joystick (`J`) / keypad keys (`K`): a constant turn rate while the direction is held, zero after
  release, pro rata for a tap shorter than a tick.
- Result: `games/in_progress/Midwinter-2/work/build/d1_direct.adf` (git-ignored; rebuild it, §6).

Files: patch source `games/in_progress/Midwinter-2/patches/p5_direct.s`, patch tool `tools/mw2patch.py`,
probe helpers `games/in_progress/Midwinter-2/tools/mw2probe.py` and `mw2harness.py`, harness
`tools/amigaharness.py`, disassembler `tools/m68dis.py`.

---------------------------------------------------------------------------------------------------

## 0. Ground rules (each one cost hours once)

1. **Runtime addresses change between runs and between load phases.** Never reuse an address from a
   note, a log or a previous session. Dump RAM in the session you are measuring and find the code by
   its instruction skeleton (§2). Addresses written in this document are *examples from one run*.
2. **Every debugger call pauses the emulation.** The game only runs between `h.resume()` and the
   next debugger call. Emulated time does not pass while you are in the debugger.
3. **Entering the debugger releases the host mouse.** After any debugger stop, the next mouse motion is
   lost until you click inside the window again (`mw2probe.regrab(h)`). Keyboard input needs no regrab.
4. **`W <addr> 0000` writes ONE BYTE** (values below $100 are bytes). Always write words with `.w`:
   `W 6d404 0001.w 0000.w`. `AmigaHarness.write_mem` now does this for you.
5. **`fd` does not delete all breakpoints** in this UAE build: it removes at most one. Toggle each one
   with `f <addr>`; `h.clear_breakpoints()` does this. Because of this bug an old note concluded "the
   steering consumer is never called": leftover breakpoints silently stopped the CPU at every `g`, so
   nothing ever ran between probes. When a probe says "nothing happens", first run `fl`.
6. The ADFs under `originals/` are never modified. Everything is built into `work/build/`.

---------------------------------------------------------------------------------------------------

## 1. Boot the game to the 3D cockpit

Needs `fs-uae`, `Xvfb`, `xdotool`, ImageMagick (`import`), `twm`, python3 with `cv2`+`numpy`.
All menu presses must be HELD about one second; a click is ignored. This is scripted:

```python
import sys, time
sys.path.insert(0, 'tools'); sys.path.insert(0, 'games/in_progress/Midwinter-2/tools')
import mw2harness as mw, mw2probe as pr

h = mw.boot_to_cockpit(mw.D1_DIRECT, extra=['joystick_port_1=keyboard'])   # ~2.5 minutes, warp mode
h.screenshot('/tmp/cockpit.png')           # expect: a jeep cockpit (green dashboard, steering wheel)
```

- `mw.D1` = `d1_skipintro.adf` (unpatched), `mw.D1_DIRECT` = `d1_direct.adf` (patched). The three
  drives (d1, disk 2 graphics, disk 3 missions) satisfy every "insert disk" prompt with no swaps.
- What `boot_to_cockpit` does: 30 s wait, grab the mouse, `space`, hold RAIDS (281,140), hold
  INTERMEDIATE (295,385), `space` (raid map -> CAMARGO briefing, 12 s), hold "?" (75,420), hold
  the thumbs-up (600,45) 8 s -> cockpit.
- `extra=['joystick_port_1=keyboard']` makes the host arrow keys act as a port-1 joystick, needed
  only for the `J` test. The mouse stays on port 0.
- The game is in **mouse mode (M) at mission start**: the mouse gate word is 1 at cockpit entry.
  `J`/`K` are tested by setting their gate words in the debugger (§5.3). The in-game selector
  screen (strings "Press M/J/K") is the routine near live `0x56df6`; no direct caller of it was
  found, so how a player reaches it is **not verified**.

---------------------------------------------------------------------------------------------------

## 2. Dump RAM and find a routine by instruction skeleton

Why skeletons: the loader relocates every absolute operand, so the same routine has different
bytes in the file and in RAM. A skeleton is the instruction bytes with the absolute operands left
out; it is identical everywhere. Fixed hardware addresses (`$DFF00A`, `$BFE001`) are never relocated
and make good anchors.

### 2.1 Dump chip RAM (A1200 with no fast RAM: all 2 MB)

```python
ram = pr.dump(h, 'cock')                     # debugger command: S /tmp/cock.bin 0 200000 ; ~12 s
print(len(ram))                              # 2097152
```

Equivalent raw debugger command: `S /tmp/cock.bin 0 200000` (`S <file> <addr> <len>`, hex, no spaces
in the path). The S command returns before the file is complete; `pr.dump` waits for the size.

### 2.2 Find the steering consumer (worked example)

The consumer clamps the X accumulator (mouse dx) with the vehicle's limits and applies a deadzone.
Its body, operands excluded, is

```
b0680014 6e06 30280014 600a b0680016 6d04 30280016        cmp.w $14(a0),d0 ; bgt ; move.w $14(a0),d0 ; bra ; cmp.w $16(a0),d0 ; blt ; move.w $16(a0),d0
```

```python
hits = pr.findall(ram, pr.CONSUMER_SKEL)
print([hex(x) for x in hits])                # unpatched run: ['0x5c646']  -> routine starts at hit-6 = 0x5c640
```

`hit-6` because `move.w <acc>,d0` (`3039 xxxxxxxx`, 6 bytes) precedes the skeleton. The two
absolute operands are then readable straight from the dump, **already relocated**:

```
5c640: 3039 0006d404      move.w $6d404.l,d0      -> X accumulator   = 0x6d404 in this run
5c65c: 33c0 0006d404      move.w d0,$6d404.l      -> clamp written back (the "yoke")
5c66a: 33c0 0006c5ca      move.w d0,$6c5ca.l      -> X rate handed on = 0x6c5ca
```

Disassemble it (68020 option is harmless):

```
python3 tools/m68dis.py /tmp/cock.bin 5c640 --end 5c672 --cpu 68020
```

Who calls it, who reads the output, who touches the accumulator:

```
python3 tools/m68dis.py /tmp/cock.bin --callers 5c640                 # 05be46: bsr.w $5c640
python3 tools/m68dis.py /tmp/cock.bin --xref 6c5ca --lo 30000 --hi 100000   # readers/writers of the output
python3 tools/m68dis.py /tmp/cock.bin --xref 6d404 --lo 30000 --hi 100000   # accumulator users
```

(`--callers`/`--xref` find direct `bsr`/`jsr`/absolute uses only. `--lo/--hi` restricts the scan to
the code range; the game's code in this run is `0x30000-0x70000`.)

The accumulator users in the unpatched dump are exactly these (output of the `--xref 6d404` line
above): `0x4b810 add.l d1,acc` (the poller), `0x5c640`/`0x5c65c` (consumer read / clamp write-back),
clears at `0x58386`, `0x59000`, `0x599fa` (clr.w) and `0x5fa02` (scene setups), and a push/pop of the
high word around the pause handler (`0x36890`/`0x36936`). That list shows the accumulator is fed by
one routine and read by one routine, which is what makes a consume-and-clear patch safe.

### 2.3 Find the poller that feeds it (second worked example)

Mouse hardware read, anchor on the fixed operand `btst.b #6,$bfe001` (`0839 0006 00bfe001`) or
`move.w $dff00a,d0` (JOY0DAT):

```
python3 tools/m68dis.py /tmp/cock.bin --xref dff00a --lo 20000 --hi 100000     # 04b742: move.w $dff00a.l,d0
python3 tools/m68dis.py /tmp/cock.bin 4b716 --end 4b868                         # the mouse poller
python3 tools/m68dis.py /tmp/cock.bin 4b868 --end 4b962                         # joystick poller
python3 tools/m68dis.py /tmp/cock.bin 4b962 --end 4bb5a                         # keyboard poller
python3 tools/m68dis.py /tmp/cock.bin --callers 4b43a                           # 04afd0: jsr 4b43a (VBL handler)
```

What these show (unpatched layout, 2026-11-14; shapes matter, not the numbers):
- `sub_04b43a` is called once per **VBL** from the level-3 interrupt handler (`0x4afb0`): it runs
  the keyboard (`0x4b962`), joystick (`0x4b868`) and mouse (`0x4b716`) pollers in turn, then writes
  `JOYTEST` (`$dff036`) to reset the mouse counters.
- Each poller starts with `tst.w <gate> ; beq return`. The three gate words are the M/J/K
  selection: mouse gate (`0x74ee6`), joystick (`0x74ee2` = mouse-4), keyboard (`0x74ee4` = mouse-2).
  Only the selected device polls. This was proven by the `tst.w` at each poller entry.
- All three end in the same dispatch through a table indexed by the mode word `0x6d458`; mode 2
  (in-game) is the 14-byte routine at `0x4b810`: `add.l d1,<accX> ; neg.l d0 ; add.l d0,<accY> ; rts`.
  d1 = X delta: mouse dx (hi word), or a joystick/key ramp value (+ for right, - for left).
- Mouse deltas are units of half counts (`dx/2` rounded to even); the counter remainder is kept by
  the hardware across the `JOYTEST` reset, so nothing is lost.

### 2.4 Tools you can use on the file instead of RAM

`python3 tools/amigabin.py info MWII` (hunks, relocation counts) and `flat MWII out.bin --base 0`
(relocated image; runtime = base + offset). Skeleton search in the **file** also works and is what
`mw2patch.py` does: file offset = hunk-0 offset + `0x2c`.

---------------------------------------------------------------------------------------------------

## 3. Is the routine really on the executed path? (clamp poke, breakpoint, watchpoint)

Do not argue from the disassembly alone. Three independent proofs, in order of cost:

### 3.1 Clamp poke (cheapest, no breakpoints)

```python
acc = a['acc']                                   # from pr.locate(h) or the dump; unpatched run: 0x6d404
h.write_mem(acc, [0x7fff])                       # write a word with .w semantics
h.resume(); time.sleep(2)
print(hex(pr.word(h, acc)))                      # unpatched: 0x1f4 (=500 = vehicle clamp) -> consumer IS called
```

Unpatched, this printed `0x1f4` and the output word `0x6c5ca` read `0x190` (500 - deadzone 100 = 400):
the consumer ran and clamped. If the value stays `0x7fff` the consumer was **not** called —
but first rule out stale breakpoints (`h.breakpoints()` must be `[]`) and the window still being
in the debugger.

### 3.2 Breakpoint at the routine

```python
h.breakpoint(0x5c640)                            # f 5c640
out = h.run_until_stop(timeout=10)               # g, then wait for the register dump
print(out[-300:])                                # ends with: 0005C640 3039 0006 d404  MOVE.W $0006d404,D0 / Next PC: 0005c646
print(h.breakpoints())                           # f? list:  fl
h.breakpoint(0x5c640)                            # toggles it off again
```

Return addresses / callers: `h.debugger('m a7 4')` shows the stack. The caller seen here was
`0x5be46` (`bsr.w $5c640` in `sub_05be34`), called from the player sim `0x5b7a6` (`bsr.w $5be34`
at `0x5b7fc`), which is entered from `0x5b790` (`tst.w $6a398 ; bne other ; bsr.w $5b7a6`).
`$6a398` was 0 in the cockpit, so the player sim and the consumer run.

### 3.3 Watchpoint on the data

```
w 0 <acc> 4 W       memory watchpoint #0, 4 bytes, break on WRITE   (R = read, I = opcode, F = freeze, C = change)
w 0 <acc> 4 W       the same line again removes it
g
```

When it triggers the register dump shows the PC *after* the writing instruction; here
`0004B816 NEG.L D0` = the instruction after `add.l d1,$6d404` at `0x4b810`, i.e. the poller. A READ
watch (`w 0 <acc> 2 R`) shows who consumes it.

### 3.4 "Not called" versus "called but overwritten"

| What you see | Meaning |
|---|---|
| Poke persists unchanged for seconds, no breakpoint hit, `fl` is empty | routine not called in this state |
| Poke persists, but `fl` lists breakpoints | **you are paused at a stale breakpoint**; clear them with `f <addr>` each |
| Poke changes to a clamped / cleared value | consumer called (value is the consumer's result) |
| Poke changes to a small non-zero number, not a clamp bound | someone else (the poller, every VBL) is adding to it: the poke was overwritten/combined; use a breakpoint or a write watchpoint on the address and read `PC` |
| Breakpoint hits, but the stop is not the address you set | `h._in_debugger` was stale (a breakpoint can stop the CPU on its own); use `h.run_until_stop()` after every `g` |

---------------------------------------------------------------------------------------------------

## 4. The patch: design, in the order it was derived

### 4.1 What the unpatched game does (the reason for the "yoke")

`consumer`: `d0 = clamp(acc_hi, [$14(a0),$16(a0)])`, then **writes d0 back to `acc`**, so the
accumulator is the persistent stick position; `out = sign*(|d0| - deadzone)`. The poller adds to `acc`
every VBL and nobody clears it, so after the mouse stops `out` keeps the last value and the view
keeps turning (and a small push inside the deadzone does nothing at all). Measured on the unpatched
build: a 400-pixel mouse move left `acc` non-zero for good and the heading kept changing (see §5.4).
Joystick/keys feed the same accumulator (ramps), so they have the same problem.

The per-vehicle control block `a0 = <blocks> + type*$3e` has: `+$12` deadzone, `+$14/+$16` lower/upper
X limit, `+$18/+$1a` rate limits (x16), `+$34/+$35` rate selector and scale. The downstream rate
handler multiplies `out` by the scale, clamps it and the heading changes by that >>4 per tick.

### 4.2 The design (same as ST p5, adapted)

1. The poller's mode-2 routine (`0x4b810`, once per VBL for the selected device) is replaced:
   - mouse gate set: `acc += d1` as before (dx);
   - otherwise (J or K): `acc.lo += 1` (VBLs elapsed) and `acc.hi += sign(d1)` (net VBLs held, right
     minus left). `acc` low word is free because mouse d1 has a zero low word.
2. The consumer (`0x5c640`) reads **and clears** `acc` with interrupts masked and then:
   - mouse: `out = hi * 768/256 = 3 * hi`, capped at +-1000 (the ST values: 1.5 per mouse count);
   - J/K: `out = +-50% * (clamp - deadzone) * |net| / elapsed` (held a whole tick: constant,
     released: 0, tap: pro rata); `elapsed == 0` leaves `out` as it was.
3. Y (throttle/pitch) stays as the original; the replaced poller routine re-emits its Y add.

Why a blob: the consumer is 50 bytes with three absolute operands, too small for this logic and it
needs a fourth operand (the gate). The tool appends the new code to the end of CODE hunk 0 (§4.3).
All instructions are 68000 (assembled with `vasmm68k_mot -m68000`), so the A500 path is not blocked.

### 4.3 Relocation: why the patch is safe, and how to keep it so

The file stores every absolute operand as a hunk-relative value (e.g. accumulator `0x400C`) and
lists its position in a `HUNK_RELOC32` table; the loader adds the load address of the target hunk.
So a patch in the **file**:
- must copy operand values from the **file**, never from a RAM dump (those are already relocated);
- every absolute operand it creates must have a RELOC32 entry at its position, otherwise it stays
  `0x0000400C` and points into low memory;
- the in-place variant (50-byte consumer replacement) needs each new operand to sit at an existing
  RELOC32 offset; that is why the old build kept `nop`s at odd places.
The blob variant used now adds the entries itself: `mw2patch.py` assembles `p5_direct.s` twice with
different data-hunk bases and records every 4-byte field that moved by exactly the shift as a RELOC32
entry; the two `jmp <blob>` operands are moved from the DATA group to the hunk-0 group. Everything
else in the file is byte-identical, which the tool checks.

Do not change the order or size of anything in hunks 1..3 or the code before the blob: absolute
addresses in the rest of the program are relocated from the original hunk layout.

---------------------------------------------------------------------------------------------------

## 5. Build and test

### 5.1 Build the patched MWII and the ADF

```
xdftool "games/in_progress/Midwinter-2/originals/Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 1 of 3)[cr SPL].adf" read MWII /tmp/MWII_orig
python3 tools/mw2patch.py find /tmp/MWII_orig
python3 tools/mw2patch.py apply /tmp/MWII_orig /tmp/MWII_new
python3 tools/mw2patch.py apply-adf games/in_progress/Midwinter-2/work/build/d1_skipintro.adf games/in_progress/Midwinter-2/work/build/d1_direct.adf /tmp/MWII_orig
```

Expected output of `find`:
```
cons     0x28588 (hunk-0 offset, file offset 0x285b4)
handler  0x17758 (hunk-0 offset, file offset 0x17784)
acc      0x400c (DATA hunk (1) offset)
accy     0x4010 (DATA hunk (1) offset)
out      0x31d2 (DATA hunk (1) offset)
gate     0xbaee (DATA hunk (1) offset)
```
Expected output of `apply`/`apply-adf`:
```
hunk 0: 217912 bytes, blob appended at +0x35338 (196 bytes)
consumer @ hunk0+0x28588  orig 30390000400cb06800146e06...4e75        (50 bytes, verified)
handler  @ hunk0+0x17758  orig d3b90000400c4480d1b9000040104e75
DATA offsets: acc 0x400c accy 0x4010 out 0x31d2 gate 0xbaee
relocs added to DATA group: 10; moved to hunk-0 group: 2
verify: OK (only the two 6-byte jmp sites changed; blob relocs exact; hunks 1-3 intact)
wrote .../d1_direct.adf
```
`apply` refuses (non-zero exit, message) unless the consumer skeleton, the handler skeleton and the
poller entry each occur exactly once and their operands are consistent; it then re-parses its own
output and checks that only the 12 site bytes changed. Round-trip check of the ADF:
`xdftool d1_direct.adf read MWII /tmp/chk && cmp /tmp/chk /tmp/MWII_new`.

xdftool syntax notes (amitools): `xdftool IMG.adf list`, `xdftool IMG.adf delete NAME`,
`xdftool IMG.adf write HOSTFILE NAME`, `xdftool IMG.adf read NAME HOSTFILE` (the AmigaDOS name is
the LAST argument of `write` and the FIRST of `read`). A file replaced with delete+write moves on
the disk; the patched MWII is 505724 bytes (original 505488) and the disk still has room.

### 5.2 Confirm the patched code is loaded (signature scan)

```python
h = mw.boot_to_cockpit(mw.D1_DIRECT, extra=['joystick_port_1=keyboard'])
a = pr.locate(h)
print({k: hex(v) if isinstance(v, int) else v for k, v in a.items() if k != 'ram'})
```
Seen in the patched run: consumer entry `0x5c640` now holds `4ef9 00069430` (`jmp 0x69430`), the
poller routine `0x4b810` holds `4ef9 000693f0`, the blob is at `0x693f0` (handler) and `0x69430`
(consumer); `acc 0x6d4cc`, `accy 0x6d4d0`, `out 0x6c692`, gate `0x74fae`. (The data hunk moved up by
`0xC8` bytes because hunk 0 grew; that is why you must not reuse unpatched addresses.) Disassemble
the blob to see the relocated operands: `python3 tools/m68dis.py /tmp/cockP.bin 693f0 --end 694b8`.
The old consumer body stays in the file after the `jmp` as dead code; a skeleton search still finds
it (`hit-6` is the `jmp`).

### 5.3 Set the device and the key mapping

M/J/K gates (word each; mouse gate address `G`; J = `G-4`, K = `G-2`):
```python
G = a['gate']
h.write_mem(G, [1]);      h.write_mem(G-4, [0]);      h.write_mem(G-2, [0])        # M (mouse)  [default]
h.write_mem(G, [0]);      h.write_mem(G-4, [0xffff]); h.write_mem(G-2, [0])        # J (joystick)
h.write_mem(G, [0]);      h.write_mem(G-4, [0]);      h.write_mem(G-2, [0xffff])   # K (keypad)
```
J: host `Left`/`Right` arrow keys (config `joystick_port_1=keyboard`). K: host `KP_4`/`KP_6`
(also KP_7/KP_1 and KP_9/KP_3 count as left/right).
Hold a key with `h.key_down('Left')` ... `h.key_up('Left')` (xdotool keydown/keyup).

The state variables that matter, all derived from the accumulator address `acc` of the run (they are in
the same data hunk, so the differences are constant for a given MWII build; verify with
`m68dis --xref` in a new build):
`heading = acc - 0xFF0` (word, 1024 = 360 degrees, even values), `out` from `locate`.

### 5.4 Measurements (all on the same cockpit, jeep, type 1: clamp 500, deadzone 100)

Helper used below:
```python
acc, out, head = a['acc'], a['out'], a['acc'] - 0xFF0
def st(): return dict(head=pr.word(h, head), acc=pr.long(h, acc), out=pr.word(h, out))
```

**Mouse, unpatched (baseline, `d1_skipintro.adf`)** — `pr.regrab(h)`, `h.resume()`, `pr.mouse_burst(h, N)`:

| move | `acc` after motion | `out` | heading |
|---|---|---|---|
| +80 px | `0x260000` (38) | 0 (inside the deadzone 100: no turn at all) | 384 -> 384 |
| +400 px | `0xC60000` (198) | 98 = 198 - 100 | 384 -> 52 (wrapped) -> 100 -> 756 over the next 6 s |

`acc` and `out` stayed at those non-zero values for the whole 9 s of observation (the yoke does not
return), the HUD turn arrow stayed lit, and the heading kept changing while the mouse was still
(it stopped at 756 later; the cause of that plateau was not investigated). This is the behaviour the
patch removes.

**Mouse, patched (`d1_direct.adf`), gate M** — heading is the observable (emulation in warp mode):

| action | heading before | after motion | 3 s idle | 6 s idle |
|---|---|---|---|---|
| mouse +80 px | 294 | 332 | 332 | 332 |
| mouse +160 px | 332 | 410 | 410 | 410 |
| mouse +400 px | 434 | 632 | 632 | 632 |

`acc` and `out` read 0 whenever sampled at rest. The view stops when the mouse stops.

**Mouse, consume-and-clear and cap, tick by tick.** Breakpoint on the store of `out` in the blob
(`0x694ac`), poke `acc`, resume to the next stop, read D0 (the value about to be stored) and `acc`:

| poked acc hi word | D0 at the next tick | acc after | D0 on the following tick |
|---|---|---|---|
| 20 | 60 | 0 | 0 |
| -20 | -60 | 0 | 0 |
| 1 | 3 | 0 | 0 |
| -1 | -3 | 0 | 0 |
| 0x7fff | 1000 (cap) | 0 | 0 |
| -0x7fff | -1000 (cap) | 0 | 0 |

**Joystick/keys, constant rate while held.** Breakpoint at `0x694ac`, `h.key_down('Left')`, loop
`run_until_stop` and print D0 and the heading: D0 = `-200` on every tick while held (exactly
50% of 400 = clamp 500 - deadzone 100); heading `284, 284, 200, 100, 0, 924, 824, 724, 624, 524, 424,
324`, i.e. **-100 units per tick, constant**; after `key_up` D0 = 0 and the heading stays put.

| key | mode | out while held (3 samples) | after release | heading 2 s later |
|---|---|---|---|---|
| Left | J | -200, -200, -200 | 0 | unchanged |
| Right | J | +200, +200, +200 | 0 | unchanged |
| KP_4 | K | -200, -200, -200 | 0 | unchanged |
| KP_6 | K | +200, +200, +200 | 0 | unchanged |

Tap / pro rata (poke `acc` = net<<16 | elapsed at the blob entry `0x69430`, read D0 at `0x694ac`,
J mode): (net 1, elapsed 4) -> 50; (-3, 4) -> -150; (2, 4) -> 100; (4, 4) -> 200; (-1, 5) -> -40;
(5, 4) -> 200 (net > elapsed is clamped to elapsed).

Typical `acc` seen mid-tick in J/K mode: `0xfffc0004` = net -4 of 4 VBLs elapsed (a tick is about 4-5
VBLs here).

### 5.5 Tick structure facts (needed when tuning)

- Player sim = `0x5b7a6`, once per logic tick (4-5 VBLs in the cockpit in this run); the input
  sampler runs every VBL. Hence the "VBLs held / VBLs elapsed" counters.
- Heading change per tick = `(out * scale) >> 4` after the per-type rate clamp (`$18/$1a` times 16).
  For the jeep (scale 8, rate clamp +-100): `out = +-200` -> exactly the rate clamp -> 100 units
  (35 degrees) per tick. So **YAW_PCT 50 is already the vehicle's maximum for the jeep**. For
  on-foot (type 5: clamp 300, deadzone 150) it is `(300-150)*50% = 75` -> 37 units per tick. The
  value is a constant at the top of `patches/p5_direct.s` (`YAW_PCT`); change it and rebuild.
- Mouse gain: `MOUSE_GAIN 768` on the poller's half-count units = 1.5 heading units per mouse count
  before the scale, like the ST. `MOUSE_CAP 1000`.
- Heading is stored in even units; odd per-tick steps floor, so very small per-tick mouse motion is
  slightly asymmetric between left and right (seen in warp mode where ticks see ~1 count).

---------------------------------------------------------------------------------------------------

## 6. Doing it again for another feature (checklist)

1. Boot to the state where the feature is active (§1) in the **unpatched** build.
2. Dump RAM (§2.1). Anchor on something unrelocated (hardware register, a string, a unique constant
   such as `c0fc003e` = `mulu #$3e,d0` for the vehicle table). `--xref`/`--callers` to walk outward.
3. Prove it is on the executed path (§3): clamp/value poke, breakpoint, watchpoint. Record
   the routine start, the caller, the data words, **and the file-level skeleton**.
4. Read the operands from the **file**: `python3 tools/mw2patch.py find MWII` style (skeleton search in
   the hunk-0 data, values are file operand values).
5. Write the replacement; prefer a blob appended to hunk 0 (needs more than the original bytes) and
   let `mw2patch.py` find the relocations. Keep instructions 68000-only.
6. Verify original bytes before replacing; build into a copy under `work/build/`.
7. Boot the copy, locate the new code by signature (§5.2), repeat the measurements (§5.4).

---------------------------------------------------------------------------------------------------

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Poke never changes, breakpoint never fires | Stale breakpoints (`fl`); `fd` does not clear them. `h.clear_breakpoints()`. Also the emulator is stopped until `resume()`. |
| `short memory read` / debugger commands print nothing | The chord `F12+d` opened the FS-UAE menu instead. `debugger()` now holds F12 and retries with Escape; if you drive keys by hand, press Escape and retry. |
| Mouse moves are ignored after a debugger stop | Input grab lost: `pr.regrab(h)` (clicks in the window) before moving. |
| Values written with `W` look wrong / only one byte changes | Use `.w`: `W 6d404 0001.w`. |
| Address from last session is wrong | Addresses move per run and per phase. Run `pr.locate(h)` again; compute data addresses as hunk-1 base + file offset (base = live acc - file acc). |
| `mw2patch.py find` says 0 or 2 hits | A different MWII build (QTX, PRD) or an already patched file. Run on the original SPL `MWII` from the originals disk. |
| xdftool `IOError: image file not found` | A path with `[cr SPL]` brackets/spaces must be quoted; `read` takes `NAME HOSTFILE`, `write` takes `HOSTFILE NAME`. |
| Game shows the "insert disk" prompt in the cockpit run | Mount all three drives as in §1. |
| Patched build boots, steering unchanged | `locate` must report `patched: True` and the consumer entry must start `4ef9`. Check the gate words (§5.3) — in J/K mode with M still 1 both pollers run and the mouse path wins. |
| In J mode keys do nothing | The FS-UAE config lacks `joystick_port_1=keyboard`, or the window has no focus (`h.focus()`). |
| Screenshot shows the FS-UAE menu on the right | The menu is open; press Escape (only when it really is open). |
| `Ungrab input` in the log | Normal after entering the debugger. |

---------------------------------------------------------------------------------------------------

## 8. Finding the game's own clock (VBL counters)

The game's VBL handler ends with the same fingerprint in every load phase:
`jsr <routine>` followed by two `addq.w #1,<abs>` and a `clr.w <abs>`:

```python
import re
m = re.search(rb'\x4e\xb9([\s\S]{4})\x52\x79([\s\S]{4})\x52\x79([\s\S]{4})\x42\x79', ram)
c1 = int.from_bytes(m.group(2), 'big')   # general frame/VBL counter
c2 = int.from_bytes(m.group(3), 'big')   # wrapped-at-6 counter (1/6 s tick)
```

In one observed run these were `$4076` and `$476C` (example only — always
re-derive them in the session's dump). `pr.long(h, c1)` then a `time.sleep(N)`
and a second read gives the vertical-sync rate directly.

Two traps seen while measuring:

- The counters **only advance after `MWII` has installed its handler**. On the
  title/cracktro screen they read a constant 0, which looks like a frozen
  machine but is not: reach the cockpit (§1) before measuring.
- `video_sync=1` with this configuration stopped the emulator entirely
  (`frame_stats` returned 0 frames). Use the default `video_sync=0` and
  `warp=0` for real-time measurements; warp multiplies emulated time and must
  never be used for rate numbers.
