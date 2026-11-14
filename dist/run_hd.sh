#!/usr/bin/env bash
# Boot the Amiga "enhanced games" hard-disk image in FS-UAE (A1200, Kickstart 3.1).
#   ./run_amiga.sh [IMAGE] [FS-UAE OPTIONS...]
# Default image: the newest dist/Amiga_enhanced_games_*.hdf
# The image is used directly, so game saves persist in it.
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd -P)"
root="$(dirname "$here")"

# No argument: mount every enhanced-games image in dist/ (newest first) so all
# the games' volumes show up on the Workbench desktop.  With an argument: mount
# just that one image.
imgs=()
if [[ $# -gt 0 && "$1" != -* ]]; then
    imgs=("$1"); shift
else
    while IFS= read -r f; do imgs+=("$f"); done < <(ls -t "$here"/Amiga_enhanced_games_*.hdf 2>/dev/null)
fi
[[ ${#imgs[@]} -gt 0 ]] || { echo "no hard-disk image found (build one with tools/make_amiga_hd.py)" >&2; exit 1; }

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
$(for i in "${!imgs[@]}"; do echo "hard_drive_$i = ${imgs[$i]}"; done)
fast_memory = 8
warp_mode = 0
automatic_input_grab = 1
initial_input_grab = 1
EOF

echo "A1200 (Kickstart 3.1), hard drives:"
for f in "${imgs[@]}"; do echo "  $(basename "$f")"; done
echo "Boots to the Workbench desktop; open a volume and double-click a game,"
echo "or from a Shell:  CD Games:   then   mwII"
exec fs-uae "$cfg" "$@"
