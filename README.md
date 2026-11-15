# gamebench (Amiga)

**Speeding up and modernising classic Amiga games by patching them, without their source code.**

This is the Amiga counterpart of [`AtariST/gamebench`](../../AtariST/gamebench): tools, patches, tests and working notes, plus an all-games hard-disk image in which each game is a volume you open and run. It does **not** contain any game, Kickstart ROM or anything extracted from them; you supply your own copies.

Current work: **Midwinter II: Flames of Freedom** (1991, Rainbird) on a fast **Amiga 1200**. The Atari port of the same game is done (`AtariST/gamebench/games/done/midwinter2`). The goal here is the same behaviour:

- the world runs at its original rate whatever the CPU speed;
- **direct controls**: the mouse turns the view by its motion and stops when it stops; joystick/keys turn at a constant rate while held and stop on release (no "yoke");
- faster drawing with an identical picture;
- a release that runs on a real A1200, shows a version credit (`vX.Y enhanced by dad_prg`), and leaves the originals untouched.

Every patch tool verifies each original byte it replaces and refuses to build against anything else.

## Emulator: Copperline

All emulation, navigation, measurement and testing uses [Copperline](https://copperline.dev) (deterministic, headless, JSON-RPC control). `tools/fetch_copperline.sh` installs it into `tools/bin/`. Headless runs need no display server and run unthrottled (a 30 s Workbench boot takes about 6 s). The harness is `tools/clharness.py`; the method is in `.omp/skills/amiga-copperline/SKILL.md`.

## Status

| Item | State |
|---|---|
| Bench: ADF/hunk tools, disassembler, Copperline harness, skills | built |
| Hard-disk image (RDB: Workbench 3.1 + one volume per game) and fixed VHD | built; boots to the Workbench desktop |
| Tests | `python3 -m pytest tests`: 27 pass (static, VHD, HD boot, bit-exact load, desktop click-through, direct-controls gate) |
| Midwinter II on A1200 / KS 3.1 | boots and plays from the HD image and from three floppies |
| Direct controls | done and gated tick by tick (`patches/p5_direct.s`, `tools/mw2patch.py`, `tests/test_mw2_direct_controls.py`); method in `games/in_progress/Midwinter-2/work/notes/direct_controls_howto.md` |
| World rate (VBL-locked or CPU-bound?) | open: needs the Copperline measurement (`PLAN.md` P4) |
| Rendering, credit line, A500/A600 runs, real-hardware test | not started / not verified |
| Midwinter (1) | disks collected; not started |

## Run a game

```sh
tools/fetch_copperline.sh                 # once
python3 tools/mw2patch.py apply <MWII from disk 1> games/in_progress/Midwinter-2/work/build/MWII_direct   # once
python3 tools/make_amiga_hd.py            # dist/Amiga_enhanced_games_<date>.hdf + .vhd + .layout.txt

dist/run_hd.sh                            # Workbench desktop; open Midwinter2, double-click Play
dist/run_mw2.sh                           # straight into Midwinter II (scratch copy: saves not kept)
dist/run_mw2_floppy.sh                    # the three-floppy set
dist/run_hd.sh mw2orig                    # the unpatched game, for comparison
```
Options: `--model A600|A500`, `--cpu 68030 --clock 50`, `--scale 3`, `--image FILE`, `--no-warp`.

## The hard-disk image

An RDB disk (so it mounts in emulators and on real hardware), geometry 16 heads x 63 sectors:

| dev | volume | contents |
|---|---|---|
| DH0 | Workbench | Workbench 3.1 (bootable), `ReadMe.txt` |
| DH1 | Midwinter2 | patched game at the volume root + `Play` |
| DH2 | Midwinter2Orig | the unpatched game + `Play` |

- Each game has its own volume: it only runs from the **root** of its volume.
- `Play` is a script behind an IconX project icon: the game needs a CLI process (started as a Workbench tool it Gurus).
- **Every partition has `MaxTransfer = 0x1FE00`.** With the default the A1200's IDE path returns wrong data for reads over 128 KiB and the game crashes at start. `tests/` guards this.
- Adding a game = a `Part(...)` and a `stage_*` function in `tools/make_amiga_hd.py`, an entry in `tools/amigahd.py` `GAMES`, and a game harness (see the skill).
- The shipped image is never touched by tests or `run_hd.sh GAME`: they boot a scratch copy whose `S:User-Startup` starts the game (`tools/amigahd.py scratch`).

`dist/Midwinter2-Amiga-hd-<date>.zip` (`tools/make_amiga_zip.py`) is the install-into-your-own-partition alternative.

## Tests

```sh
python3 -m pytest tests -m "not emu"      # static: config, icon format, image structure, patch verify, VHD (seconds)
python3 -m pytest tests                   # + emulator: real boots (about 5 minutes)
python3 tools/test_hd_image.py dist/<image>.hdf mw2     # one game, power-on to cockpit, one RESULT line
python3 -m pytest tests --bless           # re-record goldens (frame hashes) after an intended change
```
Goldens are frame hashes in `tests/goldens.json` (no pictures are committed) and are valid for the emulator version and image they were recorded with.

## Layout

| Path | What |
|---|---|
| `tools/clharness.py` | Copperline harness: `Machine` (config), `capture` (scheduled headless runs), `Session` (control protocol) |
| `tools/clrun.py` | what `dist/run_*.sh` call: build a config and start Copperline windowed |
| `tools/make_amiga_hd.py`, `amigahd.py`, `amigaicon.py` | build the RDB image + VHD; scratch copies with an autorun; Workbench `.info` writer |
| `tools/test_hd_image.py` | boot one game from the image to its in-game view |
| `tools/adf.py`, `amigabin.py`, `m68dis.py` | ADF images, hunk load files, 68k disassembler |
| `tools/fetch_copperline.sh` | install Copperline into `tools/bin/` (git-ignored) |
| `tests/` | pytest suite and `goldens.json` |
| `games/in_progress/<game>/` | per-game README, PLAN, `patches/`, `tools/` (game harness, patch tool), `work/notes/` |
| `kickstarts/`, `os/` | your Kickstart ROMs and Workbench disks (git-ignored) |
| `.omp/skills/` | method, Copperline, ADF/hunk and delegation notes for the agent |

## Requirements

- Linux, Python 3.10+, `pytest`; Copperline (fetched by the script above; no Vulkan/display needed headless, a window needs Vulkan).
- `amitools` (`xdftool`, `rdbtool`), `vasmm68k_mot` (patch assembly), Python `capstone`, `numpy`/`Pillow` for some tools.
- Your own Kickstart ROMs (`os/Kickstart/`; 3.1 for the A1200 target).

## Machines and targets

- **Target: a fast Amiga 1200** (68020/030, AGA, Kickstart 3.1).
- Nothing may break on a plain A500/A600 where the original works. This is **not yet tested**; Copperline models them (`--model A500|A600`).
- **Pixel-identical by default**; visual tradeoffs need before/after pictures and approval.
- **Deliverables:** patched copies, never modified originals; a verifying patch tool; images and launchers; the version credit line.

## Getting the game files

The chosen Midwinter II release is the three-disk SPL set. Put your copies in `games/in_progress/Midwinter-2/originals/` (git-ignored); the per-game README lists MD5 sums.

## Credits and legal

- *Midwinter* and *Midwinter II: Flames of Freedom* are © Maelstrom Games / Rainbird / MicroProse.
- Kickstart and Workbench are © Commodore/Cloanto. None are included here.
- Copperline is GPL-3.0-or-later (https://copperline.dev); it is downloaded, not bundled.
- The code and documentation in this repository are released under the MIT licence (see `LICENSE`).
