"""Desktop settings persistence."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("jarvis.desktop.settings")

SETTINGS_DIR = Path(
    os.environ.get("JARVIS_DESKTOP_HOME", Path.home() / ".jarvis-desktop")
)
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

DEFAULTS = {
    "model": "",
    "voice_enabled": True,
    "gesture_enabled": False,
}


def load() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        merged = {**DEFAULTS, **data}
        return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULTS)


def save(settings: dict) -> None:
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        logger.info("Settings saved to %s", SETTINGS_FILE)
    except OSError as e:
        logger.warning("Failed to save settings: %s", e)
