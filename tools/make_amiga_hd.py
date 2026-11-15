#!/usr/bin/env python3
"""Build the Amiga "enhanced games" hard-disk image: one RDB disk, one partition per game.

    python3 tools/make_amiga_hd.py                 # dist/Amiga_enhanced_games_<date>.hdf (+ .layout.txt)
    python3 tools/make_amiga_hd.py --out my.hdf

Why this shape
  * A real RDB (partition table) disk: mounts in FS-UAE and on real hardware
    (CF/SD/IDE adapters), unlike a bare filesystem image.
  * Midwinter II only runs from the ROOT of its volume (that is what its own DH0
    installer produces; in a drawer it stops at "insert graphics disk"), so every
    game gets its OWN partition.  Adding a game = adding an entry to GAMES below.
  * It boots to the Workbench 3.1 desktop; each game is a volume icon -> Play icon.

Partition map (device / volume)
  DH0  Workbench      bootable   Workbench 3.1 (os/WorkBench/amiga-os-310-workbench.adf)
  DH1  Midwinter2     patched build (direct controls) with its data at the volume root
  DH2  Midwinter2Orig the unpatched build, for A/B comparison

Needs `xdftool` and `rdbtool` (amitools) on PATH.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import math
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from amigaicon import project_icon

ROOT = Path(__file__).resolve().parent.parent
ORIG = ROOT / "games/in_progress/Midwinter-2/originals"
BUILD = ROOT / "games/in_progress/Midwinter-2/work/build"
WB = ROOT / "os/WorkBench/amiga-os-310-workbench.adf"

D1 = ORIG / "Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 1 of 3)[cr SPL].adf"
D2 = ORIG / "Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 2 of 3)(Graphics)[cr SPL].adf"
D3 = ORIG / "Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 3 of 3)(Missions)[cr SPL].adf"

HEADS, SECTORS = 16, 63                      # a conventional IDE geometry
CYL_BYTES = HEADS * SECTORS * 512
MAX_TRANSFER = 0x1FE00                      # see build(): larger values corrupt big reads on A1200 IDE


def run(*cmd: str) -> str:
    r = subprocess.run(cmd, capture_output=True)
    out = (r.stdout + r.stderr).decode(errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"{' '.join(cmd[:3])} ... failed: {out[:300]}")
    return out


def unpack(adf: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    run("xdftool", str(adf), "unpack", str(dest))
    return next(p for p in dest.iterdir() if p.is_dir())


# --- what goes on each partition -------------------------------------------------
USER_STARTUP = (
    "; Boots to the Workbench desktop.  Each game lives on its own volume:\n"
    ";   open the volume's icon and double-click Play, or from a Shell:\n"
    ";   CD Midwinter2:  then  mwII\n"
)


def stage_workbench(stage: Path, src: Path) -> None:
    wb = unpack(WB, src / "wb")
    shutil.copytree(wb, stage, dirs_exist_ok=True)
    (stage / "S/User-Startup").write_text(USER_STARTUP)
    (stage / "ReadMe.txt").write_text(
        "Amiga enhanced games\n"
        "====================\n\n"
        "Midwinter2      Midwinter II, patched (direct controls)\n"
        "Midwinter2Orig  the same game, unpatched, for comparison\n\n"
        "Each game has its own volume (the game only runs from the root of its volume).\n"
        "Open the volume on the desktop and double-click Play, or from a Shell:\n"
        "    CD Midwinter2:\n"
        "    mwII\n\n"
        "Direct controls: the view turns by the mouse's motion and stops when it stops;\n"
        "with the joystick or keypad it turns at a constant rate while held (M/J/K selects\n"
        "the device when the game asks).\n"
    )


def stage_mw2(stage: Path, src: Path, exe: Optional[Path], volume: str) -> None:
    """What the game's own DH0 installer (dh0_install1) copies, at the volume root."""
    for adf, name in ((D1, "d1"), (D2, "d2"), (D3, "d3")):
        if not (src / name).exists():
            unpack(adf, src / name)
    d1, d2, d3 = [next(p for p in (src / n).iterdir() if p.is_dir()) for n in ("d1", "d2", "d3")]
    stage.mkdir(parents=True, exist_ok=True)
    exe = exe or d1 / "MWII"
    if not exe.exists():
        raise SystemExit(f"missing {exe}; build it with tools/mw2patch.py apply")
    shutil.copyfile(exe, stage / "mwII")
    for name in ("progdir", "midword.fsd", "cods.bin"):
        shutil.copyfile(d1 / name, stage / name)
    shutil.copytree(d2, stage, dirs_exist_ok=True)
    shutil.copytree(d3, stage, dirs_exist_ok=True)
    stage_play(stage, src, volume)


PLAY_ICON_TEMPLATE = "System/Shell.info"      # a project icon from Workbench 3.1; only its picture is reused


def stage_play(stage: Path, src: Path, volume: str) -> None:
    """`Play` + `Play.info`: double-click starts the game.

    mwII needs a CLI process (the floppy boot runs it from a startup-sequence); started
    directly as a Workbench tool it dies with a Guru.  A project icon whose default tool
    is C:IconX runs the script in a CLI, and the script CDs to the volume root first (the
    game only works from the root of its volume).
    """
    (stage / "Play").write_text(f"CD {volume}:\nmwII\n")
    wb = next(p for p in (src / "wb").iterdir() if p.is_dir())
    (stage / "Play.info").write_bytes(project_icon((wb / PLAY_ICON_TEMPLATE).read_bytes(), "C:IconX", stack=40000))


@dataclass
class Part:
    device: str                 # DH0, DH1, ...
    volume: str                 # volume label shown on the desktop
    size_mib: Optional[int]     # None = take what is left
    bootable: bool
    stage: Callable[[Path, Path], None]


def parts(patched_exe: Path) -> list[Part]:
    return [
        Part("DH0", "Workbench", 12, True, stage_workbench),
        Part("DH1", "Midwinter2", 8, False, lambda s, src: stage_mw2(s, src, patched_exe, "Midwinter2")),
        Part("DH2", "Midwinter2Orig", None, False, lambda s, src: stage_mw2(s, src, None, "Midwinter2Orig")),
    ]


# --- image assembly --------------------------------------------------------------

def partition_table(rdb: Path) -> dict[str, tuple[int, int, int]]:
    """device name -> (low cyl, high cyl, blocks) read back from rdbtool."""
    info = run("rdbtool", str(rdb), "info")
    table = {}
    for m in re.finditer(r"Partition: #\d+ '([^']+)'\s+(\d+)\s+(\d+)\s+(\d+)\s", info):
        table[m.group(1)] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    return table


def build(out: Path, patched_exe: Path) -> list[dict]:
    plist = parts(patched_exe)
    fixed = sum(p.size_mib for p in plist if p.size_mib) * 1024 * 1024
    last_floor = 6 * 1024 * 1024                            # the partition that takes the rest
    cyls = math.ceil((fixed + last_floor) / CYL_BYTES) + 2   # +2: the RDB itself
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    run("rdbtool", str(out), "create", f"chs={cyls},{HEADS},{SECTORS}")
    run("rdbtool", str(out), "init")
    for p in plist:
        # max_transfer: the default (16 MB) makes FFS issue reads larger than the A1200's
        # IDE path handles; everything past the first 128 KiB of a big file (e.g. the
        # 218 KB code hunk of mwII) comes back wrong.  0x1fe00 (255 sectors) is the
        # standard safe value for Kickstart 3.1 scsi.device and is verified bit-exact.
        args = ["add", f"name={p.device}", "dostype=DOS1", f"bootable={p.bootable}", f"max_transfer={MAX_TRANSFER:#x}"]
        if p.size_mib:
            args.append(f"size={p.size_mib}MiB")
        run("rdbtool", str(out), *args)
    table = partition_table(out)

    report = []
    with tempfile.TemporaryDirectory(prefix="amigahd-") as tmp:
        tmp = Path(tmp)
        src = tmp / "src"
        for p in plist:
            _lo, _hi, blocks = table[p.device]
            stage = tmp / p.device
            stage.mkdir()
            p.stage(stage, src)
            vol = tmp / f"{p.device}.hdf"
            with open(vol, "wb") as fh:
                fh.truncate(blocks * 512)
            run("xdftool", str(vol), "format", p.volume, "ffs")
            for entry in sorted(stage.iterdir()):
                run("xdftool", str(vol), "write", str(entry))
            if p.bootable:
                run("xdftool", str(vol), "boot", "install")
            run("rdbtool", str(out), "import", p.device, str(vol))
            n_files = sum(1 for f in stage.rglob("*") if f.is_file())
            kib = sum(f.stat().st_size for f in stage.rglob("*") if f.is_file()) // 1024
            report.append(dict(device=p.device, volume=p.volume, blocks=blocks,
                               mib=blocks * 512 // 1048576, boot=p.bootable,
                               files=n_files, kib=kib))
    return report


def write_layout(out: Path, report: list[dict]) -> Path:
    md5 = hashlib.md5(out.read_bytes()).hexdigest()
    lay = out.with_suffix(".layout.txt")
    lines = [
        f"{out.name}  ({out.stat().st_size} bytes, RDB disk, md5 {md5})",
        f"built {dt.date.today()} by tools/make_amiga_hd.py from the current patched builds",
        "",
        "Partition table (RDB, geometry 16 heads x 63 sectors, all DOS\\1 = FFS)",
        "  dev  volume           size    boot  files",
    ]
    for r in report:
        lines.append(f"  {r['device']:<4} {r['volume']:<16} {r['mib']:>3} MiB  {'yes' if r['boot'] else '-':<4}  "
                     f"{r['files']} files, {r['kib']} KiB")
    lines += [
        "",
        "Boots to the Workbench 3.1 desktop (DH0). Each game is its own volume: open it and",
        "double-click Play (a script run by C:IconX), or from a Shell:  CD Midwinter2:  then  mwII",
        "The game only runs from the ROOT of its volume (its own DH0 installer's layout) and",
        "needs a CLI process, hence the Play script rather than a bare tool icon.",
        "MaxTransfer is 0x1FE00 on every partition: with a larger value the A1200's IDE path",
        "returns wrong data for reads over 128 KiB and mwII crashes at start.",
        "",
        "Use",
        "  Copperline:  dist/run_hd.sh  (see README)",
        "  real Amiga:  dd if=<this file> of=/dev/sdX bs=1M conv=fsync  (CF/SD/IDE adapter; check the device)",
        "               or copy the install zip's files to the root of an existing partition",
        "  Needs Kickstart 3.1 (FFS and Workbench 3.1 are 2.0+ only); tested A1200 + KS 3.1",
        "",
        "Rebuild",
        "  python3 tools/mw2patch.py apply <MWII from disk 1> games/in_progress/Midwinter-2/work/build/MWII_direct",
        "  python3 tools/make_amiga_hd.py",
        "  python3 tools/make_amiga_zip.py            (the install zip)",
        "  python3 tools/test_hd.py                   (boot + desktop click-through check)",
    ]
    lay.write_text("\n".join(lines) + "\n")
    return lay


def main() -> int:
    global USER_STARTUP
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--user-startup", default=None, help="text file used as S:User-Startup on the Workbench partition")
    args = ap.parse_args()
    if args.user_startup:
        USER_STARTUP = Path(args.user_startup).read_text()
    for tool in ("xdftool", "rdbtool"):
        if shutil.which(tool) is None:
            raise SystemExit(f"{tool} (amitools) not found")
    out = Path(args.out) if args.out else ROOT / "dist" / f"Amiga_enhanced_games_{dt.date.today():%Y-%m-%d}.hdf"
    report = build(out, BUILD / "MWII_direct")
    lay = write_layout(out, report)
    print(f"wrote {out} ({out.stat().st_size} bytes) and {lay.name}")
    for r in report:
        print(f"  {r['device']} {r['volume']:<15} {r['mib']:>3} MiB  boot={r['boot']}  {r['files']} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
