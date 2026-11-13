#!/usr/bin/env python3
"""Headless FS-UAE harness for Amiga game work: boot, screenshot, input, debugger.

    from amigaharness import FSUAE

    h = FSUAE(machine='A1200', disks=[d1, d2, d3])
    h.wait(20)
    h.screenshot('shot.png')
    h.key('Return')
    h.debugger('m 4')          # UAE console debugger (F12+D)
    h.close()

Each instance gets a private Xvfb display, a private scratch base dir and its
own floppy overlays, so the supplied ADFs are never written and instances can
run in parallel. Screenshots use the X server (`import -window`), not FS-UAE's
OpenGL read-back, which returns white under Xvfb.

Requires: fs-uae (3.2+), Xvfb, xdotool, ImageMagick (`import`).
Kickstart ROMs are looked up in <gamebench>/kickstarts; see kickstarts/README.md.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    from PIL import Image
except Exception:          # screenshot menu detection degrades gracefully
    Image = None

ROOT = Path(__file__).resolve().parent.parent
KICKSTARTS = ROOT / "kickstarts"
OS_KICKSTARTS = ROOT / "os" / "Kickstart"

# MD5 -> description. Only used for reporting; unknown ROMs are still usable.
KNOWN_ROMS = {
    "85ad74194e87c08904327de1a9443b7a": ("1.2", "Kickstart 1.2 rev 33.180 (A1000/A500)"),
    "82a21c1890cae844b3df741f2762d48d": ("1.3", "Kickstart 1.3 rev 34.5 (A500/A500+)"),
    "dc10d7bdd1b6f450773dfb558477c230": ("2.04", "Kickstart 2.04 rev 37.175 (A500+/A600)"),
    "646773759326fbac3b2311fd8c8793ee": ("3.1", "Kickstart 3.1 rev 40.68 (A1200)"),
    "e40a5dfb3d017ba8779faba30cbd1c8e": ("3.1", "Kickstart 3.1 rev 40.63 (A600)"),
    "465646c9b6729f77eea5314d1f057951": ("2.05", "Kickstart 2.05 rev 37.350 (A600)"),
}

# machine -> (amiga_model, kickstart key, implied options)
MACHINES = {
    "A500":      ("A500",      "1.3",  {}),
    "A500+":     ("A500+",     "2.04", {}),
    "A600":      ("A600",      "2.05", {}),
    "A1200":     ("A1200",     "3.1",  {}),
    "A1200/020": ("A1200/020", "3.1",  {}),
    "A1200/1230": ("A1200/1230", "3.1", {}),
    "A1200/1240": ("A1200/1240", "3.1", {}),
    "A4000":     ("A4000/040", "3.1",  {}),
}

# Preferred ROM file names, in order. `kickstart-3.1-a1200.rom` is the target.
ROM_NAMES = {
    "1.2": ["amiga-os-120.rom", "kickstart-1.2-a1000-a500.rom", "kickstart-1.2.rom"],
    "1.3": ["amiga-os-130.rom", "kickstart-1.3-a500-a500plus.rom", "kickstart-1.3.rom"],
    "2.04": ["amiga-os-204.rom", "kickstart-2.04-a500plus-a600.rom", "kickstart-2.04.rom"],
    "2.05": ["amiga-os-205-a600.rom", "kickstart-2.05-a600.rom"],
    "3.1": ["amiga-os-310-a1200.rom", "kickstart-3.1-a1200.rom", "kickstart-3.1.rom"],
}


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def rom_info(path: str | Path) -> dict:
    data = Path(path).read_bytes()
    md5 = hashlib.md5(data).hexdigest()
    text = data.decode("latin1", "ignore")
    known = KNOWN_ROMS.get(md5)
    if known:
        version, description = known
    else:
        m = re.search(r"KS ROM v(\d+\.\d+)", text) or re.search(r"Kickstart\s+(\d+\.\d+)", text)
        version = m.group(1) if m else "?"
        description = "unrecognised"
    return {"path": str(path), "size": len(data), "md5": md5,
            "version": version, "description": description}


def find_rom(key: str, explicit: str | None = None) -> Path | None:
    if explicit:
        return Path(explicit)
    for folder in (KICKSTARTS, OS_KICKSTARTS):
        for name in ROM_NAMES.get(key, []):
            candidate = folder / name
            if candidate.exists():
                return candidate
    # Last resort: any ROM in either folder whose recognised version matches.
    for folder in (KICKSTARTS, OS_KICKSTARTS):
        for candidate in sorted(folder.glob("*.rom")):
            if rom_info(candidate)["version"] == key:
                return candidate
    return None


def free_display() -> tuple[str, int]:
    for number in range(90, 120):
        if not Path(f"/tmp/.X{number}-lock").exists() and not Path(f"/tmp/.X11-unix/X{number}").exists():
            return f":{number}", number
    raise RuntimeError("no free X display")


class FSUAE:
    def __init__(self, machine: str = "A1200", disks: list[str] | None = None,
                 images: list[str] | None = None,
                 rom: str | None = None, extra: list[str] | None = None,
                 fast_mb: int | None = None, chip_kb: int | None = None,
                 warp: bool = False, headless: bool = True,
                 window_size: tuple[int, int] = (720, 568),
                 debugger: bool = True, copy_disks: bool = False):
        if machine not in MACHINES:
            raise ValueError(f"unknown machine {machine!r}; choose {sorted(MACHINES)}")
        self.machine = machine
        amiga_model, rom_key, implied = MACHINES[machine]
        self.rom_path = find_rom(rom_key, rom)
        self.using_aros = self.rom_path is None
        self.scratch = Path(tempfile.mkdtemp(prefix="amigrun-"))
        self.base = self.scratch / "base"
        self.base.mkdir()
        self.shots = self.scratch / "shots"
        self.shots.mkdir()
        self.log = self.scratch / "fs-uae.log"
        self.stdout_path = self.scratch / "stdout.txt"
        self.config_path = self.scratch / "test.fs-uae"
        self.disks = [str(Path(d).resolve()) for d in (disks or [])][:4]
        self.images = [str(Path(d).resolve()) for d in (images or disks or [])][:20]
        self.copy_disks = copy_disks
        if copy_disks:
            copied = []
            for i, disk in enumerate(self.disks):
                dest = self.scratch / f"df{i}.adf"
                shutil.copyfile(disk, dest)
                copied.append(str(dest))
            self.disks = copied

        self.display, display_number = free_display()
        self.xvfb = None
        self.wm = None
        self.proc = None
        self.window = None
        self._log_pos = 0
        self._in_debugger = False
        self._menu_open = False

        options = {
            "amiga_model": amiga_model,
            "fullscreen": "0",
            "window_width": str(window_size[0]),
            "window_height": str(window_size[1]),
            "window_x": "0",
            "window_y": "0",
            "window_border": "0",
            "video_sync": "0",
            "sound_output": "none",
            "floppy_drive_volume": "0",
            "floppy_drive_volume_empty": "0",
            "writable_floppy_images": "0",
            "floppy_overlays_dir": str(self.scratch / "overlays"),
            "screenshots_output_dir": str(self.shots),
            "screenshots_output_prefix": "fsuae",
            "log_file": str(self.log),
            "log_flush": "1",
            "console_debugger": "1" if debugger else "0",
            "automatic_input_grab": "1",
            "initial_input_grab": "1",
            "base_dir": str(self.base),
            "kickstart_file": str(self.rom_path) if self.rom_path else "",
            "warp_mode": "1" if warp else "0",
        }
        if chip_kb:
            options["chip_memory"] = str(chip_kb)
        if fast_mb is not None:
            options["fast_memory"] = str(fast_mb)
        elif machine.startswith("A1200/") and machine != "A1200/020":
            options["fast_memory"] = "8"
        if machine == "A1200/020":
            options["zorro_iii_memory"] = "0"
        for i, disk in enumerate(self.disks):
            options[f"floppy_drive_{i}"] = disk
        for i, image in enumerate(self.images):
            options[f"floppy_image_{i}"] = image
        for item in extra or []:
            if "=" not in item:
                raise ValueError(f"extra option must be key=value: {item!r}")
            k, v = item.split("=", 1)
            options[k.lstrip("-").replace("-", "_")] = v

        with open(self.config_path, "w") as fh:
            fh.write("[config]\n")
            for key, value in options.items():
                fh.write(f"{key} = {value}\n")

        self._start_xvfb(display_number)
        self._start_emulator()

        if not headless:
            print(f"display {self.display}, scratch {self.scratch}")

    # --- process management --------------------------------------------
    def _start_xvfb(self, number: int) -> None:
        self.xvfb = subprocess.Popen(
            ["Xvfb", f":{number}", "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            if Path(f"/tmp/.X11-unix/X{number}").exists():
                break
            time.sleep(0.1)
        else:
            raise RuntimeError(f"Xvfb :{number} did not start")
        # A window manager is required for FS-UAE to take focus and grab the
        # mouse; without one, pointer motion never reaches the guest.
        wm = os.environ.get("GAMEBENCH_WM") or shutil.which("twm") or shutil.which("matchbox-window-manager")
        if wm:
            self.wm = subprocess.Popen(
                [wm], env=dict(os.environ, DISPLAY=self.display),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.4)

    def _start_emulator(self) -> None:
        env = dict(os.environ, DISPLAY=self.display, SDL_AUDIODRIVER="dummy",
                   PYTHONUNBUFFERED="1")
        exe = shutil.which("fs-uae")
        if not exe:
            raise RuntimeError("fs-uae not found")
        self._stdout = open(self.stdout_path, "wb")
        cmd = [exe, str(self.config_path), "--stdout"]
        stdbuf = shutil.which("stdbuf")
        if stdbuf:
            cmd = [stdbuf, "-oL"] + cmd
        self.proc = subprocess.Popen(
            cmd,
            env=env, stdin=subprocess.PIPE, stdout=self._stdout,
            stderr=subprocess.STDOUT)
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"fs-uae exited early:\n{self.tail(2000)}")
            ids = self.windows()
            if ids:
                self.window = ids[-1]
                return
            time.sleep(0.2)
        raise RuntimeError(f"fs-uae window did not appear:\n{self.tail(2000)}")

    def windows(self) -> list[str]:
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", "FS-UAE"],
                env=dict(os.environ, DISPLAY=self.display),
                capture_output=True, text=True, timeout=5)
        except subprocess.TimeoutExpired:
            return []
        return result.stdout.split()

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    # --- log ------------------------------------------------------------
    def tail(self, n: int = 4000) -> str:
        try:
            data = Path(self.stdout_path).read_bytes()
        except FileNotFoundError:
            return ""
        return data[-n:].decode("latin1", "replace")

    def log_text(self) -> str:
        try:
            return Path(self.log).read_text(errors="replace")
        except FileNotFoundError:
            return ""

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)

    def wait_for(self, needle: str, timeout: float = 30, poll: float = 0.2) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if needle in self.tail(200000):
                return True
            time.sleep(poll)
        return False

    # --- display/input --------------------------------------------------
    def screenshot(self, path: str | Path | None = None) -> Path:
        if path is None:
            path = self.shots / f"shot-{int(time.time() * 1000)}.png"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["import", "-display", self.display, "-window", self.window,
                        str(path)], check=True)
        return path

    def _xdotool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["xdotool", *args], capture_output=True, text=True,
                              env=dict(os.environ, DISPLAY=self.display), timeout=20)

    def key(self, *keys: str) -> None:
        for key in keys:
            self._xdotool("key", "--window", self.window, key)

    def key_down(self, key: str) -> None:
        self._xdotool("keydown", "--window", self.window, key)

    def key_up(self, key: str) -> None:
        self._xdotool("keyup", "--window", self.window, key)

    def type_text(self, text: str) -> None:
        self._xdotool("type", "--window", self.window, text)

    def mouse_to(self, x: int, y: int) -> None:
        self._xdotool("mousemove", "--window", self.window, str(x), str(y))

    def mouse_rel(self, dx: int, dy: int) -> None:
        self._xdotool("mousemove_relative", "--", str(dx), str(dy))

    def mouse_click(self, button: int = 1) -> None:
        self._xdotool("click", str(button))

    def mouse_down(self, button: int = 1) -> None:
        self._xdotool("mousedown", str(button))

    def mouse_up(self, button: int = 1) -> None:
        self._xdotool("mouseup", str(button))

    def focus(self) -> None:
        self._xdotool("windowactivate", "--sync", self.window)
        self._xdotool("windowfocus", self.window)

    def grab_mouse(self) -> None:
        """Focus the window and click, so FS-UAE grabs the mouse."""
        self.focus()
        self.mouse_to(360, 280)
        self.mouse_click(1)
        time.sleep(0.3)

    # --- debugger -------------------------------------------------------
    def debugger(self, *commands: str, wait: float = 0.6) -> str:
        """Enter the UAE console debugger (once) and run commands; return new output."""
        if not self.alive():
            raise RuntimeError("emulator not running")
        before = len(self.tail(2_000_000))
        if not self._in_debugger:
            self.key("F12+d")
            if not self.wait_for("Activated debugger", timeout=10):
                raise RuntimeError("debugger did not activate (is console_debugger=1?)")
            time.sleep(0.5)
            self._in_debugger = True
            self._menu_open = True
            before = len(self.tail(2_000_000))
        for command in commands:
            self.proc.stdin.write((command + "\n").encode())
            self.proc.stdin.flush()
            time.sleep(wait)
        return self.tail(2_000_000)[before:]

    # --- memory (via the debugger; emulation is stopped while these run) ---
    def read_mem(self, addr: int, length: int) -> bytes:
        """Read `length` bytes; returns exactly that many (memory dump, 16/line)."""
        out = self.debugger(f"m {addr:x} {(length + 15) // 16}", wait=0.15 + length / 20000)
        data = bytearray()
        for line in out.splitlines():
            m = re.match(r"^([0-9A-Fa-f]{6,8})\s+((?:[0-9A-Fa-f]{4}\s*)+)", line)
            if not m:
                continue
            for word in m.group(2).split():
                data += struct.pack(">H", int(word, 16))
        if len(data) < length:
            raise RuntimeError(f"short memory read at {addr:#x}: {len(data)}/{length}")
        return bytes(data[:length])

    def read_word(self, addr: int) -> int:
        return struct.unpack(">H", self.read_mem(addr, 2))[0]

    def read_long(self, addr: int) -> int:
        return struct.unpack(">I", self.read_mem(addr, 4))[0]

    def write_mem(self, addr: int, words: list[int] | None = None, string: str | None = None) -> None:
        if string is not None:
            escaped = string.replace("'", "")
            self.debugger(f"W {addr:x} '{escaped}'", wait=0.3)
            return
        words = words or []
        for i in range(0, len(words), 64):
            chunk = " ".join(f"{w:04x}" for w in words[i:i + 64])
            self.debugger(f"W {addr + i * 2:x} {chunk}", wait=0.3)

    def save_mem(self, path: str | Path, addr: int, length: int) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if " " in str(path):
            raise ValueError("debugger S command cannot take a path with spaces")
        self.debugger(f"S {path} {addr:x} {length:x}", wait=0.5 + length / 200000)
        return path

    def breakpoint(self, addr: int) -> None:
        self.debugger(f"f {addr:x}", wait=0.2)

    def clear_breakpoints(self) -> None:
        self.debugger("fd", wait=0.2)

    def run(self) -> None:
        self.debugger("g", wait=0.1)
        self._in_debugger = False

    def frame_stats(self) -> dict:
        """Cumulative frame counter/time from the debugger's `c` command."""
        out = self.debugger("c", wait=0.4)
        m = re.search(r"frames:\s*(\d+)\s+time:\s*(\d+)", out)
        avg = re.search(r"Average frame time:\s*([\d.]+)\s*ms", out)
        if not m:
            raise RuntimeError(f"no frame stats in debugger output:\n{out[-800:]}")
        frames, time_us = int(m.group(1)), int(m.group(2))
        return {
            "frames": frames,
            "time_us": time_us,
            "seconds": time_us / 1e6,
            "avg_frame_ms": float(avg.group(1)) if avg else None,
            "fps": frames / (time_us / 1e6) if time_us else None,
        }

    def fps(self, seconds: float = 5.0) -> dict:
        """Measure presented-frame rate over `seconds` of emulated time.

        Leaves the emulator paused in the debugger; call resume() to continue.
        """
        first = self.frame_stats()
        self.resume()
        time.sleep(seconds)
        second = self.frame_stats()
        df = second["frames"] - first["frames"]
        dt = (second["time_us"] - first["time_us"]) / 1e6
        return {"seconds": dt, "frames": df,
                "fps": df / dt if dt else None,
                "start": first, "end": second}

    def registers(self) -> str:
        return self.debugger("r", wait=0.3)

    def memory_map(self) -> str:
        return self.debugger("dm", wait=0.5)

    def custom_regs(self) -> str:
        return self.debugger("e", wait=0.5)

    def tasks(self) -> str:
        return self.debugger("T", wait=0.5)

    def history(self, count: int = 32) -> str:
        return self.debugger(f"H {count}", wait=0.5)

    def menu_open(self) -> bool:
        """True when the FS-UAE host menu panel is visible on the right."""
        if Image is None:
            return self._menu_open
        path = self.scratch / "menucheck.png"
        self.screenshot(path)
        im = Image.open(path).convert("L")
        w, h = im.size
        box = im.crop((max(0, w - 190), 0, w, h))
        total = box.size[0] * box.size[1]
        mean = sum(i * c for i, c in enumerate(box.histogram())) / total
        return mean > 4

    def close_menu(self) -> None:
        """Close the FS-UAE host menu if it is open (F12 toggles it)."""
        if self.menu_open():
            self._xdotool("key", "--window", self.window, "F12")
            time.sleep(0.2)
        self._menu_open = False

    def resume(self) -> None:
        if self._in_debugger:
            self.proc.stdin.write(b"g\n")
            self.proc.stdin.flush()
            self._in_debugger = False
            time.sleep(0.2)
            if self._menu_open:
                self._xdotool("key", "--window", self.window, "F12")
                self._menu_open = False

    # --- shutdown -------------------------------------------------------
    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        if self.wm and self.wm.poll() is None:
            self.wm.terminate()
            try:
                self.wm.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.wm.kill()
        if self.xvfb and self.xvfb.poll() is None:
            self.xvfb.terminate()
            try:
                self.xvfb.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.xvfb.kill()
        try:
            self._stdout.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def cmd_roms(_args) -> int:
    print(f"kickstart directory: {KICKSTARTS}")
    found = sorted(KICKSTARTS.glob("*.rom")) + sorted(OS_KICKSTARTS.glob("*.rom"))
    if not found:
        print("  (none)")
    print(f"  {KICKSTARTS}" + ("" if KICKSTARTS.exists() else " (missing)"))
    print(f"  {OS_KICKSTARTS}" + ("" if OS_KICKSTARTS.exists() else " (missing)"))
    for path in found:
        info = rom_info(path)
        print(f"  {path.name:44s} {info['size']:>7} bytes  md5 {info['md5']}  "
              f"v{info['version']}  {info['description']}")
    missing = [k for k in ("1.3", "2.04", "3.1") if not find_rom(k)]
    if missing:
        print(f"\nmissing for machines in use: {', '.join(missing)}")
        print("See kickstarts/README.md; 3.1 is required for A1200 gates.")
    return 0


def cmd_run(args) -> int:
    disks = [d for d in args.disks]
    h = FSUAE(machine=args.machine, disks=disks, warp=args.warp,
              fast_mb=args.fast_mb, chip_kb=args.chip_kb, headless=False)
    try:
        print(f"rom: {h.rom_path or 'AROS (no Kickstart found)'}")
        print(f"scratch: {h.scratch}")
        print(f"stdout: {h.stdout_path}")
        h.wait(args.seconds)
        if args.screenshot:
            print(f"screenshot: {h.screenshot(args.screenshot)}")
        if args.keys:
            h.key(*args.keys.split(","))
            h.wait(1)
            if args.screenshot2:
                print(f"screenshot: {h.screenshot(args.screenshot2)}")
        if args.hold:
            print("running; press Ctrl-C to stop")
            while h.alive():
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        h.close()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("roms", help="list available Kickstart ROMs").set_defaults(func=cmd_roms)
    p = sub.add_parser("run", help="boot disks and take a screenshot")
    p.add_argument("disks", nargs="+")
    p.add_argument("--machine", default="A1200", choices=sorted(MACHINES))
    p.add_argument("--seconds", type=float, default=20)
    p.add_argument("--screenshot")
    p.add_argument("--keys", help="comma-separated xdotool keys to send after the wait")
    p.add_argument("--screenshot2")
    p.add_argument("--warp", action="store_true")
    p.add_argument("--fast-mb", type=int)
    p.add_argument("--chip-kb", type=int)
    p.add_argument("--hold", action="store_true")
    p.set_defaults(func=cmd_run)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
