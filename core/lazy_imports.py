"""Lazy Import Firewall — Deferred module loading for faster startup.

Usage:
    from core.lazy_imports import LazyModule
    tts_mod = LazyModule("pipeline.tts")
    # Module not imported until .load() or attribute access
    tts = tts_mod.TextToSpeech(config)
"""
import importlib
from typing import Any


class LazyModule:
    """Import a module only when its attributes are first accessed.

    Reduces startup time by deferring heavy imports (pipeline, providers,
    actions, web) until they are actually needed.
    """

    def __init__(self, module_name: str):
        self._name = module_name
        self._module: Any | None = None

    def load(self):
        """Force the import now. Returns the module object."""
        if self._module is None:
            self._module = importlib.import_module(self._name)
        return self._module

    @property
    def is_loaded(self) -> bool:
        return self._module is not None

    def __getattr__(self, attr: str):
        return getattr(self.load(), attr)

    def __repr__(self):
        loaded = "loaded" if self._module else "not loaded"
        return f"LazyModule({self._name!r}, {loaded})"


def lazy(module_name: str) -> LazyModule:
    """Shorthand for creating a LazyModule."""
    return LazyModule(module_name)
