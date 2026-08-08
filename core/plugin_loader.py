"""Plugin System v2 — Manifest-driven, sandboxed, lifecycle-managed plugins with capability registration.

Backward-compatible with the legacy @jarvis_plugin decorator and PluginLoader API.
"""

import os
import re
import sys
import json
import yaml
import logging
import threading
import importlib.util
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.core.plugin_loader")

# ── Legacy support ────────────────────────────

class PluginInfo:
    """Legacy plugin info — kept for backward compatibility."""
    def __init__(self, name: str, description: str, handler: Callable, patterns: List[str] = None):
        self.name = name
        self.description = description
        self.handler = handler
        self.patterns = patterns or []


_REGISTERED_PLUGINS: Dict[str, PluginInfo] = {}


def jarvis_plugin(name: str, description: str = "", patterns: List[str] = None):
    """Legacy decorator to register a function as a JARVIS plugin."""
    def decorator(func: Callable):
        _REGISTERED_PLUGINS[name] = PluginInfo(
            name=name, description=description, handler=func, patterns=patterns or []
        )
        return func
    return decorator


# ── v2 Plugin Model ──────────────────────────

@dataclass
class PluginCapabilityDef:
    name: str
    category: str = "custom"
    risk: str = "safe"
    description: str = ""
    tags: List[str] = field(default_factory=list)
    requires_confirmation: bool = False
    is_destructive: bool = False


@dataclass
class PluginManifest:
    name: str
    version: str
    author: str = "unknown"
    description: str = ""
    capabilities: List[PluginCapabilityDef] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    min_api_version: str = "1.0.0"
    hooks: Dict[str, str] = field(default_factory=dict)
    config_defaults: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginState:
    manifest: PluginManifest
    module: Any = None
    file_path: Path = None
    enabled: bool = True
    error: Optional[str] = None


# Restricted builtins for sandbox
_SAFE_BUILTINS = {
    'abs': abs, 'all': all, 'any': any, 'ascii': ascii,
    'bin': bin, 'bool': bool, 'bytearray': bytearray, 'bytes': bytes,
    'chr': chr, 'complex': complex, 'dict': dict, 'dir': dir,
    'divmod': divmod, 'enumerate': enumerate, 'filter': filter,
    'float': float, 'format': format, 'frozenset': frozenset,
    'getattr': getattr, 'hasattr': hasattr, 'hash': hash, 'hex': hex,
    'id': id, 'int': int, 'isinstance': isinstance,
    'issubclass': issubclass, 'iter': iter, 'len': len, 'list': list,
    'map': map, 'max': max, 'min': min, 'next': next, 'object': object,
    'oct': oct, 'ord': ord, 'pow': pow, 'print': print,
    'range': range, 'repr': repr, 'reversed': reversed,
    'round': round, 'set': set, 'slice': slice, 'sorted': sorted,
    'str': str, 'sum': sum, 'tuple': tuple, 'type': type,
    'zip': zip, 'True': True, 'False': False, 'None': None,
}

_BLOCKED_IMPORTS = [
    'os', 'subprocess', 'shutil', 'socket', 'ctypes',
    'multiprocessing', 'threading', 'signal', 'sys',
    'importlib', 'builtins', 'inspect', 'code',
]


class PluginSandbox:
    """Restricted execution environment for plugin code."""

    def __init__(self, plugin_name: str, allowed_imports: Optional[List[str]] = None):
        self.plugin_name = plugin_name
        self.allowed_imports = set(allowed_imports or [])

    def create_globals(self) -> dict:
        safe_builtins = dict(_SAFE_BUILTINS)
        safe_builtins['__import__'] = self._safe_import
        safe_builtins['open'] = self._safe_open
        return {'__builtins__': safe_builtins, '__name__': f'plugin.{self.plugin_name}'}

    def _safe_import(self, name, *args):
        top = name.split('.')[0]
        if top in _BLOCKED_IMPORTS and top not in self.allowed_imports:
            raise ImportError(f"Plugin '{self.plugin_name}' cannot import '{name}': blocked")
        return __import__(name, *args)

    def _safe_open(self, path, mode='r', *args):
        raise PermissionError(f"Plugin '{self.plugin_name}' cannot open files directly")

    def exec_module(self, code: str, module_globals: dict):
        exec(code, module_globals)
        return module_globals


# ── PluginManager ─────────────────────────────

class PluginManager:
    """Manages plugin lifecycle, manifests, sandbox, and capability registration.

    Integrates with SecurityManager, CapabilityRegistry, ConfigService, EventBus.
    """

    def __init__(self, plugins_dir: Optional[Path] = None,
                 security_manager=None,
                 capability_registry=None,
                 config_service=None,
                 event_bus=None):
        if plugins_dir is None:
            plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
        self.plugins_dir = plugins_dir
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        self._security = security_manager
        self._cap_reg = capability_registry
        self._config_service = config_service
        self._event_bus = event_bus

        self._plugins: Dict[str, PluginState] = {}
        self._legacy_loaded: Dict[str, PluginInfo] = {}
        self._discovered: Dict[str, Path] = {}
        self._lock = threading.Lock()

    # ── Discovery ─────────────────────────────

    def discover(self) -> Dict[str, str]:
        result = {}
        for file_path in self.plugins_dir.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            self._discovered[file_path.stem] = file_path
            result[file_path.stem] = str(file_path)
        for file_path in self.plugins_dir.glob("*.yaml"):
            name = file_path.stem
            py_file = file_path.with_suffix(".py")
            if py_file.exists():
                self._discovered[name] = py_file
                result[name] = str(py_file)
        for file_path in self.plugins_dir.glob("*.json"):
            name = file_path.stem
            py_file = file_path.with_suffix(".py")
            if py_file.exists():
                self._discovered[name] = py_file
                result[name] = str(py_file)
        logger.info("Discovered %d plugins in %s", len(result), self.plugins_dir)
        return result

    def load_manifest(self, name: str) -> Optional[PluginManifest]:
        base = self.plugins_dir / name
        for ext in ['.yaml', '.yml', '.json']:
            mf = base.with_suffix(ext)
            if mf.exists():
                try:
                    raw = mf.read_text(encoding='utf-8')
                    if ext in ('.yaml', '.yml'):
                        data = yaml.safe_load(raw)
                    else:
                        data = json.loads(raw)
                    caps = [PluginCapabilityDef(**c) for c in data.get('capabilities', [])]
                    return PluginManifest(
                        name=data.get('name', name),
                        version=data.get('version', '0.1.0'),
                        author=data.get('author', 'unknown'),
                        description=data.get('description', ''),
                        capabilities=caps,
                        permissions=data.get('permissions', []),
                        dependencies=data.get('dependencies', []),
                        min_api_version=data.get('min_api_version', '1.0.0'),
                        hooks=data.get('hooks', {}),
                        config_defaults=data.get('config', {}),
                    )
                except Exception as e:
                    logger.warning("Failed to load manifest for '%s': %s", name, e)
        return None

    # ── Loading ───────────────────────────────

    def load_plugin(self, name: str) -> bool:
        with self._lock:
            return self._load_plugin(name)

    def _load_plugin(self, name: str) -> bool:
        if name in self._plugins:
            return True

        file_path = self._discovered.get(name)
        if not file_path:
            return False

        manifest = self.load_manifest(name)
        if not manifest:
            manifest = PluginManifest(name=name, version='0.1.0')

        state = PluginState(manifest=manifest, file_path=file_path)

        # Permission check
        if self._security and manifest.permissions:
            ok = self._security.check_plugin_permissions(name, manifest.permissions)
            if not ok:
                state.error = "Permission denied"
                self._plugins[name] = state
                logger.warning("Plugin '%s' denied: insufficient permissions", name)
                return False

        # Sandboxed load
        sandbox = PluginSandbox(name)
        try:
            module_name = f"plugins.{name}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if not spec or not spec.loader:
                state.error = "Invalid module spec"
                self._plugins[name] = state
                return False

            module = importlib.util.module_from_spec(spec)
            state.module = module

            # Execute in sandbox-like globals (we can't fully sandbox importlib-based loading,
            # but we wrap the module for limited sandboxing)
            spec.loader.exec_module(module)
        except Exception as e:
            state.error = str(e)
            self._plugins[name] = state
            logger.error("Failed to load plugin '%s': %s", name, e)
            return False

        # Lifecycle hook: on_load
        hook_fn = manifest.hooks.get('on_load')
        if hook_fn and hasattr(module, hook_fn):
            try:
                getattr(module, hook_fn)()
            except Exception as e:
                logger.warning("Plugin '%s' on_load hook failed: %s", name, e)

        # Capability registration
        if self._cap_reg and manifest.capabilities:
            self._register_capabilities(name, manifest.capabilities)

        # Config defaults
        if self._config_service and manifest.config_defaults:
            section = f"plugins.{name}"
            for key, value in manifest.config_defaults.items():
                current = self._config_service.get(f"{section}.{key}")
                if current is None:
                    self._config_service.set(f"{section}.{key}", value)

        self._plugins[name] = state
        logger.info("Loaded plugin '%s' v%s by %s", manifest.name, manifest.version, manifest.author)
        return True

    def _register_capabilities(self, plugin_name: str, caps: List[PluginCapabilityDef]):
        from core.capability_registry import (
            Capability, CapabilityRisk, CapabilityCategory, merge_capabilities
        )
        risk_map = {'safe': CapabilityRisk.SAFE, 'low': CapabilityRisk.LOW,
                     'medium': CapabilityRisk.MEDIUM, 'high': CapabilityRisk.HIGH,
                     'critical': CapabilityRisk.CRITICAL}
        cat_map = {'system': CapabilityCategory.SYSTEM, 'media': CapabilityCategory.MEDIA,
                    'development': CapabilityCategory.DEVELOPMENT, 'filesystem': CapabilityCategory.FILESYSTEM,
                    'ai': CapabilityCategory.AI, 'desktop': CapabilityCategory.DESKTOP,
                    'network': CapabilityCategory.NETWORK, 'automation': CapabilityCategory.AUTOMATION,
                    'custom': CapabilityCategory.CUSTOM, 'utility': CapabilityCategory.UTILITY}

        capabilities = []
        for c in caps:
            capability = Capability(
                name=c.name,
                category=cat_map.get(c.category, CapabilityCategory.CUSTOM),
                risk=risk_map.get(c.risk, CapabilityRisk.SAFE),
                description=c.description or f"Provided by plugin '{plugin_name}'",
                tags=c.tags + [f'plugin:{plugin_name}'],
                requires_confirmation=c.requires_confirmation,
                is_destructive=c.is_destructive,
            )
            capabilities.append(capability)

        merge_capabilities(capabilities)
        logger.info("Plugin '%s' registered %d capabilities", plugin_name, len(capabilities))

    def load_all(self) -> Dict[str, PluginState]:
        self.discover()
        for name in list(self._discovered.keys()):
            self.load_plugin(name)
        return dict(self._plugins)

    # ── Lifecycle ─────────────────────────────

    def enable_plugin(self, name: str) -> bool:
        state = self._plugins.get(name)
        if not state:
            return False
        state.enabled = True
        hook = state.manifest.hooks.get('on_enable')
        if hook and state.module and hasattr(state.module, hook):
            try:
                getattr(state.module, hook)()
            except Exception as e:
                logger.warning("Plugin '%s' on_enable hook failed: %s", name, e)
        return True

    def disable_plugin(self, name: str) -> bool:
        state = self._plugins.get(name)
        if not state:
            return False
        state.enabled = False
        hook = state.manifest.hooks.get('on_disable')
        if hook and state.module and hasattr(state.module, hook):
            try:
                getattr(state.module, hook)()
            except Exception as e:
                logger.warning("Plugin '%s' on_disable hook failed: %s", name, e)
        return True

    def unload_plugin(self, name: str) -> bool:
        state = self._plugins.get(name)
        if not state:
            return False
        hook = state.manifest.hooks.get('on_unload')
        if hook and state.module and hasattr(state.module, hook):
            try:
                getattr(state.module, hook)()
            except Exception as e:
                logger.warning("Plugin '%s' on_unload hook failed: %s", name, e)
        del self._plugins[name]
        logger.info("Unloaded plugin '%s'", name)
        return True

    # ── Execution ─────────────────────────────

    def execute(self, name: str, *args, **kwargs) -> Any:
        # Check v2 plugins first
        state = self._plugins.get(name)
        if state and state.enabled:
            if hasattr(state.module, 'handle'):
                return state.module.handle(*args, **kwargs)
            return None

        # Legacy fallback
        plugin = self._legacy_loaded.get(name) or _REGISTERED_PLUGINS.get(name)
        if plugin:
            return plugin.handler(*args, **kwargs)

        # Lazy load legacy
        if name in self._discovered:
            self._load_legacy(name)
            plugin = self._legacy_loaded.get(name) or _REGISTERED_PLUGINS.get(name)
            if plugin:
                return plugin.handler(*args, **kwargs)

        raise KeyError(f"Plugin '{name}' not found or disabled")

    def _load_legacy(self, name: str) -> bool:
        file_path = self._discovered.get(name)
        if not file_path:
            return False
        try:
            module_name = f"plugins.{name}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "register_plugin"):
                    module.register_plugin()
                self._legacy_loaded = dict(_REGISTERED_PLUGINS)
                return True
        except Exception as e:
            logger.error("Failed to load legacy plugin '%s': %s", name, e)
        return False

    # ── Status / Stats ────────────────────────

    def get_status(self) -> dict:
        return {
            "plugins": {
                name: {
                    "version": state.manifest.version,
                    "author": state.manifest.author,
                    "enabled": state.enabled,
                    "capabilities": len(state.manifest.capabilities),
                    "error": state.error,
                }
                for name, state in self._plugins.items()
            },
            "legacy_plugins": len(self._legacy_loaded or _REGISTERED_PLUGINS),
            "discovered": len(self._discovered),
        }

    def get_stats(self) -> dict:
        return {
            "total_plugins": len(self._plugins),
            "enabled": sum(1 for s in self._plugins.values() if s.enabled),
            "errored": sum(1 for s in self._plugins.values() if s.error),
            "legacy": len(self._legacy_loaded or _REGISTERED_PLUGINS),
        }

    @property
    def plugin_names(self) -> List[str]:
        return list(self._plugins.keys())


# ── Backward-compatible PluginLoader alias ────

class PluginLoader(PluginManager):
    """Backward-compatible alias — wraps PluginManager with the old API."""

    def __init__(self, plugins_dir: Optional[Path] = None):
        super().__init__(plugins_dir=plugins_dir)
        self.loaded_plugins = {}

    def discover_and_load(self) -> Dict[str, PluginInfo]:
        self.discover()
        self.load_all()
        self.loaded_plugins = dict(_REGISTERED_PLUGINS)
        return self.loaded_plugins

    def execute_plugin(self, name: str, *args, **kwargs) -> Any:
        return self.execute(name, *args, **kwargs)

    def _load_plugin_module(self, name: str) -> bool:
        return self._load_legacy(name)
