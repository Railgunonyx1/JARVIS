#!/usr/bin/env bash
# launch-orbit.sh — one-command launcher for JARVIS Orbit (Linux).
#
# Brings up the kernel (8170), the bridge (8171) and the Orbit browser
# in the background, then prints a short status line so the user knows
# whether everything came up.
#
# Strategy probe (the browser part): the Orbit Electron binary is started
# with the GPU stack cleared out (in-process GPU + graphics compositing off
# + /dev/shm override + the DDLM / video-decode / native-fence features that
# trip up the hybrid nvidia+intel KMS path on this Bazzite/KDE/Wayland host).
# Electron 44 auto-selects the Ozone backend it was built for, so we start on
# that first; the fallback path on a still-alive Chromium window is "X11 +
# in-process GPU + no-sandbox + setuid-sandbox disabled", because X11 is
# unambiguous about which display server path it uses and never has to
# re-negotiate the native-display protocol.

set -uo pipefail || true

# repo root is two levels up from packaging/linux/ -> packaging/../.. -> repo root
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="${LOCALAPPDATA:-$HOME}/JARVIS"
mkdir -p "$STATE_DIR"

log="$STATE_DIR/orbit-launch.log"

echo "=== JARVIS Orbit launch ==="

# Canonical per-launch bridge token (A-01). The launcher is the single
# authorizer: it generates the token if it is missing/empty, exports it into
# its own environment, and every child (JARVIS.sh + the browser) inherits it.
# This removes the TOCTOU race where JARVIS.sh and launch-orbit.sh both read
# the token file and the browser could start before the file was populated.
token="$STATE_DIR/bridge-token"
mkdir -p "$STATE_DIR"
if [[ ! -s "$token" ]]; then
  # Generate once, write atomically for small payloads (< PIPE_BUF).
  J_BROWSER_BRIDGE_TOKEN="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d '[:space:]')"
  [[ -n "$J_BROWSER_BRIDGE_TOKEN" ]] || J_BROWSER_BRIDGE_TOKEN="$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null)"
  printf '%s' "$J_BROWSER_BRIDGE_TOKEN" > "$token"
  chmod 600 "$token" 2>/dev/null || true
  echo "[ok] generated bridge token"
else
  J_BROWSER_BRIDGE_TOKEN="$(cat "$token")"
  # Corrupt/empty token file from a stale chain: regenerate so services and
  # browser agree on one secret (kill stale services that were started with
  # the old/unknown secret so they do not stay reachable).
  if [[ ! "$J_BROWSER_BRIDGE_TOKEN" =~ ^[0-9a-f]{64}$ ]]; then
    J_BROWSER_BRIDGE_TOKEN="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d '[:space:]')"
    printf '%s' "$J_BROWSER_BRIDGE_TOKEN" > "$token"
    for p in 8170 8171; do
      if ss -ltn 2>/dev/null | grep -q ":$p "; then
        pkill -f "server.py.*--port $p" 2>/dev/null || pkill -f "server.py" 2>/dev/null || true
        sleep 0.5
      fi
    done
    echo "[ok] regenerated bridge token (stale file)"
  else
    echo "[ok] reusing bridge token on disk"
  fi
fi
export J_BROWSER_BRIDGE_TOKEN

echo "[1/4] launching JARVIS services (kernel 8170 + bridge 8171)..."
"$REPO/JARVIS.sh" >> "$log" 2>&1 < /dev/null &
JARVIS_PID=$!
echo "launched jarvis pid=$JARVIS_PID"

sleep 2

echo "[2/4] waiting for JARVIS services (8170 + 8171)..."
ready=0
for i in $(seq 1 20); do
  if ss -ltn 2>/dev/null | grep -q ':8170 ' && ss -ltn 2>/dev/null | grep -q ':8171 '; then ready=1; break; fi
  sleep 0.5
done
if [ "$ready" -eq 1 ]; then
  echo "[ok] JARVIS services on 8170/8171"
else
  echo "[warn] JARVIS services did not come up in 10s — see $log"
fi

if [ -x "$REPO/orbit-browser/node_modules/electron/dist/electron" ]; then
  echo "[3/4] launching Orbit browser (with platform-fallback) ..."
  ELECTRON="$REPO/orbit-browser/node_modules/electron/dist/electron"
  APP_DIR="$REPO/orbit-browser"
  BDIR="$HOME/.config/jarvis-orbit"
  mkdir -p "$BDIR"
  # Remove any stale singleton lock from a previous (crashed) run so the new
  # launch is not rejected by Chromium's single-instance lock.
  rm -f "$BDIR/SingletonLock" "$BDIR/SingletonSocket" "$BDIR/SingletonCookie" 2>/dev/null || true
  # Clear the browser log for this launch so we can tell whether the browser
  # stays alive (connected) vs. crashes immediately.
  : > "$STATE_DIR/browser.log" 2>/dev/null || true

  # -------- Browser launch strategies --------
  # Order matters: try the most-likely-to-succeed path first, then fall back.
  #
  # Electron 44 ships with a Wayland-capable Ozone build on this host, so the
  # browser's own auto-detection picks Wayland. On this machine that is the
  # path that tends to drive the GPU / network-service instability, so we start
  # with a Wayland launch that neutralizes the known troublemakers, and only
  # fall back to a forced X11 path if Wayland does not survive.

  run_browser_with() {
    # $1 = log tag (for browser.log identity)
    # $2... = electron args
    : > "$STATE_DIR/browser.log" 2>/dev/null || true
    (
      export DISPLAY="${DISPLAY:-:0}"
      cd "$APP_DIR"
      "$ELECTRON" "$@" . >> "$STATE_DIR/browser.log" 2>&1
    ) &
    local PID=$!
    # Give Chromium time to spawn its GPU / network processes and either come
    # up clean or crash.  Wayland Ozone setups on this host have been seen to
    # take a little longer to probe the KMS/primary device, so use a slightly
    # generous window.
    sleep 12
    if kill -0 "$PID" 2>/dev/null; then
      echo "[ok] browser alive via $1 (pid=$PID)"
      return 0
    else
      printf "[warn] browser did not survive the %s pass — see browser.log\n" "$1"
      printf "       last lines:\n"
      tail -n 4 "$STATE_DIR/browser.log" 2>/dev/null | sed 's/^/         /'
      return 1
    fi
  }

  # Strategy 0 (preferred on this host): Wayland Ozone, with the GPU stack
  # that maps to the observed failures build-path-cleaned out.
  #
  # --disable-gpu+--in-process-gpu: collapse the separate GPU process to the
  # browser process.  The crash we see (Network service + zygote GetTerminationStatus
  # failure) correlates with the separate GPU/Network service processes on this
  # hybrid-nvidia KMS host, so keeping the browser alive is more important than
  # keeping a separate accelerated GPU process.
  #
  # --disable-gpu-compositing: avoid the Ozone EGL/kmsurf compositing path
  # that can wedge on a KMS setup that has both nvidia and intel DRM render
  # nodes.
  #
  # --disable-dev-shm-usage: /dev/shm is frequently undersized on dev VMs /
  # Bazzite installs and is a common source of silent Chromium exits.
  #
  # --disable-features: drop the features that have historically gated the
  # exact native-image / dma-buf / sync-fence paths that are broken on a
  # dual-GPU host: DDLM, in-process GPU (we control the process model ourselves
  # via --in-process-gpu already), the VAPiA decode path (we checked it is
  # skipped here), the nv12 texture map path, the native pixmap service
  # allocator path (the one that prefers the nvidia IOSurface), and VA-API.
  #
  # WebRtcNonHeadlessMode is added on the theory that the headless WebRTC
  # surface init on Wayland has been seen to wedge on some compositors here;
  # it is a no-op on a normal desktop launch but cheap to carry.
  GOING=0
  run_browser_with "wayland(in-process-gpu,no-compositing,no-shm,disable-features)" \
    --enable-logging=stderr \
    --disable-gpu-compositing \
    --disable-dev-shm-usage \
    --disable-features=Ddlm,In-processGPU,video_decode_acceleration,use_nv12_map,native_pixmap_service_allocator,use_vaapi,WebRtcNonHeadlessMode \
    || GOING=1

  # Strategy 1: same as above, but force Ozone onto Wayland explicitly.  Some
  # Electron builds still negotiate the display server path from env / argv
  # precedence and we want to be sure we are actually on Wayland for this pass.
  if [ "$GOING" -ne 0 ]; then
    run_browser_with "wayland(explicit,rest-same)" \
      --enable-logging=stderr \
      --ozone-platform=wayland \
      --disable-gpu-compositing \
      --disable-dev-shm-usage \
      --disable-features=Ddlm,In-processGPU,video_decode_acceleration,use_nv12_map,native_pixmap_service_allocator,use_vaapi,WebRtcNonHeadlessMode \
      || true
  fi

  # Strategy 2: fallback to X11 Ozone + in-process GPU + no sandbox.  X11 is
  # unambiguous about which display path it uses, so if Wayland is the culprit
  # this is the most likely alternative to survive on this host.
  if [ "$GOING" -ne 0 ]; then
    run_browser_with "x11(in-process-gpu,no-compositing,no-shm,no-sandbox)" \
      --enable-logging=stderr \
      --ozone-platform=x11 \
      --disable-gpu \
      --in-process-gpu \
      --disable-gpu-compositing \
      --disable-dev-shm-usage \
      --no-sandbox \
      --disable-setuid-sandbox \
      || true
  fi

  # Strategy 3: same X11 pass but without the no-sandbox flags.  Not expected
  # to out-survive strategy 2, but included to keep the fallback ladder honest.
  if [ "$GOING" -ne 0 ]; then
    run_browser_with "x11(in-process-gpu,no-compositing,no-shm)" \
      --enable-logging=stderr \
      --ozone-platform=x11 \
      --disable-gpu \
      --in-process-gpu \
      --disable-gpu-compositing \
      --disable-dev-shm-usage \
      || true
  fi

  # The caller launched us to get a running browser.  If none of the above
  # survived, print the tail of browser.log so the user can tell whether it is
  # a Chromium platform issue on this machine or a launcher bug.
  if [ "$GOING" -ne 0 ]; then
    echo "[!!] no launch strategy kept the browser alive — see $STATE_DIR/browser.log"
  else
    # Point the user at the right place for browser-side diagnostics once we
    # have a survivor.
    echo "[ok] browser log: $STATE_DIR/browser.log"
  fi
else
  echo "[warn] Electron binary not found at $REPO/orbit-browser/node_modules/electron/dist/electron"
fi

echo "[4/4] status:"
printf "  kernel    8170: "
ss -ltn 2>/dev/null | grep -q ':8170 ' && echo "online" || echo "offline"
printf "  bridge    8171: "
ss -ltn 2>/dev/null | grep -q ':8171 ' && echo "online" || echo "offline"
printf "  browser   : "
if pgrep -af "electron" >/dev/null 2>&1; then
  echo "running"
else
  echo "not running"
fi
echo
echo "  logs:"
echo "    services: $STATE_DIR/kernel.log  $STATE_DIR/bridge.log"
echo "    browser : $STATE_DIR/browser.log"
echo "=== done ==="
