"""Graceful Degradation — degrades service tiers based on system health."""

from __future__ import annotations

import time
import logging
import threading
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("jarvis.reliability.graceful_degradation")

try:
    import psutil
    _psutil_ok = True
except ImportError:
    _psutil_ok = False

DEGRADATION_FULL = 0
DEGRADATION_REDUCED = 1
DEGRADATION_MINIMAL = 2
DEGRADATION_EMERGENCY = 3

_ESSENTIAL_MIN_PRIORITY = 8
_CORE_MIN_PRIORITY = 6


class GracefulDegradation:
    """Executes services with automatic fallback based on degradation level."""

    def __init__(self) -> None:
        self._services: Dict[str, dict] = {}
        self._stats: Dict[str, dict] = {}
        self._level: int = DEGRADATION_FULL
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_service(
        self,
        name: str,
        primary_fn: Callable[..., Any],
        fallback_fn: Optional[Callable[..., Any]] = None,
        priority: int = 5,
    ) -> None:
        """Register a service with an optional fallback.

        Higher *priority* values indicate more essential services.
        """
        with self._lock:
            self._services[name] = {
                "primary_fn": primary_fn,
                "fallback_fn": fallback_fn,
                "priority": priority,
            }
            self._stats[name] = {
                "fallback_count": 0,
                "last_error": None,
                "last_success": 0.0,
                "last_fallback": 0.0,
            }
        logger.info(
            "Service '%s' registered (priority=%d, fallback=%s)",
            name,
            priority,
            "yes" if fallback_fn else "no",
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a service's primary function, falling back on failure."""
        with self._lock:
            if name not in self._services:
                raise KeyError(f"Service '{name}' is not registered")
            svc = self._services[name]
            stats = self._stats[name]

        if self.should_degrade(name):
            if svc["fallback_fn"] is not None:
                logger.debug("Service '%s' degraded, using fallback", name)
                return self._execute_fallback(name, svc, stats, args, kwargs)
            logger.warning("Service '%s' degraded with no fallback", name)
            raise RuntimeError(f"Service '{name}' is degraded and has no fallback")

        try:
            result = svc["primary_fn"](*args, **kwargs)
        except Exception as exc:
            logger.warning("Primary function failed for '%s': %s", name, exc)
            with self._lock:
                stats["last_error"] = str(exc)
            if svc["fallback_fn"] is not None:
                return self._execute_fallback(name, svc, stats, args, kwargs)
            raise

        with self._lock:
            stats["last_success"] = time.perf_counter()
        return result

    def _execute_fallback(
        self,
        name: str,
        svc: dict,
        stats: dict,
        args: tuple,
        kwargs: dict,
    ) -> Any:
        """Execute the fallback and update stats."""
        if svc["fallback_fn"] is None:
            raise RuntimeError(f"Service '{name}' has no fallback configured")
        result = svc["fallback_fn"](*args, **kwargs)
        with self._lock:
            stats["fallback_count"] += 1
            stats["last_fallback"] = time.perf_counter()
        logger.info("Fallback succeeded for '%s'", name)
        return result

    # ------------------------------------------------------------------
    # Degradation level
    # ------------------------------------------------------------------

    def get_degradation_level(self) -> int:
        """Return the current degradation level (0-3)."""
        self._auto_detect_level()
        return self._level

    def set_degradation_level(self, level: int) -> None:
        """Manually set the degradation level."""
        if not 0 <= level <= 3:
            raise ValueError("Level must be 0-3")
        old = self._level
        self._level = level
        if old != level:
            logger.warning("Degradation level changed: %d -> %d", old, level)

    def should_degrade(self, service_name: str) -> bool:
        """Return True if *service_name* should be skipped at the current level."""
        with self._lock:
            if service_name not in self._services:
                return False
            priority = self._services[service_name]["priority"]

        level = self.get_degradation_level()
        if level == DEGRADATION_FULL:
            return False
        if level == DEGRADATION_REDUCED:
            return priority < _ESSENTIAL_MIN_PRIORITY
        if level == DEGRADATION_MINIMAL:
            return priority < _CORE_MIN_PRIORITY
        # DEGRADATION_EMERGENCY — only top-priority services survive
        return priority < 10

    def _auto_detect_level(self) -> None:
        """Auto-detect degradation level from system metrics."""
        if not _psutil_ok:
            return
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory().percent
        except Exception:
            return

        if cpu > 95 or mem > 95:
            self._set_if_changed(DEGRADATION_EMERGENCY)
        elif cpu > 85 or mem > 85:
            self._set_if_changed(DEGRADATION_MINIMAL)
        elif cpu > 70 or mem > 75:
            self._set_if_changed(DEGRADATION_REDUCED)
        else:
            self._set_if_changed(DEGRADATION_FULL)

    def _set_if_changed(self, new_level: int) -> None:
        if self._level != new_level:
            old = self._level
            self._level = new_level
            if old != new_level:
                logger.warning(
                    "Auto-degradation level changed: %d -> %d", old, new_level,
                )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_service_status(self) -> Dict[str, dict]:
        """Return per-service statistics."""
        with self._lock:
            return {
                name: {
                    "priority": self._services[name]["priority"],
                    "has_fallback": self._services[name]["fallback_fn"] is not None,
                    "fallback_count": self._stats[name]["fallback_count"],
                    "last_error": self._stats[name]["last_error"],
                    "last_success": self._stats[name]["last_success"],
                    "last_fallback": self._stats[name]["last_fallback"],
                }
                for name in self._services
            }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[GracefulDegradation] = None
_instance_lock = threading.Lock()


def get_graceful_degradation() -> GracefulDegradation:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = GracefulDegradation()
    return _instance
