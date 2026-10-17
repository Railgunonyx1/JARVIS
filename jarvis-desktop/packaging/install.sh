#!/bin/bash
# JARVIS Desktop Companion — Installer for Bazzite Linux
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/jarvis-desktop}"
DESKTOP_DIR="${DESKTOP_DIR:-/usr/share/applications}"
ICON_DIR="${ICON_DIR:-/usr/share/icons/hicolor/scalable/apps}"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

echo "=== JARVIS Desktop Companion Installer ==="
echo "Install directory: $INSTALL_DIR"

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python version: $PYTHON_VERSION"

# Check PySide6
if ! python3 -c "import PySide6" 2>/dev/null; then
    echo "WARNING: PySide6 not installed. Installing via pip..."
    python3 -m pip install --user PySide6 || {
        echo "ERROR: Failed to install PySide6"
        exit 1
    }
fi

# Install application files
echo "Installing application files to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp -a "$REPO_ROOT/jarvis-desktop/app" "$INSTALL_DIR/app"
cp -a "$REPO_ROOT/jarvis-desktop/README.md" "$INSTALL_DIR/README.md"

# Create wrapper script
cat > "$BIN_DIR/jarvis-desktop" <<EOF
#!/bin/bash
export JARVIS_DESKTOP_HOME="$INSTALL_DIR"
export PYTHONPATH="\$JARVIS_DESKTOP_HOME:\${PYTHONPATH:-}"
exec python3 "\$JARVIS_DESKTOP_HOME/app/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/jarvis-desktop"

# Install desktop entry
mkdir -p "$DESKTOP_DIR"
cp "$REPO_ROOT/jarvis-desktop/packaging/JARVIS.desktop" "$DESKTOP_DIR/com.jarvis.desktop.desktop"
sed -i "s|Exec=jarvis-desktop|Exec=$BIN_DIR/jarvis-desktop|g" "$DESKTOP_DIR/com.jarvis.desktop.desktop"

# Install icon
mkdir -p "$ICON_DIR"
cp "$REPO_ROOT/jarvis-desktop/assets/icon.svg" "$ICON_DIR/jarvis-desktop.svg" 2>/dev/null || true

# Update desktop database
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo "=== Installation complete ==="
echo "Run: jarvis-desktop"
echo "Or: $BIN_DIR/jarvis-desktop"
