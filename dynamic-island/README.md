# Dynamic Island application

The PySide6 desktop surface is the primary product entry point. It runs independently of the model backend and lazily activates optional capabilities.

## Launch

From the repository root:

```bash
PYTHONPATH="$PWD/dynamic-island:$PWD" python scripts/island-launcher.py
```

Or use `python -m app.main` with `dynamic-island/` and the repository root on `PYTHONPATH`.

## Components

- `app/ui/`: compact overlay, conversation panel, chat window and island state controller.
- `app/integration/`: Qt-to-AgentLoop bridge and desktop coordinator.
- `app/desktop/`: desktop action boundary.
- `app/voice/`: explicit push-to-talk capture, speech recognition and speech output.
- `app/gestures/`: opt-in camera capture and gesture mapping.
- `app/workspace3d/`: optional Qt Quick 3D workspace.
- `app/diagnostics/`: desktop diagnostics.
- `app/autostart.py`: user-level autostart management.

## Operating rules

- The island must start without provider credentials or a running local model.
- AI calls run through the existing AgentLoop and its permission, tool execution and verification layers.
- Voice capture is user-initiated push-to-talk. No always-on microphone or wake-word listener.
- Gesture mode is disabled by default and camera capture starts only after explicit activation.
- The 3D workspace is loaded only when requested; failure must leave the island usable.
- Desktop actions requiring approval must remain behind the confirmation boundary.

## Verification

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/desktop -q
QT_QPA_PLATFORM=offscreen python -m pytest dynamic-island/tests -q
```

A headless test run does not validate KWin placement, actual microphone/audio devices, camera hardware or GPU-backed Qt Quick 3D. Verify those on a KDE Plasma 6 Wayland session before release.
