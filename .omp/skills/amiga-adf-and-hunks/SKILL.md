---
name: amiga-adf-and-hunks
description: Practical facts about Amiga ADF floppy images, RDB hard-disk images (MaxTransfer, rdbtool/xdftool), Workbench icons, AmigaDOS bootblocks, hunk executables and how to patch them in place. Covers disk geometry, OFS/FFS, xdftool usage, hunk parsing gotchas, flat-image disassembly, disk space budgeting and byte-level build verification. Use whenever reading, unpacking, rebuilding, patching or packaging an Amiga game disk or hard-disk image.
---

# ADF images and Amiga hunk programs

## ADF geometry

- 901120 bytes = 80 cylinders x 2 heads x 11 sectors x 512 bytes. `((cyl*2+head)*11+sector)*512`.
- ADF stores sectors in track order 0..10; physical interleave is not represented.
- Block number `n` in the filesystem is just `n*512` in the ADF.

`tools/adf.py` wraps this: `info`, `list`, `unpack`, `diff`, `boot`. `diff` collapses changed sectors to runs, which is what a build gate wants.

## Bootblock

- First 1024 bytes. `DOS` + flags byte: bit 0 = FFS (else OFS), bit 1 = directory cache (OFS only), bit 2/3 = international. Long at +4 is the bootblock checksum; long at +8 is the root block (usually 880).
- A checksum-valid bootblock with `DOS` boots through Kickstart and runs `S/startup-sequence` (1.3/2.0) or `startup-sequence` (3.x shells).
- A **non-DOS** bootblock (often `DOS` copies at +0x11 etc.) is a custom loader: the boot code reads tracks itself and the disk has no filesystem. `xdftool` cannot list it. Patching is then byte-level in the image, and the loader's own checksums/obfuscation must be understood.
  - Midwinter (1) Amiga disks are all this type (trackloader, Defjam/CCS/ACC crack). Midwinter II is standard OFS.

## Filesystem work

`xdftool <image> <cmd> ...` (amitools) handles OFS and FFS:
- `list`, `unpack / <dir>`, `info`, `bitmap`, `block <n>`.
- `write <hostfile> <amigapath>` writes a file; delete first if it exists.
- `format` creates a new OFS/FFS volume, but a fresh format loses the bootblock. For a bootable patched disk, **copy the original ADF and replace files**, rather than rebuilding from scratch.
- Old cracks may have damaged bitmaps: `list` can fail with `Bitmap Block Count Mismatch`. Treat such images as suspect; prefer another variant.

## Hunk executables (load files)

`tools/amigabin.py info|flat|entry` parses the types used by AmigaDOS. Format facts that cost time:

- `HUNK_HEADER` (0x3F3), then resident-library names (longword count, 0 terminates), then `table_size`, `first`, `last`, then exactly **`table_size`** size longs. `table_size` is the number of hunks, not "hunks - 1" (the latter is the library format).
- Every size in the header is in **longwords**, and the top bit (0x40000000) marks a **chip** hunk. Strip the flag before multiplying by 4.
- The hunk type word also carries the chip flag: a chip data hunk is `0x400003EA`, not `0x3EA`.
- Relocation offsets are **byte offsets inside the segment**. `RELOC32` entries are `count, target_hunk, offsets...`, terminated by count 0. The long at each offset is an offset within the target hunk; the loader adds the target's load address.
- `HUNK_EXT`, `HUNK_SYMBOL`, `HUNK_DEBUG`, `HUNK_END`: consume them correctly or the parser shifts. Overlays/libs are rejected on purpose.
- `tools/amigabin.py flat` lays hunks out sequentially from `--base` and resolves relocations. **This is a static layout, not the runtime layout**: LoadSeg allocates non-chip hunks in one block and chip hunks separately, and the base varies with the OS version, startup sequence and RAM. Use the flat image for disassembly and the map to translate offsets; read the real bases from Copperline (`segments.list`, or stop at `break.add kind=loadseg`) when it matters.

`tools/m68dis.py` disassembles a flat image (`--base` for runtime addresses, `--cpu 68020`), labels call targets, answers `--xref`/`--callers`, and annotates Amiga custom-chip/CIA registers.

## Patching a floppy-only release

Constraints:
- The SPL Midwinter II program disk (`program`) is 72.6% used with about **241 KB free** (483 free blocks; `xdftool info`). A 32 KB payload fits, but the patched `MWII` grows too (the appended blob is 196 bytes). (An earlier note of "19 KB free / 97% full" misread `xdftool list`'s data-vs-filesystem split of the used blocks.)
- Options, cheapest first:
  1. **Same-size in-place edits** in the executable (patch, then trampoline into a gap or into a new hunk).
  2. **Append a new hunk** to the executable: add `HUNK_CODE`, bump `table_size`/`last` and the size table, keep relocations valid. File grows by code + ~40 bytes of headers; verify with `adf.py diff` that only MWII's sectors changed.
  3. **A separate file on the boot disk**, loaded by a modified `S/startup-sequence` before the game runs. Needs the same free space but keeps the executable untouched.
  4. **RAM above the game** (`AllocMem` from startup or a fixed high address) for a large payload; a real A1200 has 2 MB chip + fast RAM, but a 1 MB A500 does not, so state the minimum machine. The Atari project's 32 KB payload lived in free RAM and was copied there by the loader; the Amiga equivalent needs an `AllocMem`/fixed-address proof.
- Any new boot sequence must still work when the game asks for disks 2 and 3 (volume names `grafix`, `missions`) and must not depend on a hard disk.

Build gates:
- `python3 tools/adf.py diff original.adf build.adf`: only expected sectors changed.
- Every patch site's original bytes are checked by the patch tool before writing; all-or-nothing.
- Cold boot from the built ADFs on the target machine; screenshot the title and the in-game view.

## Disk labels and the game's loader

Midwinter II's startup runs `INTRO` then `mwII`; the game later opens files by name from the volumes `program`, `grafix`, `missions`. If you rename a volume or repack a disk, the game's "insert disk" prompts and its directory cache break. Keep labels and file names identical unless the loader is patched and gated.

## Hard-disk images (RDB) and xdftool/rdbtool quirks

`tools/make_amiga_hd.py` builds the all-games disk; `tools/amigahd.py` makes scratch copies with a rewritten `S:User-Startup`; `tools/amigaicon.py` writes Workbench `.info` files.

- **MaxTransfer must be 0x1FE00 on every RDB partition** (`rdbtool IMG add ... max_transfer=0x1fe00`, or `rdbtool IMG change DH1 max_transfer=0x1fe00`). The amitools default 0xFFFFFF made the A1200 IDE path return wrong data for any read past the first 128 KiB of a transfer: a 218 KB hunk loaded corrupt and the game Guru'd differently with each memory layout. Check it with `rdbtool IMG info`.
- A 218 KB executable that LoadSegs bit-exact proves the read path: relocate the file with the real hunk bases (`segments.list`) and diff against RAM at the `loadseg` stop (`tools/test_hd_image.py check_load`).
- `rdbtool` commands are **separate argv items** (`create chs=C,H,S`, `init`, `add name=DH1 dostype=DOS1 bootable=False max_transfer=0x1fe00 size=8MiB`), `size=` accepts `MiB`. `import <part> <file>` needs a file of exactly the partition size; `export <part> <file>` gives one.
- `xdftool` takes the image type from the **file extension**: name the exported partition `*.hdf`. `unpack <host_dir>` (not `/ <dir>`); `format <volume> ffs`; `boot install`; `pack` needs `.blkdev`.
- Rewriting one file on an RDB partition: `rdbtool IMG export DH0 p.hdf; xdftool p.hdf delete S/User-Startup; xdftool p.hdf write host S/User-Startup; rdbtool IMG import DH0 p.hdf` (about 1 s).
- A fixed VHD is the raw disk + a 512-byte `conectix` footer (`make_amiga_hd.write_vhd`); Copperline reads it, use the raw `.hdf` for `dd` to real media.
- **Game-on-HD facts for Midwinter II:** the game's own installer (`dh0_install1`) copies `mwII, progdir, midword.fsd, cods.bin` plus all of `grafix:` and `missions:` to the **volume root** and runs `mwII`; it only works there (a drawer ends at "insert graphics disk"). It needs a CLI process: started as a Workbench tool (a plain tool icon) it Gurus. Hence a `Play` script run by `C:IconX` from a project icon (default tool `C:IconX`, stack 40000).
- Workbench `.info`: see `tools/amigaicon.py` (round-trips all 42 icons of the 3.1 Workbench disk byte-exactly). The on-disk "pointer" fields are present-flags; absent and empty tool-type tables are different.
