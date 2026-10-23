#!/bin/sh
# Install (or remove) the KWin script that pins the JARVIS Dynamic Island to
# the top-centre of the screen. Wayland compositors ignore client-side window
# positions, so KWin has to do the placement.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PKG="$SCRIPT_DIR/kwin/jarvis-island"
# Target the real user session, not sandbox-redirected XDG_* overrides.
DEST="${KWIN_SCRIPT_DIR:-$HOME/.local/share/kwin/scripts}/jarvis-island"
KWINRC="${KWINRC_PATH:-$HOME/.config/kwinrc}"
KEY="jarvis-islandEnabled"

set_kwin_key() {
    if command -v kwriteconfig6 >/dev/null 2>&1; then
        kwriteconfig6 --file kwinrc --group Plugins --key "$KEY" "$1"
    elif command -v kwriteconfig5 >/dev/null 2>&1; then
        kwriteconfig5 --file kwinrc --group Plugins --key "$KEY" "$1"
    elif command -v python3 >/dev/null 2>&1; then
        python3 - "$KWINRC" "$KEY" "$1" <<'PY'
import sys
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    text = open(path).read()
except FileNotFoundError:
    text = ""
lines = text.splitlines()
out, in_plugins, found = [], False, False
for line in lines:
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        if in_plugins and not found:
            out.append("%s=%s" % (key, value))
            found = True
        in_plugins = stripped == "[Plugins]"
    if in_plugins and stripped.startswith(key + "="):
        out.append("%s=%s" % (key, value))
        found = True
        continue
    out.append(line)
if in_plugins and not found:
    out.append("%s=%s" % (key, value))
    found = True
if not any(l.strip() == "[Plugins]" for l in out):
    out.extend(["[Plugins]", "%s=%s" % (key, value)])
open(path, "w").write("\n".join(out) + "\n")
PY
    else
        echo "error: need kwriteconfig6/5 or python3 to enable the script" >&2
        return 1
    fi
    return 0
}

reconfigure() {
    if command -v qdbus6 >/dev/null 2>&1; then
        qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
    elif command -v qdbus >/dev/null 2>&1; then
        qdbus org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
    fi
}

case "${1:-}" in
    --uninstall)
        rm -rf "$DEST"
        set_kwin_key false
        reconfigure
        echo "Removed KWin script. The island will fall back to compositor placement."
        exit 0
        ;;
    ""|--install)
        ;;
    *)
        echo "usage: $0 [--install|--uninstall]" >&2
        exit 2
        ;;
esac

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -r "$PKG" "$DEST"
set_kwin_key true
reconfigure

echo "Installed KWin script: $DEST"
echo "Enabled in: $KWINRC"
echo
echo "If the island is not pinned yet, restart KWin (log out/in, or run"
echo "  qdbus6 org.kde.KWin /KWin reconfigure"
echo "or toggle 'JARVIS Island' in System Settings > Window Management > KWin Scripts)."
