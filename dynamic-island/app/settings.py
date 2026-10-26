"""Desktop settings persistence."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app.paths import JARVIS_DESKTOP_HOME, ensure_dirs

logger = logging.getLogger("jarvis.desktop.settings")

# XDG-compatible configuration home. Falls back to JARVIS_DESKTOP_HOME or
# ~/.jarvis-desktop. Kept for test compatibility.
HOME_ENV = "JARVIS_DESKTOP_HOME"
DEFAULT_SETTINGS_DIR = Path.home() / ".jarvis-desktop"

# A schema version key that tolerates unknown future keys without crashing.
SCHEMA_VERSION = "1.0"

# Module-level attributes for test compatibility (monkeypatchable).
SETTINGS_DIR = Path(
    os.environ.get(HOME_ENV, str(DEFAULT_SETTINGS_DIR))
)
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

DEFAULTS = {
    "schema_version": SCHEMA_VERSION,
    "model": "",
    "voice_enabled": True,
    "gesture_enabled": False,
    "autostart_enabled": False,
}


def _ensure_dir() -> Path:
    """Ensure the settings directory exists, return the path."""
    try:
        ensure_dirs()
        return JARVIS_DESKTOP_HOME
    except OSError as e:
        logger.error("Cannot create settings directory %s: %s", JARVIS_DESKTOP_HOME, e)
        raise


def load() -> dict:
    """Load persisted settings, merging with defaults.

    Returns a copy of the merged dict. If the file is missing or contains
    invalid JSON, defaults are returned unchanged (no crash).
    Malformed JSON files are renamed to *.bad for diagnostics, not deleted.
    """
    if not SETTINGS_FILE.exists():
        return dict(DEFAULTS)

    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        # Merge defaults, giving precedence to persisted values.
        merged = {**DEFAULTS, **data}
        # Ensure schema_version is always present.
        if "schema_version" not in merged:
            merged["schema_version"] = SCHEMA_VERSION
        return merged
    except json.JSONDecodeError:
        # Rename malformed file for diagnostics; do not silently delete it.
        bad_path = SETTINGS_FILE.with_suffix(".bad")
        if not bad_path.exists():
            try:
                SETTINGS_FILE.rename(bad_path)
                logger.warning(
                    "Renamed malformed settings file to %s for diagnostics", bad_path
                )
            except Exception:
                pass
        return dict(DEFAULTS)
    except Exception as e:
        logger.error("Unexpected error loading settings: %s", e)
        return dict(DEFAULTS)


def save(settings: dict) -> bool:
    """Save settings atomically using temp file + replace.

    Returns True on success, False on failure (caller should surface the error).
    The written file always contains valid JSON; if writing fails, the old
    file is preserved.
    """
    _ensure_dir()
    try:
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
        # Atomic replace — old file preserved if this fails.
        os.replace(tmp, target)
        logger.info("Settings saved to %s", SETTINGS_FILE)
        return True
    except OSError as e:
        logger.warning("Failed to save settings: %s", e)
        return False
    except Exception as e:
        logger.warning("Unexpected error saving settings: %s", e)
        return False


def update(partial: dict) -> dict:
    """Merge ``partial`` into the persisted settings and save.

    Returns the merged settings dict. Callers should check persistence
    success separately if needed; this function always returns the merged
    dict (even if the write failed, the dict is still returned for inspection).

    Preserves keys owned by other surfaces (e.g. ``autostart_enabled``) instead
    of overwriting the whole file. Uses atomic temp+replace semantics.
    """
    merged = load()
    merged.update(partial)
    save(merged)  # best-effort save; caller can inspect merged dict
    return merged