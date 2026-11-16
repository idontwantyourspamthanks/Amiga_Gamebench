# Midwinter II (Amiga) v1.0: release report

Credit line: `Midwinter II v1.0 enhanced by dad_prg` (shown at start-up and in the READMEs).
Base: the SPL three-disk release (`originals/`, MD5s in `README.md`); originals are never modified.

## What changed in the game

| Change | How | Gate |
|---|---|---|
| **Direct controls**: mouse turns by its motion and stops; joystick/keys turn at a constant rate while held (±200 per tick for the jeep) and stop on release | `patches/p5_direct.s`, blob appended to CODE hunk 0, two `jmp` sites (`tools/mw2patch.py`, site-verified, all-or-nothing) | `tests/test_mw2_direct_controls.py`: poke -> exact turn value, cap ±1000, consume-and-clear, real injected mouse, joystick; the unpatched volume keeps the old "yoke" (negative control). The user confirmed it on foot and in the plane; other vehicles untested |
| **Device selector restored** ("Press 'M' / 'J' / 'K'") | the SPL crack had NOPed the call (found by diffing the Quartex release); 4-byte `bsr.w` restored | `test_device_selector_is_offered_and_sets_the_gates` (M, J, K each reach the hallway and set the game's gates) |
| **Clean start-up** | floppy disk 1: new `s/startup-sequence` (credit line, no cracker text), `startup-sequence.bak` removed, INTRO's demo loop skipped (6 bytes; removing INTRO makes mwII fail) | `mw2release.py --check`, `tests/test_release.py` (real three-floppy boot to the hallway) |

## What ships (`dist/`, git-ignored)

```
  d91d9f2adb0d98d4f523e0ae8e1e8c1e  Midwinter2_v1.0_patched_2026-11-16.zip
  3befc3d08b2bd3f58dd58c2b271ddc3c  Midwinter2_v1.0_patched_floppies_2026-11-16.zip
```
- floppies zip: three ADFs + README (disk 1 patched; disks 2 and 3 are the unmodified originals).
- hard-drive zip: `MW2HD/` = the files the game's own installer copies (to the volume **root**) + `Play`, `Play.info`, README. `Play` needs no volume name.

## Evidence (Copperline 1.1.0, A1200, Kickstart 3.1.40.68, 8 MB fast)

- `python3 -m pytest tests`: see the commit message / last run; static, VHD, HD-image boot, bit-exact LoadSeg, desktop click-through, direct-controls gate, release content and floppy boot.
- Release floppies: three drives, disk 1 boots, the credit shows, the selector appears, M reaches the hallway at about 137 s of emulated time (real floppy speed).
- The all-games hard-disk image (`dist/Amiga_enhanced_games_<date>.hdf`/`.vhd`) is the development and test vehicle, not part of this release.

## Not in v1.0 (honest list)

- World-rate decoupling (whether the sim is frame-locked as on the ST): unmeasured, see PLAN P4.
- Rendering speed-ups (P6). In-game credit text (the credit is at start-up and in the READMEs only).
- Real hardware (A1200 with CF/IDE) and A500/A600 runs: never tried. Single-drive floppy swaps: not tested.
- After choosing J or K the game drives its menus with that device; our harness only navigates with M.
- The unpatched INTRO file on disk 1 still contains the cracker's demo text (its loop is skipped and never runs).
