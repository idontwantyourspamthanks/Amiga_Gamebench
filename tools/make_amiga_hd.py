#!/usr/bin/env python3
"""Build the Amiga "enhanced games" hard-disk image (HDF) from the patched builds.

    python3 tools/make_amiga_hd.py            # build dist/Amiga_enhanced_games_<date>.hdf
    python3 tools/make_amiga_hd.py --size 64  # bigger volume

The image is a plain FFS hardfile (no RDB): FS-UAE mounts it with
`hard_drive_0=<file>` and the Amiga boots it directly (verified, Workbench 3.1,
Kickstart 3.1).  It boots Workbench and S:User-Startup starts the game.

Layout
  Games:                  volume (FFS, DOS\\1)
  Games:C,Libs,Devs,S,... Workbench 3.1 (from os/WorkBench/amiga-os-310-workbench.adf)
  Games:root              Midwinter II, patched: mwII + progdir + midword.fsd +
                          cods.bin + grafix/ + grafdir + missions/ + missdir
                          (the game only runs from the volume root)
  Games:ORIG/             the unpatched mwII (comparison)
  Games:README.txt

Requires xdftool/xdftool (amitools) on PATH.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIG = ROOT / "games/in_progress/Midwinter-2/originals"
BUILD = ROOT / "games/in_progress/Midwinter-2/work/build"
WB = ROOT / "os/WorkBench/amiga-os-310-workbench.adf"

D1 = ORIG / "Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 1 of 3)[cr SPL].adf"
D2 = ORIG / "Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 2 of 3)(Graphics)[cr SPL].adf"
D3 = ORIG / "Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 3 of 3)(Missions)[cr SPL].adf"


def run(*cmd: str) -> None:
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"{' '.join(cmd[:3])}...: "
                         f"{(r.stderr or r.stdout).decode(errors='replace')[:300]}")


def unpack(adf: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    run("xdftool", str(adf), "unpack", str(dest))
    subs = [p for p in dest.iterdir() if p.is_dir()]
    return subs[0] if len(subs) == 1 else dest


def mw2_tree(stage: Path, exe_name: str | None, src: Path) -> None:
    """Populate `stage` with what the game's own DH0 installer would copy.

    The installer copies every file to the ROOT of DH0: and the game only starts
    from there (a sub-drawer gives the "insert graphics disk" prompt), so the
    files must land at the volume root.  `exe_name` replaces mwII with a patched
    build from work/build (None keeps the original).
    """
    d1, d2, d3 = [next(p for p in (src / n).iterdir() if p.is_dir()) for n in ("d1", "d2", "d3")]
    stage.mkdir(parents=True, exist_ok=True)
    exe = BUILD / exe_name if exe_name else d1 / "MWII"
    if not exe.exists():
        raise SystemExit(f"missing {exe}; build it with tools/mw2patch.py apply-adf")
    shutil.copyfile(exe, stage / "mwII")
    for name in ("progdir", "midword.fsd", "cods.bin"):
        shutil.copyfile(d1 / name, stage / name)
    shutil.copytree(d2, stage, dirs_exist_ok=True)
    shutil.copytree(d3, stage, dirs_exist_ok=True)


def write_tree(hdf: Path, tree: Path) -> None:
    for entry in sorted(tree.iterdir()):
        run("xdftool", str(hdf), "write", str(entry))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=32, help="volume size in MiB (default 32)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if shutil.which("xdftool") is None:
        raise SystemExit("xdftool (amitools) not found")

    out = Path(args.out) if args.out else ROOT / "dist" / f"Amiga_enhanced_games_{dt.date.today():%Y-%m-%d}.hdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="amigahd-") as tmp:
        tmp = Path(tmp)
        tree = tmp / "hd"
        wb = unpack(WB, tmp / "wb")
        shutil.copytree(wb, tree)
        src = tmp / "src"
        for adf, name in ((D1, "d1"), (D2, "d2"), (D3, "d3")):
            unpack(adf, src / name)
        mw2_tree(tree, "MWII_direct", src)
        orig = tmp / "orig"
        mw2_tree(orig, None, src)
        shutil.copytree(orig, tree / "ORIG")

        user_startup = tree / "S/User-Startup"
        user_startup.parent.mkdir(parents=True, exist_ok=True)
        user_startup.write_text(
            "; Boots to the Workbench desktop.\n"
            "; The games are in the root of this volume; double-click an icon to start\n"
            "; one.  To start Midwinter II from a Shell instead:\n"
            ";     CD Games:  then  mwII\n"
        )
        # A generic tool icon so the game can be started from the desktop
        icon_src = tree / "Utilities/Clock.info"
        if icon_src.exists():
            shutil.copyfile(icon_src, tree / "mwII.info")
        (tree / "README.txt").write_text(
            "Amiga enhanced games\n\n"
            "Midwinter II (patched: direct controls) is installed in the root of\n"
            "this volume, exactly where the game's own DH0 installer puts it.\n"
            "ORIG/ holds the unpatched mwII for comparison (do not run it from there:\n"
            "copy it to the root as mwII to test the original behaviour).\n\n"
            "The patched build is started automatically from S:User-Startup.\n"
            "Comment that file out to boot to the Workbench desktop.\n"
            "Controls: mouse turns the view by its motion; M/J/K selects mouse,\n"
            "joystick or keypad. Original: the view keeps turning after the mouse stops.\n"
        )

        if out.exists():
            out.unlink()
        size_bytes = args.size * 1024 * 1024
        with open(out, "wb") as fh:
            fh.truncate(size_bytes)
        run("xdftool", str(out), "format", "Games", "ffs")
        write_tree(out, tree)
        run("xdftool", str(out), "boot", "install")

    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
