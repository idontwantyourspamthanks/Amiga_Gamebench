"""Tests that need no emulator: config rendering, icon format, image structure, patch verification."""
from __future__ import annotations

import re
import struct
import subprocess
from pathlib import Path

import pytest

import amigaicon
from clharness import Machine, Schedule

ROOT = Path(__file__).resolve().parent.parent


# --- Machine / config -----------------------------------------------------------------------

def test_machine_defaults_are_the_target():
    t = Machine().toml()
    assert 'profile = "A1200"' in t
    assert "amiga-os-310-a1200.rom" in t          # Kickstart 3.1, never the bundled AROS
    assert 'fast = "8M"' in t
    assert "rtc_time" in t                         # seeded clock: reproducible runs


def test_machine_storage_sections():
    t = Machine(ide="/x/a.hdf", floppies=["/x/d1.adf", "/x/d2.adf"],
                filesys=[("/w", "Workbench", False, 6), ("/g", "Game", True)]).toml()
    assert t.count("[[filesys]]") == 2
    assert 'master = "/x/a.hdf"' in t
    assert "[floppy.df1]" in t and "drives = 2" in t
    assert "bootpri = 6" in t and "readonly = true" in t
    # a floppy-only machine must not grow an [ide] section
    assert "[ide]" not in Machine(floppies=["/x/d1.adf"]).toml()


def test_schedule_flags():
    s = Schedule().press(10, "space").double_click(20).expect(30, "a.png", 0.001)
    assert s.args[:3] == ["--press-after", "10", "space"]
    assert s.args.count("--click-after") == 2
    assert s.args[-4:] == ["--expect-screenshot", "30", "a.png", "0.001"]


# --- Workbench icon writer ------------------------------------------------------------------

def _synthetic_tool_icon() -> bytes:
    """A valid 16x4, 1-plane tool icon built from the format description (no Commodore data)."""
    head = bytearray(78)
    head[0:4] = b"\xe3\x10\x00\x01"
    struct.pack_into(">II", head, 22, 1, 0)             # GadgetRender present, no SelectRender
    head[48] = amigaicon.WBTOOL
    struct.pack_into(">ii", head, 58, amigaicon.NO_POS, amigaicon.NO_POS)
    struct.pack_into(">I", head, 74, 4096)
    image = struct.pack(">HHHHH", 0, 0, 16, 4, 1) + b"\0\0\0\1" + b"\x01\x00" + b"\0\0\0\0"   # 20-byte header
    return bytes(head) + image + bytes(8)               # 16 px * 4 rows * 1 plane = 8 bytes


def test_icon_roundtrip_exact():
    raw = _synthetic_tool_icon()
    assert amigaicon.Icon.parse(raw).build() == raw


def test_project_icon_gets_default_tool_and_stack():
    out = amigaicon.project_icon(_synthetic_tool_icon(), "C:IconX", stack=40000)
    ic = amigaicon.Icon.parse(out)
    assert (ic.type, ic.default_tool, ic.stack) == (amigaicon.WBPROJECT, "C:IconX", 40000)
    assert ic.tooltypes is None and ic.tail == b""


def test_icon_with_tooltypes_roundtrips():
    out = amigaicon.project_icon(_synthetic_tool_icon(), "C:IconX", tooltypes=["WINDOW=NIL:"])
    ic = amigaicon.Icon.parse(out)
    assert ic.tooltypes == ["WINDOW=NIL:"] and ic.build() == out


# --- the shipped hard-disk image ------------------------------------------------------------

def test_image_partitions_are_safe_for_a1200_ide(image):
    """MaxTransfer above 0x1FE00 corrupts reads over 128 KiB on the A1200's IDE path (mwII then crashes)."""
    info = subprocess.run(["rdbtool", str(image), "info"], capture_output=True, text=True, check=True).stdout
    parts = re.findall(r"Partition: #\d+ '(\w+)'", info)
    assert parts[:3] == ["DH0", "DH1", "DH2"]
    mts = [int(x, 16) for x in re.findall(r"max_transfer=(0x[0-9a-f]+)", info)]
    assert len(mts) == len(parts) and all(m <= 0x1FE00 for m in mts), mts
    assert info.count("bootable=1") == 1                         # only Workbench boots


def test_game_volumes_have_play_launchers(image, tmp_path):
    """Each game volume needs its Play script and an IconX project icon (a bare tool icon gurus)."""
    for dev, vol in (("DH1", "Midwinter2"), ("DH2", "Midwinter2Orig")):
        part = tmp_path / f"{dev}.hdf"
        subprocess.run(["rdbtool", str(image), "export", dev, str(part)], check=True, capture_output=True)
        script = subprocess.run(["xdftool", str(part), "type", "Play"], capture_output=True, text=True, check=True).stdout
        assert script.split()[-1] == "mwII" and "enhanced by dad_prg" in script and "CD" not in script.split()
        subprocess.run(["xdftool", str(part), "read", "Play.info", str(tmp_path / "p.info")], check=True, capture_output=True)
        ic = amigaicon.Icon.parse((tmp_path / "p.info").read_bytes())
        assert ic.type == amigaicon.WBPROJECT and ic.default_tool == "C:IconX"


@pytest.fixture(scope="module")
def patched_exe():
    p = ROOT / "games/done/Midwinter-2/work/build/MWII_direct"
    if not p.exists():
        pytest.skip("patched MWII not built (tools/mw2patch.py apply)")
    return p


def test_patched_exe_differs_from_original_only_where_intended(patched_exe, tmp_path):
    orig_adf = next((ROOT / "games/done/Midwinter-2/originals").glob("*Disk 1 of 3*SPL*.adf"), None)
    if orig_adf is None:
        pytest.skip("original disk 1 not available")
    orig = tmp_path / "MWII_orig"
    subprocess.run(["xdftool", str(orig_adf), "read", "MWII", str(orig)], check=True, capture_output=True)
    r = subprocess.run(["python3", str(ROOT / "tools/mw2patch.py"), "verify", str(orig), str(patched_exe)],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "verify: OK" in r.stdout, r.stdout + r.stderr


def test_vhd_is_the_same_disk_with_a_valid_fixed_footer(image):
    vhd = image.with_suffix(".vhd")
    if not vhd.exists():
        pytest.skip("no .vhd next to the image")
    raw, v = image.read_bytes(), vhd.read_bytes()
    assert v[:-512] == raw
    f = bytearray(v[-512:])
    assert f[:8] == b"conectix"
    size, cur = struct.unpack(">QQ", f[40:56])
    assert size == cur == len(raw)
    assert struct.unpack(">I", f[60:64])[0] == 2                      # fixed disk
    stored = struct.unpack(">I", f[64:68])[0]
    f[64:68] = bytes(4)
    assert stored == (~sum(f)) & 0xFFFFFFFF
