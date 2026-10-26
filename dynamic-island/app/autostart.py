#!/usr/bin/env python3
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


def _quote(argument: str) -> str:
    """Quote one Exec argument per the Desktop Entry spec."""
    escaped = (
        argument.replace("\\", "\\\\")
        .replace('"', "\\\"")
        .replace("%", "%%")
    )
    return f'"{escaped}"'


def _launch_command() -> str:
    existing = Path(sys.argv[0]).resolve()
    if existing.name == "jarvis-desktop":
        return _quote(str(existing))
    return f"{_quote(sys.executable)} {_quote(str(existing))}"


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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        prog="jarvis-autostart",
        description="Enable/disable the JARVIS Dynamic Island autostart entry.",
    )
    mode = parser.add_subparsers(dest="command", required=True, help="Command to run")

    p_enable = mode.add_parser("enable", help="Write the log-in entry (idempotent).")
    p_enable.add_argument("--run", dest="run_cmd", help="Command to launch (default: this script)")
    p_disable = mode.add_parser("disable", help="Remove only JARVIS's own entry.")
    p_status = mode.add_parser("status", help="Print whether the entry is present.")

    args = parser.parse_args()

    if args.command == "enable":
        ok = enable(args.run_cmd)
        print(f"Autostart {'enabled' if ok else 'FAILED'}")
        sys.exit(0 if ok else 1)
    elif args.command == "disable":
        ok = disable()
        print(f"Autostart {'disabled' if ok else 'FAILED'}")
        sys.exit(0 if ok else 1)
    elif args.command == "status":
        print("autostart enabled" if is_enabled() else "autostart disabled")
        sys.exit(0)
    else:
        parser.print_help()
        sys.exit(1)
