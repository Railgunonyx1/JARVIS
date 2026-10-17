#!/bin/bash
# JARVIS Desktop Companion — Uninstaller
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/jarvis-desktop}"
DESKTOP_DIR="${DESKTOP_DIR:-/usr/share/applications}"
ICON_DIR="${ICON_DIR:-/usr/share/icons/hicolor/scalable/apps}"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"

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
