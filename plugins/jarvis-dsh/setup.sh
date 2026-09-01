#!/bin/bash
# JARVIS MK-X — DSH Plugin Setup
#
# This script sets up the JARVIS DSH plugin and configures
# DeepSeek Harness to use JARVIS's capabilities.

set -e

echo "=========================================="
echo "  JARVIS MK-X — DSH Plugin Setup"
echo "=========================================="
echo

# Check prerequisites
echo "Checking prerequisites..."

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js not found. Install from https://nodejs.org"
    exit 1
fi
echo "✓ Node.js $(node --version)"

# Check Python
if ! command -v python &> /dev/null && ! command -v python3 &> /dev/null; then
    echo "ERROR: Python not found. Install from https://python.org"
    exit 1
fi
echo "✓ Python found"

# Check Ollama
if ! command -v ollama &> /dev/null; then
    echo "WARNING: Ollama not found. Install from https://ollama.com/download"
    echo "         JARVIS will work but local models won't be available."
else
    echo "✓ Ollama found"
fi

# Check DSH
if ! command -v dsh &> /dev/null; then
    echo "WARNING: DSH not found. Installing..."
    npm install -g @deepseek-ai/dsh
fi
echo "✓ DSH found"

echo
echo "Setting up JARVIS DSH plugin..."

# Create plugin directory
PLUGIN_DIR="plugins/jarvis-dsh"
mkdir -p "$PLUGIN_DIR"

# Install dependencies
echo "Installing dependencies..."
cd "$PLUGIN_DIR"
npm install

# Build plugin
echo "Building plugin..."
npm run build

# Copy profile to DSH config
echo "Installing JARVIS profile..."
DSH_CONFIG_DIR="$HOME/.dsh/profiles/jarvis"
mkdir -p "$DSH_CONFIG_DIR"
cp config/jarvis.profile.yml "$DSH_CONFIG_DIR/cordis.patch.yml"

# Copy MCP server
echo "Installing MCP server..."
MCP_DIR="plugins/jarvis-mcp-server"
mkdir -p "$MCP_DIR"
cp ../jarvis-mcp-server/jarvis_mcp_server.py "$MCP_DIR/"

# Create launcher script
echo "Creating launcher..."
cat > launch-jarvis-dsh.bat << 'EOF'
@echo off
title JARVIS MK-X via DSH
echo Launching JARVIS MK-X via DeepSeek Harness...
dsh --profile jarvis
pause
EOF

cat > launch-jarvis-dsh.sh << 'EOF'
#!/bin/bash
echo "Launching JARVIS MK-X via DeepSeek Harness..."
dsh --profile jarvis
EOF
chmod +x launch-jarvis-dsh.sh

echo
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo
echo "To launch JARVIS via DSH:"
echo "  - Windows: launch-jarvis-dsh.bat"
echo "  - Linux/Mac: ./launch-jarvis-dsh.sh"
echo "  - Or: dsh --profile jarvis"
echo
echo "To launch JARVIS standalone:"
echo "  - JARVIS.bat"
echo "  - python -m cli.main"
echo
