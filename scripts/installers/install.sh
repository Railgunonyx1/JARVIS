#!/usr/bin/env bash
# JARVIS MK-X — Linux / Bazzite dependency installer
#
# Installs, in order:
#   1. Python 3.11+ detection (system python3 is fine on Bazzite/Fedora)
#   2. Virtual environment (./venv, created once, reused after)
#   3. Runtime dependencies from requirements.txt
#   4. Dev tools (pytest, ruff)
#   5. Orbit browser npm dependencies (skipped when Node.js is absent)
#   6. Optional Playwright Chromium engine:  ./install.sh --playwright
#   7. Desktop app entry + icon — 'JARVIS Orbit' appears in the app grid
#      like Chrome; installed by default, skip with --no-desktop
#
# After deps: precompiles bytecode (scripts/precompile.py) so cold start
# skips code generation.
#
# Idempotent — safe to re-run; satisfied steps are fast no-ops.
#
# Bazzite notes (immutable Fedora Atomic desktop):
#   - No root needed: the repo and venv live in $HOME.
#   - Python: system python3 >= 3.11 works; otherwise layer one with
#     `rpm-ostree install python3.12` (reboot once) or use dnf5 from a
#     devcontainer/toolbox.
#   - Node.js: `sudo dnf install nodejs` (Fedora repo) or use nvm/fnm in $HOME.
#   - Chromium for Orbit: `./install.sh --playwright` downloads an unbranded
#     Chromium into ~/.cache/ms-playwright (no rpm-ostree layering needed).

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PLAYWRIGHT=0
DESKTOP=1
for arg in "$@"; do
    case "$arg" in
        --playwright) PLAYWRIGHT=1 ;;
        --no-desktop) DESKTOP=0 ;;
        *) echo "  [!!] Unknown option: $arg (known: --playwright, --no-desktop)" >&2; exit 1 ;;
    esac
done

info() { printf '  [..] %s\n' "$*"; }
ok()   { printf '  [ok] %s\n' "$*"; }
warn() { printf '  [!!] %s\n' "$*"; }
fail() { printf '  [!!] %s\n' "$*" >&2; exit 1; }

echo
echo "  JARVIS MK-X - Linux/Bazzite Dependency Installer"
echo "  ================================================="

# ── 1. Resolve Python 3.11+ ──────────────────────────────────────
PY=""
for cand in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$cand" >/dev/null 2>&1 \
        && "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
        PY="$cand"
        break
    fi
done
[[ -n "$PY" ]] || fail "Python 3.11+ not found. On Bazzite: rpm-ostree install python3.12 (then reboot), or use a toolbox/devcontainer with dnf."
ok "Python: $("$PY" --version 2>&1)"

# ── 2. Create / reuse the virtual environment ────────────────────
if [[ ! -x venv/bin/python ]]; then
    info "Creating virtual environment in venv/ ..."
    "$PY" -m venv venv || fail "venv creation failed (On Fedora/Bazzite layer python3-devel: rpm-ostree install python3-devel)."
fi
PY="$PWD/venv/bin/python"

# ── 3. Runtime dependencies ──────────────────────────────────────
info "Installing runtime dependencies (requirements.txt)..."
"$PY" -m pip install --upgrade pip -q
"$PY" -m pip install -r requirements.txt || fail "pip install -r requirements.txt failed"
ok "Runtime dependencies installed."

# ── 4. Dev / test tools ─────────────────────────────────────────
info "Installing dev tools (requirements-dev.txt)..."
"$PY" -m pip install -r requirements-dev.txt || fail "Dev tool install failed"
ok "Dev tools installed."

# ── 4b. Precompile bytecode (fast startup) ────────────────────────
info "Precompiling bytecode for fast startup..."
"$PY" scripts/precompile.py || warn "Precompile skipped (non-fatal)"
ok "Bytecode precompiled — subsequent starts skip code generation."

# ── 5. Orbit browser npm dependencies ────────────────────────────
if [[ -f orbit-browser/package.json ]]; then
    if ! command -v npm >/dev/null 2>&1; then
        warn "Node.js/npm not found - skipping Orbit browser deps."
        echo "       Install Node.js 20+:  sudo dnf install nodejs  (or https://nodejs.org/)"
    elif [[ -x orbit-browser/node_modules/electron/dist/electron ]]; then
        ok "Orbit browser dependencies already installed."
    else
        info "Installing Orbit browser dependencies (npm)..."
        (
            cd orbit-browser
            if [[ -f package-lock.json ]]; then
                npm ci --prefer-offline --no-audit --no-fund
            else
                npm install --prefer-offline --no-audit --no-fund
            fi
        ) || fail "npm install failed in orbit-browser"
        ok "Orbit browser dependencies installed."
    fi
fi

# ── 6. Optional Playwright Chromium engine (Orbit's runtime) ─────
if [[ "$PLAYWRIGHT" == "1" ]]; then
    info "Installing Playwright Chromium engine..."
    "$PY" -m pip install playwright
    "$PY" -m playwright install chromium || fail "playwright install failed"
    ok "Playwright Chromium installed into ~/.cache/ms-playwright"
fi

# ── 7. Desktop application entry (app grid / dock, like Chrome) ───
if [[ "$DESKTOP" == "1" ]]; then
    info "Installing desktop entry (JARVIS Orbit)..."
    APPS_DIR="$HOME/.local/share/applications"
    mkdir -p "$APPS_DIR"
    chmod +x packaging/linux/jarvis-orbit.sh JARVIS.sh
    sed "s|@WRAPPER@|$PWD/packaging/linux/jarvis-orbit.sh|" \
        packaging/linux/jarvis-orbit.desktop > "$APPS_DIR/jarvis-orbit.desktop"
    for size in 128 64 48 32; do
        dest="$HOME/.local/share/icons/hicolor/${size}x${size}/apps"
        mkdir -p "$dest"
        cp "packaging/linux/icons/hicolor/${size}x${size}/apps/jarvis-orbit.png" "$dest/"
    done
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
    fi
    ok "Desktop entry installed — launch 'JARVIS Orbit' from the app grid."
fi

echo
echo "  [ok] INSTALL COMPLETE"
echo "       Launch the agent:   ./JARVIS.sh"
echo "       Or run directly:    venv/bin/python -m cli"
echo "       Tests:              venv/bin/python -m pytest tests -q"
echo
