"""Autostart registration for JARVIS Desktop.

Writes/removes a freedesktop autostart entry so the island launches on login.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("jarvis.desktop.autostart")

AUTOSTART_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
ENTRY_FILE = AUTOSTART_DIR / "jarvis-desktop.desktop"

_DESKTOP_TEMPLATE = """[Desktop Entry]
Type=Application
Name=JARVIS Desktop Island
Comment=JARVIS dynamic island assistant
Exec={exec_cmd}
Icon=jarvis-desktop
Terminal=false
X-GNOME-Autostart-enabled=true
StartupNotify=false
"""


def _launch_command() -> str:
    existing = Path(sys.argv[0]).resolve()
    if existing.name == "jarvis-desktop":
        return str(existing)
    return f"{sys.executable} {existing}"


def is_enabled() -> bool:
    return ENTRY_FILE.is_file()


def enable(run_command: str | None = None) -> bool:
    try:
        AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
        cmd = run_command or _launch_command()
        ENTRY_FILE.write_text(_DESKTOP_TEMPLATE.format(exec_cmd=cmd), encoding="utf-8")
        logger.info("Autostart enabled: %s", ENTRY_FILE)
        return True
    except OSError as e:
        logger.warning("Failed to enable autostart: %s", e)
        return False


def disable() -> bool:
    try:
        ENTRY_FILE.unlink(missing_ok=True)
        logger.info("Autostart disabled")
        return True
    except OSError as e:
        logger.warning("Failed to disable autostart: %s", e)
        return False


def set_enabled(enabled: bool) -> bool:
    return enable() if enabled else disable()
