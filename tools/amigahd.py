#!/usr/bin/env python3
"""Work on the Amiga hard-disk image without touching it: scratch copies with an autorun.

    python3 tools/amigahd.py info IMG                       # partition table (rdbtool info)
    python3 tools/amigahd.py scratch IMG OUT --game mw2     # copy IMG to OUT; S:User-Startup starts the game
    python3 tools/amigahd.py scratch IMG OUT --startup FILE # ... or runs FILE's commands

The shipped image boots to the Workbench desktop and has no autorun (you pick a game).  A
test or a `run_hd.sh --game X` instead copies the image, rewrites S:User-Startup in the
bootable partition (export DH0 -> xdftool -> import), and boots the copy.  Saves made by
the game therefore never reach the shipped image.

Needs amitools (`xdftool`, `rdbtool`) on PATH.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

#: game key -> (volume, command run from S:User-Startup).  The game only runs from the
#: ROOT of its volume, so every launch is `CD <volume>:` then the executable.
GAMES = {
    "mw2": ("Midwinter2", "mwII"),
    "mw2orig": ("Midwinter2Orig", "mwII"),
}


def run(*cmd: str) -> str:
    r = subprocess.run(cmd, capture_output=True)
    out = (r.stdout + r.stderr).decode(errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])} failed: {out[:400]}")
    return out


def autorun_script(game: str, extra: str = "") -> str:
    vol, exe = GAMES[game]
    return f"CD {vol}:\n{exe}\n{extra}"


def scratch(image: str | Path, out: str | Path, startup: str, device: str = "DH0") -> Path:
    """Copy ``image`` to ``out`` and make ``startup`` the S:User-Startup of ``device``."""
    out = Path(out)
    shutil.copyfile(image, out)
    with tempfile.TemporaryDirectory(prefix="amigahd-") as td:
        td = Path(td)
        part = td / f"{device}.hdf"          # xdftool takes the image type from the extension
        run("rdbtool", str(out), "export", device, str(part))
        us = td / "User-Startup"
        us.write_text(startup)
        try:
            run("xdftool", str(part), "delete", "S/User-Startup")
        except RuntimeError:
            pass
        run("xdftool", str(part), "write", str(us), "S/User-Startup")
        run("rdbtool", str(out), "import", device, str(part))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("info")
    i.add_argument("image")
    s = sub.add_parser("scratch")
    s.add_argument("image")
    s.add_argument("out")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--game", choices=sorted(GAMES))
    g.add_argument("--startup")
    a = ap.parse_args(argv)
    if a.cmd == "info":
        print(run("rdbtool", a.image, "info"))
        return 0
    text = autorun_script(a.game) if a.game else Path(a.startup).read_text()
    scratch(a.image, a.out, text)
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
