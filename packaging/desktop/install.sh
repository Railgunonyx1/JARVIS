#!/usr/bin/env bash
# User-level installer for JARVIS Dynamic Island on KDE Plasma 6.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/jarvis-desktop}"
REPO_DIR="$INSTALL_DIR/jarvis-repo"
VENV_DIR="$INSTALL_DIR/venv"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
DESKTOP_DIR="${DESKTOP_DIR:-$HOME/.local/share/applications}"
ICON_DIR="${ICON_DIR:-$HOME/.local/share/icons/hicolor/scalable/apps}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../" && pwd)"
KWIN_PACKAGE_DIR="$REPO_DIR/packaging/desktop"
KWIN_INSTALLED_MARKER="$REPO_DIR/.kwin-helper-installed"

command -v python3 >/dev/null || { echo "ERROR: python3 is required"; exit 1; }
mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"

echo "Installing JARVIS Dynamic Island into $INSTALL_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$REPO_ROOT/requirements.txt"

# Stage the complete runtime and its configuration. Exclude only development
# metadata, tests and caches; the agent's skills/providers/tools remain intact.
mkdir -p "$REPO_DIR"
tar -C "$REPO_ROOT" \
  --exclude='./.git' \
  --exclude='./.venv' --exclude='./venv' \
  --exclude='./.pytest_cache' --exclude='./.ruff_cache' \
  --exclude='./.mypy_cache' --exclude='./__pycache__' \
  --exclude='*.pyc' --exclude='*.pyo' \
  --exclude='./node_modules' --exclude='./dist' --exclude='./build' \
  --exclude='./tests' --exclude='./dynamic-island/tests' \
  --exclude='./packaging' --exclude='./.github' \
  -cf - . | tar -C "$REPO_DIR" -xf -

# Keep the KWin placement helper and its script payload with the installed
# application. This allows maintenance after the source checkout is removed.
mkdir -p "$KWIN_PACKAGE_DIR"
install -m 755 "$REPO_ROOT/packaging/desktop/install-kwin-rule.sh" "$KWIN_PACKAGE_DIR/install-kwin-rule.sh"
cp -a "$REPO_ROOT/packaging/desktop/kwin" "$KWIN_PACKAGE_DIR/"

# Thin wrappers keep the install root explicit, including custom INSTALL_DIRs.
cat > "$BIN_DIR/jarvis-desktop-island" <<EOF
#!/usr/bin/env bash
export JARVIS_DESKTOP_HOME="$INSTALL_DIR"
export JARVIS_DESKTOP_LAUNCHER="$BIN_DIR/jarvis-desktop-island"
exec "$VENV_DIR/bin/python" "$REPO_DIR/scripts/island-launcher.py" "\$@"
EOF
cat > "$BIN_DIR/jarvis-island" <<EOF
#!/usr/bin/env bash
export JARVIS_DESKTOP_HOME="$INSTALL_DIR"
export JARVIS_DESKTOP_LAUNCHER="$BIN_DIR/jarvis-desktop-island"
exec "$VENV_DIR/bin/python" "$REPO_DIR/scripts/island-launcher.py" "\$@"
EOF
cat > "$BIN_DIR/jarvis-autostart" <<EOF
#!/usr/bin/env bash
export JARVIS_DESKTOP_HOME="$INSTALL_DIR"
exec "$VENV_DIR/bin/python" "$REPO_DIR/scripts/jarvis-autostart" "\$@"
EOF
chmod +x "$BIN_DIR/jarvis-desktop-island" "$BIN_DIR/jarvis-island" "$BIN_DIR/jarvis-autostart"

cp "$REPO_ROOT/packaging/desktop/JARVIS-Island.desktop" "$DESKTOP_DIR/com.jarvis.island.desktop"
sed -i "s|^Exec=.*|Exec=$BIN_DIR/jarvis-desktop-island|" "$DESKTOP_DIR/com.jarvis.island.desktop"
if [ -f "$REPO_ROOT/assets/jarvis-island.svg" ]; then
  cp "$REPO_ROOT/assets/jarvis-island.svg" "$ICON_DIR/jarvis-desktop.svg"
fi

# Write a valid login command that invokes the actual island executable.
"$BIN_DIR/jarvis-autostart" enable --run "$BIN_DIR/jarvis-desktop-island"

# Only record KWin integration as installed when this invocation succeeds.
# The uninstaller uses this marker to avoid removing an unrelated/pre-existing
# KWin script when installation skipped or failed the helper step.
rm -f "$KWIN_INSTALLED_MARKER"
if [ -n "${XDG_CURRENT_DESKTOP:-}" ] && [ -x "$KWIN_PACKAGE_DIR/install-kwin-rule.sh" ]; then
  if "$KWIN_PACKAGE_DIR/install-kwin-rule.sh"; then
    touch "$KWIN_INSTALLED_MARKER"
  else
    echo "WARNING: KWin placement helper was not installed; compositor placement will be used."
  fi
fi

command -v update-desktop-database >/dev/null && update-desktop-database "$DESKTOP_DIR" || true
echo "Installation complete. Run: jarvis-desktop-island"
