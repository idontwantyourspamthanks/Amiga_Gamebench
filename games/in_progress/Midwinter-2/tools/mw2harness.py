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


def boot_to_easy(disks=None, images=None):
    """Return an FSUAE instance sitting on the raid map at difficulty chosen."""
    disks = disks or [D1]
    images = images or [D1, D2, D3]
    h = FSUAE(machine='A1200', disks=disks, images=images, warp=True)
    boot(h)
    hold_click(h, *RAIDS)
    return h
