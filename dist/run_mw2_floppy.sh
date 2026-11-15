#!/usr/bin/env bash
# Midwinter II from the three floppies (start-up disk in df0, graphics and missions in df1/df2, so the
# game's "insert disk" prompts need no swapping).  Uses the patched d1_direct.adf when it is built.
#   dist/run_mw2_floppy.sh [--original] [--model A500] [--scale 3]
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd -P)"
exec python3 "$here/../tools/clrun.py" floppy mw2 "$@"
