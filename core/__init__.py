"""JARVIS MK-X Core — Central intelligence module.

The heavy submodules (intent router, governor, health checks, api_keys)
are imported lazily via module ``__getattr__``: merely importing the
``core`` package (e.g. ``from core import events``) used to pay a ~650ms
import cost through core/__init__ re-exports that nothing active consumed.
Accessing a name still works exactly as before; the import happens on
first use.
"""

from __future__ import annotations

import importlib

__all__ = ["Config", "setup_logging", "get_project_root", "get_api_key", "get_all_api_keys",
           "IntentRouter", "Intent", "run_all_checks", "format_health_report", "get_governor"]

_LAZY = {
    "Config": ("core.config", "Config"),
    "setup_logging": ("core.utils", "setup_logging"),
    "get_project_root": ("core.utils", "get_project_root"),
    "get_api_key": ("core.api_keys", "get_api_key"),
    "get_all_api_keys": ("core.api_keys", "get_all_api_keys"),
    "IntentRouter": ("core.intent_router", "IntentRouter"),
    "Intent": ("core.intent_router", "Intent"),
    "run_all_checks": ("core.health", "run_all_checks"),
    "format_health_report": ("core.health", "format_health_report"),
    "get_governor": ("core.resource_governor", "get_governor"),
}


def __getattr__(name):
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module 'core' has no attribute {name!r}")
    mod = importlib.import_module(target[0])
    return getattr(mod, target[1])


def __dir__():
    return sorted(set(globals()) | set(_LAZY))