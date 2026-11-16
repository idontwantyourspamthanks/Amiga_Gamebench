#!/usr/bin/env python3
"""Build the Midwinter II (Amiga) release: one zip of floppy images, one zip of files for a hard drive.

    python3 games/done/Midwinter-2/tools/mw2release.py          # -> games/done/Midwinter-2/dist/
    python3 games/done/Midwinter-2/tools/mw2release.py --check  # verify existing zips against the sources

Outputs (dist/, git-ignored: they contain game data)
    Midwinter2_v<VER>_patched_floppies_<date>.zip   three ADFs + README.txt (insert disk 1 and boot)
    Midwinter2_v<VER>_patched_<date>.zip            MW2HD/ : the files to copy to the ROOT of a hard-disk partition

<VER> is the single release version in games/done/Midwinter-2/VERSION; it is also the credit line
"Midwinter II v<VER> enhanced by dad_prg" shown at start-up (floppy start-up-sequence, the Play script)
and in the READMEs.

Everything is built from the original SPL disks in originals/ (never modified):
  * mwII is the original executable with direct controls and the restored M/J/K device selector
    (tools/mw2patch.py, site-verified, all-or-nothing);
  * floppy disk 1 additionally has INTRO's demo loop skipped (tools/mk_testdisks.py; removing INTRO
    entirely makes mwII fail) and a clean s/startup-sequence: the cracker's text and the
    startup-sequence.bak that keeps it are removed;
  * disks 2 and 3 are the unmodified originals.
Needs xdftool (amitools); Play.info needs os/WorkBench/amiga-os-310-workbench.adf (only its picture is used).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

GAME = Path(__file__).resolve().parent.parent
ROOT = GAME.parents[2]                      # games/done/<game> -> repo root
sys.path.insert(0, str(ROOT / "tools"))
from amigaicon import project_icon  # noqa: E402

ORIG = GAME / "originals"
BUILD = GAME / "work" / "build"
DIST = GAME / "dist"
WB = ROOT / "os/WorkBench/amiga-os-310-workbench.adf"
VERSION = (GAME / "VERSION").read_text().strip()
CREDIT = f"Midwinter II v{VERSION} enhanced by dad_prg"

SET = "Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)"
D1 = ORIG / f"{SET}(Disk 1 of 3)[cr SPL].adf"
D2 = ORIG / f"{SET}(Disk 2 of 3)(Graphics)[cr SPL].adf"
D3 = ORIG / f"{SET}(Disk 3 of 3)(Missions)[cr SPL].adf"
FLOPPY_NAMES = (f"Midwinter2_v{VERSION}_disk1_program.adf", f"Midwinter2_v{VERSION}_disk2_graphics.adf",
                f"Midwinter2_v{VERSION}_disk3_missions.adf")

STARTUP = f"""\
setpatch >nil:
binddrivers

echo ""
echo "           Midwinter II (c) 1991 Maelstrom Games."
echo ""
echo "           {CREDIT}"
echo ""
echo "Loading"
FastMemFirst ; move C00000 memory to last in list
INTRO
mwII
endcli >nil:
"""

PLAY = f'echo "{CREDIT}"\nmwII\n'

FEATURES = """\
What is different from the original
  * Direct controls. The view turns in proportion to mouse motion and stops when the mouse
    stops. With the joystick or the keypad the view turns at a constant rate while a direction
    is held and stops when it is released. (The original kept turning at the last rate.)
  * The "Press 'M' for Mouse / 'J' for Joystick / 'K' for Keyboard" screen is back. The copy
    this release is based on had had it removed.
  * The cracker's start-up text and intro are gone: the start-up shows the credit line and the
    game starts. (INTRO is still run, with its demo loop skipped: the game fails without it.)
  * Nothing else is changed; every byte replaced in the program was checked against the original.

Tested in the Copperline emulator (A1200, Kickstart 3.1, 2 MB chip + 8 MB fast). Not yet tested on
real hardware, or on an A500/A600. Needs Kickstart 2.0 or newer (it was written against 3.1) and 2 MB.

Controls note: the menus need the mouse button HELD for about a second; a quick click is missed.
"""

FLOPPY_README = f"""\
{CREDIT}
{'=' * len(CREDIT)}

Three disks of the 1991 Rainbird release, patched.

  Midwinter2_v{VERSION}_disk1_program.adf    boot disk (volume "program")
  Midwinter2_v{VERSION}_disk2_graphics.adf   volume "grafix"
  Midwinter2_v{VERSION}_disk3_missions.adf   volume "missions"

Start: put disk 1 in DF0: and switch on. When the game asks for the graphics or missions disk,
insert it in any drive (with a second or third drive, or an emulator with three drives, put them
in DF1: and DF2: and no swapping is needed). Write-protect disks 2 and 3; campaigns are saved to
a disk you create inside the game.

{FEATURES}"""

HD_README = f"""\
{CREDIT}
{'=' * len(CREDIT)}

The files to put on a hard drive.

Install
  Copy EVERYTHING inside this MW2HD folder to the ROOT of the partition you want (for example
  DH1: or WORK:). The game only runs from the root of a volume, which is where its own original
  installer puts it. Do not put it in a drawer.

Run
  Double-click "Play" (needs C:IconX from Workbench, present in every normal installation), or
  from a Shell:   CD <your partition>:   then   mwII

Files: mwII (program), progdir, grafdir, missdir, midword.fsd, cods.bin, grafix/, missions/
(the game's data, exactly what its own installer copies) and Play, Play.info.

{FEATURES}"""


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def run(*cmd: str) -> str:
    r = subprocess.run(cmd, capture_output=True)
    out = (r.stdout + r.stderr).decode(errors="replace")
    if r.returncode:
        raise SystemExit(f"{' '.join(cmd[:3])} failed: {out[:300]}")
    return out


def need(p: Path):
    if not p.exists():
        raise SystemExit(f"missing {p}")


def build_patched_exe(tmp: Path) -> Path:
    """Patched mwII from the original: direct controls + restored selector (site-verified)."""
    orig = tmp / "MWII_orig"
    run("xdftool", str(D1), "read", "MWII", str(orig))
    out = tmp / "mwII"
    run(sys.executable, str(ROOT / "tools/mw2patch.py"), "apply", str(orig), str(out))
    run(sys.executable, str(ROOT / "tools/mw2patch.py"), "verify", str(orig), str(out))
    return out


def build_floppy_d1(tmp: Path, exe: Path) -> Path:
    """Disk 1: original SPL disk + INTRO demo loop skipped + patched mwII + clean start-up."""
    run(sys.executable, str(GAME / "tools/mk_testdisks.py"))                  # -> work/build/d1_skipintro.adf
    d1 = tmp / FLOPPY_NAMES[0]
    run(sys.executable, str(ROOT / "tools/mw2patch.py"), "apply-adf", str(BUILD / "d1_skipintro.adf"),
        str(d1), str(tmp / "MWII_orig"))
    ss = tmp / "startup-sequence"
    ss.write_text(STARTUP)
    run("xdftool", str(d1), "delete", "s/startup-sequence")
    run("xdftool", str(d1), "write", str(ss), "s/startup-sequence")
    run("xdftool", str(d1), "delete", "s/startup-sequence.bak")                # keeps the cracker's text
    listing = run("xdftool", str(d1), "list")
    assert "startup-sequence.bak" not in listing
    return d1


def unpack(adf: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    run("xdftool", str(adf), "unpack", str(dest))
    return next(p for p in dest.iterdir() if p.is_dir())


def stage_hd(tmp: Path, exe: Path) -> Path:
    stage = tmp / "MW2HD"
    stage.mkdir()
    d1, d2, d3 = (unpack(a, tmp / n) for a, n in ((D1, "u1"), (D2, "u2"), (D3, "u3")))
    shutil.copyfile(exe, stage / "mwII")
    for name in ("progdir", "midword.fsd", "cods.bin"):
        shutil.copyfile(d1 / name, stage / name)
    shutil.copytree(d2, stage, dirs_exist_ok=True)
    shutil.copytree(d3, stage, dirs_exist_ok=True)
    (stage / "Play").write_text(PLAY)
    if WB.exists():
        wb = unpack(WB, tmp / "wb")
        (stage / "Play.info").write_bytes(project_icon((wb / "System/Shell.info").read_bytes(), "C:IconX", stack=40000))
    else:
        print(f"warning: {WB} missing: the HD zip will have no Play.info icon", file=sys.stderr)
    (stage / "README.txt").write_text(HD_README)
    return stage


def zip_dir(out: Path, base: Path, files: list[tuple[Path, str]]):
    out.unlink(missing_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in sorted(files, key=lambda x: x[1]):
            z.write(src, arc)


def build() -> list[Path]:
    for p in (D1, D2, D3):
        need(p)
    DIST.mkdir(exist_ok=True)
    date = f"{dt.date.today():%Y-%m-%d}"
    with tempfile.TemporaryDirectory(prefix="mw2rel-") as t:
        tmp = Path(t)
        exe = build_patched_exe(tmp)
        d1 = build_floppy_d1(tmp, exe)
        fl = DIST / f"Midwinter2_v{VERSION}_patched_floppies_{date}.zip"
        (tmp / "README.txt").write_text(FLOPPY_README)
        zip_dir(fl, tmp, [(d1, FLOPPY_NAMES[0]), (D2, FLOPPY_NAMES[1]), (D3, FLOPPY_NAMES[2]), (tmp / "README.txt", "README.txt")])
        stage = stage_hd(tmp, exe)
        hd = DIST / f"Midwinter2_v{VERSION}_patched_{date}.zip"
        zip_dir(hd, tmp, [(f, f"MW2HD/{f.relative_to(stage)}") for f in stage.rglob("*") if f.is_file()])
    return [hd, fl]


def check(zips: list[Path] | None = None) -> None:
    """Re-derive what the zips must contain and compare (the release gate; also run by tests)."""
    date = f"{dt.date.today():%Y-%m-%d}"
    hd = sorted(DIST.glob(f"Midwinter2_v{VERSION}_patched_2*.zip"))[-1]
    fl = sorted(DIST.glob(f"Midwinter2_v{VERSION}_patched_floppies_*.zip"))[-1]
    with tempfile.TemporaryDirectory(prefix="mw2chk-") as t:
        tmp = Path(t)
        exe = build_patched_exe(tmp)
        with zipfile.ZipFile(hd) as z:
            names = set(z.namelist())
            got = {n: z.read(n) for n in names}
        assert got["MW2HD/mwII"] == exe.read_bytes(), "HD mwII is not the verified patched executable"
        assert got["MW2HD/Play"].decode() == PLAY
        d1, d2, d3 = (unpack(a, tmp / n) for a, n in ((D1, "u1"), (D2, "u2"), (D3, "u3")))
        for src in (d2, d3):
            for f in src.rglob("*"):
                if f.is_file():
                    arc = f"MW2HD/{f.relative_to(src)}"
                    assert got.get(arc) == f.read_bytes(), f"{arc} differs from the original disk"
        for name in ("progdir", "midword.fsd", "cods.bin"):
            assert got[f"MW2HD/{name}"] == (d1 / name).read_bytes(), name
        with zipfile.ZipFile(fl) as z:
            assert set(z.namelist()) == {*FLOPPY_NAMES, "README.txt"}
            assert z.read(FLOPPY_NAMES[1]) == D2.read_bytes() and z.read(FLOPPY_NAMES[2]) == D3.read_bytes()
            (tmp / "d1.adf").write_bytes(z.read(FLOPPY_NAMES[0]))
        ss = run("xdftool", str(tmp / "d1.adf"), "type", "s/startup-sequence")
        assert CREDIT in ss and "CRACKED" not in ss.upper() and "CUNT" not in ss.upper()
        assert "startup-sequence.bak" not in run("xdftool", str(tmp / "d1.adf"), "list")
        for name in ("MWII", "mwII"):
            try:
                run("xdftool", str(tmp / "d1.adf"), "read", name, str(tmp / "mwII_on_disk"))
                break
            except SystemExit:
                continue
        assert (tmp / "mwII_on_disk").read_bytes() == exe.read_bytes(), "floppy mwII is not the patched executable"
    print(f"release check OK: {hd.name}, {fl.name}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        check()
        return 0
    paths = build()
    check()
    for p in paths:
        print(f"{md5(p.read_bytes())}  {p.name}  ({p.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
