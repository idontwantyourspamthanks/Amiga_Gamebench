#!/usr/bin/env python3
"""Build the hard-disk install zip for the patched Midwinter II (Amiga).

    python3 tools/make_amiga_zip.py  ->  dist/Midwinter2-Amiga-hd-<date>.zip

The archive holds exactly what the game's own DH0 installer copies: the
executable and data at the TOP level (the game only runs from the root of the
volume), plus an AmigaDOS install script and a README.

Install on an Amiga:
    copy the zip's contents to a drawer, then from a Shell:
        execute MW2Install
    (edit the DH0: in MW2Install to your volume name first)
"""
from __future__ import annotations

import datetime as dt
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIG = ROOT / "games/in_progress/Midwinter-2/originals"
BUILD = ROOT / "games/in_progress/Midwinter-2/work/build"
D1 = ORIG / "Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 1 of 3)[cr SPL].adf"
D2 = ORIG / "Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 2 of 3)(Graphics)[cr SPL].adf"
D3 = ORIG / "Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 3 of 3)(Missions)[cr SPL].adf"

INSTALL = """\
; Midwinter II (Amiga) - install to a hard-disk partition
; Change DH0: below to the volume you want (e.g. WORK:), then from a Shell:
;     execute MW2Install
echo "Installing Midwinter II (patched) to DH0:"
copy mwII        to DH0: quiet
copy progdir     to DH0: quiet
copy midword.fsd to DH0: quiet
copy cods.bin    to DH0: quiet
copy grafix      to DH0: all quiet
copy grafdir     to DH0: quiet
copy missions    to DH0: all quiet
copy missdir     to DH0: quiet
echo "Done. Start it with:  CD DH0: ; DH0:mwII"
"""

README = """\
Midwinter II: Flames of Freedom (Amiga), patched build
======================================================

Direct controls: the view turns in proportion to mouse motion and stops when the
mouse stops; with the joystick or keypad (M/J/K selects the device) the view turns
at a constant rate while a direction is held and stops on release.

Install
  Copy these files to the ROOT of a hard-disk partition - the game only runs from
  the volume root, which is where its own original DH0 installer puts them.
  From a Shell:  execute MW2Install    (edit DH0: in that script first)

Run
  CD DH0:
  DH0:mwII

Notes
  * Needs Kickstart 2.0+ (tested on an A1200 with 3.1) and ~2 MB of RAM.
  * The data drawers keep their original names (grafix, missions).
  * The files come from the SPL 3-disk release; the executable is patched by
    tools/mw2patch.py (site-verified: input poller + X-axis consumer -> blob).
"""


def unpack(adf: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    import subprocess
    r = subprocess.run(["xdftool", str(adf), "unpack", str(dest)], capture_output=True)
    if r.returncode:
        raise SystemExit(f"xdftool unpack failed for {adf.name}: "
                         f"{(r.stderr or r.stdout).decode(errors='replace')[:200]}")
    return next(p for p in dest.iterdir() if p.is_dir())


def main() -> int:
    out = ROOT / "dist" / f"Midwinter2-Amiga-hd-{dt.date.today():%Y-%m-%d}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mw2zip-") as tmp:
        tmp = Path(tmp)
        d1, d2, d3 = (unpack(a, tmp / n) for a, n in ((D1, "d1"), (D2, "d2"), (D3, "d3")))
        stage = tmp / "stage"
        stage.mkdir()
        shutil.copyfile(BUILD / "MWII_direct", stage / "mwII")
        for name in ("progdir", "midword.fsd", "cods.bin"):
            shutil.copyfile(d1 / name, stage / name)
        shutil.copytree(d2, stage, dirs_exist_ok=True)
        shutil.copytree(d3, stage, dirs_exist_ok=True)
        (stage / "MW2Install").write_text(INSTALL)
        (stage / "README.txt").write_text(README)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    z.write(path, path.relative_to(stage))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
