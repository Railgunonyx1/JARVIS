# Dynamic Island packaging

The supported desktop target is KDE Plasma 6 on Linux. The user-level installer is maintained in `packaging/desktop/`.

## Install

```bash
chmod +x packaging/desktop/install.sh
./packaging/desktop/install.sh
```

The installer creates an isolated Python environment under `~/.local/share/jarvis-desktop`, installs runtime requirements, stages the application, installs the `jarvis-desktop-island` and `jarvis-island` launchers, and registers the KDE desktop entry and optional KWin placement helper.

## Uninstall

```bash
packaging/desktop/uninstall.sh
```

## Release gates

1. `ruff check .` passes.
2. `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q
QT_QPA_PLATFORM=offscreen python -m pytest dynamic-island/tests/ -q` passes.
3. `python scripts/scan_secrets.py` reports no potential secrets.
4. The installer and uninstaller are exercised on a clean KDE Plasma 6 user account.
5. Compact/expanded states, autostart, KWin placement, push-to-talk, gesture opt-in and lazy 3D loading are manually checked on the target Wayland session.

Do not describe a release as Wayland/audio/camera validated based only on CI.
