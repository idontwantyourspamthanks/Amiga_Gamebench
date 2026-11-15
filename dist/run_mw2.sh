#!/usr/bin/env bash
# Play Midwinter II (patched: direct controls) from the hard-disk image in Copperline.
# Starts the game by itself on a scratch copy of the image (saves are not kept); for the desktop
# and persistent saves use dist/run_hd.sh.  Front-end menus want a held (~1 s) left button.
#   dist/run_mw2.sh [--model A600] [--cpu 68030 --clock 50] [--scale 3] [--no-warp]
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd -P)"
exec python3 "$here/../tools/clrun.py" hd mw2 "$@"
