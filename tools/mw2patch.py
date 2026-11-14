#!/usr/bin/env python3
"""Apply the Midwinter II Amiga patches to MWII (and optionally an ADF).

The patch sites are byte ranges inside the hunk file.  Because each absolute
operand in a replacement sits at exactly the same file offset as an operand in
the original code, the existing HUNK_RELOC32 entries relocate it at load time;
the patch tool therefore copies the *original file's* pre-relocation operand
values into the replacement and never needs to know the load base.

    python3 tools/mw2patch.py find   MWII
    python3 tools/mw2patch.py apply  MWII OUT
    python3 tools/mw2patch.py apply-adf IN.adf OUT.adf  MWII

Sites are located by instruction skeleton, not by absolute address, so the
same tool works for any build that contains the routine.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

# ---- sites ----------------------------------------------------------------

CONSUMER_SKEL = bytes.fromhex('b06800146e0630280014600ab06800166d0430280016')
CONSUMER_LEN = 50


def find_consumer(data: bytes) -> int:
    """Return the file offset of the X consumer (start of `move.w acc,d0`)."""
    hits = [i for i in range(len(data)) if data.startswith(CONSUMER_SKEL, i)]
    if len(hits) != 1:
        raise SystemExit(f"expected 1 consumer skeleton, found {len(hits)}: "
                         f"{[hex(h) for h in hits]}")
    return hits[0] - 6


def build_consumer(orig: bytes) -> bytes:
    """Consume-and-clear replacement built from the original file operands."""
    assert len(orig) == CONSUMER_LEN, len(orig)
    acc = orig[2:6]          # operand of `move.w <acc>,d0`
    out = orig[0x2A + 2:0x2A + 6]  # operand of `move.w d0,<out>`
    return (
        b'\x30\x39' + acc +            # move.w <acc>,d0
        bytes.fromhex('b0680014') +    # cmp.w $14(a0),d0
        bytes.fromhex('6e04') +        # bgt.s +4
        bytes.fromhex('30280014') +    # move.w $14(a0),d0
        bytes.fromhex('b0680016') +    # cmp.w $16(a0),d0
        bytes.fromhex('6d04') +        # blt.s +4
        bytes.fromhex('30280016') +    # move.w $16(a0),d0
        bytes.fromhex('4e71') +        # nop (keeps reloc offsets)
        b'\x42\xb9' + acc +            # clr.l <acc>
        bytes.fromhex('32280012') +    # move.w $12(a0),d1
        bytes.fromhex('6100003c') +    # bsr.w deadzone (displacement unchanged)
        b'\x33\xc0' + out +            # move.w d0,<out>
        bytes.fromhex('4e75')          # rts
    )


def apply(data: bytes) -> bytes:
    off = find_consumer(data)
    orig = data[off:off + CONSUMER_LEN]
    new = build_consumer(orig)
    print(f"consumer at file offset {off:#x}")
    print(f"  orig: {orig.hex()}")
    print(f"  new : {new.hex()}")
    if data[off - 2:off] != b'\x4e\x75':
        raise SystemExit("unexpected bytes before the consumer site")
    return data[:off] + new + data[off + len(new):]


# ---- CLI ------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "find" and len(argv) == 3:
        data = Path(argv[2]).read_bytes()
        off = find_consumer(data)
        print(f"consumer file offset {off:#x}")
        return 0
    if cmd == "apply" and len(argv) == 4:
        src, dst = Path(argv[2]), Path(argv[3])
        dst.write_bytes(apply(src.read_bytes()))
        print(f"wrote {dst}")
        return 0
    if cmd == "apply-adf" and len(argv) == 5:
        src, dst, mwii = Path(argv[2]), Path(argv[3]), Path(argv[4])
        patched = apply(mwii.read_bytes())
        with tempfile.NamedTemporaryFile(prefix="mwii-", delete=False) as fh:
            fh.write(patched)
            tmp = fh.name
        try:
            dst.write_bytes(src.read_bytes())
            subprocess.run(["xdftool", str(dst), "delete", "MWII"],
                           check=True, capture_output=True)
            subprocess.run(["xdftool", str(dst), "write", tmp, "MWII"],
                           check=True, capture_output=True)
        finally:
            Path(tmp).unlink(missing_ok=True)
        print(f"wrote {dst}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
