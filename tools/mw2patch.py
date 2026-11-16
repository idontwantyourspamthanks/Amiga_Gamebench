#!/usr/bin/env python3
"""Apply the Midwinter II Amiga direct-controls patch to MWII (and optionally an ADF).

    python3 tools/mw2patch.py find      MWII
    python3 tools/mw2patch.py apply     MWII OUT
    python3 tools/mw2patch.py apply-adf IN.adf OUT.adf MWII
    python3 tools/mw2patch.py verify    MWII PATCHED

What is patched (see games/done/Midwinter-2/patches/p5_direct.s):

  * the in-game input accumulate routine (mode 2 of the input poller)  -> `jmp blob.handler`
  * the X-axis steering consumer                                      -> `jmp blob.cons`
  * a ~190 byte blob appended to CODE hunk 0, assembled with vasm (68000 code).

Why a blob: the original consumer is 50 bytes and has only three absolute operands. The new
logic (mouse consume-and-clear with gain, joystick/keyboard held-VBL counting, a device gate)
needs more room and more operands. The tool therefore grows hunk 0 and rewrites its RELOC32
table: every absolute operand of the blob is a RELOC32 entry (target hunk 1 = DATA), and the
two `jmp` operands are moved from the DATA group to the hunk 0 group. Nothing else changes:
hunks 1..3, the loader view of every other relocation, and all addresses of existing code are
identical; the blob is simply more code at the end of hunk 0.

Sites are located by instruction skeleton, never by a runtime address, and every original
byte that is replaced is verified first. The operand values (DATA hunk offsets of the
accumulators, the output word and the mouse gate) are read out of the file itself.

Needs `vasmm68k_mot` (vasm) on PATH and `xdftool` (amitools) for apply-adf.
"""
from __future__ import annotations

import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import amigabin  # noqa: E402

ASM = ROOT / "games" / "done" / "Midwinter-2" / "patches" / "p5_direct.s"

# ---- site skeletons (operands excluded, so they match any linked layout) ------------------

# X consumer: clamp + deadzone; `move.w <ACC>,d0` precedes this skeleton by 6 bytes.
CONSUMER_SKEL = bytes.fromhex("b06800146e0630280014600ab06800166d0430280016")
CONSUMER_LEN = 50
# mode-2 accumulate of the poller: add.l d1,<ACC>; neg.l d0; add.l d0,<ACCY>; rts
HANDLER_RE = re.compile(rb"\xd3\xb9(....)\x44\x80\xd1\xb9(....)\x4e\x75", re.S)
HANDLER_LEN = 16
# mouse poller entry: tst.w <GATE>; beq.w +$f0; lea <x>,a0; btst.b #6,$bfe001
POLLER_RE = re.compile(rb"\x4a\x79(....)\x67\x00\x00\xf0\x41\xf9....\x08\x39\x00\x06\x00\xbf\xe0\x01", re.S)

# Device selector ("Press 'M' for Mouse / 'J' / 'K'"): the retail game calls it with `bsr.w` right after the
# start-up `jsr` below.  The SPL crack overwrote that call (and a second one) with four NOPs, which is why
# the selector never appeared.  The Quartex release still has `61 00 3b cc` (bsr.w to the routine) there.
SELECTOR_SLOT_RE = re.compile(rb"\x4e\xb9....(\x4e\x71\x4e\x71)\x4e\x71\x4e\x71\x43\xf9....\x41\xf9....\x4a\x10\x67\x0a", re.S)
# the routine itself: jsr <a>; move.w #-1,<w>; jsr <b>; move.w #1,$12e(a6); move.w #$a0,$1e(a6); move.w #$96,$20(a6)
SELECTOR_RE = re.compile(rb"\x4e\xb9....\x33\xfc\xff\xff....\x4e\xb9....\x3d\x7c\x00\x01\x01\x2e\x3d\x7c\x00\xa0\x00\x1e\x3d\x7c\x00\x96\x00\x20", re.S)


def find_selector(code: bytes) -> tuple[int, int]:
    slot = unique(code, SELECTOR_SLOT_RE, "device-selector call slot")
    slot = SELECTOR_SLOT_RE.match(code, slot).start(1)
    return slot, unique(code, SELECTOR_RE, "device-selector routine")


def selector_call(site: dict) -> bytes:
    disp = site["selector_to"] - (site["selector_at"] + 2)
    if not -0x8000 <= disp < 0x8000:
        raise PatchError("selector routine out of bsr.w range")
    return b"\x61\x00" + struct.pack(">h", disp)


JMP_ABS = b"\x4e\xf9"


class PatchError(SystemExit):
    pass


# ---- hunk file: only what we need (hunk 0 code + RELOC32) ----------------------------------

class Hunk0:
    """MWII with hunk 0 split into header | code | reloc groups | rest."""

    def __init__(self, raw: bytes):
        L = lambda o: struct.unpack_from(">I", raw, o)[0]  # noqa: E731
        if L(0) != 0x3F3 or L(4) != 0:
            raise PatchError("not a hunk executable (HUNK_HEADER with no resident names)")
        first, last = L(12), L(16)
        if first != 0:
            raise PatchError("unexpected first hunk")
        self.nhunks = last - first + 1
        self.size_off = 20                       # size word of hunk 0
        h0 = 20 + 4 * self.nhunks
        if L(h0) != 0x3E9:
            raise PatchError("hunk 0 is not CODE")
        self.nlongs = L(h0 + 4)
        self.code_off = h0 + 8
        self.code = bytearray(raw[self.code_off:self.code_off + 4 * self.nlongs])
        p = self.code_off + 4 * self.nlongs
        if L(p) != 0x3EC:
            raise PatchError("hunk 0 has no RELOC32 right after the code")
        p += 4
        self.groups: dict[int, list[int]] = {}
        self.group_order: list[int] = []
        while L(p) != 0:
            cnt, tgt = L(p), L(p + 4)
            offs = list(struct.unpack_from(f">{cnt}I", raw, p + 8))
            if tgt in self.groups:
                raise PatchError("duplicate RELOC32 target group")
            self.groups[tgt] = offs
            self.group_order.append(tgt)
            p += 8 + 4 * cnt
        self.reloc_end = p + 4                   # after the terminating 0
        if L(self.reloc_end) != 0x3F2:
            raise PatchError("hunk 0 has trailing hunk blocks this tool does not understand")
        self.raw = raw
        self.h0_off = h0

    def reloc_bytes(self) -> bytes:
        out = struct.pack(">I", 0x3EC)
        for tgt in self.group_order:
            offs = self.groups[tgt]
            if offs:
                out += struct.pack(">II", len(offs), tgt) + struct.pack(f">{len(offs)}I", *offs)
        return out + struct.pack(">I", 0)

    def serialise(self) -> bytes:
        raw = self.raw
        assert len(self.code) % 4 == 0
        nlongs = len(self.code) // 4
        size_word = struct.unpack_from(">I", raw, self.size_off)[0]
        size_word = (size_word & 0xC0000000) | nlongs
        return (raw[:self.size_off] + struct.pack(">I", size_word)
                + raw[self.size_off + 4:self.h0_off + 4]
                + struct.pack(">I", nlongs) + bytes(self.code)
                + self.reloc_bytes() + raw[self.reloc_end:])


def long_at(code: bytes | bytearray, off: int) -> int:
    return struct.unpack_from(">I", code, off)[0]


def reloc_target(h: Hunk0, off: int) -> int:
    hits = [t for t, offs in h.groups.items() if off in offs]
    if len(hits) != 1:
        raise PatchError(f"no unique RELOC32 entry at hunk-0 offset {off:#x}: {hits}")
    return hits[0]


# ---- site discovery --------------------------------------------------------------------------

def unique(code: bytes, pattern, what: str) -> int:
    if isinstance(pattern, bytes):
        hits = [m.start() for m in re.finditer(re.escape(pattern), code)]
    else:
        hits = [m.start() for m in pattern.finditer(code)]
    if len(hits) != 1:
        raise PatchError(f"expected exactly 1 {what}, found {len(hits)}: {[hex(x) for x in hits]}")
    return hits[0]


def find_sites(h: Hunk0) -> dict:
    code = bytes(h.code)
    cons = unique(code, CONSUMER_SKEL, "consumer skeleton") - 6
    if code[cons:cons + 2] == JMP_ABS:
        raise PatchError("MWII is already patched (the consumer starts with jmp)")
    if code[cons:cons + 2] != b"\x30\x39" or code[cons - 2:cons] != b"\x4e\x75":
        raise PatchError("consumer is not preceded by rts / does not start with move.w <abs>,d0")
    orig = code[cons:cons + CONSUMER_LEN]
    if orig[0x1C:0x1E] != b"\x33\xc0" or orig[0x2A:0x2C] != b"\x33\xc0" or orig[0x30:0x32] != b"\x4e\x75":
        raise PatchError("consumer body differs from the expected 50-byte routine")
    acc = long_at(orig, 2)
    if long_at(orig, 0x1E) != acc:
        raise PatchError("consumer accumulator operands disagree")
    out = long_at(orig, 0x2C)

    handler = unique(code, HANDLER_RE, "poller mode-2 accumulate")
    m = HANDLER_RE.match(code, handler)
    if struct.unpack(">I", m.group(1))[0] != acc:
        raise PatchError("poller accumulate adds to a different accumulator than the consumer reads")
    accy = struct.unpack(">I", m.group(2))[0]

    poller = unique(code, POLLER_RE, "mouse poller entry")
    gate = struct.unpack(">I", POLLER_RE.match(code, poller).group(1))[0]

    # every operand we copy must be a DATA-hunk (1) relocation and each jmp slot must be one now
    for name, off in (("acc", cons + 2), ("out", cons + 0x2C), ("accy", handler + 10),
                      ("gate", poller + 2), ("handler acc", handler + 2)):
        if reloc_target(h, off) != 1:
            raise PatchError(f"{name} operand at {off:#x} does not relocate against the DATA hunk")
    sel_at, sel_to = find_selector(code)
    return dict(cons=cons, handler=handler, acc=acc, accy=accy, out=out, gate=gate,
                selector_at=sel_at, selector_to=sel_to)


# ---- blob assembly (vasm), with relocation discovery ---------------------------------------

def assemble(defs: dict[str, int], db: int) -> tuple[bytes, str]:
    with tempfile.TemporaryDirectory(prefix="mw2blob-") as tmp:
        out = Path(tmp) / "blob.bin"
        lst = Path(tmp) / "blob.lst"
        cmd = ["vasmm68k_mot", "-Fbin", "-m68000", "-no-opt", "-L", str(lst), "-o", str(out),
               str(ASM), f"-DDB={db}"] + [f"-D{k}={v}" for k, v in defs.items()]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            raise PatchError("vasm failed:\n" + r.stdout + r.stderr)
        return out.read_bytes(), lst.read_text()


def build_blob(site: dict) -> tuple[bytes, dict[str, int], list[int]]:
    """Return (blob bytes with DATA offsets, entry symbols, blob offsets of DATA relocations)."""
    defs = dict(ACC_OFF=site["acc"], ACCY_OFF=site["accy"], OUT_OFF=site["out"], GATE_OFF=site["gate"])
    shift = 0x10000000
    a, lst = assemble(defs, 0)
    b, _ = assemble(defs, shift)
    if len(a) != len(b):
        raise PatchError("blob size depends on DB (absolute operand optimised to short?)")
    relocs, i, diff = [], 0, 0
    while i + 4 <= len(a):
        va, vb = long_at(a, i), long_at(b, i)
        if vb - va == shift:
            relocs.append(i)
            i += 4
            continue
        i += 2 if i % 2 == 0 else 1
    # the shift only touches the top byte of each absolute operand
    changed = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if changed != relocs:
        raise PatchError("stray differences between the two assemblies; check the source")
    syms = {}
    for name in ("handler", "cons"):
        m = re.search(rf"^{name}\s+[0-9A-Z]{{1,2}}:([0-9A-Fa-f]+)", lst, re.M)
        if not m:
            raise PatchError(f"symbol {name} not found in listing")
        syms[name] = int(m.group(1), 16)
    return a, syms, relocs


# ---- apply -------------------------------------------------------------------------------------

def apply(raw: bytes, verbose: bool = True) -> bytes:
    h = Hunk0(raw)
    site = find_sites(h)
    blob, syms, blob_relocs = build_blob(site)
    blob += b"\x00" * (-len(blob) % 4)

    cons, handler = site["cons"], site["handler"]
    base = len(h.code)                           # hunk-0-relative start of the blob
    orig_cons = bytes(h.code[cons:cons + CONSUMER_LEN])
    orig_handler = bytes(h.code[handler:handler + HANDLER_LEN])
    if verbose:
        print(f"hunk 0: {len(h.code)} bytes, blob appended at +{base:#x} ({len(blob)} bytes)")
        print(f"consumer @ hunk0+{cons:#x}  orig {orig_cons.hex()}")
        print(f"handler  @ hunk0+{handler:#x}  orig {orig_handler.hex()}")
        print(f"DATA offsets: acc {site['acc']:#x} accy {site['accy']:#x} out {site['out']:#x} "
              f"gate {site['gate']:#x}")

    h.code += blob
    for off in blob_relocs:
        h.groups[1].append(base + off)
    # the two jmp operands now point into hunk 0 itself
    for site_off, entry in ((cons, "cons"), (handler, "handler")):
        slot = site_off + 2
        h.groups[1].remove(slot)
        h.groups.setdefault(0, [])
        if 0 not in h.group_order:
            h.group_order.append(0)
        h.groups[0].append(slot)
        h.code[site_off:site_off + 2] = JMP_ABS
        struct.pack_into(">I", h.code, slot, base + syms[entry])
    code_sel = site["selector_at"]
    if bytes(h.code[code_sel:code_sel + 4]) != b"\x4e\x71\x4e\x71":
        raise PatchError("selector slot is not two NOPs")
    h.code[code_sel:code_sel + 4] = selector_call(site)      # restore the M/J/K device-selector screen
    if verbose:
        print(f"relocs added to DATA group: {len(blob_relocs)}; moved to hunk-0 group: 2")
    return h.serialise()


def verify(orig_raw: bytes, new_raw: bytes) -> None:
    """Parse both files, relocate at one base, and check only sites + blob differ."""
    import os
    with tempfile.TemporaryDirectory(prefix="mw2v-") as tmp:
        po, pn = Path(tmp) / "o", Path(tmp) / "n"
        po.write_bytes(orig_raw)
        pn.write_bytes(new_raw)
        lo, ln = amigabin.LoadFile(str(po)), amigabin.LoadFile(str(pn))
    if [h.size for h in lo.hunks[1:]] != [h.size for h in ln.hunks[1:]]:
        raise PatchError("hunks 1..3 changed size")
    ho, hn = Hunk0(orig_raw), Hunk0(new_raw)
    site = find_sites(ho)
    old = bytes(ho.code)
    new = bytes(hn.code)
    assert new[:len(old)] != old
    diffs = [i for i in range(len(old)) if old[i] != new[i]]
    allowed = (set(range(site["cons"], site["cons"] + 6)) | set(range(site["handler"], site["handler"] + 6))
               | set(range(site["selector_at"], site["selector_at"] + 4)))
    stray = [i for i in diffs if i not in allowed]
    if stray:
        raise PatchError(f"unexpected modified bytes in the original code: {[hex(i) for i in stray[:8]]}")
    for t in (1, 2, 3):
        if t in ho.groups and t in hn.groups:
            extra = set(hn.groups[t]) - set(ho.groups[t])
            if any(e < len(old) for e in extra):
                raise PatchError("original code gained RELOC32 entries")
    for t, offs in ho.groups.items():
        lost = set(offs) - set(hn.groups.get(t, []))
        if lost and not (t == 1 and lost == {site["cons"] + 2, site["handler"] + 2}):
            raise PatchError(f"RELOC32 entries lost from target {t}: {[hex(x) for x in sorted(lost)]}")
    # blob data operands resolve to the same DATA offsets the original code used
    want = {site["acc"], site["acc"] + 2, site["accy"], site["out"], site["gate"]}
    got = {long_at(new, off) for off in hn.groups[1] if off >= len(old)}
    if got != want:
        raise PatchError(f"blob DATA operands {sorted(map(hex, got))} != {sorted(map(hex, want))}")
    for slot in (site["cons"] + 2, site["handler"] + 2):
        if long_at(new, slot) < len(old) or slot not in hn.groups[0]:
            raise PatchError("jmp operand does not point into the blob or is not relocated")
    for off in (site["selector_at"], site["selector_at"] + 1, site["selector_at"] + 2, site["selector_at"] + 3):
        if off not in diffs:
            raise PatchError("device-selector call was not restored")
    if new[site["selector_at"]:site["selector_at"] + 4] != selector_call(site):
        raise PatchError("device-selector call has the wrong displacement")
    print("verify: OK (only the two 6-byte jmp sites and the 4-byte selector call changed; blob relocs exact; hunks 1-3 intact)")


# ---- CLI ------------------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "find" and len(argv) == 3:
        h = Hunk0(Path(argv[2]).read_bytes())
        for k, v in find_sites(h).items():
            where = f"hunk-0 offset, file offset {v + h.code_off:#x}" if k in ("cons", "handler", "selector_at", "selector_to") \
                else "DATA hunk (1) offset"
            print(f"{k:8s} {v:#x} ({where})")
        return 0
    if cmd == "apply" and len(argv) == 4:
        src, dst = Path(argv[2]), Path(argv[3])
        raw = src.read_bytes()
        new = apply(raw)
        verify(raw, new)
        dst.write_bytes(new)
        print(f"wrote {dst}")
        return 0
    if cmd == "verify" and len(argv) == 4:
        verify(Path(argv[2]).read_bytes(), Path(argv[3]).read_bytes())
        return 0
    if cmd == "apply-adf" and len(argv) == 5:
        src, dst, mwii = Path(argv[2]), Path(argv[3]), Path(argv[4])
        raw = mwii.read_bytes()
        patched = apply(raw)
        verify(raw, patched)
        with tempfile.NamedTemporaryFile(prefix="mwii-", delete=False) as fh:
            fh.write(patched)
            tmp = fh.name
        try:
            dst.write_bytes(src.read_bytes())
            subprocess.run(["xdftool", str(dst), "delete", "MWII"], check=True, capture_output=True)
            subprocess.run(["xdftool", str(dst), "write", tmp, "MWII"], check=True, capture_output=True)
        finally:
            Path(tmp).unlink(missing_ok=True)
        print(f"wrote {dst}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
