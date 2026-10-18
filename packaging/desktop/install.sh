#!/bin/bash
# JARVIS Desktop Companion — Installer for Bazzite Linux
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/jarvis-desktop}"
DESKTOP_DIR="${DESKTOP_DIR:-$HOME/.local/share/applications}"
ICON_DIR="${ICON_DIR:-$HOME/.local/share/icons/hicolor/scalable/apps}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"

# Resolve the directory containing this script, then go up to the repo root.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../" && pwd)"

echo "=== JARVIS Desktop Companion Installer ==="
echo "Install directory: $INSTALL_DIR"
echo "Repository root: $REPO_ROOT"

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python version: $PYTHON_VERSION"

# Create isolated venv for dependencies
VENV_DIR="$INSTALL_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR" || {
        echo "ERROR: Failed to create venv (python3-venv missing)"
        exit 1
    }
fi

# Install runtime dependencies into the venv
echo "Installing runtime dependencies..."
"$VENV_DIR/bin/pip" install \
  'PySide6==6.8.1' \
  'sounddevice==0.5.5' \
  'numpy>=1.26' \
  'psutil>=5.9' \
  'onnxruntime>=1.17' \
  'kokoro-onnx>=0.4' \
  'edge-tts>=7.2' || {
    echo "ERROR: Failed to install runtime dependencies"
    exit 1
  }

# Stage only required runtime files — never secrets, caches, or dev artifacts.
echo "Installing application files to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR/jarvis-repo"

tar -C "$REPO_ROOT" \
  --exclude='./.git' \
  --exclude='./.env' \
  --exclude='./.env.*' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='./.pytest_cache' \
  --exclude='./.ruff_cache' \
  --exclude='./venv' \
  --exclude='*.egg-info' \
  --exclude='./dist' \
  --exclude='./build' \
  --exclude='./.mypy_cache' \
  --exclude='./node_modules' \
  --exclude='./orbit-browser' \
  --exclude='./extensions' \
  --exclude='./jbrowser-bridge' \
  --exclude='./.github' \
  --exclude='*.md' \
  --exclude='./docs' \
  --exclude='./audits' \
  --exclude='./benchmark' \
  --exclude='./packaging' \
  --exclude='./scripts' \
  --exclude='*.bat' \
  --exclude='*.sh' \
  --exclude='*.ps1' \
  --exclude='*.desktop' \
  --exclude='*.xml' \
  --exclude='*.spec' \
  --exclude='*.iss' \
  --exclude='*.yml' \
  --exclude='*.yaml' \
  --exclude='./pytest.ini' \
  --exclude='./pyproject.toml' \
  -cf - . | tar -C "$INSTALL_DIR/jarvis-repo" -xf -

# Ensure required subdirectories exist even if empty after exclusions
mkdir -p "$INSTALL_DIR/jarvis-repo/jarvis-desktop/app"

# Create wrapper script — PYTHONPATH points into the installed repo copy so
# core, providers, tools, runtime, memory are importable.
cat > "$BIN_DIR/jarvis-desktop" <<EOF
#!/bin/bash
export JARVIS_DESKTOP_HOME="$INSTALL_DIR"
export PYTHONPATH="\$JARVIS_DESKTOP_HOME/jarvis-repo/jarvis-desktop:\$JARVIS_DESKTOP_HOME/jarvis-repo:\${PYTHONPATH:-}"
exec "\$JARVIS_DESKTOP_HOME/venv/bin/python" "\$JARVIS_DESKTOP_HOME/jarvis-repo/jarvis-desktop/app/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/jarvis-desktop"

# Install desktop entry
mkdir -p "$DESKTOP_DIR"
cp "$REPO_ROOT/packaging/desktop/JARVIS.desktop" "$DESKTOP_DIR/com.jarvis.desktop.desktop"
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