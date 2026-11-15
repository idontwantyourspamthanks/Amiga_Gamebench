#!/usr/bin/env python3
"""Find and drive the mouse cursor on FS-UAE Amiga screenshots.

The Midwinter II front-end draws a 16x16 white arrow; this module finds it by
connected components and can close the loop from the current position to a
target. FS-UAE loses the first relative motion after the pointer grab, so a
priming move is required.

    from amiganav import find_cursor, move_to
    move_to(h, 273, 132)          # hover the RAIDS label
"""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

# Front-end label boxes to ignore when looking for the arrow (720x568 shots).
LABELS = [
    (135, 45, 265, 80), (455, 45, 615, 80),
    (230, 115, 315, 150), (310, 115, 400, 150), (400, 115, 490, 150),
]


def find_cursor(path: str | Path, labels: list[tuple[int, int, int, int]] | None = None):
    """Return (area, x, y) for the white arrow, or None."""
    labels = LABELS if labels is None else labels
    im = cv2.imread(str(path))
    b, g, r = cv2.split(im)
    mask = ((b > 225) & (g > 225) & (r > 225)).astype(np.uint8)
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    outside, inside = [], []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if not (8 <= area <= 160 and 4 <= w <= 24 and 6 <= h <= 26):
            continue
        cx, cy = centroids[i]
        candidate = (int(area), float(cx), float(cy))
        if any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in labels):
            inside.append(candidate)
        else:
            outside.append(candidate)
    # Prefer a component outside the labels, but do not lose the arrow when it
    # is over a label (the common case just before a click).
    pool = outside or inside
    return max(pool, key=lambda c: c[0]) if pool else None


def move_to(h, x: int, y: int, tries: int = 10, tolerance: int = 12,
            step: int = 120, wait: float = 0.6) -> tuple[int, int] | None:
    """Move the guest cursor to (x, y) using screenshot feedback.

    `h` is an amigaharness.FSUAE already grabbed and primed. Returns the last
    detected position, or None if the cursor was lost.
    """
    last = None
    for _ in range(tries):
        shot = h.screenshot(h.scratch / "nav.png")
        cursor = find_cursor(shot)
        if cursor is None:
            return last
        _, cx, cy = cursor
        last = (int(cx), int(cy))
        dx, dy = x - cx, y - cy
        if abs(dx) <= tolerance and abs(dy) <= tolerance:
            return last
        h.mouse_rel(int(max(-step, min(step, dx))), int(max(-step, min(step, dy))))
        time.sleep(wait)
    return last


def find_wb_pointer(path: str | Path):
    """Return (x, y) of the Workbench 3.1 pointer's hot spot (top-left of the red arrow), or None.

    The Workbench pointer is red/orange with a dark outline; the hot spot is the tip, which is
    the top-left corner of its bounding box.
    """
    im = cv2.imread(str(path))
    b, g, r = cv2.split(im)
    mask = ((r > 170) & (g < 110) & (b < 110)).astype(np.uint8)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    best = None
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if 20 <= area <= 400 and 6 <= w <= 30 and 8 <= h <= 34:
            if best is None or area > best[0]:
                best = (int(area), int(x), int(y))
    return (best[1], best[2]) if best else None


def wb_move_to(h, x: int, y: int, tries: int = 14, tolerance: int = 6,
               step: int = 80, wait: float = 0.35) -> tuple[int, int] | None:
    """Move the Workbench pointer's hot spot to (x, y) (720x568 screenshot coordinates)."""
    last = None
    for _ in range(tries):
        pos = find_wb_pointer(h.screenshot(h.scratch / "nav.png"))
        if pos is None:
            return last
        last = pos
        dx, dy = x - pos[0], y - pos[1]
        if abs(dx) <= tolerance and abs(dy) <= tolerance:
            return last
        h.mouse_rel(int(max(-step, min(step, dx))), int(max(-step, min(step, dy))))
        time.sleep(wait)
    return last


def wb_double_click(h, x: int, y: int, settle: float = 3.0, hold: float = 0.12, gap: float = 0.12):
    """Hover (x, y) then double-click with explicit press/release steps.

    Each press is held ~`hold` s so it spans several frames (a zero-length click can fall between
    two input samples), and the gap is small enough for Workbench's double-click interval.
    Run the emulator at warp=False: under warp the Amiga clock runs several times faster than
    the wall clock and the gap would exceed that interval.
    """
    pos = wb_move_to(h, x, y)
    for i in range(2):
        h.mouse_down(1)
        time.sleep(hold)
        h.mouse_up(1)
        if i == 0:
            time.sleep(gap)
    time.sleep(settle)
    return pos
