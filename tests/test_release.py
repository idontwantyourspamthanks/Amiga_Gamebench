"""The Midwinter II release zips (games/done/Midwinter-2/dist): content gate and a real floppy boot."""
from __future__ import annotations

import glob
import zipfile
from pathlib import Path

import pytest

import mw2release
from clharness import Machine

DIST = mw2release.DIST


def _latest(pattern: str) -> Path:
    found = sorted(glob.glob(str(DIST / pattern)))
    if not found:
        pytest.skip(f"no {pattern} in {DIST}: run games/done/Midwinter-2/tools/mw2release.py")
    return Path(found[-1])


def test_release_zips_match_their_sources():
    """HD files are the verified patched exe + the original data; floppy disk 1 has the credit, no cracker text."""
    _latest("Midwinter2_v*_patched_2*.zip")
    _latest("Midwinter2_v*_patched_floppies_*.zip")
    mw2release.check()


def test_hd_zip_is_one_folder_with_the_game_at_its_top_level():
    names = zipfile.ZipFile(_latest("Midwinter2_v*_patched_2*.zip")).namelist()
    assert all(n.startswith("MW2HD/") for n in names)
    for need in ("mwII", "progdir", "midword.fsd", "cods.bin", "Play", "README.txt"):
        assert f"MW2HD/{need}" in names, need
    assert any(n.startswith("MW2HD/grafix/") for n in names) and any(n.startswith("MW2HD/missions/") for n in names)


@pytest.mark.emu
def test_release_floppies_boot_to_the_hallway(tmp_path):
    """Three drives, as shipped: disk 1 boots, the selector appears, M reaches the hallway (INTRO skipped)."""
    import mw2cl
    zipfile.ZipFile(_latest("Midwinter2_v*_patched_floppies_*.zip")).extractall(tmp_path)
    disks = sorted(tmp_path.glob("*.adf"))
    assert len(disks) == 3
    with mw2cl.MW2(Machine(floppies=disks)) as g:
        g.boot()
