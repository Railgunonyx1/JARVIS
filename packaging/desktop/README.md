# JARVIS Desktop Companion — Packaging

Packaging for Bazzite Linux. Supports:
- System installation via `install.sh` / `uninstall.sh`
- Flatpak (manifest included, build with `flatpak-builder`)

## System Installation

```bash
cd packaging
chmod +x install.sh uninstall.sh
./install.sh
jarvis-desktop
```

Installs to `/opt/jarvis-desktop` by default. Wrapper script at `/usr/local/bin/jarvis-desktop`.

### Uninstall

```bash
./uninstall.sh
```

## Flatpak

```bash
flatpak-builder --repo=repo --force-clean build-dir com.jarvis.desktop.flatpak.json
flatpak build-bundle repo com.jarvis.desktop.flatpak com.jarvis.desktop
flatpak install com.jarvis.desktop.flatpak
flatpak run com.jarvis.desktop
```

Requires `flatpak-builder` and the KDE runtime SDK.

## Permissions

The app needs:
- Camera access (gesture mode, on demand)
- Microphone access (voice STT, push-to-talk)
- Audio output (TTS playback)
- Wayland/X11 socket (display)
- Session D-Bus (desktop integration)

## Configuration Persistence

User configuration and memory are stored under `~/.jarvis/` by the parent
JARVIS backend. The desktop app reuses this directory, so settings persist
across upgrades.

## Dependencies

- Python 3.11+
- PySide6 6.x
- sounddevice, numpy (audio capture)
- opencv-python-headless, mediapipe (hand tracking)
- whisper-cpp-python or whisper-cli binary (local STT)

All are installed by `install.sh` via pip if missing.
