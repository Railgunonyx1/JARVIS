# JARVIS Desktop Companion

Lightweight desktop AI assistant for Bazzite Linux, built on the existing
`Railgunonyx1/JARVIS` agent core with a new PySide6 interface.

## Status

- [x] Phase 1 — Backend audit
- [x] Phase 2 — Desktop foundation (minimal chat) — 4 tests passing
- [x] Phase 3 — Voice (push-to-talk STT + TTS) — 10 tests passing
- [x] Phase 4 — Gestures + desktop actions — 16 tests passing
- [x] Phase 5 — 3D holographic workspace — 8 tests (6 pass, 2 skip on headless)
- [x] Phase 6 — Integration — 10 tests passing
- [x] Phase 7 — Optimization — 14 tests passing
- [ ] Phase 8 — Packaging

## Quick start

```bash
cd jarvis-desktop
python3 app/main.py
```

Requires: Python 3.11+, PySide6, and the parent JARVIS repo on `PYTHONPATH`.

## Structure

```
app/
  main.py                  # Entry point
  ui/chat_window.py        # PySide6 chat UI
  integration/jarvis_backend.py  # AgentLoop ↔ Qt bridge
  voice/                   # STT/TTS (Phase 3)
  gestures/                # Camera + tracking (Phase 4)
  desktop/                 # Action layer (Phase 5)
  workspace3d/             # Qt Quick 3D (Phase 6)
  config/                  # Settings
  diagnostics/             # Perf monitoring
tests/
assets/
packaging/
```

## Architecture

The existing JARVIS agent core (`core/`, `providers/`, `runtime/`, `memory/`)
is reused unchanged. The desktop UI communicates through `JarvisBackend`,
which runs `AgentLoop` in a dedicated worker thread with its own asyncio
event loop. Qt signals deliver chunks and responses to the UI thread.

No browser dependency. No direct shell execution from AI text.
