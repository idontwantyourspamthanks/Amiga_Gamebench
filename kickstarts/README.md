# Kickstart ROMs

Put your own Kickstart images here. They are copyrighted and are **not**
committed; this directory is git-ignored apart from this file.

FS-UAE also ships the open-source AROS ROM. It boots, but it is not a
substitute for testing: AROS differs from Kickstart in timing, in the
filesystem and in several libraries, so gates must run on real Kickstart.

## What the harness needs

| File name (expected) | Machine | Notes |
|---|---|---|
| `kickstart-1.3-a500-a500plus.rom` | A500, A500+ | 256 KB. Kickstart 1.3 rev 34.5. |
| `kickstart-2.04-a500plus-a600.rom` | A500+, A600 | 512 KB. Useful for the ECS path. |
| `kickstart-3.1-a1200.rom` | **A1200 (target)** | 512 KB. This is the one the port is gated on. |

`tools/amigaharness.py` picks the ROM by machine unless you pass one
explicitly. `tools/amigaharness.py roms` lists what is present and what each
one is, by MD5.

## If a required ROM is missing

The harness starts but prints which ROM it used. Runs that fall back to AROS
are marked `[AROS]` in the log and must not be used for compatibility or
performance gates.
