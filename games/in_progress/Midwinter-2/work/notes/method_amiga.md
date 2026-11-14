# Method: porting the ST patch approach to the Amiga

## What the ST project does (read from `AtariST/.../midwinter2`)

- `patches/*.s` are vasm sources with a header: `; name:`, `; site: <runtime addr>`,
  `; orig: <bytes>`, `; data: <addr> <len>`, optional `; phase: boot|deferred`.
  The segment at `org` = site holds the replacement (<= orig length, nop-padded);
  extra segments at a fixed RAM org are the blob payload.
- `tools/mw2patch.py` verifies every original byte, edits the executable image
  (reloc-aware), appends a payload + copy routine, and the boot trampoline then
  re-verifies every boot-phase site in RAM and applies all or nothing
  ('MWPF' marker on mismatch, 'MWPO' on success).
- Addresses were established empirically: RAM dumps, Hatari breakpoints,
  watchpoints, frame counters, and screenshots; never guessed.
- The direct-control patch (`p5_ctl_x`) replaces the per-tick consumer call
  (site `$34152`) with `jsr` to a blob that turns the persistent mouse ramp
  into "dx since last tick" and clears it, and turns the held-joystick/keys
  counts into a constant yaw rate. The VBL patch (`p5_ctl_vbl`) samples held
  direction into VBL counters.

## What that means for the Amiga build

- `MWII` is an Amiga hunk load file. An in-place site patch changes instruction
  bytes only; it travels inside the hunk and the loader's RELOC32 entries still
  relocate the operand fields, so absolute addresses in the replacement are
  fixed up at load time. **No payload or copy routine is needed for a
  consume-and-clear consumer replacement** if it fits inside the original
  routine's bytes (48 bytes for the X consumer, 44 for Y).
- Runtime bases are not stable across load phases: the front-end copy and the
  mission copy of the same routine sit at different addresses, and a live write
  at a stale address was proven wrong (reads returned `$3039`). Addresses must
  therefore be discovered **per session by signature scan**, exactly as the ST
  work used RAM dumps/breakpoints rather than static assumptions.
- Signature used (address-independent, operands excluded):
  `b0680014 6e06 30280014 600a b0680016 6d04 30280016`
  (the clamp/deadzone body of the X consumer).

## Status and next steps

- The consumer routine exists once in the file at flat offset `$28588`
  (front-end copy in the flat image); the mission copy was seen at live
  `$5C640`. A live write at `$5C640` in a later boot did not take effect
  (the data words read `$3039`), so the next step is:
  1. add a `find_signature` helper (dump RAM, locate the skeleton, return the
     live address and its live operands);
  2. apply the consume-and-clear replacement at that live address and prove it
     with `$6D404`/`$6C5CA` before/after mouse motion;
  3. build `tools/mw2patch.py` for the hunk file (site verify + write, no hunk
     size changes) and produce a patched d1;
  4. boot the patched disk and re-run the signature/behaviour check.

## First real patch: mouse consume-and-clear (2026-11-14)

- The consumer exists **once** in `MWII`, at file offset `$285B4` (found by the
  skeleton `b06800146e0630280014600ab06800166d0430280016`; it is preceded by
  `rts`). Pre-relocation linked operands in the file: accumulator `$400C`,
  output `$31D2`; the deadzone helper is at consumer+`$66`.
- `tools/mw2patch.py` verifies the 50 original bytes, builds the replacement
  from the **file's** operands, and writes it back at the same offset:
  ```
  move.w <acc>,d0 / cmp.w $14(a0),d0 / bgt +4 / move.w $14(a0),d0
  cmp.w $16(a0),d0 / blt +4 / move.w $16(a0),d0 / nop
  clr.l <acc> / move.w $12(a0),d1 / bsr deadzone / move.w d0,<out> / rts
  ```
  The new absolute operands sit at exactly the original operands' file offsets,
  so the hunk's existing RELOC32 entries relocate them at load time; no payload
  or trampoline is needed.
- `mw2patch.py apply-adf` builds `work/build/d1_direct.adf` (delete + write via
  xdftool; the written MWII round-trips byte-identically).
- Boot/phased verification is running; the patched skeleton with `bgt +4`
  (`b06800146e0430280014b0680016`) identifies the patched code in RAM.

## Clamp probe on the patched build (2026-11-14)

In the patched cockpit, poking the accumulator `$6D404`:

| poke | value a tick later | verdict |
|---|---|---|
| `$7FFF` | `$7FFF` | consumer did **not** clamp — not called in this state |
| `$0001` | `$01FF` | something re-accumulated (poller active), consumer did nothing |

So the patched routine is correctly loaded but is **not on the executed path**
while the jeep is stationary at mission start; the input poller is running and
accumulating. Next probe (running now): breakpoint on the patched consumer
(matched by the dump's patched skeleton, in-session) and read the registers if
it fires, to find whether/when the control step calls it.

## UAE debugger: breakpoints (2026-11-14)

The console debugger (`F12+d`, `console_debugger=1`) has:

- `f <addr>` add/remove a breakpoint, `fl` list, `fd` remove all;
- `r` registers, `m`/`d` memory/disassembly, `S`/`W` save/write,
- `w <num> <addr> <len> <R/W/I/F/C>` watchpoints, `H` PC history.

Confirmed working: break at the current PC, `g` resumes, and the stop prints a
register dump. The breakpoint probe at the patched consumer (`$5C640`) did
**not** fire while the cockpit sat idle, and the log shows the game looping in
`acquire_mouse`/`get_mouse_flags` — the 3D view is waiting for input before the
vehicle control step runs. The probe is being repeated after a fire click.
