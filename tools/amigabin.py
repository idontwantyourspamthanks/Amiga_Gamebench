#!/usr/bin/env python3
"""Amiga hunk executables: parse, relocate to a flat image, disassemble targets.

    python3 tools/amigabin.py info  MWII
    python3 tools/amigabin.py flat  MWII work/dumps/mwii_flat.bin --base 0
    python3 tools/amigabin.py entry MWII

`flat` writes the load image with every hunk laid out sequentially from
`--base` and all relocations resolved against that layout. Runtime address =
base + flat offset. The map is printed as JSON; redirect it if needed.

Only the load-file hunk types used by AmigaDOS (CODE, DATA, BSS, RELOC32,
SYMBOL, DEBUG, EXT, END) are handled. Overlays and libraries are rejected
explicitly instead of being parsed wrongly.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from dataclasses import dataclass, field

HUNK_CODE = 0x3E9
HUNK_DATA = 0x3EA
HUNK_BSS = 0x3EB
HUNK_RELOC32 = 0x3EC
HUNK_RELOC16 = 0x3ED
HUNK_RELOC8 = 0x3EE
HUNK_EXT = 0x3EF
HUNK_SYMBOL = 0x3F0
HUNK_DEBUG = 0x3F1
HUNK_END = 0x3F2
HUNK_HEADER = 0x3F3
HUNK_OVERLAY = 0x3F5
HUNK_BREAK = 0x3F6
HUNK_DREL32 = 0x3F7
HUNK_DREL16 = 0x3F8
HUNK_DREL8 = 0x3F9
HUNK_LIB = 0x3FA
HUNK_INDEX = 0x3FB

KIND = {
    HUNK_CODE: "CODE", HUNK_DATA: "DATA", HUNK_BSS: "BSS",
}
CHIP_FLAGS = {
    HUNK_CODE: "CODE", HUNK_DATA: "DATA", HUNK_BSS: "BSS",
}
EXT_SYMBOL, EXT_DEF, EXT_ABS, EXT_RESERVED, EXT_COMMON = 0, 1, 2, 0x81, 0x82


class HunkError(Exception):
    pass


@dataclass
class Hunk:
    kind: int
    index: int
    size: int                      # bytes as allocated
    file_offset: int               # where the hunk body starts in the file
    data: bytes = b""              # CODE/DATA only; BSS is zero-filled
    relocs: list[tuple[int, int]] = field(default_factory=list)  # (target hunk, byte offset)
    chip: bool = False
    name: str = ""

    @property
    def kind_name(self) -> str:
        return KIND.get(self.kind, f"${self.kind:04x}")


class LoadFile:
    def __init__(self, path: str):
        self.path = path
        with open(path, "rb") as fh:
            self.raw = fh.read()
        self.pos = 0
        self.hunks: list[Hunk] = []
        self.libs: list[str] = []
        self.header: tuple[int, int, int] | None = None
        self._parse()

    # --- primitives -----------------------------------------------------
    def _u32(self) -> int:
        if self.pos + 4 > len(self.raw):
            raise HunkError(f"truncated at {self.pos:#x}")
        value = struct.unpack_from(">I", self.raw, self.pos)[0]
        self.pos += 4
        return value

    def _skip(self, n: int) -> None:
        if self.pos + n > len(self.raw):
            raise HunkError(f"truncated at {self.pos:#x} (need {n})")
        self.pos += n

    # --- parser ---------------------------------------------------------
    def _parse(self) -> None:
        if self._u32() != HUNK_HEADER:
            raise HunkError("not a load file (no HUNK_HEADER)")
        while True:
            n = self._u32()
            if n == 0:
                break
            self.libs.append(self.raw[self.pos:self.pos + n * 4].rstrip(b"\0").decode("latin1"))
            self._skip(n * 4)
        table_size = self._u32()
        first = self._u32()
        last = self._u32()
        sizes = [(self._u32() & 0x3FFFFFFF) * 4 for _ in range(table_size)]
        self.header = (first, last, table_size)

        pending: Hunk | None = None
        while self.pos < len(self.raw):
            raw_kind = self._u32()
            chip = bool(raw_kind & 0x40000000)
            kind = raw_kind & 0x3FFFFFFF
            if kind in (HUNK_CODE, HUNK_DATA, HUNK_BSS):
                if pending is not None:
                    raise HunkError(f"hunk {pending.index} not terminated by HUNK_END")
                size = self._u32() * 4
                file_offset = self.pos
                if kind == HUNK_BSS:
                    pending = Hunk(kind, len(self.hunks), size, file_offset, chip=chip)
                else:
                    pending = Hunk(kind, len(self.hunks), size, file_offset,
                                   data=self.raw[self.pos:self.pos + size], chip=chip)
                    self._skip(size)
                self.hunks.append(pending)
            elif kind in (HUNK_RELOC32, HUNK_RELOC16, HUNK_RELOC8):
                if pending is None:
                    raise HunkError(f"relocation outside a hunk at {self.pos - 4:#x}")
                while True:
                    n = self._u32()
                    if n == 0:
                        break
                    target = self._u32()
                    for _ in range(n):
                        off = self._u32()
                        pending.relocs.append((target, off))
            elif kind == HUNK_SYMBOL:
                while True:
                    n = self._u32()
                    if n == 0:
                        break
                    self._skip(n * 4 + 4)
            elif kind == HUNK_DEBUG:
                n = self._u32()
                self._skip(n * 4)
            elif kind == HUNK_EXT:
                self._parse_ext()
            elif kind == HUNK_END:
                pending = None
            elif kind == HUNK_HEADER:
                raise HunkError("duplicate HUNK_HEADER")
            elif kind in (HUNK_OVERLAY, HUNK_BREAK, HUNK_LIB, HUNK_INDEX):
                raise HunkError(f"unsupported hunk type ${kind:04x} at {self.pos - 4:#x}")
            else:
                raise HunkError(f"unknown hunk type ${kind:04x} at {self.pos - 4:#x}")
        if pending is not None:
            raise HunkError(f"hunk {pending.index} not terminated")

    def _parse_ext(self) -> None:
        # Names and references; we only need to consume them.
        while True:
            n = self._u32()
            if n == 0:
                return
            name = self.raw[self.pos:self.pos + n * 4].rstrip(b"\0").decode("latin1")
            self._skip(n * 4)
            kind = self._u32()
            base = kind & 0x7F
            if kind == EXT_SYMBOL:
                continue
            if kind in (EXT_DEF, EXT_COMMON):
                if kind == EXT_COMMON:
                    self._u32()
                continue
            if kind == EXT_ABS:
                count = self._u32()
                self._skip(count * 4)
                continue
            if kind == EXT_RESERVED:
                continue
            raise HunkError(f"unsupported EXT type ${kind:02x} for {name}")

    # --- layout ---------------------------------------------------------
    def flat(self, base: int = 0, align: int = 8) -> tuple[bytes, dict]:
        """Lay hunks out sequentially from `base`, resolve relocations, return (image, map)."""
        addr: dict[int, int] = {}
        off = 0
        for hunk in self.hunks:
            addr[hunk.index] = base + off
            off += hunk.size
            off = (off + align - 1) & ~(align - 1)
        image = bytearray(off)
        for hunk in self.hunks:
            start = addr[hunk.index] - base
            body = hunk.data if hunk.kind != HUNK_BSS else b""
            image[start:start + len(body)] = body
        for hunk in self.hunks:
            start = addr[hunk.index] - base
            for target, roff in hunk.relocs:
                if target not in addr:
                    raise HunkError(f"relocation to missing hunk {target}")
                if roff + 4 > hunk.size:
                    raise HunkError(f"relocation at {roff:#x} beyond hunk {hunk.index}")
                value = struct.unpack_from(">I", image, start + roff)[0]
                struct.pack_into(">I", image, start + roff, addr[target] + value)
        info = {
            "path": self.path,
            "base": base,
            "size": off,
            "entry": addr[0] if self.hunks else None,
            "hunks": [
                {"index": h.index, "kind": h.kind_name, "size": h.size,
                 "addr": addr[h.index], "file_offset": h.file_offset,
                 "relocs": len(h.relocs)}
                for h in self.hunks
            ],
        }
        return bytes(image), info


def cmd_info(path: str) -> int:
    lf = LoadFile(path)
    print(f"{os.path.basename(path)}: load file, {len(lf.hunks)} hunks")
    if lf.libs:
        print(f"  resident libraries: {', '.join(lf.libs)}")
    for hunk in lf.hunks:
        print(f"  #{hunk.index} {hunk.kind_name:<4} size {hunk.size:6d} "
              f"file +{hunk.file_offset:#08x} relocs {len(hunk.relocs)}")
    return 0


def cmd_flat(path: str, out: str, base: int) -> int:
    lf = LoadFile(path)
    image, info = lf.flat(base)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "wb") as fh:
        fh.write(image)
    print(json.dumps(info, indent=2))
    return 0


def cmd_entry(path: str) -> int:
    lf = LoadFile(path)
    print(f"{lf.flat()[1]['entry']:#x}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info"); p.add_argument("file")
    p = sub.add_parser("flat"); p.add_argument("file"); p.add_argument("out")
    p.add_argument("--base", type=lambda s: int(s, 16), default=0)
    p = sub.add_parser("entry"); p.add_argument("file")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "info":
            return cmd_info(args.file)
        if args.cmd == "flat":
            return cmd_flat(args.file, args.out, args.base)
        return cmd_entry(args.file)
    except HunkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
