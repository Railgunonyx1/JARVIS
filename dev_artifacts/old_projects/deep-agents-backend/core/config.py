"""TOML-based configuration loader for JARVIS MK-X.

Loads from config/*.toml files. Supports hot-reload via file watching.
Provides a single Config instance used across the entire system.
"""

import logging
import time
from pathlib import Path
from typing import Any, Optional

import toml

logger = logging.getLogger("jarvis.config")

SERVER_POLL_INTERVAL = 0.05
CALLBACK_WAIT = 0.1
LONG_CALLBACK_WAIT = 0.3

# API keys are cached briefly (30s) to avoid re-reading env/config files on
# every access, but the cache expires so new keys picked up without a restart.
_API_KEYS_TTL = 30.0

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_instance: Optional["Config"] = None
_instance_lock = __import__("threading").Lock()


class Config:
    """Central configuration store. Reads all .toml files from config/ directory."""

    def __init__(self, config_dir: Path | None = None):
        self._config_dir = config_dir or _CONFIG_DIR
        self._data: dict[str, dict[str, Any]] = {}
        self._listeners: list[callable] = []
        self._lock = __import__("threading").Lock()
        self.load_all()

    @classmethod
    def instance(cls) -> "Config":
        global _instance
        if _instance is None:
            with _instance_lock:
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
        """Get API keys from .env / api_keys.json / environment (cached with TTL)."""
        now = time.time()
        cached_at = getattr(self, "_api_keys_cached_at", 0.0)
        if (
            hasattr(self, "_api_keys_cache")
            and now - cached_at < _API_KEYS_TTL
        ):
            return self._api_keys_cache

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
            "mistral": raw.get("mistral_api_key", ""),
            "mistral_extra": [raw.get("mistral_api_key_2", "")],
            "nvidia_nim": raw.get("nvidia_nim_api_key", ""),
            "cerebras": raw.get("cerebras_api_key", ""),
            "deepseek": raw.get("deepseek_api_key", ""),
            "huggingface": raw.get("huggingface_api_key", ""),
        }
        self._api_keys_cached_at = now
        return self._api_keys_cache

    def reload_api_keys(self) -> dict[str, str]:
        """Force-refresh the API key cache on the next access."""
        if hasattr(self, "_api_keys_cache"):
            del self._api_keys_cache
        if hasattr(self, "_api_keys_cached_at"):
            del self._api_keys_cached_at
        return self.api_keys

    # ── Failure-analyzer recovery config ──────────────────────────────
    # Default mapping keyed by event name. Admins can override per-event via
    # config/failure_analyzer.toml (section [failure_analyzer]).
    FAILURE_RECOVERY_CONFIG: dict[str, str] = {
        "tool.executed": "retry",
        "action.executed": "retry",
        "llm.completed": "replan",
        "permission.checked": "abort",
        "llm.failed": "replan",
    }

    def get_failure_recovery(self, event_name: str, default: str = "replan") -> str:
        """Get recovery action for a failure event, with config override.

        Checks ``config/failure_analyzer.toml`` ``[failure_analyzer]`` section
        first; falls back to the built-in ``FAILURE_RECOVERY_CONFIG`` dict;
        finally returns *default*.
        """
        # Check for config override
        cfg_val = self.get("failure_analyzer", event_name, default=None)
        if cfg_val is not None:
            return cfg_val
        # Fall back to built-in mapping
        return self.FAILURE_RECOVERY_CONFIG.get(event_name, default)

    def __repr__(self):
        sections = ", ".join(self._data.keys())
        return f"<Config sections=[{sections}]>"


# ──────────────────────────────────────────────────────────────────────
# ModelCatalog — centralized model name catalog (single source of truth).
# ──────────────────────────────────────────────────────────────────────
class ModelCatalog:
    """Centralized model name catalog — single source of truth for all LLM model references.

    Use ``Config.ModelCatalog`` or ``from core.config import ModelCatalog`` to access.
    All model names live in one place so there's a single location to add/modify
    models without touching 10+ files.

    Example::

        from core.config import Config, ModelCatalog
        model = ModelCatalog.GEMINI_FLASH_LITE
        # or: model = Config.ModelCatalog.GEMINI_FLASH_LITE
    """

    # ── Gemini models (primary providers) ──────────────────────────────
    GEMINI_FLASH_LITE = "gemini-2.5-flash-lite"
    GEMINI_FLASH = "gemini-2.5-flash"
    GEMINI_FLASH_20 = "gemini-2.0-flash"
    GEMINI_1_5_FLASH = "gemini-1.5-flash"

    # ── Provider-specific models ───────────────────────────────────────
    GROQ_LLAMA3_1 = "llama-3.1-8b-instant"
    GROQ_MIXTRAL = "mixtral-8x7b-instant"

    # ── OpenRouter models ──────────────────────────────────────────────
    OPENROUTER_GEMINI = "google/gemini-2.5-flash"
    OPENROUTER_CLAUDE = "anthropic/claude-3.5-sonnet"
    OPENROUTER_MIXTRAL = "mistralai/mixtral-8x7b-instant"

    # ── Default mappings by tier ───────────────────────────────────────
    DEFAULT_BY_TIER = {
        "tiny": GROQ_LLAMA3_1,
        "small": GROQ_LLAMA3_1,
        "medium": OPENROUTER_GEMINI,
        "large": GEMINI_FLASH_LITE,
    }

    @classmethod
    def get_model(cls, tier: str, provider: str | None = None) -> str:
        """Get model name by tier and optional provider."""
        if provider and provider in cls.__dict__:
            val = getattr(cls, provider, None)
            if val:
                return val
        return cls.DEFAULT_BY_TIER.get(tier, cls.GEMINI_FLASH_LITE)

    @classmethod
    def get_model_for_purpose(cls, purpose: str) -> str:
        """Get model by intended use case."""
        purposes = {
            "planning": cls.GEMINI_FLASH_LITE,
            "execution": cls.GEMINI_FLASH,
            "streaming": cls.GEMINI_FLASH,
            "coding": cls.OPENROUTER_MIXTRAL,
            "analysis": cls.GEMINI_FLASH,
            "creative": cls.OPENROUTER_CLAUDE,
        }
        return purposes.get(purpose, cls.GEMINI_FLASH_LITE)
