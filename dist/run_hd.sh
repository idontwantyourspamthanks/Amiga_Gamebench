#!/usr/bin/env bash
# Boot the Amiga enhanced-games hard-disk image in Copperline (A1200, Kickstart 3.1, 8 MB fast).
#   dist/run_hd.sh                 Workbench desktop. Open a game's volume, double-click Play.
#                                  The image is used directly: saves and desktop changes persist.
#   dist/run_hd.sh mw2             Midwinter II (patched), started automatically on a scratch copy.
#   dist/run_hd.sh mw2orig         the unpatched game, for comparison.
#   dist/run_hd.sh [GAME] --model A600 | --cpu 68030 --clock 50 | --scale 3 | --image FILE | --no-warp
# Needs tools/bin/copperline (tools/fetch_copperline.sh) and os/Kickstart/amiga-os-310-a1200.rom.
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd -P)"
exec python3 "$here/../tools/clrun.py" hd "$@"
