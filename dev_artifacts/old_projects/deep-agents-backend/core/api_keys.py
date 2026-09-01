"""
Central API Key Loader — reads from .env and api_keys.json.
Priority: environment variable > .env file > api_keys.json
"""

import json
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger("jarvis.api_keys")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
API_KEYS_JSON = CONFIG_DIR / "api_keys.json"
DOT_ENV = CONFIG_DIR / ".env"

_merged_keys: dict | None = None
_keys_lock = threading.Lock()

ENV_TO_KEY = {
    "GEMINI_API_KEY": "gemini_api_key",
    "GEMINI_API_KEY_2": "gemini_api_key_2",
    "OPENAI_API_KEY": "openai_api_key",
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "MISTRAL_API_KEY": "mistral_api_key",
    "MISTRAL_API_KEY_2": "mistral_api_key_2",
    "NVIDIA_NIM_API_KEY": "nvidia_nim_api_key",
    "OPENROUTER_API_KEY": "openrouter_api_key",
    "OPENROUTER_API_KEY_2": "openrouter_api_key_2",
    "OPENROUTER_API_KEY_3": "openrouter_api_key_3",
    "OPENROUTER_API_KEY_4": "openrouter_api_key_4",
    "ELEVENLABS_API_KEY": "elevenlabs_api_key",
    "PORCUPINE_ACCESS_KEY": "porcupine_access_key",
    "GROQ_API_KEY": "groq_api_key",
    "GROQ_API_KEY_2": "groq_api_key_2",
    "OPENCODE_ZEN_API_KEY": "opencode_zen_api_key",
    "OMNIROUTE_API_KEY": "omni_route_api_key",
    "WORLDMONITOR_API_KEY": "worldmonitor_api_key",
    "CEREBRAS_API_KEY": "cerebras_api_key",
    "DEEPSEEK_API_KEY": "deepseek_api_key",
    "HF_API_KEY": "huggingface_api_key",
    "HUGGINGFACE_API_KEY": "huggingface_api_key",
}


def _load_dotenv() -> dict:
    if not DOT_ENV.exists():
        return {}
    env = {}
    try:
        for raw_line in DOT_ENV.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip("\"'")
    except Exception as e:
        logger.warning("Failed to parse .env: %s", e)
    return env


def _load_all() -> dict:
    merged = {}

    if API_KEYS_JSON.exists():
        try:
            merged.update(json.loads(API_KEYS_JSON.read_text(encoding="utf-8")))
        except Exception as e:
            logger.warning("Failed to load api_keys.json: %s", e)

    dotenv = _load_dotenv()
    for env_key, config_key in ENV_TO_KEY.items():
        if env_key in dotenv:
            merged[config_key] = dotenv[env_key]

    for env_key, config_key in ENV_TO_KEY.items():
        val = os.environ.get(env_key)
        if val:
            merged[config_key] = val

    return merged


def get_api_key(key_name: str) -> str | None:
    global _merged_keys
    if _merged_keys is None:
        with _keys_lock:
            if _merged_keys is None:
                _merged_keys = _load_all()
    return _merged_keys.get(key_name)


def get_all_api_keys() -> dict:
    global _merged_keys
    if _merged_keys is None:
        with _keys_lock:
            if _merged_keys is None:
                _merged_keys = _load_all()
    return dict(_merged_keys)


def reload_api_keys() -> dict:
    global _merged_keys
    with _keys_lock:
        _merged_keys = _load_all()
    return dict(_merged_keys)
