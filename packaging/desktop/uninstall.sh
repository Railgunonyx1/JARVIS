#!/usr/bin/env bash
# User-level uninstaller for JARVIS Dynamic Island.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/jarvis-desktop}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
DESKTOP_DIR="${DESKTOP_DIR:-$HOME/.local/share/applications}"
ICON_DIR="${ICON_DIR:-$HOME/.local/share/icons/hicolor/scalable/apps}"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"

if [ -x "$BIN_DIR/jarvis-autostart" ]; then
  "$BIN_DIR/jarvis-autostart" disable || true
fi
rm -f "$BIN_DIR/jarvis-desktop-island" "$BIN_DIR/jarvis-island" "$BIN_DIR/jarvis-autostart"
rm -f "$DESKTOP_DIR/com.jarvis.island.desktop"
rm -f "$AUTOSTART_DIR/jarvis-desktop.desktop"
rm -f "$ICON_DIR/jarvis-desktop.svg"
rm -rf "$INSTALL_DIR"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -x "$SCRIPT_DIR/install-kwin-rule.sh" ]; then
  "$SCRIPT_DIR/install-kwin-rule.sh" --uninstall || true
fi
command -v update-desktop-database >/dev/null && update-desktop-database "$DESKTOP_DIR" || true
echo "JARVIS Dynamic Island uninstalled. User data outside $INSTALL_DIR was left untouched."
