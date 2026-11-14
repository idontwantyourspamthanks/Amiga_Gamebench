#!/usr/bin/env bash
# Play Midwinter II (Amiga) on a fast A1200 in FS-UAE, floppy only.
#
# The start-up disk is mounted in df0 and the graphics/missions disks in
# df1/df2, so the game's "insert X disk into any drive" prompts are satisfied
# without swapping. The front end wants held ~1 s mouse presses, not clicks.
#
# Usage: dist/run_mw2.sh [extra fs-uae options...]
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
orig="$root/games/in_progress/Midwinter-2/originals"

d1="$root/games/in_progress/Midwinter-2/work/build/d1_skipintro.adf"
if [ ! -f "$d1" ]; then
    d1=$(ls "$orig"/*"Disk 1 of 3)[cr SPL].adf")
    echo "skip-intro build missing; using the original start-up disk" >&2
    echo "(hold the left mouse button ~1 s to leave the intro)" >&2
fi
d2=$(ls "$orig"/*"Disk 2 of 3)(Graphics)[cr SPL].adf")
d3=$(ls "$orig"/*"Disk 3 of 3)(Missions)[cr SPL].adf")

kick=${MW2_KICKSTART:-}
if [ -z "$kick" ]; then
    for f in "$root/os/Kickstart/kickstart-3.1-a1200.rom" \
             "$root/os/Kickstart/amiga-os-310-a1200.rom"; do
        [ -f "$f" ] && { kick=$f; break; }
    done
fi
[ -n "$kick" ] || { echo "no A1200 Kickstart 3.1 ROM found; set MW2_KICKSTART" >&2; exit 1; }
for f in "$d1" "$d2" "$d3"; do
    [ -f "$f" ] || { echo "missing disk: $f" >&2; exit 1; }
done

cfg=$(mktemp -t mw2.XXXXXX.fs-uae)
trap 'rm -f "$cfg"' EXIT
cat >"$cfg" <<EOF
[config]
amiga_model = A1200
kickstart_file = $kick
floppy_drive_0 = $d1
floppy_drive_1 = $d2
floppy_drive_2 = $d3
fast_memory = 8
warp_mode = 0
automatic_input_grab = 1
initial_input_grab = 1
EOF

echo "Midwinter II on A1200; disks df0=startup, df1=graphics, df2=missions"
echo "Front end: hold the left mouse button ~1 s on RAIDS, then a difficulty,"
echo "then hover an island and press SPACE; '?' then thumbs-up starts the mission."
exec fs-uae "$cfg" "$@"
