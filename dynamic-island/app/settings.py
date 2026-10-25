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
    "autostart_enabled": False,
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
        target = SETTINGS_FILE
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        f = None
        try:
            f = open(tmp, "w", encoding="utf-8")
            f.write(json.dumps(settings, indent=2))
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        finally:
            if f is not None:
                try:
                    f.close()
                except Exception:
                    pass
        os.replace(tmp, target)
        logger.info("Settings saved to %s", SETTINGS_FILE)
    except OSError as e:
        logger.warning("Failed to save settings: %s", e)


def update(partial: dict) -> dict:
    """Merge ``partial`` into the persisted settings and save.

    Preserves keys owned by other surfaces (e.g. ``autostart_enabled``) instead
    of overwriting the whole file.
    """
    merged = load()
    merged.update(partial)
    save(merged)
    return merged
