"""Startup Optimizer — dependency-ordered lazy module initialization."""

import time
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("jarvis.performance_engine.startup")


class _LazyProxy:
    """Proxy object that initializes the target module on first attribute access."""

    def __init__(self, optimizer: "StartupOptimizer", name: str) -> None:
        object.__setattr__(self, "_optimizer", optimizer)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_resolved", None)

    def _resolve(self) -> Any:
        resolved = object.__getattribute__(self, "_resolved")
        if resolved is None:
            optimizer = object.__getattribute__(self, "_optimizer")
            name = object.__getattribute__(self, "_name")
            resolved = optimizer._init_module(name)
            object.__setattr__(self, "_resolved", resolved)
        return resolved

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._resolve(), attr)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._resolve()(*args, **kwargs)

    def __repr__(self) -> str:
        resolved = object.__getattribute__(self, "_resolved")
        name = object.__getattribute__(self, "_name")
        if resolved is not None:
            return repr(resolved)
        return f"<LazyProxy for {name!r} (not yet initialized)>"


class StartupOptimizer:
    """Manages module initialization order based on declared dependencies and priority."""

    def __init__(self) -> None:
        self._modules: Dict[str, Dict[str, Any]] = {}
        self._initialized: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._total_startup_time_ms: float = 0.0

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_module(
        self,
        name: str,
        init_fn: Callable[[], Any],
        priority: int = 50,
        dependencies: Optional[List[str]] = None,
    ) -> None:
        """Register a module for deferred startup.

        Args:
            name: Unique module identifier.
            init_fn: Callable that returns the initialized module object.
            priority: Lower values are initialized first (default 50).
            dependencies: Names of modules that must be initialized before this one.
        """
        with self._lock:
            self._modules[name] = {
                "init_fn": init_fn,
                "priority": priority,
                "dependencies": dependencies or [],
                "status": "pending",
                "init_time_ms": 0.0,
                "result": None,
            }
        logger.debug("Registered module '%s' (priority=%d, deps=%s)", name, priority, dependencies)

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def startup(self) -> float:
        """Initialize all registered modules in dependency order.

        Returns total startup time in milliseconds.
        """
        start = time.perf_counter()
        order = self._resolve_order()
        logger.info("Startup order: %s", order)

        for name in order:
            self._init_module(name)

        self._total_startup_time_ms = (time.perf_counter() - start) * 1000.0
        logger.info("All modules initialized in %.1f ms", self._total_startup_time_ms)
        return self._total_startup_time_ms

    def _init_module(self, name: str) -> Any:
        """Initialize a single module if not already done."""
        with self._lock:
            entry = self._modules.get(name)
            if entry is None:
                raise KeyError(f"Module '{name}' is not registered")
            if entry["status"] == "initialized":
                return entry["result"]

        # Initialize outside the lock so init_fn can register further modules.
        entry = self._modules[name]
        for dep in entry["dependencies"]:
            if dep not in self._initialized:
                self._init_module(dep)

        mod_start = time.perf_counter()
        try:
            result = entry["init_fn"]()
        except Exception:
            logger.exception("Failed to initialize module '%s'", name)
            with self._lock:
                entry["status"] = "failed"
            raise
        elapsed_ms = (time.perf_counter() - mod_start) * 1000.0

        with self._lock:
            entry["status"] = "initialized"
            entry["init_time_ms"] = elapsed_ms
            entry["result"] = result
            self._initialized[name] = result

        logger.info("Module '%s' initialized in %.1f ms", name, elapsed_ms)
        return result

    # ------------------------------------------------------------------
    # Dependency resolution (topological sort)
    # ------------------------------------------------------------------

    def _resolve_order(self) -> List[str]:
        """Return module names in a valid initialization order (topological sort)."""
        with self._lock:
            modules = dict(self._modules)

        visited: Set[str] = set()
        order: List[str] = []

        def dfs(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            entry = modules.get(name)
            if entry is None:
                return
            for dep in entry["dependencies"]:
                dfs(dep)
            order.append(name)

        # Sort by priority first for deterministic output among independent modules.
        for name in sorted(modules, key=lambda n: modules[n]["priority"]):
            dfs(name)

        return order

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------

    def get_module_status(self) -> Dict[str, Dict[str, Any]]:
        """Return initialization status for every registered module."""
        with self._lock:
            return {
                name: {
                    "status": entry["status"],
                    "init_time_ms": round(entry["init_time_ms"], 2),
                    "priority": entry["priority"],
                    "dependencies": entry["dependencies"],
                }
                for name, entry in self._modules.items()
            }

    def get_total_startup_time_ms(self) -> float:
        return self._total_startup_time_ms

    def get_initialized(self, name: str) -> Any:
        """Return the initialized module object for *name* (raises if not yet initialized)."""
        with self._lock:
            entry = self._modules.get(name)
            if entry is None:
                raise KeyError(f"Module '{name}' is not registered")
            if entry["status"] != "initialized":
                raise RuntimeError(f"Module '{name}' has not been initialized yet")
            return entry["result"]

    def lazy_load(self, name: str) -> _LazyProxy:
        """Return a proxy that initializes *name* on first attribute access."""
        if name not in self._modules:
            raise KeyError(f"Module '{name}' is not registered")
        return _LazyProxy(self, name)

    def reset(self) -> None:
        """Clear all registrations and initialized state."""
        with self._lock:
            self._modules.clear()
            self._initialized.clear()
            self._total_startup_time_ms = 0.0
        logger.info("StartupOptimizer reset")


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_startup_optimizer: Optional[StartupOptimizer] = None
_startup_lock = threading.Lock()


def get_startup_optimizer() -> StartupOptimizer:
    global _startup_optimizer
    if _startup_optimizer is None:
        with _startup_lock:
            if _startup_optimizer is None:
                _startup_optimizer = StartupOptimizer()
    return _startup_optimizer
