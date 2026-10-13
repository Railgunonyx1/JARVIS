#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ICON_SRC="$HERE/icons/hicolor"
ICON_DST="$HOME/.local/share/icons"
echo "==> installing JARVIS Orbit icons =="
for size in "$ICON_SRC"/*/apps/jarvis-orbit.png; do
  [ -f "$size" ] || continue
  rel="${size#$ICON_SRC/}"
  dst="$ICON_DST/$rel"
  mkdir -p "$(dirname "$dst")"
  cp -f "$size" "$dst"
  echo "  installed $rel -> $dst"
done
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f "$ICON_DST/hicolor" 2>/dev/null || true
fi
echo "==> icons installed into $ICON_DST/hicolor"
