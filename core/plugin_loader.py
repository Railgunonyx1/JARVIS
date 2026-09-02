"""JARVIS MK-X — Plugin loader.

Auto-discovers plugins dropped into the ``plugins/`` tree and exposes them
through a small registry. Two integration points are supported:

* ``@jarvis_plugin(...)`` — decorator that registers a callable. The original
  callable is returned unchanged so plugin authors can keep calling it
  directly.
* ``PluginLoader().discover_and_load()`` — scans the plugins tree, imports
  every module containing a decorated plugin, and returns
  ``{plugin_name: registration}``.

This mirrors the Cordis "everything is a plugin" philosophy from the daemon
architecture (AGENTS.md Architecture Contract).
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core.utils import get_project_root

logger = logging.getLogger("jarvis.plugin_loader")

# Dotted plugin names that are packages, not plugins to load directly.
_SKIP = {"__init__", "__pycache__"}


@dataclass
class PluginRegistration:
    """Metadata + callable for one discovered plugin."""

    name: str
    fn: Callable[..., Any]
    description: str = ""
    patterns: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


# Global registry so any number of plugin modules can decorate without
# needing a shared loader instance in scope.
_REGISTRY: dict[str, PluginRegistration] = {}


def jarvis_plugin(
    name: str,
    description: str = "",
    patterns: list[str] | None = None,
    **meta: Any,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register ``fn`` as a JARVIS plugin and return it unchanged."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _REGISTRY[name] = PluginRegistration(
            name=name,
            fn=fn,
            description=description,
            patterns=patterns or [],
            meta=meta,
        )
        return fn

    return decorator


def get_plugin(name: str) -> PluginRegistration | None:
    return _REGISTRY.get(name)


def list_plugins() -> dict[str, PluginRegistration]:
    return dict(_REGISTRY)


class PluginLoader:
    """Discovers and loads ``@jarvis_plugin``-decorated callables.

    Scans ``<project_root>/plugins`` recursively for Python modules, imports
    them (so their top-level decorators run and populate the registry), and
    returns the current registry snapshot keyed by plugin name.
    """

    def __init__(self, plugins_dir: str | Path | None = None) -> None:
        self.plugins_dir: Path = (
            Path(plugins_dir)
            if plugins_dir is not None
            else get_project_root() / "plugins"
        )

    def _module_files(self) -> list[Path]:
        if not self.plugins_dir.is_dir():
            return []
        return [
            p
            for p in self.plugins_dir.rglob("*.py")
            if p.name not in _SKIP and "__pycache__" not in p.parts
        ]

    def discover_and_load(self) -> dict[str, PluginRegistration]:
        loaded: dict[str, PluginRegistration] = {}
        for path in self._module_files():
            try:
                self._import_module(path)
            except Exception as e:  # noqa: BLE001 - one bad plugin must not block the rest
                logger.warning("Failed to load plugin module %s: %s", path, e)
        # Snapshot after importing so both freshly decorated and previously
        # registered plugins are surfaced.
        for name, reg in _REGISTRY.items():
            loaded[name] = reg
        return loaded

    @staticmethod
    def _import_module(path: Path) -> None:
        module_name = "jarvis_plugin_" + path.stem.replace("-", "_")
        if module_name in sys.modules:
            return
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        # Per-plugin convention: if a module exposes register_plugin(),
        # invoke it once after import so it can log or wire up state.
        register = getattr(module, "register_plugin", None)
        if callable(register):
            register()


__all__ = [
    "PluginLoader",
    "PluginRegistration",
    "get_plugin",
    "jarvis_plugin",
    "list_plugins",
]
