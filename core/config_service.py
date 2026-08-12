"""Configuration Service — wraps Config with runtime updates, validation, profiles.

All services read config through this, never directly from config files.
Supports runtime changes with subscriber notification.
"""
import logging
from collections.abc import Callable
from typing import Any

from core.config import Config

logger = logging.getLogger("jarvis.config_service")


class ConfigService:
    """Centralized config with profiles, validation, and change notification."""

    def __init__(self, config: Config):
        self._config = config
        self._profile: str = "default"
        self._overrides: dict[str, Any] = {}
        self._listeners: list[Callable[[str, Any, Any], None]] = []

    def get(self, section: str, key: str, default: Any = None) -> Any:
        if section in self._overrides and key in self._overrides[section]:
            return self._overrides[section][key]
        return self._config.get(section, key, default)

    def set(self, section: str, key: str, value: Any):
        old = self.get(section, key)
        if section not in self._overrides:
            self._overrides[section] = {}
        self._overrides[section][key] = value
        for listener in self._listeners:
            try:
                listener(f"{section}.{key}", old, value)
            except Exception as e:
                logger.debug("Config listener error: %s", e)

    def get_section(self, section: str) -> dict[str, Any]:
        base = dict(getattr(self._config, "get_section", lambda s: {})(section))
        if section in self._overrides:
            base.update(self._overrides[section])
        return base

    @property
    def api_keys(self):
        return self._config.api_keys

    # ── Profiles ──────────────────────────────────────────────────

    def set_profile(self, name: str):
        self._profile = name
        logger.info("Config profile set to '%s'", name)

    def get_profile(self) -> str:
        return self._profile

    # ── Change listeners ──────────────────────────────────────────

    def on_change(self, listener: Callable[[str, Any, Any], None]):
        self._listeners.append(listener)

    # ── Feature flags ─────────────────────────────────────────────

    def feature_enabled(self, name: str) -> bool:
        return bool(self.get("features", name, False))

    # ── Save ──────────────────────────────────────────────────────

    def save(self, section: str):
        merged = self.get_section(section)
        self._config.save(section)

    def shutdown(self):
        self._listeners.clear()
        self._overrides.clear()
