"""TOML-based configuration loader for JARVIS MK-X.

Loads from config/*.toml files. Supports hot-reload via file watching.
Provides a single Config instance used across the entire system.
"""

import logging
from pathlib import Path
from typing import Any, Optional

import toml

logger = logging.getLogger("jarvis.config")

SERVER_POLL_INTERVAL = 0.05
CALLBACK_WAIT = 0.1
LONG_CALLBACK_WAIT = 0.3

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_instance: Optional["Config"] = None


class Config:
    """Central configuration store. Reads all .toml files from config/ directory."""

    def __init__(self, config_dir: Path | None = None):
        self._config_dir = config_dir or _CONFIG_DIR
        self._data: dict[str, dict[str, Any]] = {}
        self._listeners: list[callable] = []
        self.load_all()

    @classmethod
    def instance(cls) -> "Config":
        global _instance
        if _instance is None:
            _instance = cls()
        return _instance

    def load_all(self):
        """Load all .toml files from the config directory."""
        if not self._config_dir.exists():
            self._config_dir.mkdir(parents=True, exist_ok=True)
            logger.warning("Config directory created at %s", self._config_dir)
            return

        for toml_file in sorted(self._config_dir.glob("*.toml")):
            try:
                data = toml.load(toml_file)
                section = toml_file.stem
                self._data[section] = data
                logger.info("Loaded config: %s", toml_file.name)
            except Exception as e:
                logger.error("Failed to load %s: %s", toml_file.name, e)

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a config value. Section maps to file stem, key is nested path."""
        section_data = self._data.get(section, {})
        keys = key.split(".")
        value = section_data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def get_section(self, section: str) -> dict[str, Any]:
        """Get entire section as dict."""
        return self._data.get(section, {}).copy()

    def set(self, section: str, key: str, value: Any):
        """Set a config value in memory (does not persist to disk)."""
        if section not in self._data:
            self._data[section] = {}
        keys = key.split(".")
        target = self._data[section]
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        target[keys[-1]] = value
        self._notify_listeners(section, key, value)

    def save(self, section: str):
        """Persist a section back to its TOML file."""
        if section not in self._data:
            return
        toml_path = self._config_dir / f"{section}.toml"
        with open(toml_path, "w") as f:
            toml.dump(self._data[section], f)
        logger.info("Saved config: %s.toml", section)

    def watch(self, callback: callable):
        """Register a callback for config changes."""
        self._listeners.append(callback)

    def _notify_listeners(self, section: str, key: str, value: Any):
        for cb in self._listeners:
            try:
                cb(section, key, value)
            except Exception as e:
                logger.error("Config listener error: %s", e)

    @property
    def api_keys(self) -> dict[str, str]:
        """Get API keys from .env / api_keys.json / environment (cached)."""
        if not hasattr(self, "_api_keys_cache"):
            from core.api_keys import get_all_api_keys
            raw = get_all_api_keys()
            self._api_keys_cache = {
                "groq": raw.get("groq_api_key", ""),
                "groq_extra": [raw.get("groq_api_key_2", "")],
                "gemini": raw.get("gemini_api_key", ""),
                "openrouter": raw.get("openrouter_api_key", ""),
                "openrouter_extra": [
                    raw.get("openrouter_api_key_2", ""),
                    raw.get("openrouter_api_key_3", ""),
                    raw.get("openrouter_api_key_4", ""),
                ],
                "opencode_zen": raw.get("opencode_zen_api_key", ""),
            }
        return self._api_keys_cache

    def __repr__(self):
        sections = ", ".join(self._data.keys())
        return f"<Config sections=[{sections}]>"
