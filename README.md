# JARVIS Dynamic Island

A native KDE Plasma 6 Dynamic Island for Linux, with an optional JARVIS AI assistant panel.

The project is designed to work as a desktop component first. The island, system interactions, notifications and desktop controls must remain useful when no model provider is configured. AI, voice, gestures and the 3D workspace are integrated capabilities, not prerequisites for launching the shell.

## Current scope

- **Dynamic Island:** compact top-centre overlay, expandable conversation surface and state-driven UI.
- **Desktop integration:** KDE Plasma 6 / KWin, Wayland placement helper, desktop entry, autostart and installer.
- **AI:** existing JARVIS AgentLoop, provider routing, tool execution, permissions, verification and memory.
- **Voice:** explicit push-to-talk STT and TTS. No background wake-word listener.
- **Gestures:** opt-in camera-based controls; camera access is not required for normal operation.
- **3D workspace:** optional QML workspace, loaded only when requested.

## Quick start

Python 3.11+ and KDE Plasma 6 are recommended.

```bash
git clone https://github.com/Railgunonyx1/JARVIS.git
cd JARVIS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Run the island from a checkout:

```bash
PYTHONPATH="$PWD/dynamic-island:$PWD" python scripts/island-launcher.py
```

Install into the current user account:

```bash
chmod +x packaging/desktop/install.sh
./packaging/desktop/install.sh
```

The launcher is `jarvis-desktop-island` (also exposed as `jarvis-island`).

## Optional capabilities

- **Cloud AI:** configure provider credentials using environment variables or the supported JARVIS configuration. Never commit API keys.
- **Local AI:** configure an Ollama endpoint and model in the provider configuration.
- **Voice:** audio capture uses `sounddevice`; TTS engines are loaded on demand. Model downloads may be required for local engines.
- **Gestures:** install optional `opencv-python-headless` and `mediapipe` dependencies when enabling camera controls.
- **3D workspace:** requires the Qt Quick 3D modules available for the installed PySide6/Qt version.

## Architecture

```text
Dynamic Island UI (PySide6 / Qt Quick)
        |
        +-- desktop actions / notifications / state
        +-- voice manager (push-to-talk STT / TTS)
        +-- optional gesture controller
        +-- optional 3D workspace
        |
        +-- JarvisBackend (worker thread + asyncio)
                    |
                 AgentLoop
                    |
        permissions -> ToolExecutionService -> verification
                    |
        providers / routing / memory / MCP / tools
```

The authoritative desktop application is under `dynamic-island/`. The reusable AI runtime remains in `core/`, `providers/`, `runtime/`, `memory/`, `tools/`, `security/` and the selected plugins/packages.

## Development and verification

```bash
ruff check .
PYTHONPATH="$PWD/dynamic-island:$PWD" QT_QPA_PLATFORM=offscreen python -m pytest tests/ dynamic-island/tests/ -q
python scripts/scan_secrets.py
```

Hardware-dependent camera, audio-device, live-provider and compositor checks must be run on a real KDE session. CI cannot certify Wayland placement or physical device behaviour.

See:
- [Dynamic Island application notes](dynamic-island/README.md)
- [Architecture and cleanup audit](docs/architecture/DYNAMIC-ISLAND-AUDIT.md)
- [Desktop packaging](packaging/desktop/README.md)
- [Security policy](SECURITY.md)

## License

Proprietary software. All rights reserved. See [LICENSE](LICENSE).
