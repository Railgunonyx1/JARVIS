# Contributing to JARVIS Dynamic Island

This repository is focused on the KDE Plasma 6 Dynamic Island and its optional JARVIS AI backend.

## Architecture rules

1. The UI lives under `dynamic-island/app/`; do not introduce a second desktop shell or agent loop.
2. AI requests use the existing AgentLoop and `ToolExecutionService` permission/execution/verification path.
3. Keep the island usable without model credentials or a running local model.
4. Voice is push-to-talk. Never add always-on microphone capture or background wake-word detection.
5. Gesture mode and the 3D workspace are opt-in and loaded lazily.
6. Desktop actions with meaningful side effects require explicit approval.
7. Preserve KDE/Wayland-specific packaging and test lifecycle behaviour where possible.

## Development setup

```bash
git clone https://github.com/Railgunonyx1/JARVIS.git
cd JARVIS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Run the app:

```bash
PYTHONPATH="$PWD/dynamic-island:$PWD" python scripts/island-launcher.py
```

## Quality gates

```bash
ruff check .
QT_QPA_PLATFORM=offscreen python -m pytest tests/ dynamic-island/tests/ -q
python scripts/scan_secrets.py
```

Tests requiring a live KDE session, camera, microphone, GPU-backed Qt Quick 3D, or live provider credentials must be labelled and reported separately. Do not claim those checks passed from headless CI.

## Pull requests

- Use a focused branch and a clear imperative commit message.
- Include tests for behavioural changes and lifecycle edge cases.
- Never commit API keys, provider credentials, local memory databases or user settings.
- State exactly which checks were run and which were not.
