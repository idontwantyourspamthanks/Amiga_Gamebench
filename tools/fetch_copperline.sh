#!/bin/sh
# Download and unpack Copperline (https://copperline.dev) into tools/bin/.
# Verifies the release SHA256SUMS. No FUSE needed: the AppImage is extracted once.
#   tools/fetch_copperline.sh            # default version below
#   COPPERLINE_VERSION=1.1.0 tools/fetch_copperline.sh
set -eu
V="${COPPERLINE_VERSION:-1.1.0}"
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HERE/bin"
URL="https://github.com/CopperlineHQ/Copperline/releases/download/v$V"
mkdir -p "$BIN"
cd "$BIN"
for f in "Copperline-$V-x86_64.AppImage" "Copperline-$V-x86_64-tools.tar.gz" "Copperline-$V-SHA256SUMS.txt"; do
    [ -f "$f" ] || curl -fsSL -o "$f" "$URL/$f"
done
sha256sum -c --ignore-missing "Copperline-$V-SHA256SUMS.txt"
chmod +x "Copperline-$V-x86_64.AppImage"
rm -rf squashfs-root "Copperline-$V-x86_64-tools"
"./Copperline-$V-x86_64.AppImage" --appimage-extract >/dev/null
tar xzf "Copperline-$V-x86_64-tools.tar.gz"
ln -sfn "Copperline-$V-x86_64-tools/copperline-ctl" copperline-ctl
ln -sfn squashfs-root/usr/bin/copperline copperline
./copperline --version
