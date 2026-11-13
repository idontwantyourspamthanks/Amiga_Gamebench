---
name: amiga-adf-and-hunks
description: Practical facts about Amiga ADF floppy images, AmigaDOS bootblocks, hunk executables and how to patch them in place on floppy-only releases. Covers disk geometry, OFS/FFS, xdftool usage, hunk parsing gotchas, flat-image disassembly, disk space budgeting and byte-level build verification. Use whenever reading, unpacking, rebuilding or patching an Amiga game disk.
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
- `tools/amigabin.py flat` lays hunks out sequentially from `--base` and resolves relocations. **This is a static layout, not the runtime layout**: LoadSeg allocates non-chip hunks in one block and chip hunks separately, and the base varies with the OS version, startup sequence and RAM. Use the flat image for disassembly and the map to translate offsets; read the actual base from the debugger when it matters.

`tools/m68dis.py` disassembles a flat image (`--base` for runtime addresses, `--cpu 68020`), labels call targets, answers `--xref`/`--callers`, and annotates Amiga custom-chip/CIA registers.

## Patching a floppy-only release

Constraints:
- A stock Midwinter II program disk has about **19 KB free** (OFS, 97% full). Do not assume room for a 32 KB payload like the Atari ST build.
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
