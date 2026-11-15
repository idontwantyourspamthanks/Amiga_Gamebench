#!/usr/bin/env python3
"""Minimal Workbench .info (DiskObject) reader/writer: enough to make launcher icons.

Layout (AmigaOS 2/3 DiskObject, big-endian):
    0   u16 magic 0xE310     2  u16 version 1
    4   Gadget (44 bytes)    48 u8 do_Type (1 disk, 2 drawer, 3 tool, 4 project, 5 garbage)
    50  u32 default tool*    54 u32 tool types*   58 i32 CurrentX   62 i32 CurrentY
    66  u32 drawer data*     70 u32 tool window*  74 u32 stack size
    78  [DrawerData 56 B if drawer*] [Image] [Image if SelectRender] [default tool]
        [tool types] [tool window] ...
An Image is a 20-byte header followed by ((w+15)//16)*2*h*depth bytes of planar data.
Strings are u32 length (including the NUL) + bytes + NUL; tool types are a u32 table
size ((n+1)*4) then each string likewise.  The `*` pointers on disk are just
"present" flags (the stored values are stale memory addresses).

    python3 tools/amigaicon.py show X.info
    python3 tools/amigaicon.py project TEMPLATE.info OUT.info --tool C:IconX --stack 40000 [--pos X Y] [--tt KEY=VAL ...]
"""
from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

NO_POS = 0x80000000
WBDISK, WBDRAWER, WBTOOL, WBPROJECT = 1, 2, 3, 4


def _image_len(buf: bytes, off: int) -> int:
    w, h, depth = struct.unpack_from(">HHH", buf, off + 4)
    return 20 + ((w + 15) // 16) * 2 * h * depth


@dataclass
class Icon:
    type: int
    stack: int
    pos: tuple[int, int]
    head: bytes                              # header + drawer data + images (before the default tool)
    default_tool: str | None = None          # None: no default-tool section
    tooltypes: list[str] | None = None       # None: no tool-type table; [] : present but empty
    tail: bytes = b""                        # tool window, OS2 drawer data 2, ...: kept verbatim

    @classmethod
    def parse(cls, raw: bytes) -> "Icon":
        if raw[:4] != b"\xe3\x10\x00\x01":
            raise ValueError("not an Amiga .info (bad magic/version)")
        dt_ptr, tt_ptr = struct.unpack_from(">II", raw, 50)
        pos = struct.unpack_from(">ii", raw, 58)
        drawer, _twin, stack = struct.unpack_from(">III", raw, 66)
        gad_render, gad_select = struct.unpack_from(">II", raw, 22)
        off = 78 + (56 if drawer else 0)
        if gad_render:
            off += _image_len(raw, off)
        if gad_select:
            off += _image_len(raw, off)
        head = raw[:off]
        dtool = None
        if dt_ptr:
            (n,) = struct.unpack_from(">I", raw, off)
            dtool = raw[off + 4: off + 4 + n].rstrip(b"\0").decode("latin1")
            off += 4 + n
        tts = None
        if tt_ptr:
            tts = []
            (tbl,) = struct.unpack_from(">I", raw, off)
            off += 4
            for _ in range(tbl // 4 - 1):
                (n,) = struct.unpack_from(">I", raw, off)
                tts.append(raw[off + 4: off + 4 + n].rstrip(b"\0").decode("latin1"))
                off += 4 + n
        return cls(raw[48], stack, pos, head, dtool, tts, raw[off:])

    def build(self) -> bytes:
        head = bytearray(self.head)
        head[48] = self.type
        struct.pack_into(">II", head, 50, int(self.default_tool is not None), int(self.tooltypes is not None))
        struct.pack_into(">ii", head, 58, *self.pos)
        struct.pack_into(">I", head, 74, self.stack)
        out = bytes(head)
        if self.default_tool is not None:
            b = self.default_tool.encode("latin1") + b"\0"
            out += struct.pack(">I", len(b)) + b
        if self.tooltypes is not None:
            out += struct.pack(">I", (len(self.tooltypes) + 1) * 4)
            for t in self.tooltypes:
                b = t.encode("latin1") + b"\0"
                out += struct.pack(">I", len(b)) + b
        return out + self.tail


def project_icon(template: bytes, default_tool: str, stack: int = 40000,
                 pos: tuple[int, int] | None = None, tooltypes: list[str] | None = None) -> bytes:
    """A project (script/document) icon that opens with ``default_tool``, imaged like ``template``."""
    ic = Icon.parse(template)
    ic.type = WBPROJECT
    ic.default_tool = default_tool
    ic.stack = stack
    ic.tooltypes = list(tooltypes) if tooltypes else None
    if pos:
        ic.pos = pos
    return ic.build()


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("info")
    p = sub.add_parser("project")
    p.add_argument("template")
    p.add_argument("out")
    p.add_argument("--tool", default="C:IconX")
    p.add_argument("--stack", type=int, default=40000)
    p.add_argument("--pos", nargs=2, type=int)
    p.add_argument("--tt", action="append", default=[])
    a = ap.parse_args(argv)
    if a.cmd == "show":
        ic = Icon.parse(Path(a.info).read_bytes())
        print(f"type={ic.type} stack={ic.stack} pos={ic.pos} tool={ic.default_tool!r} tooltypes={ic.tooltypes} "
              f"head={len(ic.head)} tail={len(ic.tail)}")
        return 0
    Path(a.out).write_bytes(project_icon(Path(a.template).read_bytes(), a.tool, a.stack,
                                         tuple(a.pos) if a.pos else None, a.tt))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
