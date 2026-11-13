#!/usr/bin/env python3
"""Amiga ADF disk images: raw track access, bootblock checks, file I/O, diffs.

    python3 tools/adf.py info  disk.adf
    python3 tools/adf.py list  disk.adf
    python3 tools/adf.py unpack disk.adf DIR
    python3 tools/adf.py diff  a.adf b.adf
    python3 tools/adf.py boot  disk.adf

An ADF is the raw 901120-byte image of a 3.5" DD Amiga disk:
80 cylinders x 2 heads x 11 sectors x 512 bytes. Sectors inside a track are
stored in the order 0..10 (physical interleave is not represented in ADF).

File-level operations shell out to `xdftool` (amitools), which handles OFS
and FFS; raw operations use the image bytes directly.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys

CYLINDERS = 80
HEADS = 2
SECTORS = 11
SECTOR_SIZE = 512
TRACK_SIZE = SECTORS * SECTOR_SIZE
IMAGE_SIZE = CYLINDERS * HEADS * TRACK_SIZE  # 901120

# AmigaDOS bootblock: 'DOS' + filesystem type/flags, checksum, root block.
DOS_MAGIC = b"DOS"
FS_OFS = 0
FS_FFS = 1
FS_EXT = 2   # Directory caching (International/AmigaOS 3+)
FS_MASK = 0x07

BOOTBLOCK_CHECKSUM_OFFSET = 4
BOOTBLOCK_ROOT_OFFSET = 8
BOOTBLOCK_END = 1024


def bootblock_checksum(block: bytes) -> int:
    """Amiga bootblock checksum: sum of big-endian longs with end-around carry
    applied on every addition, field at +4 skipped, then complemented."""
    total = 0
    for off in range(0, BOOTBLOCK_END, 4):
        if off == BOOTBLOCK_CHECKSUM_OFFSET:
            continue
        total += struct.unpack_from(">I", block, off)[0]
        if total > 0xFFFFFFFF:      # end-around carry, per addition
            total = (total + 1) & 0xFFFFFFFF
    return (~total) & 0xFFFFFFFF


class BootBlock:
    def __init__(self, data: bytes):
        self.raw = bytes(data[:BOOTBLOCK_END])

    @property
    def magic(self) -> bytes:
        return self.raw[0:3]

    @property
    def flags(self) -> int:
        return self.raw[3]

    @property
    def fs(self) -> int:
        return self.flags & FS_MASK

    @property
    def fs_name(self) -> str:
        return {FS_OFS: "OFS", FS_FFS: "FFS", FS_EXT: "OFS+dir-cache"}.get(
            self.fs, f"type{self.fs}")

    @property
    def is_dos(self) -> bool:
        return self.magic == DOS_MAGIC

    @property
    def stored_checksum(self) -> int:
        return struct.unpack_from(">I", self.raw, BOOTBLOCK_CHECKSUM_OFFSET)[0]

    @property
    def computed_checksum(self) -> int:
        return bootblock_checksum(self.raw)

    @property
    def checksum_ok(self) -> bool:
        return self.stored_checksum == self.computed_checksum

    @property
    def root_block(self) -> int:
        return struct.unpack_from(">I", self.raw, BOOTBLOCK_ROOT_OFFSET)[0]

    def summary(self) -> str:
        if not self.is_dos:
            return (f"non-DOS bootblock: magic={self.magic.hex()} "
                    f"(custom loader / trackloader)")
        return (f"{self.fs_name} bootblock, flags=${self.flags:02x}, "
                f"root block {self.root_block}, checksum "
                f"{'OK' if self.checksum_ok else 'BAD'}")


class ADF:
    """A floppy image, addressable by cylinder/head/sector or linear block."""

    def __init__(self, path: str, readonly: bool = True):
        self.path = os.path.abspath(path)
        with open(self.path, "rb") as fh:
            self.data = bytearray(fh.read())
        self.readonly = readonly
        if len(self.data) != IMAGE_SIZE:
            raise SystemExit(f"{path}: {len(self.data)} bytes, expected {IMAGE_SIZE}")

    @staticmethod
    def offset(cyl: int, head: int, sector: int) -> int:
        return ((cyl * HEADS + head) * SECTORS + sector) * SECTOR_SIZE

    @staticmethod
    def linear_offset(block: int) -> int:
        return block * SECTOR_SIZE

    def track(self, track: int) -> bytes:
        return bytes(self.data[track * TRACK_SIZE:(track + 1) * TRACK_SIZE])

    def write_track(self, track: int, data: bytes) -> None:
        if self.readonly:
            raise RuntimeError("image opened read-only")
        if len(data) != TRACK_SIZE:
            raise ValueError(f"track must be {TRACK_SIZE} bytes")
        self.data[track * TRACK_SIZE:(track + 1) * TRACK_SIZE] = data

    def block(self, n: int) -> bytes:
        return bytes(self.data[n * SECTOR_SIZE:(n + 1) * SECTOR_SIZE])

    def write_block(self, n: int, data: bytes) -> None:
        if self.readonly:
            raise RuntimeError("image opened read-only")
        if len(data) != SECTOR_SIZE:
            raise ValueError(f"block must be {SECTOR_SIZE} bytes")
        self.data[n * SECTOR_SIZE:(n + 1) * SECTOR_SIZE] = data

    @property
    def bootblock(self) -> BootBlock:
        return BootBlock(self.data[:BOOTBLOCK_END])

    def save(self, path: str | None = None) -> None:
        with open(path or self.path, "wb") as fh:
            fh.write(self.data)

    def md5(self) -> str:
        return hashlib.md5(self.data).hexdigest()


def xdftool(image: str, *commands: str, readonly: bool = True) -> str:
    exe = shutil.which("xdftool")
    if not exe:
        raise SystemExit("xdftool not found (pip install amitools)")
    args = [exe]
    if readonly:
        args.append("-r")
    args.append(image)
    args.extend(commands)
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"xdftool failed ({result.returncode}): "
                         f"{result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def cmd_info(path: str) -> int:
    adf = ADF(path)
    print(f"{os.path.basename(path)}")
    print(f"  md5      {adf.md5()}")
    print(f"  size     {len(adf.data)} bytes")
    print(f"  boot     {adf.bootblock.summary()}")
    print(f"  volume   ", end="")
    try:
        out = xdftool(path, "info")
        print(out.strip().replace("\n", " "))
    except SystemExit as exc:
        print(f"(no AmigaDOS filesystem: {exc})")
    return 0


def cmd_list(path: str) -> int:
    print(xdftool(path, "list"), end="")
    return 0


def cmd_unpack(path: str, dest: str) -> int:
    if os.path.exists(dest):
        raise SystemExit(f"{dest}: already exists")
    os.makedirs(dest)
    xdftool(path, f"unpack / {dest}")
    return 0


def cmd_diff(a_path: str, b_path: str) -> int:
    a, b = ADF(a_path), ADF(b_path)
    blocks = []
    for block in range(len(a.data) // SECTOR_SIZE):
        if a.block(block) != b.block(block):
            blocks.append(block)
    print(f"{a_path}\n{b_path}")
    print(f"differing sectors: {len(blocks)} / {len(a.data)//SECTOR_SIZE}")
    if blocks:
        # Collapse to runs of consecutive sectors (track = 11 sectors).
        runs = []
        start = prev = blocks[0]
        for block in blocks[1:]:
            if block == prev + 1:
                prev = block
                continue
            runs.append((start, prev))
            start = prev = block
        runs.append((start, prev))
        for s, e in runs:
            t0, t1 = s // SECTORS, e // SECTORS
            print(f"  sectors {s}-{e}  (tracks {t0}-{t1})")
    return 0


def cmd_boot(path: str) -> int:
    adf = ADF(path)
    bb = adf.bootblock
    print(bb.summary())
    if not bb.is_dos:
        print("\nfirst 128 bytes of the bootblock:")
        for off in range(0, 128, 16):
            chunk = adf.data[off:off + 16]
            print(f"  {off:04x}: {chunk.hex(' ')}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info"); p.add_argument("image")
    p = sub.add_parser("list"); p.add_argument("image")
    p = sub.add_parser("unpack"); p.add_argument("image"); p.add_argument("dest")
    p = sub.add_parser("diff"); p.add_argument("a"); p.add_argument("b")
    p = sub.add_parser("boot"); p.add_argument("image")
    args = ap.parse_args(argv)
    return {
        "info": lambda: cmd_info(args.image),
        "list": lambda: cmd_list(args.image),
        "unpack": lambda: cmd_unpack(args.image, args.dest),
        "diff": lambda: cmd_diff(args.a, args.b),
        "boot": lambda: cmd_boot(args.image),
    }[args.cmd]()


if __name__ == "__main__":
    sys.exit(main())
