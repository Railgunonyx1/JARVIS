#!/bin/bash
# JARVIS Desktop Companion — Uninstaller
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/jarvis-desktop}"
DESKTOP_DIR="${DESKTOP_DIR:-$HOME/.local/share/applications}"
ICON_DIR="${ICON_DIR:-$HOME/.local/share/icons/hicolor/scalable/apps}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"

echo "=== JARVIS Desktop Companion Uninstaller ==="

# Remove wrapper script
rm -f "$BIN_DIR/jarvis-desktop"

# Remove application files
rm -rf "$INSTALL_DIR"

# Remove desktop entry
rm -f "$DESKTOP_DIR/com.jarvis.desktop.desktop"

# Remove icon
rm -f "$ICON_DIR/jarvis-desktop.svg"

# Update desktop database
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo "=== Uninstallation complete ==="
