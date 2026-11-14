"""Live probing helpers for Midwinter II on FS-UAE (A1200): dump RAM, find code by skeleton,
read/poke words, drive the mouse, read the registers at a breakpoint.

Addresses move between runs: always call `locate(h)` in the session you measure and use the
returned dict; never reuse a number from an earlier session or note.

    import sys; sys.path.insert(0, 'games/in_progress/Midwinter-2/tools')
    import mw2harness as mw, mw2probe as pr
    h = mw.boot_to_cockpit(mw.D1_DIRECT)
    a = pr.locate(h)                      # {'ram': bytes, 'consumer': 0x5c640, 'acc': ..., ...}
    print(pr.word(h, a['head']))
"""
from __future__ import annotations

import re
import struct
import time
from pathlib import Path

# Instruction skeletons (operands excluded) of the routines of interest in MWII.
CONSUMER_SKEL = bytes.fromhex("b06800146e0630280014600ab06800166d0430280016")  # clamp+deadzone body
HANDLER_TAIL = bytes.fromhex("4480d1b9")           # neg.l d0 ; add.l d0,<ACCY>   (mode-2 accumulate)
SIM_MULU = bytes.fromhex("c0fc003e")               # mulu.w #$3e,d0   (per-vehicle block index)
POLLER_SKEL = bytes.fromhex("0839000600bfe001")    # btst.b #6,$bfe001 (mouse poller, fixed HW operand)


def dump(h, name: str = "ram", start: int = 0, length: int = 0x200000, outdir: str = "/tmp") -> bytes:
    """Save `length` bytes of chip RAM through the debugger S command (about 12 s for 2 MB)."""
    path = Path(outdir) / f"{name}.bin"
    path.unlink(missing_ok=True)
    h.save_mem(path, start, length)
    for _ in range(40):                       # the S command returns before the file is complete
        if path.exists() and path.stat().st_size == length:
            break
        time.sleep(0.5)
    return path.read_bytes()


def findall(buf: bytes, pat: bytes) -> list[int]:
    out, i = [], buf.find(pat)
    while i >= 0:
        out.append(i)
        i = buf.find(pat, i + 1)
    return out


def locate(h, ram: bytes | None = None) -> dict:
    """Find the live addresses of the steering path in the current session.

    Works on the original and on the d1_direct build. For the patched build the consumer
    entry is a `jmp blob` and the blob address is reported too.
    """
    ram = ram or dump(h, "locate")
    hits = findall(ram, CONSUMER_SKEL)
    if len(hits) != 1:
        raise RuntimeError(f"consumer skeleton found {len(hits)} times: {[hex(x) for x in hits]}")
    cons = hits[0] - 6
    out = dict(ram=ram, consumer=cons)
    if ram[cons:cons + 2] == b"\x4e\xf9":      # patched: jmp <blob.cons>
        out["blob_cons"] = struct.unpack(">I", ram[cons + 2:cons + 6])[0]
        out["patched"] = True
        # blob.cons starts: move.w sr,d2; ori.w #$700,sr; move.l ACC,d0; clr.l ACC; move.w d2,sr; tst.w GATE
        m = re.match(rb"\x40\xc2\x00\x7c\x07\x00\x20\x39(....)\x42\xb9(....)\x46\xc2\x4a\x79(....)",
                     ram[out["blob_cons"]:out["blob_cons"] + 32], re.S)
        if not m or m.group(1) != m.group(2):
            raise RuntimeError("blob.cons prologue not recognised")
        out["acc"], out["gate"] = (struct.unpack(">I", m.group(1))[0], struct.unpack(">I", m.group(3))[0])
        tail = ram[out["blob_cons"]:out["blob_cons"] + 0xa0]
        out["out"] = struct.unpack(">I", re.search(rb"\x33\xc0(....)\x4e\x75", tail, re.S).group(1))[0]
        # blob.handler is 0x40 bytes before blob.cons (cnop 0,64); its Y accumulate: neg.l d0; add.l d0,ACCY
        hd = ram[out["blob_cons"] - 0x40:out["blob_cons"]]
        out["blob_handler"] = out["blob_cons"] - 0x40
        out["accy"] = struct.unpack(">I", re.search(rb"\x44\x80\xd1\xb9(....)\x4e\x75", hd, re.S).group(1))[0]
    else:
        out["patched"] = False
        out["acc"] = struct.unpack(">I", ram[cons + 2:cons + 6])[0]
        out["out"] = struct.unpack(">I", ram[cons + 0x2c:cons + 0x30])[0]
    return out


def word(h, addr: int) -> int:
    return struct.unpack(">H", h.read_mem(addr, 2))[0]


def long(h, addr: int) -> int:
    return struct.unpack(">I", h.read_mem(addr, 4))[0]


def poke(h, addr: int, *words: int) -> None:
    h.write_mem(addr, list(words))


def regrab(h) -> None:
    """Re-acquire the host mouse after any debugger stop (entering it releases the grab)."""
    h.resume()
    h.grab_mouse()
    h.mouse_rel(1, 0)
    time.sleep(0.4)


def mouse_burst(h, dx: int, step: int = 4, delay: float = 0.04) -> None:
    """Send `dx` host pixels in `step`-sized relative moves while the emulation runs."""
    s = step if dx > 0 else -step
    for _ in range(abs(dx) // step):
        h.mouse_rel(s, 0)
        time.sleep(delay)
