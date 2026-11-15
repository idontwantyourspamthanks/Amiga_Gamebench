"""The shipped hard-disk image through the real boot path: RDB -> Kickstart 3.1 -> Workbench -> game."""
from __future__ import annotations

import shutil

import pytest

import amigahd
import mw2cl
import test_hd_image as hdt
from clharness import Machine, Session

pytestmark = pytest.mark.emu

DESKTOP_ICONS = (70, 40, 100, 150)          # field pixels: the volume icon column and its labels
VOLUME_ICON = (112, 124)                    # "Midwinter2" on the Workbench desktop (field pixels)
PLAY_ICON = (146, 97)                       # "Play" in the opened Midwinter2 drawer


def test_boots_to_workbench_with_every_volume(image, goldens):
    with Session(Machine(ide=image)) as s:
        s.run_to(30)
        goldens.check("desktop_icons_a1200_ks31", s.region_digest(*DESKTOP_ICONS))


def test_vhd_boots_to_the_same_desktop_as_the_hdf(image, goldens):
    vhd = image.with_suffix(".vhd")
    if not vhd.exists():
        pytest.skip("no .vhd next to the image")
    with Session(Machine(ide=vhd)) as s:
        s.run_to(30)
        goldens.check("desktop_icons_a1200_ks31", s.region_digest(*DESKTOP_ICONS))


@pytest.mark.parametrize("game,device", [("mw2", "DH1"), ("mw2orig", "DH2")])
def test_game_loads_bit_exact_from_the_hard_disk(image, scratch_dir, game, device):
    """After LoadSeg every hunk in RAM equals the relocated file on the volume.

    This is the regression test for the MaxTransfer bug: with 0xFFFFFF the IDE path returned wrong
    data past 128 KiB and the game crashed with a Guru that changed with the memory layout.
    """
    scratch = scratch_dir / f"load_{game}.hdf"
    amigahd.scratch(image, scratch, amigahd.autorun_script(game))
    exe = hdt.exe_from_volume(image, device)
    with Session(Machine(ide=scratch)) as g:
        g.run_to(1.0)
        res = hdt.check_load(g, exe)
    assert res["bad"] == {}, res


def test_desktop_click_through_starts_the_game(image, scratch_dir):
    """The user path: double-click the volume, double-click Play -> the game reaches its hallway."""
    scratch = scratch_dir / "clickthrough.hdf"
    shutil.copyfile(image, scratch)                      # Workbench writes icon positions: never the shipped image
    with mw2cl.MW2(Machine(ide=scratch)) as s:
        s.run_to(30)
        s.mouse_to(*VOLUME_ICON)
        s.double_click()
        s.run_for(4)
        s.mouse_to(*PLAY_ICON)
        s.double_click()
        s.boot()                                         # the patched game now offers the M/J/K selector first
