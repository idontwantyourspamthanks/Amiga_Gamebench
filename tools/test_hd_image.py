#!/usr/bin/env python3
r"""Boot one game from the all-games hard-disk image in Copperline: the real boot path (IDE + RDB + Kickstart 3.1 + Workbench).

    python3 tools/test_hd_image.py IMG GAME [--model A1200] [--shots DIR] [--stop hallway|cockpit]
        GAME = mw2 | mw2orig

The image is never touched: a scratch copy gets an S:User-Startup that starts the game.  The
game's own harness (games/*/tools/mw2cl.py) then navigates from power-on to the in-game
view.  The load check runs first: right after LoadSeg every hunk of the game is compared with
the executable on the volume (this catches the MaxTransfer bug that corrupts reads over
128 KiB).  Prints one `RESULT` line and exits non-zero on any failure.
"""
from __future__ import annotations

import argparse
import struct
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "games" / "in_progress" / "Midwinter-2" / "tools"))
from clharness import CopperlineError, Machine  # noqa: E402
import amigahd  # noqa: E402
import amigabin  # noqa: E402
import mw2cl  # noqa: E402

HUD_BAR = (62, 68, 640, 8)               # the in-game HUD border: present only in the 3D view
HUD_BAR_DIGEST = "7636a639d21210e1"


def exe_from_volume(image: Path, device: str) -> Path:
    """Export a partition and read mwII back out, so the oracle is what is really on the disk."""
    td = Path(tempfile.mkdtemp(prefix="hdexe-"))
    part = td / f"{device}.hdf"
    amigahd.run("rdbtool", str(image), "export", device, str(part))
    exe = td / "mwII"
    amigahd.run("xdftool", str(part), "read", "mwII", str(exe))
    return exe


def check_load(g, exe: Path) -> dict:
    """Stop at LoadSeg and compare every hunk in RAM with the relocated executable (bit-exact)."""
    lf = amigabin.LoadFile(str(exe))
    g.call("break.add", kind="loadseg", name="mwII")
    r = g.run_to(g.now() + 120)
    if r.get("reason") != "loadseg":
        raise CopperlineError(f"mwII never loaded: {r.get('reason')}")
    segs = g.call("segments.list")["current"]
    bases = [s["start"] for s in segs]
    bad = {}
    for h, seg in zip(lf.hunks, segs):
        exp = bytearray(h.data if h.kind != 0x3EB else bytes(h.size))
        for tgt, off in h.relocs:
            struct.pack_into(">I", exp, off, struct.unpack_from(">I", exp, off)[0] + bases[tgt])
        mem = b"".join(g.read(seg["start"] + o, min(0x10000, h.size - o)) for o in range(0, h.size, 0x10000))
        diff = sum(1 for a, b in zip(mem, exp) if a != b)
        if diff:
            bad[h.index] = diff
    g.call("break.clear")
    return {"hunks": [s["size"] for s in segs], "bad": bad}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("image")
    ap.add_argument("game", choices=sorted(amigahd.GAMES))
    ap.add_argument("--model", default="A1200")
    ap.add_argument("--shots", default=None, help="directory for checkpoint screenshots")
    ap.add_argument("--stop", choices=("hallway", "cockpit"), default="cockpit")
    a = ap.parse_args(argv)
    image = Path(a.image)
    shots = Path(a.shots) if a.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    vol = amigahd.GAMES[a.game][0]
    device = {"mw2": "DH1", "mw2orig": "DH2"}[a.game]
    t0 = time.time()
    res = {"game": a.game, "machine": a.model, "load": "?", "hallway": "no", "cockpit": "no"}
    rc = 1
    try:
        exe = exe_from_volume(image, device)
        scratch = Path(tempfile.mkdtemp(prefix="hdtest-")) / "scratch.hdf"
        amigahd.scratch(image, scratch, amigahd.autorun_script(a.game))
        with mw2cl.MW2(Machine(model=a.model, ide=scratch)) as g:
            g.run_to(1.0)
            load = check_load(g, exe)
            res["load"] = "ok" if not load["bad"] else f"CORRUPT{load['bad']}"
            res["hunk0"] = load["hunks"][0]
            if load["bad"]:
                raise CopperlineError(f"hunks differ from the file after LoadSeg: {load['bad']}")
            t = g.boot(loaded=True)
            res["hallway"] = f"{t:.0f}s"
            if shots:
                g.shot(shots / f"{a.game}_hallway.png")
            if a.stop == "cockpit":
                g.to_cockpit()
                ok = g.region_digest(*HUD_BAR) == HUD_BAR_DIGEST
                res["cockpit"] = "ok" if ok else "NO-HUD"
                if shots:
                    g.shot(shots / f"{a.game}_cockpit.png")
                rc = 0 if ok else 1
            else:
                rc = 0
    except Exception as e:                      # one RESULT line even on failure
        res["error"] = f"{type(e).__name__}: {e}"[:200]
        rc = 1
    res["wall"] = f"{time.time() - t0:.0f}s"
    print("RESULT " + " ".join(f"{k}={v}" for k, v in res.items()))
    return rc


if __name__ == "__main__":
    sys.exit(main())
