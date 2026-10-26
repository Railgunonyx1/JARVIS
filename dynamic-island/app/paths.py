"""Unified path configuration for JARVIS Desktop.

Uses XDG Base Directory Specification where possible, with JARVIS_DESKTOP_HOME
as the primary override for all JARVIS-specific data.

Directory hierarchy:
  $JARVIS_DESKTOP_HOME (or $XDG_DATA_HOME/jarvis-desktop by default)
    ├── settings.json          -- persistent user settings (schema v1.0)
    ├── cache/                 -- cached model files, temp data
    ├── state/                 -- runtime state, daemon locks
    └── models/                -- downloaded model binaries

XDG-compliant defaults:
  $XDG_CONFIG_HOME/jarvis (or $HOME/.config/jarvis) -- config/scripts
  $XDG_DATA_HOME/jarvis-desktop (or $HOME/.local/share/jarvis-desktop) -- data
  $XDG_STATE_HOME/jarvis (or $HOME/.local/state/jarvis) -- runtime state
"""

from __future__ import annotations

import os
from pathlib import Path


def _env(key: str, default: Path) -> Path:
    """Read an environment variable as a Path, falling back to default."""
    value = os.environ.get(key)
    if value:
        return Path(value)
    return default


# ── Base directories ──────────────────────────────────────────────────

# Primary JARVIS desktop home. Falls back to XDG_DATA_HOME/jarvis-desktop.
# This is the main writable location for user-facing data.
JARVIS_DESKTOP_HOME = _env(
    "JARVIS_DESKTOP_HOME",
    Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    / "jarvis-desktop",
)

# Configuration directory following XDG spec.
# $XDG_CONFIG_HOME/jarvis (or $HOME/.config/jarvis by default).
JARVIS_CONFIG_HOME = _env(
    "JARVIS_CONFIG_HOME",
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "jarvis",
)

# Runtime state directory following XDG spec.
# $XDG_STATE_HOME/jarvis (or $HOME/.local/state/jarvis by default).
JARVIS_STATE_HOME = _env(
    "JARVIS_STATE_HOME",
    Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "jarvis",
)

# ── Data subdirectories within JARVIS_DESKTOP_HOME ───────────────────

# Persistent user settings (merged with defaults on load).
SETTINGS_FILE = JARVIS_DESKTOP_HOME / "settings.json"

# Cached model files, temp data, etc.
CACHE_DIR = JARVIS_DESKTOP_HOME / "cache"

# Runtime state, locks, etc.
STATE_DIR = JARVIS_DESKTOP_HOME / "state"

# Downloaded model binaries (Whisper, Kokoro, etc.).
MODELS_DIR = JARVIS_DESKTOP_HOME / "models"


def ensure_dirs() -> None:
    """Create all required directories if they don't exist."""
    for d in [JARVIS_DESKTOP_HOME, CACHE_DIR, STATE_DIR, MODELS_DIR]:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            # Log but don't raise — callers should handle gracefully
            import logging
            logging.getLogger("jarvis.paths").warning(
                "Cannot create directory %s: %s", d, e
            )


# ── Legacy migration ──────────────────────────────────────────────────

# Old paths that may exist from prior versions. These are read on first launch
# and migrated if the new path doesn't already exist.

# Old settings location: ~/.jarvis-desktop/settings.json (before JARVIS_DESKTOP_HOME)
OLD_SETTINGS_DIR = Path.home() / ".jarvis-desktop"
OLD_SETTINGS_FILE = OLD_SETTINGS_DIR / "settings.json"

# Old model cache location: ~/.jarvis/models/...
OLD_MODEL_DIR = Path.home() / ".jarvis" / "models"

# Old config location: ~/.jarvis/config/...
OLD_CONFIG_DIR = Path.home() / ".jarvis" / "config"


def migrate_legacy_data() -> None:
    """Migrate data from old ~/.jarvis paths to new JARVIS_DESKTOP_HOME layout.

    Policy: copy/merge only when destination doesn't exist. Never delete source
    until new file is validated. Log which migration occurred, without logging secrets.
    """
    logger = logging.getLogger("jarvis.paths")

    # Migrate settings if new location is empty and old exists
    if SETTINGS_FILE.exists():
        logger.debug("New settings file already exists at %s, skipping migration", SETTINGS_FILE)
    elif OLD_SETTINGS_FILE.exists():
        try:
            import json
            from app.settings import load as _load_old, save as _save_old

            old_data = _load_old()
            # Merge: give precedence to old values for keys that exist
            if SETTINGS_FILE.exists():
                new_data = _load_old()  # reload after save if needed
            else:
                _save_old(old_data)
                SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
                _save_old(old_data)
            logger.info("Migrated settings from ~/.jarvis-desktop to %s", SETTINGS_FILE)
        except Exception as e:
            logger.warning("Failed to migrate settings: %s", e)

    # Migrate model directory if new location is empty and old exists
    if not MODELS_DIR.exists() and OLD_MODEL_DIR.exists():
        try:
            import shutil
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            for item in OLD_MODEL_DIR.iterdir():
                dest = MODELS_DIR / item.name
                if not dest.exists():
                    shutil.copy2(str(item), str(dest))
            logger.info("Migrated models from ~/.jarvis/models to %s", MODELS_DIR)
        except Exception as e:
            logger.warning("Failed to migrate models: %s", e)

    # Migrate config directory if new location is empty and old exists
    if not JARVIS_CONFIG_HOME.exists() and OLD_CONFIG_DIR.exists():
        try:
            import shutil
            JARVIS_CONFIG_HOME.mkdir(parents=True, exist_ok=True)
            for item in OLD_CONFIG_DIR.iterdir():
                dest = JARVIS_CONFIG_HOME / item.name
                if not dest.exists():
                    shutil.copy2(str(item), str(dest))
            logger.info("Migrated config from ~/.jarvis/config to %s", JARVIS_CONFIG_HOME)
        except Exception as e:
            logger.warning("Failed to migrate config: %s", e)