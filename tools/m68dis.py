#!/usr/bin/env python3
"""Disassemble Amiga 68k code (hunk images, RAM dumps) with labels and profile data.

    python3 tools/amigabin.py flat MWII work/dumps/mwii.bin --base 0
    python3 tools/m68dis.py work/dumps/mwii.bin 1234               # one routine
    python3 tools/m68dis.py work/dumps/mwii.bin 1234 --end 1300    # explicit range
    python3 tools/m68dis.py work/dumps/mwii.bin --xref dff180      # who touches a register
    python3 tools/m68dis.py work/dumps/mwii.bin --callers 1234     # call sites
    python3 tools/m68dis.py work/dumps/mwii.bin 1234 --base 10000  # runtime addresses
    python3 tools/m68dis.py work/dumps/mwii.bin 1234 --cpu 68020

A routine runs from its start to the next call target unless --end is given.
Call targets become `sub_XXXXXX` labels. Amiga hardware registers and common
custom-chip addresses are annotated. Profile input is `addr pct cycles` per
line (see tools/amigaharness.py profile).
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import struct
import sys

import capstone

# Amiga custom chip, CIA and common low-memory addresses.
HW: dict[int, str] = {
    0x000004: "ExecBase",
    0xBFD000: "CIA-B PRA", 0xBFD100: "CIA-B PRB", 0xBFD200: "CIA-B DDRA",
    0xBFD300: "CIA-B DDRB", 0xBFD400: "CIA-B TALO", 0xBFD500: "CIA-B TAHI",
    0xBFD600: "CIA-B TODLO", 0xBFD700: "CIA-B TODMID", 0xBFD800: "CIA-B TODHI",
    0xBFD900: "CIA-B SDR", 0xBFDA00: "CIA-B ICR", 0xBFDD00: "CIA-B CRA",
    0xBFDE00: "CIA-B CRB",
    0xBFE001: "CIA-A PRA", 0xBFE101: "CIA-A PRB", 0xBFE201: "CIA-A DDRA",
    0xBFE301: "CIA-A DDRB", 0xBFE401: "CIA-A TALO", 0xBFE501: "CIA-A TAHI",
    0xBFE601: "CIA-A TODLO", 0xBFE701: "CIA-A TODMID", 0xBFE801: "CIA-A TODHI",
    0xBFE901: "CIA-A SDR", 0xBFEA01: "CIA-A ICR", 0xBFED01: "CIA-A CRA",
    0xBFEE01: "CIA-A CRB",
    0xDFF000: "DMACON", 0xDFF002: "DMACONR", 0xDFF004: "VPOSR", 0xDFF006: "VHPOSR",
    0xDFF008: "DSKDATR", 0xDFF00A: "JOY0DAT", 0xDFF00C: "JOY1DAT", 0xDFF00E: "CLXDAT",
    0xDFF010: "ADKCONR", 0xDFF012: "POT0DAT", 0xDFF014: "POT1DAT", 0xDFF016: "POTGOR",
    0xDFF018: "SERDATR", 0xDFF01A: "DSKBYTR", 0xDFF01C: "INTENAR", 0xDFF01E: "INTREQR",
    0xDFF020: "DSKPTH", 0xDFF022: "DSKPTL", 0xDFF024: "DSKLEN", 0xDFF026: "DSKDAT",
    0xDFF028: "REFPTR", 0xDFF02A: "VPOSW", 0xDFF02C: "VHPOSW", 0xDFF02E: "COPCON",
    0xDFF030: "SERDAT", 0xDFF032: "SERPER", 0xDFF034: "POTGO", 0xDFF036: "JOYTEST",
    0xDFF038: "STREQU", 0xDFF03A: "STRVBL", 0xDFF03C: "STRHOR", 0xDFF03E: "STRLONG",
    0xDFF040: "BLTCON0", 0xDFF042: "BLTCON1", 0xDFF044: "BLTAFWM", 0xDFF046: "BLTALWM",
    0xDFF048: "BLTCPTH", 0xDFF04A: "BLTCPTL", 0xDFF04C: "BLTBPTH", 0xDFF04E: "BLTBPTL",
    0xDFF050: "BLTAPTH", 0xDFF052: "BLTAPTL", 0xDFF054: "BLTDPTH", 0xDFF056: "BLTDPTL",
    0xDFF058: "BLTSIZE", 0xDFF05A: "BLTCON0L", 0xDFF05C: "BLTSIZV", 0xDFF05E: "BLTSIZH",
    0xDFF060: "BLTCMOD", 0xDFF062: "BLTBMOD", 0xDFF064: "BLTAMOD", 0xDFF066: "BLTDMOD",
    0xDFF068: "BLTCDAT", 0xDFF06A: "BLTBDAT", 0xDFF06C: "BLTADAT",
    0xDFF07E: "SPRHDAT", 0xDFF080: "SPR0POS", 0xDFF082: "SPR0CTL", 0xDFF084: "SPR0DATA",
    0xDFF086: "SPR0DATB", 0xDFF088: "SPR1POS", 0xDFF08A: "SPR1CTL", 0xDFF08C: "SPR1DATA",
    0xDFF08E: "SPR1DATB", 0xDFF090: "SPR2POS", 0xDFF092: "SPR2CTL", 0xDFF094: "SPR2DATA",
    0xDFF096: "SPR2DATB", 0xDFF098: "SPR3POS", 0xDFF09A: "SPR3CTL", 0xDFF09C: "SPR3DATA",
    0xDFF09E: "SPR3DATB", 0xDFF0A0: "SPR4POS", 0xDFF0A2: "SPR4CTL", 0xDFF0A4: "SPR4DATA",
    0xDFF0A6: "SPR4DATB", 0xDFF0A8: "SPR5POS", 0xDFF0AA: "SPR5CTL", 0xDFF0AC: "SPR5DATA",
    0xDFF0AE: "SPR5DATB", 0xDFF0B0: "SPR6POS", 0xDFF0B2: "SPR6CTL", 0xDFF0B4: "SPR6DATA",
    0xDFF0B6: "SPR6DATB", 0xDFF0B8: "SPR7POS", 0xDFF0BA: "SPR7CTL", 0xDFF0BC: "SPR7DATA",
    0xDFF0BE: "SPR7DATB",
    0xDFF080: "SPR0PTH", 0xDFF082: "SPR0PTL", 0xDFF084: "SPR1PTH", 0xDFF086: "SPR1PTL",
    0xDFF088: "SPR2PTH", 0xDFF08A: "SPR2PTL", 0xDFF08C: "SPR3PTH", 0xDFF08E: "SPR3PTL",
    0xDFF090: "SPR4PTH", 0xDFF092: "SPR4PTL", 0xDFF094: "SPR5PTH", 0xDFF096: "SPR5PTL",
    0xDFF098: "SPR6PTH", 0xDFF09A: "SPR6PTL", 0xDFF09C: "SPR7PTH", 0xDFF09E: "SPR7PTL",
    0xDFF0A0: "AUD0LCH", 0xDFF0A2: "AUD0LCL", 0xDFF0A4: "AUD0LEN", 0xDFF0A6: "AUD0PER",
    0xDFF0A8: "AUD0VOL", 0xDFF0AA: "AUD0DAT",
    0xDFF0B0: "AUD1LCH", 0xDFF0B2: "AUD1LCL", 0xDFF0B4: "AUD1LEN", 0xDFF0B6: "AUD1PER",
    0xDFF0B8: "AUD1VOL", 0xDFF0BA: "AUD1DAT",
    0xDFF0C0: "AUD2LCH", 0xDFF0C2: "AUD2LCL", 0xDFF0C4: "AUD2LEN", 0xDFF0C6: "AUD2PER",
    0xDFF0C8: "AUD2VOL", 0xDFF0CA: "AUD2DAT",
    0xDFF0D0: "AUD3LCH", 0xDFF0D2: "AUD3LCL", 0xDFF0D4: "AUD3LEN", 0xDFF0D6: "AUD3PER",
    0xDFF0D8: "AUD3VOL", 0xDFF0DA: "AUD3DAT",
    0xDFF0E0: "BPLCON0", 0xDFF0E2: "BPLCON1", 0xDFF0E4: "BPLCON2", 0xDFF0E6: "BPLCON3",
    0xDFF0E8: "BPL1MOD", 0xDFF0EA: "BPL2MOD", 0xDFF0EC: "BPLCON4",
    0xDFF0F0: "CLXCON", 0xDFF0F2: "CLXCON2", 0xDFF0F4: "ZOOM", 0xDFF0F6: "PRNG",
    0xDFF0F8: "BLTCON0L", 0xDFF0FA: "BLTSIZV", 0xDFF0FC: "BLTSIZH", 0xDFF0FE: "BLTCTL",
    0xDFF100: "BPL1PTH", 0xDFF102: "BPL1PTL", 0xDFF104: "BPL2PTH", 0xDFF106: "BPL2PTL",
    0xDFF108: "BPL3PTH", 0xDFF10A: "BPL3PTL", 0xDFF10C: "BPL4PTH", 0xDFF10E: "BPL4PTL",
    0xDFF110: "BPL5PTH", 0xDFF112: "BPL5PTL", 0xDFF114: "BPL6PTH", 0xDFF116: "BPL6PTL",
    0xDFF118: "BPL7PTH", 0xDFF11A: "BPL7PTL", 0xDFF11C: "BPL8PTH", 0xDFF11E: "BPL8PTL",
    0xDFF180: "COLOR00",
}
for _i in range(1, 32):
    HW[0xDFF180 + _i * 2] = f"COLOR{_i:02d}"

VARS: dict[int, str] = {}
md = capstone.Cs(capstone.CS_ARCH_M68K,
                 capstone.CS_MODE_BIG_ENDIAN | capstone.CS_MODE_M68K_000)


def call_targets(ram: bytes, lo: int, hi: int) -> list[int]:
    targets = set()
    for a in range(lo, min(hi, len(ram) - 6), 2):
        op = struct.unpack_from(">H", ram, a)[0]
        if op == 0x4EB9:
            x = struct.unpack_from(">I", ram, a + 2)[0]
        elif op in (0x6100, 0x4EBA):
            x = a + 2 + struct.unpack_from(">h", ram, a + 2)[0]
        elif (op & 0xFF00) == 0x6100 and (op & 0xFF) not in (0, 0xFF):
            x = a + 2 + struct.unpack_from(">b", ram, a + 1)[0]
        else:
            continue
        if lo <= x < hi and x % 2 == 0:
            targets.add(x)
    return sorted(targets)


def annotate(op_str: str, labels: set[int]) -> str:
    notes = []
    for m in re.finditer(r"\$([0-9a-f]+)", op_str):
        v = int(m.group(1), 16)
        v24 = v & 0xFFFFFF
        if v24 in HW:
            notes.append(HW[v24])
        elif v in VARS:
            notes.append(VARS[v])
        elif v in labels:
            notes.append(f"sub_{v:06x}")
    return ("  ; " + ", ".join(notes)) if notes else ""


def load_profile(path: str) -> dict[int, int]:
    profile = {}
    for line in open(path):
        m = re.match(r"\s*(?:0x)?([0-9a-f]+)\s+[\d.]+%\s+(\d+)", line)
        if m:
            profile[int(m.group(1), 16)] = int(m.group(2))
    return profile


def disasm(ram, start, end, labels, profile, base):
    total = sum(profile.values()) or 1
    own = 0
    out = []
    a = start
    while a < end:
        ins = next(md.disasm(ram[a:a + 10], a + base), None)
        if ins is None:
            out.append(f"{a + base:06x}: dc.w ${struct.unpack_from('>H', ram, a)[0]:04x}")
            a += 2
            continue
        if a in labels and a != start:
            out.append(f"\nsub_{a + base:06x}:")
        cyc = profile.get(a + base, 0) + profile.get(a, 0)
        own += cyc
        pct = f"{100 * cyc / total:6.2f}%" if profile else ""
        out.append(f"{a + base:06x}: {pct} {ins.bytes.hex():<20} {ins.mnemonic:<8} "
                   f"{ins.op_str}{annotate(ins.op_str, labels)}")
        a += ins.size
    head = f"sub_{start + base:06x}:"
    if profile:
        head += f"   ; {100 * own / total:.2f}% of profiled cycles"
    return head + "\n" + "\n".join(out)


def xrefs(ram, target, lo, hi):
    pattern = struct.pack(">H", target & 0xFFFF)
    hits = []
    for m in re.finditer(re.escape(pattern), ram[lo:hi]):
        a = lo + m.start()
        for back in (2, 4, 6):
            s = a - back
            ins = next(md.disasm(ram[s:s + 10], s), None)
            if ins and ins.size >= back + 2 and re.search(rf"\${target:x}\b", ins.op_str):
                hits.append(f"{s:06x}: {ins.mnemonic} {ins.op_str}")
                break
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump")
    ap.add_argument("start", nargs="?", type=lambda s: int(s, 16))
    ap.add_argument("--end", type=lambda s: int(s, 16))
    ap.add_argument("--profile")
    ap.add_argument("--vars", help="JSON {hexaddr: name} of known variables")
    ap.add_argument("--xref", type=lambda s: int(s, 16))
    ap.add_argument("--callers", type=lambda s: int(s, 16))
    ap.add_argument("--base", type=lambda s: int(s, 16), default=0,
                    help="runtime address of image offset 0")
    ap.add_argument("--lo", type=lambda s: int(s, 16), default=0)
    ap.add_argument("--hi", type=lambda s: int(s, 16))
    ap.add_argument("--cpu", choices=("68000", "68020"), default="68000")
    args = ap.parse_args(argv)

    global md
    mode = capstone.CS_MODE_M68K_020 if args.cpu == "68020" else capstone.CS_MODE_M68K_000
    md = capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_BIG_ENDIAN | mode)

    if args.vars:
        VARS.update({int(k, 16): v for k, v in json.load(open(args.vars)).items()})
    ram = open(args.dump, "rb").read()
    hi = args.hi or len(ram)
    targets = call_targets(ram, args.lo, hi)
    labels = set(targets)

    if args.xref is not None:
        print("\n".join(xrefs(ram, args.xref, args.lo, hi)))
        return 0
    if args.callers is not None:
        print("\n".join(h for h in xrefs(ram, args.callers, args.lo, hi)
                        if h.split(": ", 1)[1].startswith(("jsr", "bsr", "jmp", "bra"))))
        for s in range(args.lo, hi, 2):
            op = struct.unpack_from(">H", ram, s)[0]
            if op in (0x6100, 0x4EBA):
                tgt = s + 2 + struct.unpack_from(">h", ram, s + 2)[0]
                if tgt == args.callers:
                    print(f"{s:06x}: {'bsr.w' if op == 0x6100 else 'jsr (pc)'} ${tgt:x}")
            elif (op & 0xFF00) == 0x6100 and (op & 0xFF) not in (0, 0xFF):
                tgt = s + 2 + struct.unpack_from(">b", ram, s + 1)[0]
                if tgt == args.callers:
                    print(f"{s:06x}: bsr.b ${tgt:x}")
        return 0
    if args.start is None:
        ap.error("start address required")
    end = args.end
    if end is None:
        i = bisect.bisect_right(targets, args.start)
        end = targets[i] if i < len(targets) else args.start + 0x200
    profile = load_profile(args.profile) if args.profile else {}
    print(disasm(ram, args.start, end, labels, profile, args.base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
