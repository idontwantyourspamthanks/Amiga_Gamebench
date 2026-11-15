#!/usr/bin/env python3
"""Copperline harness for the Amiga gamebench.

Copperline (https://copperline.dev) is a deterministic, cycle-driven Amiga
emulator.  Headless it needs no display server and runs unthrottled, so a
30 s emulated boot costs ~6 s of wall time and gives the same result every
run.  Three layers here:

``Machine``
    Builds a Copperline TOML config (A1200 + Kickstart 3.1 by default) with an
    IDE hard disk, floppies, live host-folder volumes and optional extras.

``capture(machine, ...)``
    One-shot headless run: scheduled input (``press``/``type``/``click``/``mouse_to``
    ...) on *emulated* timestamps, screenshots, ``--expect-screenshot`` golden
    comparison.  Deterministic -- the right tool for regression tests.

``Session(machine)``
    Interactive control over CCP (JSON-RPC over TCP): run to an emulated
    time/frame/PC, read/write memory, registers, breakpoints/watchpoints,
    screenshots, state save/load, input injection.  The right tool for
    reverse engineering and for game-state gates.  The machine only advances
    while a ``run_*``/``step*``/``continue`` call is in progress, so there are
    no pause artefacts (unlike FS-UAE, where every debugger call stopped the
    game).

Command line::

    clharness.py version
    clharness.py shot <hd.hdf|--df0 x.adf> OUT.png [--at 40]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "tools" / "bin"
KICK_DIR = ROOT / "os" / "Kickstart"

#: model -> Kickstart file (the A1200's 3.1 is the target; the others are
#: regression machines for "nothing may break where the original worked").
KICKSTARTS = {
    "A1200": "amiga-os-310-a1200.rom",
    "A600": "amiga-os-205-a600.rom",
    "A500": "amiga-os-130.rom",
    "A500Plus": "amiga-os-205-a600.rom",
}


class CopperlineError(RuntimeError):
    pass


class CCPError(CopperlineError):
    def __init__(self, method: str, err: dict):
        super().__init__(f"{method}: [{err.get('code')}] {err.get('message')}")
        self.method, self.code, self.message = method, err.get("code"), err.get("message")


def copperline_bin() -> str:
    """``$COPPERLINE_BIN``, else tools/bin/copperline (tools/fetch_copperline.sh), else PATH."""
    for cand in (os.environ.get("COPPERLINE_BIN"), str(BIN_DIR / "copperline"), shutil.which("copperline")):
        if cand and Path(cand).exists():
            return cand
    raise CopperlineError("copperline not found: run tools/fetch_copperline.sh or set COPPERLINE_BIN")


def ctl_bin() -> str:
    for cand in (os.environ.get("COPPERLINE_CTL"), str(BIN_DIR / "copperline-ctl"), shutil.which("copperline-ctl")):
        if cand and Path(cand).exists():
            return cand
    raise CopperlineError("copperline-ctl not found: run tools/fetch_copperline.sh")


# --------------------------------------------------------------------------
# Machine / config
# --------------------------------------------------------------------------

@dataclass
class Machine:
    """A Copperline machine description rendered to TOML by :meth:`toml`."""

    model: str = "A1200"
    rom: str | None = None               # default: KICKSTARTS[model] in os/Kickstart
    fast: str | None = "8M"              # None: profile default
    chip: str | None = None
    cpu: str | None = None               # e.g. "68030"
    cpu_clock: float | None = None       # MHz; None = stock (A1200: 14.18)
    floppies: Sequence[str | os.PathLike] = ()   # df0, df1, ...
    floppy_write: bool = False           # allow writes into the ADF (default: read-only image)
    ide: str | os.PathLike | None = None  # HDF/VHD/directory on the IDE master
    ide_slave: str | os.PathLike | None = None
    filesys: Sequence[tuple] = ()        # (host dir, volume, readonly[, bootpri]): live HOSTFS volumes
    rtc_time: str | None = "2026-01-01 12:00:00"    # seeded -> reproducible
    extra: str = ""                      # raw TOML appended

    def rom_path(self) -> Path:
        return Path(self.rom) if self.rom else KICK_DIR / KICKSTARTS[self.model]

    def toml(self) -> str:
        q = lambda p: json.dumps(str(Path(p).resolve()))
        out = [f"rom = {q(self.rom_path())}", "", "[machine]", f'profile = "{self.model}"']
        if self.rtc_time:
            out.append(f'rtc_time = "{self.rtc_time}"')
        mem = [("chip", self.chip), ("fast", self.fast)]
        if any(v for _, v in mem):
            out += ["", "[memory]"] + [f'{k} = "{v}"' for k, v in mem if v]
        if self.cpu or self.cpu_clock:
            out += ["", "[cpu]"]
            if self.cpu:
                out.append(f'model = "{self.cpu}"')
            if self.cpu_clock:
                out.append(f"clock_mhz = {self.cpu_clock}")
        if self.floppies:
            out += ["", "[floppy]", f"drives = {max(1, len(self.floppies))}"]
            for i, f in enumerate(self.floppies):
                out += [f"[floppy.df{i}]", f"path = {q(f)}",
                        f"write_protected = {str(not self.floppy_write).lower()}"]
        if self.ide or self.ide_slave:
            out += ["", "[ide]"]
            if self.ide:
                out.append(f"master = {q(self.ide)}")
            if self.ide_slave:
                out.append(f"slave = {q(self.ide_slave)}")
        for path, vol, ro, *rest in self.filesys:
            out += ["", "[[filesys]]", f"path = {q(path)}", f'volume = "{vol}"']
            if ro:
                out.append("readonly = true")
            if rest and rest[0] is not None:
                out.append(f"bootpri = {rest[0]}")
        if self.extra:
            out += ["", self.extra]
        return "\n".join(out) + "\n"

    def write_config(self, path: str | os.PathLike) -> Path:
        p = Path(path)
        p.write_text(self.toml())
        return p


# --------------------------------------------------------------------------
# Scheduled one-shot runs (deterministic regression tests)
# --------------------------------------------------------------------------

@dataclass
class RunResult:
    returncode: int
    log: str
    shots: dict[str, Path] = field(default_factory=dict)
    wall: float = 0.0

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def expectation_failures(self) -> list[str]:
        return [l for l in self.log.splitlines() if "expect-screenshot:" in l and "MISMATCH" in l or "missing" in l.lower() and "expect-screenshot" in l]


class Schedule:
    """Builds ``--*-after`` flags (emulated seconds).  All times are absolute."""

    def __init__(self):
        self.args: list[str] = []
        self.shots: list[tuple[float, str]] = []

    def press(self, t, key):               self.args += ["--press-after", str(t), str(key)]; return self
    def hold(self, t, key, ms=100):        self.args += ["--key-after", str(t), str(key), str(ms)]; return self
    def type(self, t, text):               self.args += ["--type-after", str(t), text]; return self
    def click(self, t, btn="left", ms=100, port=1):
        self.args += ["--click-after", str(t), btn, str(ms), str(port)]; return self
    def double_click(self, t, btn="left", ms=80, gap=0.12):
        return self.click(t, btn, ms).click(t + gap + ms / 1000, btn, ms)
    def mouse(self, t, dx, dy, port=1):    self.args += ["--mouse-after", str(t), str(dx), str(dy), str(port)]; return self
    def mouse_to(self, t, x, y, port=1):   self.args += ["--mouse-to-after", str(t), str(x), str(y), str(port)]; return self
    def joy(self, t, btn, ms=100, port=2): self.args += ["--joy-after", str(t), btn, str(ms), str(port)]; return self
    def expect(self, t, png, tol=None):
        self.args += ["--expect-screenshot", str(t), str(png)] + ([str(tol)] if tol is not None else []); return self
    def shot(self, t, png):                self.args += ["--screenshot-after", str(t), str(png)]; return self


def capture(machine: Machine, sched: Schedule | Iterable[str] = (), *, extra: Sequence[str] = (),
            env: dict | None = None, timeout: float = 600, native: bool = False,
            workdir: str | os.PathLike | None = None) -> RunResult:
    """Run headless to the last scheduled capture and return the result.

    ``sched`` must contain at least one capture flag (``shot``/``expect``) or the
    run would not end.  Pixel coordinates for ``mouse_to`` are those of a
    ``--screenshot-after`` PNG (716x540 for a PAL A1200 desktop).
    """
    args = sched.args if isinstance(sched, Schedule) else list(sched)
    with tempfile.TemporaryDirectory(prefix="clrun-") as td:
        cfg = machine.write_config(Path(td) / "machine.toml")
        cmd = [copperline_bin(), "--config", str(cfg), "--noaudio"] + (["--native-screenshots"] if native else []) + list(extra) + args
        e = dict(os.environ)
        e.setdefault("RUST_LOG", "info")
        e.update(env or {})
        t0 = time.time()
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=e, cwd=workdir)
        wall = time.time() - t0
    shots = {}
    it = iter(args)
    for a in it:
        if a == "--screenshot-after":
            next(it); shots[a] = None
    res = RunResult(p.returncode, p.stdout + p.stderr, wall=wall)
    res.shots = {m.group(1): Path(m.group(1)) for m in re.finditer(r"screenshot saved: (\S+)", res.log)}
    return res


# --------------------------------------------------------------------------
# CCP session
# --------------------------------------------------------------------------

class Session:
    """Control-protocol session on a headless Copperline (starts paused at power-on).

        with Session(Machine(ide="dist/x.hdf")) as s:
            s.run_to(30)               # absolute emulated seconds
            s.shot("a.png")
            print(s.read(0x4, 4))
    """

    def __init__(self, machine: Machine | None = None, *, config: str | os.PathLike | None = None,
                 args: Sequence[str] = (), env: dict | None = None, log: str | os.PathLike | None = None,
                 launch_timeout: float = 60):
        self._tmp = Path(tempfile.mkdtemp(prefix="clses-"))
        if config is None:
            config = (machine or Machine()).write_config(self._tmp / "machine.toml")
        self.log_path = Path(log) if log else self._tmp / "copperline.log"
        info = self._tmp / "ccp.json"
        e = dict(os.environ)
        e.setdefault("RUST_LOG", "info")
        e.update(env or {})
        self._log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(
            [copperline_bin(), "--config", str(config), "--noaudio", "--control", ":0",
             "--control-info", str(info), *args],
            stdout=self._log, stderr=subprocess.STDOUT, env=e)
        t0 = time.time()
        while not info.exists() or not info.stat().st_size:
            if self.proc.poll() is not None:
                raise CopperlineError("copperline exited at start-up:\n" + self.log_path.read_text(errors="replace")[-2000:])
            if time.time() - t0 > launch_timeout:
                self.close()
                raise CopperlineError("timeout waiting for control endpoint")
            time.sleep(0.05)
        meta = json.loads(info.read_text())
        host, port = meta["listen"].rsplit(":", 1)
        self.sock = socket.create_connection((host, int(port)), timeout=None)
        self.f = self.sock.makefile("rwb", buffering=0)
        self._id = 0
        self.events: list[dict] = []
        self.call("auth", token=meta["token"])

    # -- plumbing
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def close(self):
        try:
            if getattr(self, "f", None):
                try:
                    self.call("shutdown")
                except Exception:
                    pass
        finally:
            for x in (getattr(self, "f", None), getattr(self, "sock", None)):
                try:
                    x and x.close()
                except Exception:
                    pass
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
            self._log.close()
            shutil.rmtree(self._tmp, ignore_errors=True) if not os.environ.get("CLHARNESS_KEEP") else None

    def call(self, method: str, **params):
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        self.f.write((json.dumps(msg) + "\n").encode())
        while True:
            line = self.f.readline()
            if not line:
                raise CopperlineError(f"connection closed during {method}; log tail:\n" + self.log_path.read_text(errors="replace")[-1500:])
            r = json.loads(line)
            if r.get("id") != self._id:
                self.events.append(r)
                continue
            if "error" in r:
                raise CCPError(method, r["error"])
            return r.get("result")

    # -- time
    def status(self) -> dict:
        return self.call("status")

    @property
    def seconds(self) -> float:
        return float(self.beam()["seconds"]) if "seconds" in self.beam() else float(self.status()["seconds"])

    def beam(self) -> dict:
        return self.call("beam.get")

    def run_to(self, seconds: float, **kw):
        """Run (unpaced) until absolute emulated time; stops early on a breakpoint."""
        return self.call("run_until", seconds=seconds, **kw)

    def run_for(self, seconds: float, **kw):
        return self.run_to(self.now() + seconds, **kw)

    def run_frames(self, n: int):
        return self.call("step_frame", n=n)

    def run_to_frame(self, frame: int, **kw):
        return self.call("run_until", frame=frame, **kw)

    def run_to_pc(self, pc: int, **kw):
        return self.call("run_until", pc=pc, **kw)

    def cont(self, **kw):
        return self.call("continue", **kw)

    def now(self) -> float:
        """Emulated seconds.  ``status`` is the cheap source; field names are checked once."""
        st = self.status()
        for k in ("seconds", "emulated_seconds", "time"):
            if k in st:
                return float(st[k])
        pos = st.get("position") or st.get("pos") or {}
        if "seconds" in pos:
            return float(pos["seconds"])
        raise CopperlineError(f"no time field in status: {st}")

    def frame(self) -> int:
        st = self.status()
        for k in ("frame", "frames"):
            if k in st:
                return int(st[k])
        pos = st.get("position") or {}
        return int(pos["frame"])

    # -- memory / registers
    def read(self, addr: int, n: int = 2) -> bytes:
        r = self.call("mem.read", addr=addr, len=n, encoding="hex")
        d = r["data"] if isinstance(r, dict) else r
        return bytes.fromhex(d)

    def read_w(self, addr: int) -> int:
        return int.from_bytes(self.read(addr, 2), "big")

    def read_l(self, addr: int) -> int:
        return int.from_bytes(self.read(addr, 4), "big")

    def write(self, addr: int, data: bytes):
        return self.call("mem.write", addr=addr, data=data.hex(), encoding="hex")

    def write_w(self, addr: int, v: int):
        return self.write(addr, (v & 0xFFFF).to_bytes(2, "big"))

    def regs(self) -> dict:
        return self.call("regs.get")

    def find(self, pattern: bytes, start: int, end: int, step: int = 0x10000) -> list[int]:
        """Scan RAM for a byte pattern (chunked mem.read; <=1 MiB per call)."""
        hits, a = [], start
        while a < end:
            n = min(step + len(pattern), end - a)
            chunk = self.read(a, n)
            i = chunk.find(pattern)
            while i >= 0:
                hits.append(a + i)
                i = chunk.find(pattern, i + 1)
            a += step
        return sorted(set(hits))

    # -- breakpoints
    def break_pc(self, addr: int, **kw) -> int:
        return self.call("break.add", kind="pc", addr=addr, **kw)["id"]

    def watch(self, addr: int, access: str = "write", **kw) -> int:
        return self.call("break.add", kind="watch", addr=addr, access=access, **kw)["id"]

    def mmio(self, addr: int, length: int = 2, access: str = "access") -> int:
        return self.call("break.add", kind="mmio", addr=addr, len=length, access=access)["id"]

    def unbreak(self, bid: int | None = None):
        return self.call("break.clear") if bid is None else self.call("break.remove", id=bid)

    # -- capture
    def shot(self, path: str | os.PathLike, native: bool = False) -> Path:
        self.call("capture.screenshot", path=str(Path(path).resolve()), native=native)
        return Path(path)

    def digest(self) -> str:
        """FNV-1a hash of the current frame (deterministic for a given run; includes the pointer sprite)."""
        return self.call("capture.digest")["digest"]

    def region_digest(self, x, y, w, h) -> str:
        """Hash of a rectangle of the :meth:`shot` raster; pick one away from the pointer."""
        return self.call("capture.region_digest", x=x, y=y, w=w, h=h)["digest"]

    def wait_region(self, region, want: str | Sequence[str], timeout: float = 120, step: float = 1.0) -> float:
        """Run in ``step`` slices until the region's hash is one of ``want``; returns emulated seconds.

        This is the synchronisation primitive for navigation: wait for the screen you expect,
        never for a guessed delay.  Raises on timeout (emulated seconds)."""
        want = {want} if isinstance(want, str) else set(want)
        end = self.now() + timeout
        while True:
            if self.region_digest(*region) in want:
                return self.now()
            if self.now() >= end:
                raise CopperlineError(f"region {region} never reached {sorted(want)} within {timeout}s (last {self.region_digest(*region)})")
            self.run_for(step)

    def save_state(self, path):
        return self.call("state.save", path=str(Path(path).resolve()))

    def load_state(self, path):
        return self.call("state.load", path=str(Path(path).resolve()))

    # -- input (emulated-time precise)
    def type(self, text: str, at: float | None = None):
        p = {"text": text}
        if at is not None:
            p["at_seconds"] = at
        return self.call("input.type", **p)

    def key(self, raw: int, action: str = "tap", hold_ms: int = 80, at: float | None = None):
        p = {"rawkey": raw, "action": action, "hold_ms": hold_ms}
        if at is not None:
            p["at_seconds"] = at
        return self.call("input.key", **p)

    def mouse(self, dx=0, dy=0, left=None, right=None, port=1, at=None):
        p = {"dx": dx, "dy": dy, "port": port}
        if left is not None:
            p["left"] = left
        if right is not None:
            p["right"] = right
        if at is not None:
            p["at_seconds"] = at
        return self.call("input.mouse", **p)

    def mouse_to(self, x, y, port=1, tolerance=2, max_frames=120):
        """Steer the pointer to a pixel of :meth:`shot` (runs the machine)."""
        return self.call("input.mouse_to", x=x, y=y, port=port, tolerance=tolerance, max_frames=max_frames)

    def click(self, button="left", hold: float = 0.1, port=1):
        t = self.now()
        self.mouse(**{button: True}, port=port, at=t)
        self.run_to(t + hold)
        self.mouse(**{button: False}, port=port, at=t + hold)
        self.run_to(t + hold + 0.05)

    def double_click(self, hold: float = 0.08, gap: float = 0.12, button="left", port=1):
        self.click(button, hold, port)
        self.run_for(gap)
        self.click(button, hold, port)

    def joy(self, port=2, at=None, **dirs):
        p = {"port": port, **{k: bool(v) for k, v in dirs.items()}}
        if at is not None:
            p["at_seconds"] = at
        return self.call("input.joy", **p)


def _cli(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version")
    s = sub.add_parser("shot", help="boot an HDF and screenshot at --at seconds")
    s.add_argument("hdf", nargs="?")
    s.add_argument("out")
    s.add_argument("--df0")
    s.add_argument("--at", type=float, default=30)
    s.add_argument("--model", default="A1200")
    a = ap.parse_args(argv)
    if a.cmd == "version":
        print(subprocess.run([copperline_bin(), "--version"], capture_output=True, text=True).stdout.strip())
        return 0
    m = Machine(model=a.model, ide=a.hdf, floppies=[a.df0] if a.df0 else ())
    r = capture(m, Schedule().shot(a.at, a.out))
    print(r.log.splitlines()[-1] if r.log else "", f"rc={r.returncode} wall={r.wall:.1f}s")
    return r.returncode


if __name__ == "__main__":
    sys.exit(_cli())
