# gamebench (Amiga)

**Speeding up and modernising classic Amiga games by patching them, without their source code.**

This is the Amiga counterpart of [`AtariST/gamebench`](../../AtariST/gamebench). It holds the tools, the patches and the working notes. It does **not** contain any game, any Kickstart ROM, or anything extracted from them; you supply your own copies.

Current work: **Midwinter II: Flames of Freedom** (1991, Rainbird), targeting a fast **Amiga 1200** from **floppy disks only**. The Atari port of the same game is done: see `AtariST/gamebench/games/done/midwinter2`. The goal here is the same behaviour:

- the world runs at its original 5 Hz whatever the CPU speed, so accelerators do not make the game run fast;
- **direct controls**: the mouse turns the view by its motion and stops when it stops; the joystick/keys turn at a constant rate while held and stop on release, instead of the original "yoke" that keeps a turn rate;
- faster drawing with an identical picture, and no redraw when nothing changed;
- a floppy-only release that boots on a real A1200, shows a version credit, and leaves the originals untouched.

Nothing in this repository is a game file. The patch tools verify every original byte they replace and refuse to build against anything else.

## Status

| Item | State |
|---|---|
| Bench (layout, ADF/hunk tools, disassembler, FS-UAE harness, skills) | built |
| Kickstart ROMs | 1.3, 2.05, 3.1 (A1200 and A600) present in `os/Kickstart/`; A1200 3.1 boots the game |
| Disk versions | chosen and documented in `games/in_progress/Midwinter-2/README.md` |
| Midwinter II port | **boots and plays on A1200 3.1**: three drives, held-press menu, in-game cockpit (`work/shots/mw2_ingame_a1200.png`); play launcher `dist/run_mw2.sh`; in-game input is joystick/keyboard; **direct controls done**: mouse turns in proportion to motion and stops, joystick/keys turn at a constant rate while held (`patches/p5_direct.s`, `tools/mw2patch.py`, built into `work/build/d1_direct.adf`, measured live; method in `games/in_progress/Midwinter-2/work/notes/direct_controls_howto.md`). Open: whether the world clock is VBL-locked or CPU-bound — emulator real-time parity is measured, the game-counter A1200-vs-A500 test is not yet valid (`work/notes/timing_baseline.md`) |
| Midwinter (1) | disks collected; not started |

## Machines and targets

The user's standing preferences, carried over from the Atari project:

- **Target: a fast Amiga 1200** — 68020/68030, AGA, 2 MB chip RAM plus fast RAM, Kickstart 3.1, booting from floppy.
- Nothing may break on a plain A500/A600 (OCS/ECS, 68000, Kickstart 1.3/2.04) where the original works. A500/A500+ runs are the fast regression loop while the A1200 ROM is unavailable; they are **not** evidence about A1200 behaviour.
- **Pixel-identical by default.** Any visual tradeoff needs before/after screenshots and explicit approval.
- **Direct controls** as described above.
- **Deliverables:** patched copies, never modified originals; a patch tool that verifies original bytes; floppy images; `play.sh`-style launchers; a version and credit line (`vX.Y enhanced by dad_prg`) visible at startup and in the README and image names.

## Layout

| Path | What |
|---|---|
| `tools/amigaharness.py` | Headless FS-UAE harness. Private Xvfb display per instance, screenshots, keyboard/mouse, the UAE console debugger (`m`, `S`, `W`, `f`, `c`, `e`), frame statistics. |
| `tools/adf.py` | ADF images: track/sector access, bootblock validation, `xdftool` file listing/unpack, sector-level diffs. |
| `tools/amigabin.py` | Amiga hunk load files: parse, list segments and relocations, build a flat image with relocations resolved, at a chosen base. |
| `tools/m68dis.py` | 68000/68020 disassembler for flat images and RAM dumps, with call labels, xrefs and Amiga hardware-register annotations. |
| `kickstarts/` | Your Kickstart ROMs (git-ignored). `kickstarts/README.md` lists the expected names. |
| `os/` | Workbench/Extras disk images for building boot disks and testing (git-ignored). |
| `.omp/skills/` | Method, harness, ADF/hunk and delegation notes for the agent. |
| `games/in_progress/<game>/` | One folder per game: chosen disks, README, PLAN, `work/notes/`. |

## Requirements

- Linux, Python 3.10+, `fs-uae` 3.2+ (Ubuntu package is fine), `Xvfb`, `xdotool`, ImageMagick (`import`).
- Python `capstone` (disassembly) and `amitools` (`xdftool`, filesystem access).
- `vasmm68k_mot` (vasm, Motorola syntax) for assembling patches.
- Your own Kickstart ROMs in `kickstarts/`.

## Quick start

```sh
python3 tools/amigaharness.py roms                  # what ROMs are available, what is missing
python3 tools/amigaharness.py run --machine A500 --seconds 20 --screenshot /tmp/shot.png \
    games/in_progress/Midwinter-2/originals/'...Disk 1 of 3...[cr SPL].adf'
python3 tools/adf.py info  <disk.adf>               # bootblock + filesystem summary
python3 tools/adf.py diff  <a.adf> <b.adf>          # sector-level changes only
```

## Getting the game files

The chosen Midwinter II release is the three-disk SPL set (program / graphics / missions). Put your own copies in `games/in_progress/Midwinter-2/originals/`; the folder is git-ignored. The per-game README lists MD5 sums and why that release was chosen.

## Credits and legal

- *Midwinter* and *Midwinter II: Flames of Freedom* are © Maelstrom Games / Rainbird / MicroProse.
- Kickstart and Workbench are © Commodore/Cloanto. None are included here.
- The code and documentation in this repository are released under the MIT licence (see `LICENSE`).
