#!/usr/bin/env bash
# Boot the Amiga "enhanced games" hard-disk image in FS-UAE (A1200, Kickstart 3.1).
#   ./run_amiga.sh [IMAGE] [FS-UAE OPTIONS...]
# Default image: the newest dist/Amiga_enhanced_games_*.hdf
# The image is used directly, so game saves persist in it.
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd -P)"
root="$(dirname "$here")"

img_arg=""
if [[ $# -gt 0 && "$1" != -* ]]; then img_arg="$1"; shift; fi
img="${img_arg:-$(ls -t "$here"/Amiga_enhanced_games_*.hdf 2>/dev/null | head -1)}"
[[ -f "$img" ]] || { echo "no hard-disk image found (build one with tools/make_amiga_hd.py)" >&2; exit 1; }

kick=""
for f in "$root/os/Kickstart/amiga-os-310-a1200.rom" "$root/os/Kickstart/kickstart-3.1-a1200.rom"; do
    [ -f "$f" ] && { kick="$f"; break; }
done
[[ -n "$kick" ]] || { echo "no A1200 Kickstart 3.1 ROM found" >&2; exit 1; }

cfg=$(mktemp -t amiga.XXXXXX.fs-uae)
trap 'rm -f "$cfg"' EXIT
cat >"$cfg" <<EOF
[config]
amiga_model = A1200
kickstart_file = $kick
hard_drive_0 = $img
fast_memory = 8
warp_mode = 0
automatic_input_grab = 1
initial_input_grab = 1
EOF

echo "A1200 (Kickstart 3.1): $(basename "$img")"
echo "The game starts automatically from S:User-Startup; comment that file out to get Workbench."
exec fs-uae "$cfg" "$@"
