#!/bin/bash
# JARVIS Desktop Companion — Uninstaller
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../" && pwd)"

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/jarvis-desktop}"
DESKTOP_DIR="${DESKTOP_DIR:-$HOME/.local/share/applications}"
ICON_DIR="${ICON_DIR:-$HOME/.local/share/icons/hicolor/scalable/apps}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
AUTOSTART_DIR="${AUTOSTART_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/autostart}"

echo "=== JARVIS Desktop Companion Uninstaller ==="

# Remove launchers
rm -f "$BIN_DIR/jarvis-desktop"
rm -f "$BIN_DIR/jarvis-desktop-island"

# Remove application files
rm -rf "$INSTALL_DIR"

# Remove desktop entries
rm -f "$DESKTOP_DIR/com.jarvis.desktop.desktop"
rm -f "$DESKTOP_DIR/com.jarvis.island.desktop"

# Remove autostart entry
rm -f "$AUTOSTART_DIR/jarvis-desktop.desktop"

# Remove icon
rm -f "$ICON_DIR/jarvis-desktop.svg"

# Update desktop database
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo "=== Uninstallation complete ==="


# Remove KWin script if installed
if [ -x "$REPO_ROOT/packaging/desktop/install-kwin-rule.sh" ]; then
    "$REPO_ROOT/packaging/desktop/install-kwin-rule.sh" --uninstall || true
fi
