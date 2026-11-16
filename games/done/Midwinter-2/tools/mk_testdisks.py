#!/usr/bin/env python3
"""Build the reproducible Midwinter II test disks.

Currently one disk:

  d1_skipintro.adf  -- the SPL program disk with INTRO's demo loop skipped.
                       INTRO's prologue (save OS state, install copper) and
                       exit path (restore OS state, clear audio) still run; only
                       the raster/demo loop is bypassed. Needed because removing
                       INTRO entirely makes mwII fail, while the demo itself is
                       several minutes long and contains offensive text.

The patch is six bytes at INTRO's code offset $102
(`move.l $dff004,d0` -> `bra.w $16e` + nop). It is PC-relative, so it works at
whatever address LoadSeg chooses.

    python3 games/done/Midwinter-2/tools/mk_testdisks.py

Original disks are never modified. Output goes to work/build/ (git-ignored).
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

GAME = Path(__file__).resolve().parent.parent
ROOT = GAME.parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import adf  # noqa: E402

ORIGINALS = GAME / "originals"
BUILD = GAME / "work" / "build"
INTRO_RENAME = "INTRO"

SPL_D1_MD5 = "a30c167b5eb21f5a47df8c56b0b65574"
SPL_D1 = "Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 1 of 3)[cr SPL].adf"

INTRO_FILE_OFFSET = 0x20 + 0x102          # hunk data start + code offset
INTRO_ORIG = bytes.fromhex("203900dff004")  # move.l $dff004,d0
INTRO_PATCH = bytes.fromhex("6000006a4e71")  # bra.w $16e ; nop


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    src = ORIGINALS / SPL_D1
    if not src.exists():
        raise SystemExit(f"missing original disk: {src}")
    if md5(src) != SPL_D1_MD5:
        raise SystemExit(f"{src.name}: md5 {md5(src)} != {SPL_D1_MD5}")

    BUILD.mkdir(parents=True, exist_ok=True)
    out = BUILD / "d1_skipintro.adf"
    shutil.copyfile(src, out)

    with tempfile.TemporaryDirectory(prefix="mw2intro-") as tmp:
        adf.xdftool(str(out), "unpack", tmp)
        intro = next(Path(tmp).rglob(INTRO_RENAME))
        data = bytearray(intro.read_bytes())
        if data[INTRO_FILE_OFFSET:INTRO_FILE_OFFSET + 6] != INTRO_ORIG:
            raise SystemExit("INTRO: unexpected bytes at code offset $102; refusing to patch")
        data[INTRO_FILE_OFFSET:INTRO_FILE_OFFSET + 6] = INTRO_PATCH
        intro.write_bytes(data)

        adf.xdftool(str(out), "delete", "INTRO", readonly=False)
        adf.xdftool(str(out), "write", str(intro), "INTRO", readonly=False)

    # Only the INTRO file's sectors and the filesystem metadata may change.
    print(f"built {out}  md5 {md5(out)}")
    adf.cmd_diff(str(src), str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
