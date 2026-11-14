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
