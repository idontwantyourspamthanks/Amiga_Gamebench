# Midwinter II: Flames of Freedom — Amiga

*Midwinter II: Flames of Freedom*, Rainbird, 1991 (Amiga release 1.7, 7 September 1991). Port of the finished Atari ST work in `AtariST/gamebench/games/done/midwinter2`: same behaviour, Amiga implementation, **floppy-only**, targeting a fast **Amiga 1200**.

Status: **disks chosen; port not started.** The bench, tools and harness are in place. The plan is [`PLAN.md`](PLAN.md).

## Chosen release: the three-disk SPL set

| Disk | Volume | MD5 | Used | Free |
|---|---|---|---|---|
| `...Disk 1 of 3)[cr SPL].adf` | `program` | `a30c167b5eb21f5a47df8c56b0b65574` | 72.6% | 241 KB |
| `...Disk 2 of 3)(Graphics)[cr SPL].adf` | `grafix` | `3ea7341676d76d3466c160e0622bfbe5` | 89.7% | 90 KB |
| `...Disk 3 of 3)(Missions)[cr SPL].adf` | `missions` | `3211405db6bbb4dfaaf2bbb54fbc4ee7` | 46.4% | 471 KB |

All three are standard AmigaDOS OFS disks with valid bootblocks; the game boots through Kickstart and `S/startup-sequence` runs `INTRO` then `mwII`.

## Why this set, and not the others

Eleven images were supplied, from three groups. Facts, not guesses:

| Set | Disks | Layout | Executable | Notes |
|---|---|---|---|---|
| **SPL** | 3 (program, grafix, missions) | AmigaDOS OFS | `MWII`, 505488 bytes, file date **01.01.1978** | No cracktro file. `INTRO` 34952 bytes. Startup sequence names MFD/Sepultura. HD-install helper files dated 2012. `xdftool list` clean. |
| QTX | 3 (+ `[a]` variants) | AmigaDOS OFS | `mwii`, 505488 bytes | **59 bytes differ** from SPL's executable, concentrated at the crack/entry area; the rest is byte-identical. Adds `benny` (Quartex cracktro) and has no `INTRO`. `[a]` disk 1 has a **corrupt bitmap** (`Bitmap Block Count Mismatch`) and `[a]` disks 2/3 were re-dated 2020 with an extra `l/` directory. |
| PRD | 2 (program+missions, graphics) | AmigaDOS OFS | `mwii`, 276816 bytes | A repack: 8 hunks, four BSS hunks whose sizes exactly match SPL's four segments, plus a 0x50-byte loader and a 0x4367C data hunk. `INTRO` 62640, `PARADISES_INFOS`, extra shell tools. Not the retail 3-disk layout. |

Decision:
1. **SPL is the retail 3-disk layout with the least-modified executable.** `MWII` keeps the original 1978 date and differs from QTX only by 59 bytes (the crack patch), so it is not a repack.
2. **The data disks are equivalent.** SPL and QTX `grafix` files have identical MD5 sums (only `grafix.xdfmeta`, metadata, differs); every `missions/campaign` and mission file across SPL, QTX and PRD that was compared is identical.
3. **PRD is rejected as the base** because its custom 8-hunk/BSS loader is a bigger reverse-engineering surface for no benefit, and it is not the retail disk layout.
4. **QTX is rejected as the base** because of the extra cracktro, the modified startup sequence, and the damaged `[a]` disk; SPL's executable is the same program with a smaller modification.
5. **Space is not a constraint.** Disk 1 has 241 KB free (SPL `info`: 483 blocks), disk 2 90 KB, disk 3 471 KB. A 32 KB patch payload can live on disk 1 as a file, or as an appended hunk.

### Cleanup required in the release build

The SPL `S/startup-sequence` and `INTRO` are a 1991 crack release and contain an offensive slur and a long Sepultura cracktro. The shipped startup sequence will **replace** this file: skip `INTRO`, print the required `vX.Y enhanced by dad_prg` credit, then run `mwII`. Verify the game still initialises without `INTRO` (the crack may install something there; if so, keep the file but bypass its text).

## Files the game reads

- Disk 1 (`program`): `MWII` (the load file), `INTRO`, `cods.bin`, `midword.fsd`, `fastmemfirst`, `binddrivers`, `setpatch`, startup sequence, HD-install helpers.
- Disk 2 (`grafix`): `grafdir`, `grafix/*` (backgrounds, sprites, overlays).
- Disk 3 (`missions`): `missdir`, `missions/*` (campaign and island data).

Keep volume names and file names. The game's own loader and its "insert disk" prompts depend on them.

## Executable facts (from `tools/amigabin.py`)

SPL `MWII` is a standard load file:

| Hunk | Type | Size | Relocations |
|---|---|---|---|
| 0 | CODE | 217912 (0x35338) | 15113 |
| 1 | DATA | 84432 (0x149D0) | 1083 |
| 2 | BSS | 100000 (0x186A0) | 0 |
| 3 | DATA (chip) | 138204 (0x21BDC) | 0 |

The first code hunk begins `4EF9 0002....` (a jump into the same hunk), so entry is not necessarily offset 0 of the code. Determine it from the load file and confirm live.

## Supplied but unused variants

The originals folder also contains the QTX and PRD sets and the `[a]` variants. They stay as reference (`diff` fodder); the build tool will refuse them.

## Midwinter (1)

Five ADFs of *Midwinter* (1990, Rainbird, Defjam/CCS/ACC) are in `../Midwinter/originals/`. All five use **non-AmigaDOS bootblocks and custom trackloaders** (`xdftool` cannot list them). That is a different patching approach (byte-level in the image, loader checksums) and is not started. Not required for the Midwinter II port.
