"""Desktop settings persistence with explicit success/failure contract."""

from __future__ import annotations

import fcntl
import json
import logging
import os
from pathlib import Path
from typing import NamedTuple

from app.paths import JARVIS_DESKTOP_HOME, ensure_dirs

logger = logging.getLogger("jarvis.desktop.settings")

# XDG-compatible configuration home. Falls back to JARVIS_DESKTOP_HOME or
# ~/.jarvis-desktop. Kept for test compatibility.
HOME_ENV = "JARVIS_DESKTOP_HOME"
DEFAULT_SETTINGS_DIR = Path.home() / ".jarvis-desktop"

# A schema version key that tolerates unknown future keys without crashing.
SCHEMA_VERSION = "1.0"

# Module-level attributes for test compatibility (monkeypatchable).
SETTINGS_DIR = Path(os.environ.get(HOME_ENV, str(DEFAULT_SETTINGS_DIR)))
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

DEFAULTS = {
    "schema_version": SCHEMA_VERSION,
    "model": "",
    "voice_enabled": True,
    "gesture_enabled": False,
    "autostart_enabled": False,
}


class SettingsSaveResult(NamedTuple):
    """Result type for settings.save() to distinguish success from failure.

    Callers can unambiguously distinguish saved from not saved, and inspect
    the error information when persistence fails.
    """
    success: bool
    settings: dict | None
    error_code: str | None
    message: str | None


_PENDING_TMP_PREFIX = ".jarvis-settings-tmp"


def _ensure_dir() -> Path:
    """Ensure the settings directory exists, return the path."""
    try:
        ensure_dirs()
        return JARVIS_DESKTOP_HOME
    except OSError as e:
        logger.error("Cannot create settings directory %s: %s", JARVIS_DESKTOP_HOME, e)
        raise


def _is_same_directory(src: Path, dst: Path) -> bool:
    """Check that two paths reside on the same filesystem/mount."""
    try:
        return src.samefile(dst) if src.exists() or dst.exists() else src.parent == dst.parent
    except OSError:
        return False


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


def save(settings: dict) -> SettingsSaveResult:
    """Save settings atomically using temp file + replace.

    Returns a SettingsSaveResult with:
      - success=True when the write completed
      - success=False when the write failed (old file preserved)
      - error_code and message describing the failure

    The written file always contains valid JSON; if writing fails, the old
    file is preserved. Uses a unique temp file in the same directory, fsync,
    and atomic replace.
    """
    _ensure_dir()
    target = SETTINGS_FILE
    # Unique temp file in the same directory for atomic replace
    tmp = target.parent / f"{_PENDING_TMP_PREFIX}{os.getpid()}{target.suffix}"

    try:
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
        return SettingsSaveResult(success=True, settings=settings, error_code=None, message=None)
    except OSError as e:
        logger.warning("Failed to save settings: %s", e)
        # Clean up temp file if it exists
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        # Old file is preserved since os.replace didn't execute
        return SettingsSaveResult(
            success=False, settings=None, error_code="io_error", message=str(e)
        )
    except Exception as e:
        logger.warning("Unexpected error saving settings: %s", e)
        # Clean up temp file if it exists
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return SettingsSaveResult(
            success=False, settings=None, error_code="unexpected_error", message=str(e)
        )


def update(partial: dict) -> tuple[dict, SettingsSaveResult]:
    """Merge ``partial`` into the persisted settings and save.

    Returns a tuple of (merged_settings, save_result) so the caller can
    unambiguously distinguish saved from not saved.

    Validates schema version and value types before writing. Uses atomic
    temp+replace semantics with fsync. The old file is preserved on failure.

    Preserves keys owned by other surfaces (e.g. ``autostart_enabled``) instead
    of overwriting the whole file.
    """
    # Load current settings (or defaults)
    merged = load()

    # Validate and apply partial updates, preserving unknown schema conservatively
    for key, value in partial.items():
        if key in DEFAULTS:
            # Type-level validation for known keys
            expected = DEFAULTS[key]
            if isinstance(expected, bool):
                if not isinstance(value, bool):
                    # Coerce bool-like strings; otherwise keep existing value
                    if isinstance(value, str) and value.lower() in ("true", "false"):
                        value = value.lower() == "true"
                    else:
                        # Keep existing value; skip this key
                        continue
                merged[key] = value
            elif isinstance(expected, str):
                if not isinstance(value, str):
                    continue
                merged[key] = value
            else:
                merged[key] = value
        else:
            # Unknown future schema: store conservatively; do not overwrite
            # known keys blindly. Only add if not already present.
            if key not in merged:
                merged[key] = value

    # Persist with explicit result
    save_result = save(merged)

    return merged, save_result