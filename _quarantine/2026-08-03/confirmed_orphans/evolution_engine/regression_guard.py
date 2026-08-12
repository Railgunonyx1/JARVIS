"""Regression Guard — baseline tracking with automatic rollback on performance regression."""

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("jarvis.evolution_engine.regression_guard")


class RegressionGuard:
    """Monitors metrics against baselines and triggers rollback callbacks on regression."""

    def __init__(self) -> None:
        self._baselines: dict[str, dict] = {}
        self._history: list[dict] = []
        self._rollback_callbacks: dict[str, Callable] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Baseline management
    # ------------------------------------------------------------------

    def set_baseline(self, name: str, value: float, threshold_pct: float = 20.0) -> None:
        """Set or update a baseline for a metric.

        Args:
            name: Metric identifier.
            value: Baseline value.
            threshold_pct: Maximum acceptable percentage increase before regression.
        """
        with self._lock:
            self._baselines[name] = {
                "value": value,
                "threshold_pct": threshold_pct,
                "set_at": time.time(),
            }
        logger.debug("Baseline set for '%s': %.4f (threshold %.1f%%)", name, value, threshold_pct)

    def get_all_baselines(self) -> dict[str, dict]:
        """Return all registered baselines."""
        with self._lock:
            return dict(self._baselines)

    # ------------------------------------------------------------------
    # Regression checking
    # ------------------------------------------------------------------

    def check_regression(self, name: str, current_value: float) -> dict[str, Any]:
        """Check if *current_value* represents a regression against the baseline.

        Returns a dict with ``regressed``, ``baseline``, ``current``, and ``change_pct``.
        """
        with self._lock:
            baseline = self._baselines.get(name)

        if baseline is None:
            return {
                "regressed": False,
                "baseline": None,
                "current": current_value,
                "change_pct": 0.0,
                "message": f"No baseline defined for '{name}'.",
            }

        base_val = baseline["value"]
        threshold = baseline["threshold_pct"]

        if base_val == 0:
            change_pct = 0.0 if current_value == 0 else 100.0
        else:
            change_pct = ((current_value - base_val) / abs(base_val)) * 100

        regressed = change_pct > threshold

        result = {
            "regressed": regressed,
            "baseline": round(base_val, 4),
            "current": round(current_value, 4),
            "change_pct": round(change_pct, 2),
            "threshold_pct": threshold,
        }

        if regressed:
            logger.warning(
                "Regression detected for '%s': baseline=%.4f current=%.4f (%+.1f%%, threshold %.1f%%)",
                name, base_val, current_value, change_pct, threshold,
            )
            entry = {
                "name": name,
                "baseline": base_val,
                "current": current_value,
                "change_pct": round(change_pct, 2),
                "detected_at": time.time(),
            }
            with self._lock:
                self._history.append(entry)

        return result

    def get_regression_history(self) -> list[dict]:
        """Return all detected regressions."""
        with self._lock:
            return list(self._history)

    # ------------------------------------------------------------------
    # Auto-rollback
    # ------------------------------------------------------------------

    def register_rollback_callback(self, name: str, callback: Callable) -> None:
        """Register a rollback callback for a specific metric."""
        with self._lock:
            self._rollback_callbacks[name] = callback
        logger.debug("Registered rollback callback for '%s'", name)

    def auto_rollback(self, name: str, current_value: float) -> bool:
        """If *current_value* regresses beyond threshold, trigger the registered rollback.

        Returns ``True`` if a rollback was triggered, ``False`` otherwise.
        """
        result = self.check_regression(name, current_value)
        if not result["regressed"]:
            return False

        with self._lock:
            callback = self._rollback_callbacks.get(name)

        if callback is None:
            logger.warning(
                "Regression detected for '%s' but no rollback callback registered.",
                name,
            )
            return False

        try:
            callback()
            logger.info("Rollback callback executed for '%s'.", name)
            return True
        except Exception as exc:
            logger.error("Rollback callback for '%s' failed: %s", name, exc)
            return False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def remove_baseline(self, name: str) -> bool:
        """Remove a baseline. Returns ``True`` if it existed."""
        with self._lock:
            if name in self._baselines:
                del self._baselines[name]
                self._rollback_callbacks.pop(name, None)
                return True
            return False

    def clear_history(self) -> int:
        """Clear regression history. Returns the number of entries removed."""
        with self._lock:
            count = len(self._history)
            self._history.clear()
            return count

    def reset(self) -> None:
        """Clear all baselines, history, and callbacks."""
        with self._lock:
            self._baselines.clear()
            self._history.clear()
            self._rollback_callbacks.clear()


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_instance: RegressionGuard | None = None
_lock = threading.Lock()


def get_regression_guard() -> RegressionGuard:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = RegressionGuard()
    return _instance
