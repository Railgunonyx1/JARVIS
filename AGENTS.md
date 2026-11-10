# Repository guide — JARVIS Dynamic Island

## Product boundary

This repository contains one product: **JARVIS Dynamic Island for KDE Plasma 6 on Linux**. Do not reintroduce Orbit, J-Browser, Chromium/Electron browser shells, browser extensions, or the old terminal cockpit as product surfaces.

The desktop shell must launch and operate without AI credentials. AI is an optional subsystem attached through the existing JARVIS backend. Voice is push-to-talk only; never add a background wake-word listener. Gesture and 3D features are opt-in and must not block startup.

## Source of truth

- Desktop application: `dynamic-island/app/`
- Desktop tests: `tests/desktop/` and `dynamic-island/tests/`
- Agent runtime: `core/`
- Model providers and routing: `providers/`, `plugins/`, `packages/`
- Memory: `memory/`
- Tool registry and implementations: `tools/`
- Runtime services: `runtime/`
- Security and permissions: `security/`
- KDE packaging: `packaging/desktop/`

Do not create a second agent loop. Route AI requests through `dynamic-island/app/integration/jarvis_backend.py` and the established AgentLoop / permission / execution / verification layers.

## Design constraints

- Keep the UI minimal, readable and functional; avoid gaming-HUD styling and decorative dashboards.
- Preserve clear hierarchy, restrained motion and progressive disclosure.
- Keep the compact island lightweight; construct optional panels and 3D workspace lazily.
- Use explicit user activation for microphone and camera features.
- Never silently bypass permission checks or verification for desktop actions.

## Engineering workflow

1. Trace imports and runtime references before deleting or moving modules.
2. Keep changes scoped to the Dynamic Island branch; do not modify `main` or historical branches.
3. Add or update tests for lifecycle, permissions, voice shutdown, gestures and workspace loading.
4. Run `ruff check .`, `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q`, and `python scripts/scan_secrets.py`.
5. Report checks that could not be run. Do not claim Wayland, audio or camera validation from a headless CI run.
