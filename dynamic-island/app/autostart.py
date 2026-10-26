"""Autostart registration for JARVIS Desktop.

Writes/removes a freedesktop autostart entry so the island launches on login.

Registry target: ~/.config/autostart/jarvis-desktop.desktop
The Exec line points at the installed jarvis-desktop-island launcher (or the
in-tree island_main.py when running from a source checkout).
"""


from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("jarvis.desktop.autostart")

AUTOSTART_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
ENTRY_FILE = AUTOSTART_DIR / "jarvis-desktop.desktop"

# The executable that the autostart entry launches. It is resolved as
# "installed launcher" (bin/jarvis-desktop-island) when present, otherwise the
# in-tree island_main.py relative to the executable's own directory.
_ENTRY_EXEC = "jarvis-desktop-island"


def _quote(argument: str) -> str:
    """Quote one Exec argument per the Desktop Entry spec."""
    escaped = (
        argument.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("%", "%%")
    )
    return f'"{escaped}"'


def _launch_command() -> str:
    """Return the Exec= value for the autostart entry."""
    existing = Path(sys.argv[0]).resolve()
    installed = Path(os.environ.get("BIN_DIR", os.path.expanduser("~/.local/bin"))) / _ENTRY_EXEC
    if installed.is_file():
        return _quote(str(installed))
    if existing.name in ("jarvis-desktop-island", "jarvis-island"):
        return _quote(str(existing))
    return f"{_quote(sys.executable)} {_quote(str(existing))}"


def is_enabled() -> bool:
    return ENTRY_FILE.is_file()


def enable(run_command: str | None = None, installed_exe: str | None = None) -> bool:
    """Write the autostart entry.

    The entry is created without overwriting an existing one so a user or an
    earlier run never loses its own configuration.
    """
    if ENTRY_FILE.is_file():
        logger.info("Autostart already present: %s", ENTRY_FILE)
        return True
    try:
        AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
        cmd = run_command or _launch_command()
        content = _DESKTOP_TEMPLATE.format(exec_cmd=cmd)
        ENTRY_FILE.write_text(content, encoding="utf-8")
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
