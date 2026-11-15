# Kickstart ROMs

Put your own Kickstart images in `os/Kickstart/` (this folder is an alternative home for them). They are copyrighted and are **not** committed.

Copperline ships an open-source AROS ROM and boots it when no ROM is configured. It is not a substitute for testing: AROS differs from Kickstart in timing, in the filesystem and in several libraries, so gates must run on real Kickstart. `tools/clharness.py` (`Machine`) always passes the Kickstart below, never AROS.

## What the harness uses

| File | Machine | Notes |
|---|---|---|
| `os/Kickstart/amiga-os-130.rom` | A500 | 256 KB, Md5 `82a21c18…`, Kickstart 1.3 rev 34.5. |
| `os/Kickstart/amiga-os-205-a600.rom` | A600, A500Plus | 512 KB, Md5 `465646c9…`, Kickstart 2.05. |
| `os/Kickstart/amiga-os-310-a1200.rom` | **A1200 (target)** | 512 KB, Md5 `64677375…`, Kickstart 3.1 rev 40.68. Boots the game. |
| `os/Kickstart/amiga-os-310-a600.rom` | A600 | 512 KB, Md5 `e40a5dfb…`, Kickstart 3.1 rev 40.63. Not selected by default; pass `Machine(rom=...)`. |

Copperline identifies a ROM by checksum and prints it in its start-up `config:` log line (for example `Kickstart 3.1 (40.68) A1200`), so a wrong or renamed file is visible in any run log. Pass another file with `Machine(rom="path")`.

## If a required ROM is missing

`pytest` skips the emulator tests with the reason, `tools/clrun.py` stops with the path it looked for, and the harness never falls back silently.
