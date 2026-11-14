# Amiga input pipeline (MWII, SPL build)

Runtime address = flat offset + `$270D0`; the flat image is built with
`tools/amigabin.py flat ... --base 0x270D0`.

## 1. Pollers (per VBL / per frame)

| Routine | Reads | Writes | Gate |
|---|---|---|---|
| flat `$1765E` = `$3E75E` | JOY0DAT `$DFF00A` (mouse counts), CIA-A PRA bit 6, POTGOR bit 2 (buttons) | mode 2: `$60414 += dx<<16`, `$60418 += -dy<<16`; modes 0/1: UI pointer clamp `$6040C/$60410` (8..$136, 8..$C3) | `$67EF6` |
| flat `$177B0` = `$3E8B0` | JOY1DAT `$DFF00C` (joystick), CIA-A PRA bit 7 | ramps `$60A20..$60A2C` into `$60A10/$60A18/$60A14/$60A1C`; buttons `$5F6D0` | `$67EF2` |
| flat `$16F6E` = `$3E03E` | CIA-A SDR `$BFEC01` (keyboard serial) | key code `$60AEC`, press flag `$60A0A` | — |

Mode dispatch in the mouse poller: table `$3E722` indexed by `$60468`:
0/1 → UI clamp `$17768`; 2 → in-game accumulate `$17758`.

## 2. Consumer (per logic tick)

`sub_027D7C` (X axis):

```
a0 = $85B98 + $5F3B0*$3E          ; per-vehicle-type table
bsr $28588                        ; clamp/deadzone $60414 -> $5F5DA
d0 = a0->$34 (rate selector)
d1 = a0->$35 (signed scale)
a1 = $4F7E6[d0]; jmp (a1)
```

`sub_028588` itself:

```
d0 = (signed.w) $60414
clamp d0 to [a0->$16, a0->$14]     ; +/- limit
$60414 = d0                        ; <-- writes the value back, never clears
d1 = a0->$12                       ; deadzone
$5F5DA = (|d0| - d1, sign kept)    ; same clamp/deadzone shape as ST $347F2
```

Rate handlers (X): `$27DAE` = derivative `$5F5C6 = (X - prevX) * scale`
(motion-proportional); `$27DCE` = clamp `X*scale` to `a0+$18..$1A`;
`$27DEA` = clamp `X*scale` to `a0+$1C..$1E`, add previous, re-clamp.

`sub_027E1E` is the Y axis mirror: `$5F5DC`, selectors `a0+$31/$32`, table
`$4F7F6`, handlers `$27E50` (derivative), `$27E70` (clamp `a0+$A/$C`),
`$27E8C` (clamp `a0+$E/$10`, add previous, re-clamp).

`$60414/$60418` are cleared only at scene/vehicle setup (`$24 2CE`, `$24F48`,
`$2B94A`, `$2B956`), not per tick.

## 3. Why the yoke persists

`$28588` clamps the **accumulated** mouse displacement and writes it back.
When the mouse stops, `$60414` keeps its last value, so `$5F5DA` (and a rate
handler such as `$27DEA`) keeps commanding the same turn rate. The keyboard
and joystick paths feed the same accumulators/flags, so the same persistence
applies to them. This is the Amiga equivalent of the ST `$6FB6` yoke.

## 4. Direct-controls patch target (mirror of the ST `p5_ctl_*` patch)

- Hook the consumer (`$28588` / `$285BA`): turn the accumulator into a
  per-tick delta, scale it (`MOUSE_GAIN`), cap it, and **clear the
  accumulator**. Keep the existing clamp/deadzone and everything downstream.
- For keys/joystick: add a constant per-tick step while the key/joystick is
  held, zero when released, so the rate is independent of mouse motion and
  stops on release.
- `$5F5DA/$5F5DC` stay the single hand-off to the rate handlers, so the
  patch does not need to touch the per-type tables.

## 5. Live layout differs from the flat image (2026-11-14)

The flat image built at base `$270D0` is **not** the runtime layout: the loader
places the hunks elsewhere (the front end's live poller is at `$44F1E`, not
`$1765E`; the live consumer is at `$55E48`, not `$28588`).

The reliable way to find live addresses is to scan live RAM for the fixed
hardware-register operands, which are never relocated:

```
move.w $DFF00A,d0     30 39 00 0D FF 0A      (mouse counters)
move.w $DFF00C,d2     34 39 00 0D FF 0C      (joystick)
btst.b #2,$DFF016     08 39 00 02 00 DF F0 16
btst.b #6,$BFE001     08 39 00 06 00 BF E0 01
```

Live addresses found this way in the SPL build (menu session, 1 MB dump):

| Purpose | Live address |
|---|---|
| mouse poller | `$44F1E` |
| poller mode | `$66C60` |
| poller gate | `$6E6EE` |
| mouse X accumulator | `$66C0C` |
| mouse Y accumulator | `$66C10` |
| UI pointer X/Y | `$66C04` / `$66C08` |
| button bits | `$66C14` |
| consumer X -> input | `$55E48` -> `$65DD2` |
| consumer Y -> input | `$55E7A` -> `$65DD4` |
| joystick block | `$67208/$67210/$6720C/$6721C` (port 1 ramps) |

The consumer at `$55E48` is byte-for-byte the routine described in §2 with the
live operands. A patch must therefore be built from **live** addresses, or
located at load time by scanning for the poller pattern.

## 6. In-game input is not the mouse poller (2026-11-14)

Live reads in the cockpit (A1200, SPL build): `$66C60` (mode) = 4,
`$6E6EE` (mouse-poll gate) = **0**, `$66C0C` = unchanged when the mouse moves.
The mouse poller (`$44F1E`) early-returns on the zero gate, so in-game steering
is **joystick (port 1, poller `$45070`, gate `$6E6EA`) and/or the keyboard**,
with the mouse reserved for menus.

The direct-controls work must therefore be aimed at the in-game joystick/key
path, not at `$55E48` (which is the menu/mouse-axis consumer). Finding that
consumer and its clamp/rate fields is the next task; the same 1 MB live dump
technique (scan for the fixed hardware operands) applies.

## 7. In-game device selector: M / J / K (2026-11-14)

`sub_0506A0` waits for a key and sets three gates:

| key | d1 `$6E6EE` (mouse) | d2 `$6E6EA` (joystick) | d3 `$6E6EC` (keyboard) |
|---|---|---|---|
| `M` | 0xFFFF | 0 | 0 |
| `J` | 0 | 0xFFFF | 0 |
| `K` | 0 | 0 | 0xFFFF |

Until one is pressed, **all three poll gates are zero and the game ignores all
input** — this is why the cockpit seemed unresponsive in earlier tests.

Pollers:
- mouse `$44F1E` (gate `$6E6EE`), accumulators `$66C0C/$66C10`, consumer `$55E48` -> `$65DD2/$65DD4`;
- joystick `$45070` (gate `$6E6EA`), ramps `$67208..$6721C`;
- keyboard `$4516A` (gate `$6E6EC`), same ramp scheme, key-held flags at `$672E6+$33..$6F`, ramp rates `$67218/$6721C/$67220/$67224`.

## 8. In-game copies and the open consumer (2026-11-14)

The cockpit runs a **second copy** of the poller with different addresses:

| purpose | cockpit | hallway |
|---|---|---|
| mouse poller | `$4B716` | `$44F1E` |
| mouse gate | `$74EE6` | `$6E6EE` |
| mouse acc X/Y | `$6D404` / `$6D408` | `$66C0C` / `$66C10` |
| mode | `$6D458` | `$66C60` |
| M/J/K selector | `$56E90` stores `$74EE6/$74EE2/$74EE4` | `$506A0` |

Forcing the cockpit gate `$74EE6` alone did not make the view respond to mouse
motion, and a 1 MB cockpit dump contains **no reader of `$6D404`** (only the
poller, stack saves at `$36892/$36938`, and scene clears). The cockpit dump has
no `JOY1DAT` access either. So the steering consumer is **not in the first
1 MB**: either it sits above `$100000` (fast RAM) or it reads the accumulators
through a base register. Next probe: dump `$100000-$200000` in the cockpit and
search for `$6D404`/`$6D408` readers, or set a breakpoint on the poller's mode-2
handler and follow the value.
