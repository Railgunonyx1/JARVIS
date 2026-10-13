#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
echo "==> JARVIS Orbit local Linux install =="
echo "    repo: $REPO"

# 1. Icons
bash "$HERE/install-icons.sh"

# 2. Desktop entry (user-local, so it shows in app grid / launcher)
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cp -f "$HERE/jarvis-orbit.desktop" "$DESKTOP_DIR/jarvis-orbit.desktop"
chmod +x "$DESKTOP_DIR/jarvis-orbit.desktop"
echo "    desktop entry: $DESKTOP_DIR/jarvis-orbit.desktop"

# 3. Launchers executable
chmod +x "$HERE/launch-orbit.sh"
chmod +x "$HERE/jarvis-orbit.sh"
echo "    launchers: $HERE/launch-orbit.sh"

echo "==> done"
echo "    launch from app grid: JARVIS Orbit"
echo "    or: $HERE/launch-orbit.sh"
