"""Shared fixtures for the Amiga gamebench tests.

    python3 -m pytest tests -m "not emu"        # static tests only (no emulator, seconds)
    python3 -m pytest tests                     # everything (several minutes: real boots)
    python3 -m pytest tests --image dist/X.hdf  # test a specific image (default: newest dist/Amiga_enhanced_games_*.hdf)
    python3 -m pytest tests --bless             # rewrite tests/goldens.json from this run

Emulator tests are marked `emu`: they need tools/bin/copperline (tools/fetch_copperline.sh), the
Kickstart ROMs in os/Kickstart and a built image; they are skipped, not failed, when those are missing.
Goldens are frame *hashes* (no pictures are committed); they are only valid for the emulator
version and image they were recorded with, which goldens.json states.
"""
from __future__ import annotations

import glob
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "games" / "in_progress" / "Midwinter-2" / "tools"))

GOLDENS = Path(__file__).with_name("goldens.json")


def pytest_addoption(parser):
    parser.addoption("--image", default=None, help="hard-disk image to test")
    parser.addoption("--bless", action="store_true", help="record goldens instead of comparing")


def pytest_configure(config):
    config.addinivalue_line("markers", "emu: needs the Copperline emulator, Kickstart ROMs and a built image")


def _emulator_problem(image: Path | None) -> str | None:
    from clharness import KICK_DIR, KICKSTARTS, CopperlineError, copperline_bin
    try:
        copperline_bin()
    except CopperlineError as e:
        return str(e)
    if not (KICK_DIR / KICKSTARTS["A1200"]).exists():
        return "Kickstart 3.1 A1200 ROM missing in os/Kickstart"
    if image is None or not image.exists():
        return "no hard-disk image: run tools/make_amiga_hd.py"
    return None


def pytest_collection_modifyitems(config, items):
    image = _find_image(config)
    problem = _emulator_problem(image)
    if problem:
        skip = pytest.mark.skip(reason=problem)
        for it in items:
            if "emu" in it.keywords:
                it.add_marker(skip)


def _find_image(config) -> Path | None:
    if config.getoption("--image"):
        return Path(config.getoption("--image"))
    found = sorted(glob.glob(str(ROOT / "dist" / "Amiga_enhanced_games_*.hdf")))
    return Path(found[-1]) if found else None


@pytest.fixture(scope="session")
def image(request) -> Path:
    img = _find_image(request.config)
    if img is None:
        pytest.skip("no hard-disk image")
    return img


class Goldens:
    def __init__(self, bless: bool):
        self.bless = bless
        self.data = json.loads(GOLDENS.read_text()) if GOLDENS.exists() else {}

    def check(self, name: str, value: str):
        if self.bless:
            self.data[name] = value
            GOLDENS.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n")
            return
        assert name in self.data, f"no golden for {name!r}; run with --bless (value {value})"
        assert value == self.data[name], f"{name}: {value} != golden {self.data[name]}"


@pytest.fixture(scope="session")
def goldens(request) -> Goldens:
    return Goldens(request.config.getoption("--bless"))


@pytest.fixture(scope="session")
def scratch_dir():
    with tempfile.TemporaryDirectory(prefix="gbtest-") as td:
        yield Path(td)


@pytest.fixture(scope="session")
def cockpit(image, scratch_dir):
    """cockpit(game) -> a MW2 session restored to the in-game cockpit of `game` (built once per game).

    The first call boots a scratch copy of the image through the real boot path and the front end
    (minutes), saves a Copperline state; every later call starts a fresh emulator and loads it.
    """
    import amigahd
    import mw2cl
    from clharness import Machine

    cache: dict[str, tuple[Path, Path]] = {}
    opened: list = []

    def make(game: str):
        if game not in cache:
            scratch = scratch_dir / f"{game}.hdf"
            amigahd.scratch(image, scratch, amigahd.autorun_script(game))
            state = scratch_dir / f"{game}_cockpit.clstate"
            with mw2cl.MW2(Machine(ide=scratch)) as g:
                g.boot()
                g.to_cockpit()
                g.save_state(state)
            cache[game] = (scratch, state)
        scratch, state = cache[game]
        g = mw2cl.MW2(Machine(ide=scratch))
        opened.append(g)
        g.load_state(state)
        return g

    yield make
    for g in opened:
        g.close()
