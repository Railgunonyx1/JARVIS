#!/usr/bin/env bash
# JARVIS Orbit — Linux / Bazzite launcher (mirrors JARVIS.bat)
#
# 1. Reuses / starts the JARVIS kernel backend (port 8170)
# 2. Reuses / starts the WebSocket bridge        (port 8171)
# 3. Launches the Orbit browser detached
#
# Idempotent: re-running reuses whatever is already listening.
# Services are spawned with nohup + disown so they survive this shell
# closing. Logs live in ~/JARVIS/ next to the token file (the same
# fallback path the Python components resolve when LOCALAPPDATA is
# unset: os.path.join(LOCALAPPDATA or ~, "JARVIS", "bridge-token")).

set -u
cd "$(dirname "${BASH_SOURCE[0]}")"

STATE_DIR="${LOCALAPPDATA:-$HOME}/JARVIS"
TOKEN_FILE="$STATE_DIR/bridge-token"
mkdir -p "$STATE_DIR"

info() { printf '  [..] %s\n' "$*"; }
ok()   { printf '  [ok] %s\n' "$*"; }
warn() { printf '  [!!] %s\n' "$*"; }

# ── Resolve Python (repo venv first, then system) ────────────────
PY=""
for cand in "$PWD/venv/bin/python" "$PWD/orbit-browser/venv/bin/python" python3 python; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import sys" >/dev/null 2>&1; then
        PY="$cand"
        break
    fi
done
if [[ -z "$PY" ]]; then
    warn "No working Python found. Install Python 3.11+ or run ./install.sh first."
    exit 1
fi

export PYTHONIOENCODING=utf-8

# ── Port liveness (no netstat/ss dependency) ─────────────────────
port_live() {
    "$PY" - "$1" <<'EOF' 2>/dev/null
import socket, sys
s = socket.socket()
s.settimeout(0.4)
r = s.connect_ex(("127.0.0.1", int(sys.argv[1])))
s.close()
sys.exit(0 if r == 0 else 1)
EOF
}

# ── Bridge auth token (A-01): one shared per-installation secret ─
# The launcher (JARVIS.sh or launch-orbit.sh) is the authorizer. If the
# caller already exported a valid hex token, reuse it verbatim — do NOT
# regenerate, so the browser and the services agree on ONE secret. Only
# regenerate when the on-disk file is missing/empty/corrupt AND the env is
# not already set (the launcher did not hand us a token).
TOKEN="${J_BROWSER_BRIDGE_TOKEN:-}"
if [[ -z "$TOKEN" ]] && [[ -f "$TOKEN_FILE" ]]; then
    TOKEN="$(cat "$TOKEN_FILE" 2>/dev/null || true)"
fi
FRESH=0
if ! [[ "$TOKEN" =~ ^[0-9a-f]+$ ]]; then
    TOKEN="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d '[:space:]')"
    printf '%s' "$TOKEN" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
    FRESH=1
fi
if [[ "$FRESH" == "1" ]]; then
    for p in 8170 8171; do
        if port_live "$p"; then
            info "Token reset - stopping stale service on port $p..."
            pkill -f "server.py.*--port $p" 2>/dev/null || pkill -f "jbrowser-bridge/server.py" 2>/dev/null || true
            sleep 1
            break
        fi
    done
fi
# Export into our own env so every child (services + browser) inherits it.
export J_BROWSER_BRIDGE_TOKEN

echo
echo "  JARVIS Orbit - starting..."
echo

# ── 1. JARVIS kernel backend (8170) ──────────────────────────────
if port_live 8170; then
    ok "JARVIS kernel already running on port 8170"
else
    info "Starting JARVIS kernel on port 8170..."
    J_BROWSER_BRIDGE_TOKEN="$TOKEN" nohup "$PY" jbrowser-bridge/server.py --backend kernel \
        > "$STATE_DIR/kernel.log" 2>&1 &
    disown || true
fi

# ── 2. WebSocket bridge (8171) ───────────────────────────────────
if port_live 8171; then
    ok "Orbit bridge already running on port 8171"
else
    info "Starting WebSocket bridge on port 8171..."
    J_BROWSER_BRIDGE_TOKEN="$TOKEN" nohup "$PY" orbit-browser/python/server.py \
        --port 8171 --bridge-port 8170 \
        > "$STATE_DIR/bridge.log" 2>&1 &
    disown || true
fi

# ── 3. Electron dependencies (sync here; desktop launch needs it) ─
ELECTRON_BIN=""
if [[ -f orbit-browser/package.json ]]; then
    if [[ -x orbit-browser/node_modules/electron/dist/electron ]]; then
        ELECTRON_BIN="orbit-browser/node_modules/electron/dist/electron"
    elif [[ -x orbit-browser/node_modules/.bin/electron ]]; then
        ELECTRON_BIN="orbit-browser/node_modules/.bin/electron"
    elif command -v electron >/dev/null 2>&1; then
        ELECTRON_BIN="electron"
    elif command -v npm >/dev/null 2>&1; then
        info "Installing Orbit browser dependencies (npm)..."
        (
            cd orbit-browser
            if [[ -f package-lock.json ]]; then
                npm ci --prefer-offline --no-audit --no-fund
            else
                npm install --prefer-offline --no-audit --no-fund
            fi
        ) && ELECTRON_BIN="orbit-browser/node_modules/electron/dist/electron"
    elif node orbit-browser/node_modules/electron/cli.js --version >/dev/null 2>&1; then
        ELECTRON_BIN="node orbit-browser/node_modules/electron/cli.js"
        [[ -n "$ELECTRON_BIN" ]] || warn "Electron install failed - run 'npm install' in orbit-browser."
    else
        warn "Node.js/npm not found - cannot launch the Orbit browser."
        echo "       Install Node.js 20+:  sudo dnf install nodejs"
    fi
fi

# ── 4. Launch the browser (single-instance lock focuses existing) ─
if [[ -n "$ELECTRON_BIN" ]]; then
    info "Launching browser..."
    ELECTRON_ABS="$PWD/$ELECTRON_BIN"
    # Export the canonical per-launch token into the browser process so
    # main.js resolveBridgeToken() finds it in process.env even before the
    # token file is readable. Same token that authenticates the WS bridge
    # handshake (subprotocol) and the kernel bridge HTTP calls (Bearer).
    (
        export J_BROWSER_BRIDGE_TOKEN="$TOKEN"
        cd orbit-browser
        if [[ "$ELECTRON_ABS" == node* || "$ELECTRON_ABS" == *"cli.js" ]]; then
            nohup $ELECTRON_ABS . > "$STATE_DIR/browser.log" 2>&1 & disown || true
        else
            nohup "$ELECTRON_ABS" . > "$STATE_DIR/browser.log" 2>&1 & disown || true
        fi
    )
fi

# ── 5. Brief readiness wait (browser already independent) ────────
WAIT=0
K_UP=0
B_UP=0
while [[ $WAIT -lt 8 ]]; do
    port_live 8170 && K_UP=1
    port_live 8171 && B_UP=1
    [[ "$K_UP" == "1" && "$B_UP" == "1" ]] && break
    sleep 1
    WAIT=$((WAIT + 1))
done

if [[ "$K_UP" == "1" && "$B_UP" == "1" ]]; then
    ok "JARVIS online"
else
    info "JARVIS services still booting - they will connect shortly."
    echo "       Logs: $STATE_DIR/kernel.log, $STATE_DIR/bridge.log"
fi
echo
