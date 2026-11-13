# Midwinter (Amiga, 1990)

*Midwinter*, Rainbird, 1990. Amiga conversion of the game whose Atari ST port is finished in `AtariST/gamebench/games/done/midwinter`.

Status: **disks collected, not started.** Midwinter II is the current job; this folder exists so its disks and findings are not lost.

## Supplied images

| File | MD5 | Format |
|---|---|---|
| `Midwinter (1990)(Rainbird)[cr Defjam - CCS - ACC].adf` | `e4445d113a0a355a8937306bef5f9f7b` | non-DOS bootblock, custom trackloader |
| `...[a].adf` | `f005048f26807ad31994152bee3da029` | non-DOS |
| `...[a2].adf` | `f5cf9c70252323b57f0f81645e5977fc` | non-DOS |
| `...[h TTC].adf` | `2ab38cc69efa24ef424875fda5d14cc1` | non-DOS |
| `...[f save PDX].adf` | `0b16c0de0068012cab2d90f9620e296c` | non-DOS |

All five fail `xdftool` with `Invalid Root Block`; the bootblock is `DOS` + a custom loader (the "DOS" copies at +0x11 are fill), not AmigaDOS. There is no file-level access: any work has to be byte-level inside the image, and the trackloader's own framing/checksums must be understood first.

Open questions: whether one variant is a plain AmigaDOS release (none seen), and which crack is the least modified. The `[h TTC]` bootblock differs from the other four and deserves its own look before choosing a base.
