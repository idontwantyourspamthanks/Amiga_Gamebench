"""Drive Midwinter II's front end on FS-UAE (A1200).

Menu flow found by tracing the game (see work/notes/boot_and_timing.md):

    boot start-up disk -> "insert graphics disk" -> hallway
    -> hold-press RAIDS -> hold-press a difficulty -> raid map
    -> click an island -> space -> "insert missions disk" -> ...

The front end needs a *held* mouse press for ~1 s; a quick click is missed by
its VBL sampler.  All positions are 720x566 pixels on the FS-UAE window.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'tools'))
from amigaharness import FSUAE
from amiganav import move_to

ORIGINALS = os.path.join(os.path.dirname(__file__), '..', 'originals')
D1 = os.path.join(os.path.dirname(__file__), '..', 'work', 'build', 'd1_skipintro.adf')
if not os.path.exists(D1):
    # Original start-up disk; the intro needs a ~1 s held left button.
    D1 = os.path.join(ORIGINALS, 'Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 1 of 3)[cr SPL].adf')
D2 = os.path.join(ORIGINALS, 'Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 2 of 3)(Graphics)[cr SPL].adf')
D3 = os.path.join(ORIGINALS, 'Midwinter II - Flames of Freedom v1.7.9.1991 (1991-09-07)(Rainbird)(Disk 3 of 3)(Missions)[cr SPL].adf')

# hallway menu
RAIDS = (281, 140)
LEVELS = {'novice': (110, 385), 'intermediate': (295, 385),
          'experienced': (470, 385), 'expert': (625, 385)}
# raid map islands (screen coords of the labels)
ISLANDS = {'agora': (130, 110), 'dhafra': (400, 140), 'lobos': (80, 240),
           'samargo': (330, 370), 'africa': (660, 370)}


def hold_click(h, x, y, hold=1.0, settle=4.0):
    """Move to (x, y) and hold the left button: the front end ignores clicks."""
    pos = move_to(h, x, y)
    h.mouse_down(1)
    h.wait(hold)
    h.mouse_up(1)
    h.wait(settle)
    return pos


def boot(h):
    h.wait(20)
    h.swap_floppy(1, 2)
    h.wait(8)
    h.grab_mouse()
    h.key('space')
    h.mouse_rel(1, 0)
    h.wait(0.3)


BRIEFING_QUESTION = (75, 420)
START_GAME = None  # filled in once the thumbs-up position is known


def boot_to_easy(disks=None, images=None):
    """Return an FSUAE instance sitting on the raid map.

    Mounting all three disks in df0/df1/df2 satisfies the game's
    "insert X disk into any drive" prompts without any swapping.
    """
    disks = disks or [D1, D2, D3]
    images = images or [D1, D2, D3]
    h = FSUAE(machine='A1200', disks=disks, images=images, warp=True)
    boot(h)
    hold_click(h, *RAIDS)
    return h


D1_DIRECT = os.path.join(os.path.dirname(__file__), '..', 'work', 'build', 'd1_direct.adf')
BRIEFING_QUESTION = (75, 420)
THUMBS_UP = (600, 45)


def boot_to_cockpit(d1=None, extra=None, warp=True):
    """Boot the three-drive set and play the front end through to the 3D cockpit.

    Verified recipe (2026-11-14, A1200, Kickstart 3.1): boot d1, ~30 s, grab the mouse,
    space (past the "press fire"), RAIDS, INTERMEDIATE, space on the raid map (jumps to the
    CAMARGO briefing), "?" icon, thumbs-up -> cockpit. Every press is HELD ~1 s.
    Returns the FSUAE instance (emulation running, no debugger entered yet).
    """
    d1 = d1 or D1
    h = FSUAE(machine='A1200', disks=[d1, D2, D3], images=[d1, D2, D3], warp=warp,
              extra=extra)
    h.wait(30)
    h.grab_mouse()
    h.key('space')
    h.mouse_rel(1, 0)
    h.wait(0.3)
    hold_click(h, *RAIDS)
    hold_click(h, *LEVELS['intermediate'])
    h.key('space')
    h.wait(12)
    hold_click(h, *BRIEFING_QUESTION)
    hold_click(h, *THUMBS_UP, hold=1.0, settle=8.0)
    return h
