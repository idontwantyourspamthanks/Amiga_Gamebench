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
