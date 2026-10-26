# JARVIS Dynamic Island

Minimal AI assistant for Bazzite Linux, built on the existing `Railgunonyx1/JARVIS`
agent core with a new PySide6 Dynamic Island overlay.

## Status

- [x] Dynamic Island UI — idle/pill overlay with compact conversation surface
- [x] Push-to-talk voice, streaming responses, inline approvals
- [x] Design tokens — dark palette from the DI-025 mockup
- [x] State machine — idle, compact, expanded; listening, thinking, speaking, approval, error
- [ ] KDE Wayland runtime validation (Bazzite)

## Design system

Palette (from the DI-025 mockup):

| Token | Hex   | Usage            |
|-------|-------|------------------|
| Token | Hex   | Usage            |
|-------|-------|------------------|
| primary   | `#141619` | island background   |
| accent    | `#8C96A3` | idle dot, hover, active button   |
| text      | `#EBEEF2` | primary content   |
| muted     | `#B0B7C1` | secondary captions, dividers   |
| divider   | `#3A3A3C` | borders and separators   |
| input bg  | `#2C1C2E` | text field background   |
| input fg  | `#FFFFFF` | text field content   |
| blue      | `#0A84FF` | send button, listening indicator   |
| blue hover| `#0071E3` | send button hover, listening hover   |
| amber     | `#FFD60A` | approval prompts   |

## Quick start

```bash
cd dynamic-island
python3 app/main.py
```

Requires: Python 3.11+, PySide6, and the parent JARVIS repo on `PYTHONPATH`.

## Structure

```
app/
  main.py                  # Entry point (launches the island)
  ui/overlay_window.py     # Dynamic Island overlay (idle -> expanded)
  ui/conversation_panel.py # Compact conversation panel (expanded state)
  ui/island_controller.py  # UI state controller
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

## Interface states

- **idle** — 180×36 pill, centred in the upper third, shadow + amber dot.
- **compact** — 320×44 pill (hover). Only the dot animates.
- **expanded** — full conversation surface: transcript, inline approval row, push-to-talk input row.

The island is the sole user-facing interface. No separate desktop chat window
remains.

## Verification

`python -m pytest tests/desktop/ -q` → 14 passed, 3 failed (pre-existing
camera-shutdown failures), 7 skipped (headless Qt skips).

## Architecture

The existing JARVIS agent core (`core/`, `providers/`, `runtime/`, `memory/`)
is reused unchanged. The island UI communicates through `JarvisBackend`,
which runs `AgentLoop` in a dedicated worker thread with its own asyncio
event loop. Qt signals deliver chunks and responses to the UI thread.