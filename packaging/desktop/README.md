# JARVIS Dynamic Island — KDE Plasma 6

User-level packaging for the Dynamic Island overlay on KDE Plasma 6 / KWin.

## Install

```bash
chmod +x install.sh uninstall.sh
./install.sh
```

The installer creates an isolated virtual environment under `~/.local/share/jarvis-desktop`, stages the project, installs the `jarvis-desktop-island` and `jarvis-island` commands, and registers the island desktop entry. It also attempts to install the KWin placement helper when running inside a KDE session.

## Run

```bash
jarvis-desktop-island
```

## Uninstall

```bash
./uninstall.sh
```

The uninstaller removes the installed application, launchers, desktop entry and JARVIS autostart entry. User data and provider credentials are not intentionally removed.

## Optional permissions

- Microphone: only while the user activates push-to-talk.
- Camera: only after the user enables gesture mode.
- Audio output: for TTS.
- Session D-Bus and Wayland/X11 display sockets: desktop integration.

## Platform notes

- Python 3.11+
- KDE Plasma 6 and KWin
- PySide6 / Qt 6
- Camera gesture dependencies are optional and installed separately.
- Physical Wayland, audio and camera behaviour must be verified on the target machine.
