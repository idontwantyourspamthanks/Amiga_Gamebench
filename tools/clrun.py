#!/usr/bin/env python3
"""Launch the gamebench images in Copperline (windowed, real time) - what dist/run_*.sh call.

    clrun.py hd                      # boot the newest hard-disk image to the Workbench desktop (changes persist)
    clrun.py hd mw2                  # ...on a scratch copy that starts Midwinter II by itself (saves are NOT kept)
    clrun.py hd mw2orig              # the unpatched game, for comparison
    clrun.py floppy mw2 [--original] # the three-floppy set (patched d1_direct.adf unless --original)
    options: --image F  --model A1200|A600|A500  --fast 8M  --cpu 68030 --clock 50  --scale 2
             --no-warp  --print-config  --shot SECS OUT.png   (headless: screenshot and exit, for testing)

The hard-disk image is an RDB disk: Workbench 3.1 + one partition per game.  Without a GAME it is
the real thing - Workbench, then open a game's volume and double-click Play.  With a GAME the
launcher boots a scratch copy whose S:User-Startup runs the game (the image is never modified).
Needs tools/bin/copperline (tools/fetch_copperline.sh) and the Kickstart 3.1 ROM in os/Kickstart.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import amigahd  # noqa: E402
from clharness import Machine, Schedule, capture, copperline_bin  # noqa: E402

MW2 = ROOT / "games/in_progress/Midwinter-2"


def newest_image() -> Path:
    found = sorted(glob.glob(str(ROOT / "dist" / "Amiga_enhanced_games_*.hdf")))
    if not found:
        raise SystemExit("no dist/Amiga_enhanced_games_*.hdf: build one with tools/make_amiga_hd.py")
    return Path(found[-1])


def floppy_set(original: bool) -> list[Path]:
    orig = MW2 / "originals"
    d1 = next(orig.glob("*Disk 1 of 3*SPL*.adf"), None)
    d2 = next(orig.glob("*Disk 2 of 3*SPL*.adf"), None)
    d3 = next(orig.glob("*Disk 3 of 3*SPL*.adf"), None)
    patched = MW2 / "work/build/d1_direct.adf"
    if not original and patched.exists():
        d1 = patched
    if not (d1 and d2 and d3):
        raise SystemExit("Midwinter II disks not found under games/in_progress/Midwinter-2/originals")
    return [d1, d2, d3]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=("hd", "floppy"))
    ap.add_argument("game", nargs="?")
    ap.add_argument("--image")
    ap.add_argument("--original", action="store_true")
    ap.add_argument("--model", default="A1200")
    ap.add_argument("--fast", default="8M")
    ap.add_argument("--cpu")
    ap.add_argument("--clock", type=float)
    ap.add_argument("--scale", type=float, default=2.0)
    ap.add_argument("--no-warp", action="store_true")
    ap.add_argument("--print-config", action="store_true")
    ap.add_argument("--shot", nargs=2, metavar=("SECS", "PNG"))
    a = ap.parse_args(argv)

    # no rtc_time: unlike the tests, a player's machine keeps real time
    m = Machine(model=a.model, fast=a.fast if a.fast != "0" else None, cpu=a.cpu, cpu_clock=a.clock, rtc_time=None)
    tmp = Path(tempfile.mkdtemp(prefix="clrun-"))
    if a.kind == "hd":
        image = Path(a.image) if a.image else newest_image()
        if a.game:
            if a.game not in amigahd.GAMES:
                raise SystemExit(f"unknown game {a.game!r}; choose from {', '.join(sorted(amigahd.GAMES))}")
            scratch = tmp / "scratch.hdf"
            amigahd.scratch(image, scratch, amigahd.autorun_script(a.game))
            image = scratch
        m.ide = image
    else:
        if a.game not in (None, "mw2"):
            raise SystemExit("floppy sets: mw2")
        m.floppies = floppy_set(a.original)

    cfg = m.write_config(tmp / "machine.toml")
    if a.print_config:
        print(cfg.read_text())
        return 0
    if a.shot:
        secs, png = float(a.shot[0]), a.shot[1]
        r = capture(m, Schedule().shot(secs, png))
        print(f"rc={r.returncode} wall={r.wall:.0f}s -> {png}")
        return r.returncode
    cmd = [copperline_bin(), "--config", str(cfg), "--window-scale", str(a.scale)]
    if not a.no_warp and a.kind == "hd":
        cmd.append("--warp-boot")                 # unpaced until the boot storage goes idle, then real time
    os.execv(cmd[0], cmd)


if __name__ == "__main__":
    sys.exit(main())
