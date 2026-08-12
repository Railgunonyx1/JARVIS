"""JARVIS MK-X Hyper-Optimization Engine — Phased startup optimizer."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("jarvis.hyper_opt.startup_optimizer")

PHASE_ORDER = ("critical", "essential", "background", "on_demand")


class StartupPhaseOptimizer:
    """Manages module initialization in phases for fastest interactive startup."""

    def __init__(self) -> None:
        self._modules: dict[str, dict[str, Any]] = {}
        self._phases: dict[str, list[str]] = {
            "critical": [],
            "essential": [],
            "background": [],
            "on_demand": [],
        }
        self._lock = threading.RLock()
        self._startup_start: float = 0.0
        self._total_startup_ms: float = 0.0
        self._phase_times: dict[str, float] = {
            "critical": 0.0,
            "essential": 0.0,
            "background": 0.0,
            "on_demand": 0.0,
        }
        self._background_thread: threading.Thread | None = None

    def register(
        self,
        name: str,
        init_fn: Callable[[], Any],
        phase: str = "essential",
        priority: int = 50,
        dependencies: list[str] | None = None,
    ) -> None:
        """Register a module for phased startup."""
        if phase not in self._phases:
            logger.warning(
                "Invalid phase '%s' for module '%s' — defaulting to 'essential'",
                phase,
                name,
            )
            phase = "essential"
        with self._lock:
            if name in self._modules:
                logger.warning(
                    "Module '%s' already registered — updating phase to '%s'",
                    name,
                    phase,
                )
                old_phase = self._modules[name]["phase"]
                if name in self._phases.get(old_phase, []):
                    self._phases[old_phase].remove(name)
            else:
                self._phases[phase].append(name)
            self._modules[name] = {
                "init_fn": init_fn,
                "phase": phase,
                "priority": priority,
                "dependencies": dependencies or [],
                "init_time_ms": 0.0,
                "loaded": False,
                "error": None,
                "load_order": len(self._modules),
            }
            for phase_list in self._phases.values():
                phase_list.sort(
                    key=lambda n: self._modules[n]["priority"],
                )
            logger.debug(
                "Registered module '%s' (phase=%s, priority=%d, deps=%s)",
                name,
                phase,
                priority,
                dependencies or [],
            )

    def _resolve_dependencies(self, names: list[str]) -> list[str]:
        """Return names sorted so dependencies come first."""
        resolved: list[str] = []
        visited: set[str] = set()
        visiting: set[str] = set()

        def _visit(n: str) -> None:
            if n in visited:
                return
            if n in visiting:
                logger.warning(
                    "Circular dependency detected involving '%s'", n
                )
                return
            visiting.add(n)
            mod = self._modules.get(n)
            if mod is not None:
                for dep in mod["dependencies"]:
                    if dep in self._modules:
                        _visit(dep)
            visiting.discard(n)
            visited.add(n)
            if n in names:
                resolved.append(n)

        for n in names:
            _visit(n)
        return resolved

    def _load_modules(self, names: list[str]) -> float:
        """Load a list of modules in dependency order. Returns total time_ms."""
        ordered = self._resolve_dependencies(names)
        total_ms = 0.0
        for name in ordered:
            mod = self._modules.get(name)
            if mod is None or mod["loaded"]:
                continue
            for dep in mod["dependencies"]:
                dep_mod = self._modules.get(dep)
                if dep_mod is not None and not dep_mod["loaded"]:
                    logger.warning(
                        "Module '%s' dependency '%s' not loaded yet",
                        name,
                        dep,
                    )
            start = time.perf_counter()
            try:
                mod["init_fn"]()
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                mod["init_time_ms"] = elapsed_ms
                mod["loaded"] = True
                total_ms += elapsed_ms
                logger.info(
                    "Loaded module '%s' in %.2f ms (phase=%s)",
                    name,
                    elapsed_ms,
                    mod["phase"],
                )
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                mod["init_time_ms"] = elapsed_ms
                mod["error"] = str(exc)
                total_ms += elapsed_ms
                logger.error(
                    "Failed to load module '%s' after %.2f ms: %s",
                    name,
                    elapsed_ms,
                    exc,
                )
        return total_ms

    def start_critical(self) -> float:
        """Load all critical-phase modules synchronously. Returns total time_ms."""
        with self._lock:
            if self._startup_start == 0.0:
                self._startup_start = time.perf_counter()
            names = list(self._phases["critical"])
        start = time.perf_counter()
        elapsed_ms = self._load_modules(names)
        with self._lock:
            self._phase_times["critical"] = elapsed_ms
        logger.info(
            "Critical phase complete: %d modules in %.2f ms",
            len(names),
            elapsed_ms,
        )
        return elapsed_ms

    def start_essential(self, background: bool = True) -> float:
        """Load essential modules, optionally in a background thread."""
        with self._lock:
            names = list(self._phases["essential"])
            if not background:
                start = time.perf_counter()
                elapsed_ms = self._load_modules(names)
                with self._lock:
                    self._phase_times["essential"] = elapsed_ms
                logger.info(
                    "Essential phase complete (sync): %d modules in %.2f ms",
                    len(names),
                    elapsed_ms,
                )
                return elapsed_ms

        def _bg_load() -> None:
            start = time.perf_counter()
            elapsed_ms = self._load_modules(names)
            with self._lock:
                self._phase_times["essential"] = elapsed_ms
            logger.info(
                "Essential phase complete (async): %d modules in %.2f ms",
                len(names),
                elapsed_ms,
            )

        t = threading.Thread(target=_bg_load, name="startup-essential", daemon=True)
        self._background_thread = t
        t.start()
        logger.info("Essential phase started in background thread (%d modules)", len(names))
        return 0.0

    def start_background(self) -> float:
        """Load background modules when CPU is idle (background thread)."""
        with self._lock:
            names = list(self._phases["background"])

        def _bg_load() -> None:
            start = time.perf_counter()
            elapsed_ms = self._load_modules(names)
            with self._lock:
                self._phase_times["background"] = elapsed_ms
            logger.info(
                "Background phase complete: %d modules in %.2f ms",
                len(names),
                elapsed_ms,
            )

        t = threading.Thread(target=_bg_load, name="startup-background", daemon=True)
        t.start()
        logger.info("Background phase started (%d modules)", len(names))
        return 0.0

    def load_on_demand(self, name: str) -> float:
        """Load a specific on-demand module now. Returns init time_ms."""
        with self._lock:
            mod = self._modules.get(name)
            if mod is None:
                logger.warning("Module '%s' not registered", name)
                return 0.0
            if mod["loaded"]:
                logger.debug("Module '%s' already loaded", name)
                return mod["init_time_ms"]
        start = time.perf_counter()
        self._load_modules([name])
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        with self._lock:
            mod = self._modules.get(name)
            if mod is not None:
                self._phase_times["on_demand"] += mod["init_time_ms"]
        return elapsed_ms

    def get_status(self) -> dict[str, Any]:
        """Returns per-module loaded/init_time/phase and overall startup_ms."""
        with self._lock:
            modules: dict[str, dict[str, Any]] = {}
            for name, mod in self._modules.items():
                modules[name] = {
                    "loaded": mod["loaded"],
                    "init_time_ms": round(mod["init_time_ms"], 3),
                    "phase": mod["phase"],
                    "priority": mod["priority"],
                    "error": mod["error"],
                }
            total_ms = sum(self._phase_times.values())
            uptime = (
                (time.perf_counter() - self._startup_start) * 1000.0
                if self._startup_start > 0
                else 0.0
            )
            return {
                "modules": modules,
                "startup_ms": round(total_ms, 3),
                "uptime_ms": round(uptime, 3),
                "total_registered": len(self._modules),
                "total_loaded": sum(1 for m in self._modules.values() if m["loaded"]),
                "total_errors": sum(
                    1 for m in self._modules.values() if m["error"] is not None
                ),
            }

    def get_module_count(self) -> dict[str, Any]:
        """Returns count by phase and total loaded."""
        with self._lock:
            counts: dict[str, int] = {}
            for phase in PHASE_ORDER:
                counts[phase] = len(self._phases[phase])
            counts["total_registered"] = len(self._modules)
            counts["total_loaded"] = sum(
                1 for m in self._modules.values() if m["loaded"]
            )
            return counts

    def suggest_phases(self) -> list[dict[str, Any]]:
        """Analyze modules and suggest optimal phase assignments."""
        with self._lock:
            suggestions: list[dict[str, Any]] = []
            for name, mod in self._modules.items():
                current = mod["phase"]
                suggested = current
                reasons: list[str] = []
                if mod["loaded"] and mod["init_time_ms"] > 500:
                    if current == "critical":
                        suggested = "essential"
                        reasons.append("Init time > 500ms — too slow for critical")
                if mod["dependencies"]:
                    dep_errors = sum(
                        1
                        for d in mod["dependencies"]
                        if d in self._modules and self._modules[d]["error"]
                    )
                    if dep_errors > 0:
                        suggested = "on_demand"
                        reasons.append("Has dependencies with errors")
                if mod["error"] and mod["load_order"] < 5:
                    reasons.append("Failed during early startup — consider deferring")
                if not reasons:
                    reasons.append("Current phase appears optimal")
                suggestions.append(
                    {
                        "module": name,
                        "current_phase": current,
                        "suggested_phase": suggested,
                        "priority": mod["priority"],
                        "init_time_ms": round(mod["init_time_ms"], 3),
                        "loaded": mod["loaded"],
                        "reasons": reasons,
                    }
                )
            suggestions.sort(key=lambda s: s["priority"])
            return suggestions

    def get_startup_time(self) -> dict[str, Any]:
        """Returns per-phase timing and total startup_ms."""
        with self._lock:
            total = sum(self._phase_times.values())
            return {
                "critical_ms": round(self._phase_times["critical"], 3),
                "essential_ms": round(self._phase_times["essential"], 3),
                "background_ms": round(self._phase_times["background"], 3),
                "on_demand_ms": round(self._phase_times["on_demand"], 3),
                "total_ms": round(total, 3),
                "modules_by_phase": {
                    p: len(self._phases[p]) for p in PHASE_ORDER
                },
            }

    def wait_for_background(self, timeout_s: float = 30.0) -> bool:
        """Block until background thread finishes. Returns True if finished."""
        t = self._background_thread
        if t is None or not t.is_alive():
            return True
        t.join(timeout=timeout_s)
        return not t.is_alive()


_instance: StartupPhaseOptimizer | None = None
_instance_lock = threading.RLock()


def get_startup_phase_optimizer() -> StartupPhaseOptimizer:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = StartupPhaseOptimizer()
            logger.info("Created StartupPhaseOptimizer singleton")
        return _instance
