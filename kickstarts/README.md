# Kickstart ROMs

Put your own Kickstart images here. They are copyrighted and are **not**
committed; this directory is git-ignored apart from this file.

FS-UAE also ships the open-source AROS ROM. It boots, but it is not a
substitute for testing: AROS differs from Kickstart in timing, in the
filesystem and in several libraries, so gates must run on real Kickstart.

## What the harness needs

| File name | Machine | Notes |
|---|---|---|
| `os/Kickstart/amiga-os-130.rom` | A500, A500+ | 256 KB, Md5 `82a21c18…`, Kickstart 1.3 rev 34.5. |
| `os/Kickstart/amiga-os-205-a600.rom` | A600 | 512 KB, Md5 `465646c9…`, Kickstart 2.05. |
| `os/Kickstart/amiga-os-310-a1200.rom` | **A1200 (target)** | 512 KB, Md5 `64677375…`, Kickstart 3.1 rev 40.68. Boots the game. |
| `os/Kickstart/amiga-os-310-a600.rom` | A600 | 512 KB, Md5 `e40a5dfb…`, Kickstart 3.1 rev 40.63. |

The harness searches both this folder and `os/Kickstart/`. The 1.3 ROM is also copied here as `kickstart-1.3-a500-a500plus.rom`.

`tools/amigaharness.py` picks the ROM by machine unless you pass one
explicitly. `tools/amigaharness.py roms` lists what is present and what each
one is, by MD5.

## If a required ROM is missing

The harness starts but prints which ROM it used. Runs that fall back to AROS
are marked `[AROS]` in the log and must not be used for compatibility or
performance gates.
