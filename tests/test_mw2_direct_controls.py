"""Midwinter II direct controls (patch p5_direct), asserted tick by tick on the emulated A1200.

Every test restores the same cockpit state, so results are exact.  The unpatched volume is the
negative control: it must show the "yoke" (accumulator persists, view keeps turning).

Patched mouse path: acc (long, hi word = half-counts since the last tick) -> blob consumer ->
D0 stored to `out` (turn value for the tick), acc cleared.  3 per half-count, capped at +-1000.
Joystick/keypad: a constant 50% of the vehicle's (clamp - deadzone) while held (+-200 for the jeep).
"""
from __future__ import annotations

import struct

import pytest

pytestmark = pytest.mark.emu


def s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def poke_acc(g, a, hi: int):
    g.write(a["acc"], struct.pack(">i", hi << 16))


def next_tick_d0(g, a) -> int:
    """Run to the blob's store of `out` and return D0 (the turn value about to be stored)."""
    bid = g.break_pc(a["store_pc"])
    try:
        r = g.run_to(g.now() + 5)
        assert r["reason"] == "breakpoint", r
        return s16(g.regs()["d"][0])
    finally:
        g.unbreak(bid)


def set_gates(g, a, mode: str):
    G = a["gate"]
    mouse, joy, keys = {"M": (1, 0, 0), "J": (0, 0xFFFF, 0), "K": (0, 0, 0xFFFF)}[mode]
    g.write_w(G, mouse)
    g.write_w(G - 4, joy)
    g.write_w(G - 2, keys)


def test_patch_is_loaded_in_patched_volume_only(cockpit):
    g = cockpit("mw2")
    a = g.locate()
    assert a["patched"] and a["blob_cons"] > a["consumer"]      # the blob is appended after the original code
    h = cockpit("mw2orig")
    assert not h.locate()["patched"]


@pytest.mark.parametrize("hi,want", [(20, 60), (-20, -60), (1, 3), (-1, -3), (0x7FFF, 1000), (-0x7FFF, -1000)])
def test_mouse_consume_and_clear_and_cap(cockpit, hi, want):
    g = cockpit("mw2")
    a = g.locate()
    poke_acc(g, a, hi)
    assert next_tick_d0(g, a) == want
    assert g.read_l(a["acc"]) == 0                       # consumed
    assert next_tick_d0(g, a) == 0                       # and nothing left over for the next tick


def test_no_input_no_turn(cockpit):
    g = cockpit("mw2")
    a = g.locate()
    h0 = g.read_w(a["heading"])
    g.run_for(6)
    assert g.read_w(a["heading"]) == h0
    assert g.read_w(a["out"]) == 0


def test_real_mouse_motion_turns_then_stops(cockpit):
    """Through the real poll path (injected counts), not a poke: the view turns by the motion and stops."""
    g = cockpit("mw2")
    a = g.locate()
    h0 = g.read_w(a["heading"])
    for _ in range(10):
        g.mouse(dx=8)
        g.run_frames(2)
    g.run_for(2)
    h1 = g.read_w(a["heading"])
    g.run_for(4)
    assert g.read_w(a["heading"]) == h1, "view kept turning after the mouse stopped"
    assert s16(h1 - h0) != 0
    assert g.read_w(a["out"]) == 0 and g.read_l(a["acc"]) == 0


@pytest.mark.parametrize("mode,press,release,want", [
    ("J", dict(left=True), dict(left=False), -200),
    ("J", dict(right=True), dict(right=False), 200),
])
def test_joystick_constant_rate_while_held(cockpit, mode, press, release, want):
    g = cockpit("mw2")
    a = g.locate()
    set_gates(g, a, mode)
    g.joy(port=2, **press)
    vals = [next_tick_d0(g, a) for _ in range(3)]
    g.joy(port=2, **release)
    g.run_for(1)
    after = next_tick_d0(g, a)
    assert vals == [want] * 3, vals
    assert after == 0, "turn must stop on release"


def test_unpatched_game_keeps_the_yoke(cockpit):
    """Negative control: the original keeps the clamped stick position and keeps turning."""
    g = cockpit("mw2orig")
    a = g.locate()
    h0 = g.read_w(a["heading"])
    g.write(a["acc"], struct.pack(">i", 0x7FFF << 16))
    g.run_for(2)
    assert g.read_l(a["acc"]) != 0, "original consumer clears the accumulator: not the yoke"
    assert s16(g.read_w(a["out"])) != 0
    g.run_for(3)
    assert g.read_w(a["heading"]) != h0
