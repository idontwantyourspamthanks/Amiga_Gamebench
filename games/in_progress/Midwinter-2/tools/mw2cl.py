"""Midwinter II on Copperline: boot from the hard-disk image, drive the front end, reach the cockpit.

    from mw2cl import MW2
    with MW2.from_image("dist/Amiga_enhanced_games_<date>.hdf", game="mw2") as g:
        g.boot()                  # autorun scratch copy -> hallway
        g.to_cockpit()            # hallway -> RAIDS -> INTERMEDIATE -> briefing -> cockpit
        print(g.read_marker())

Navigation is state-based: every step waits for the screen it expects (region digest),
never a guessed delay.  The game only sees the real input path: relative mouse counts
and a held left button (its VBL sampler ignores a quick click; hold ~1 s).

Cursor facts (measured; hunk 1 = the DATA hunk, offsets are stable per build):
  game X (word, lowres 0..319)  hunk1+0x308E       field px = 62 + 2*x
  game Y (word, 0..199)         hunk1+0x3090       field px = 16 + y
  8 mouse counts move the cursor 4 game px; counts below ~4 per frame are ignored
  (a deadzone), and motion is eased, so steer in >=8 count steps and let it settle.
"""
from __future__ import annotations

import os
import re
import struct
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from clharness import CopperlineError, Machine, Session  # noqa: E402
import amigahd  # noqa: E402

CUR_X, CUR_Y = 0x308E, 0x3090           # offsets in hunk 1

# instruction skeleton (operands excluded) of the steering consumer: clamp + deadzone body
CONSUMER_SKEL = bytes.fromhex("b06800146e0630280014600ab06800166d0430280016")

# front-end buttons in GAME coordinates (x 0..319, y 0..199); field px = (62 + 2x, 16 + y)
HALL_RAIDS = (117, 56)
LEVELS = {"novice": (42, 166), "intermediate": (120, 166), "experienced": (203, 166), "expert": (282, 166)}
CAMARGO = (155, 170)
BRIEFING_QUESTION = (15, 177)
THUMBS_UP = (264, 16)

HALLWAY_REGION = (300, 100, 120, 60)    # corridor, away from the pointer (field pixels)
HALLWAY_DIGEST = "9cb6dabffa4f3c25"     # capture.region_digest of HALLWAY_REGION in the hallway (A1200, KS 3.1)


class MW2(Session):
    @classmethod
    def from_image(cls, image: str | os.PathLike, game: str = "mw2", *, machine: Machine | None = None,
                   keep: str | os.PathLike | None = None, **kw) -> "MW2":
        """Boot a scratch copy of ``image`` whose S:User-Startup starts ``game`` (the image is not touched)."""
        scratch = Path(keep) if keep else Path(tempfile.mkdtemp(prefix="mw2cl-")) / "scratch.hdf"
        amigahd.scratch(image, scratch, amigahd.autorun_script(game))
        m = machine or Machine()
        m.ide = scratch
        return cls(m, **kw)

    # -- cursor ----------------------------------------------------------------------------
    def _hunk1(self) -> int:
        segs = self.call("segments.list")["current"]
        if len(segs) < 2:
            raise CopperlineError("segments.list has no game hunks (is the game running?)")
        return segs[1]["start"]

    def cursor(self) -> tuple[int, int]:
        h = self._hunk1()
        return self.read_w(h + CUR_X), self.read_w(h + CUR_Y)

    def goto(self, gx: int, gy: int, tol: int = 3, tries: int = 40):
        """Steer the game cursor to game coords with real mouse counts (closed loop on the game's own X/Y)."""
        for _ in range(tries):
            x, y = self.cursor()
            ex, ey = gx - x, gy - y
            if abs(ex) <= tol and abs(ey) <= tol:
                return x, y
            # 8 counts -> 4 game px: counts = 2*error, in steps the game's deadzone accepts
            dx = 0 if abs(ex) <= tol else max(-24, min(24, 2 * ex))
            dy = 0 if abs(ey) <= tol else max(-24, min(24, 2 * ey))
            if dx and abs(dx) < 8:
                dx = 8 if dx > 0 else -8
            if dy and abs(dy) < 8:
                dy = 8 if dy > 0 else -8
            self.mouse(dx=dx, dy=dy)
            self.run_frames(4)
        raise CopperlineError(f"cursor stuck at {self.cursor()} going to {(gx, gy)}")

    def hold_click(self, gx: int, gy: int, hold: float = 1.0, settle: float = 4.0):
        pos = self.goto(gx, gy)
        self.click(hold=hold)
        self.run_for(settle)
        return pos

    # -- the front end ----------------------------------------------------------------------
    def boot(self, timeout: float = 220):
        """Run from power-on (autorun scratch image) to the hallway; returns emulated seconds."""
        return self.wait_region(HALLWAY_REGION, HALLWAY_DIGEST, timeout=timeout, step=2.0)

    def to_cockpit(self, level: str = "intermediate"):
        """Hallway -> RAIDS -> level -> island -> briefing -> equipment -> thumbs-up -> in-game cockpit.

        Emulation is deterministic, so the settle times below are exact, not guesses; the
        checkpoints (see tests/) assert the screen at each stop.  Every press is HELD ~1 s.
        """
        self.hold_click(*HALL_RAIDS, settle=10)          # level pick
        self.hold_click(*LEVELS[level], settle=10)        # raid map
        self.hold_click(*CAMARGO, settle=6)               # island zoom
        self.key(0x40, hold_ms=500)                       # SPACE: briefing
        self.run_for(14)
        self.hold_click(*BRIEFING_QUESTION, settle=6)     # mission equipment
        self.hold_click(*THUMBS_UP, settle=12)            # start the mission
        self.run_for(30)                                  # map scroll-in, cockpit set-up

    # -- direct controls (patch p5_direct) ---------------------------------------------------
    def code_hunk(self) -> tuple[int, bytes]:
        seg = self.call("segments.list")["current"][0]
        n = seg["size"]
        data = b"".join(self.read(seg["start"] + o, min(0x10000, n - o)) for o in range(0, n, 0x10000))
        return seg["start"], data

    def locate(self) -> dict:
        """Live addresses of the steering path, found by instruction skeleton in the loaded code hunk.

        Addresses move between builds and load layouts: never cache them across sessions.
        Patched build: ``consumer`` holds ``jmp <blob>`` and the blob's operands give acc/gate/out.
        Unpatched: operands are read from the consumer itself.
        """
        base, code = self.code_hunk()
        hits = [m.start() for m in re.finditer(re.escape(CONSUMER_SKEL), code)]
        if len(hits) != 1:
            raise CopperlineError(f"consumer skeleton found {len(hits)} times")
        cons = hits[0] - 6
        out = {"consumer": base + cons, "patched": code[cons:cons + 2] == b"\x4e\xf9"}
        u32 = lambda b: struct.unpack(">I", b)[0]
        if out["patched"]:
            blob = u32(code[cons + 2:cons + 6]) - base
            m = re.match(rb"\x40\xc2\x00\x7c\x07\x00\x20\x39(....)\x42\xb9(....)\x46\xc2\x4a\x79(....)",
                         code[blob:blob + 32], re.S)
            if not m or m.group(1) != m.group(2):
                raise CopperlineError("blob consumer prologue not recognised")
            out["blob_cons"] = base + blob
            out["acc"], out["gate"] = u32(m.group(1)), u32(m.group(3))
            st = re.search(rb"\x33\xc0(....)\x4e\x75", code[blob:blob + 0xA0], re.S)
            out["out"] = u32(st.group(1))
            out["store_pc"] = base + blob + st.start()            # `move.w d0,out`: D0 = the tick's turn value
            hd = code[blob - 0x40:blob]
            out["blob_handler"] = base + blob - 0x40
            out["accy"] = u32(re.search(rb"\x44\x80\xd1\xb9(....)\x4e\x75", hd, re.S).group(1))
        else:
            out["acc"] = u32(code[cons + 2:cons + 6])
            out["out"] = u32(code[cons + 0x2c:cons + 0x30])
        out["heading"] = out["acc"] - 0xFF0                        # word, 1024 = 360 degrees
        return out
