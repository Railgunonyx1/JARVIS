#!/usr/bin/env bash
# JARVIS Orbit — desktop-app wrapper (app grid / dock launcher).
#
# Chrome-style launch semantics: return immediately so the desktop
# environment never blocks on the launcher, while JARVIS.sh brings up
# the kernel (8170), the WebSocket bridge (8171) and the Orbit browser
# window in the background. Re-running focuses the existing window
# (Electron single-instance lock) and reuses running services.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="${LOCALAPPDATA:-$HOME}/JARVIS"
mkdir -p "$STATE_DIR"

setsid nohup "$REPO/JARVIS.sh" >> "$STATE_DIR/desktop-launch.log" 2>&1 < /dev/null &
exit 0
