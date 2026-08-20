"""Circuit Breaker — prevents cascading failures by wrapping calls with state-based protection."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("jarvis.reliability.circuit_breaker")

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe circuit breaker for fault isolation."""

    def __init__(self) -> None:
        self._circuits: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max: int = 3,
    ) -> None:
        """Register a named circuit with configuration."""
        with self._lock:
            if name in self._circuits:
                logger.warning("Circuit '%s' already registered, skipping", name)
                return
            self._circuits[name] = {
                "state": CLOSED,
                "failure_count": 0,
                "last_failure": 0.0,
                "last_success": time.perf_counter(),
                "half_open_attempts": 0,
                "config": {
                    "failure_threshold": failure_threshold,
                    "recovery_timeout": recovery_timeout,
                    "half_open_max": half_open_max,
                },
            }
            logger.info(
                "Circuit '%s' registered (threshold=%d, recovery=%.0fs)",
                name,
                failure_threshold,
                recovery_timeout,
            )

    def _ensure_registered(self, name: str) -> None:
        if name not in self._circuits:
            raise KeyError(f"Circuit '{name}' is not registered")

    def _transition(self, name: str, new_state: str) -> None:
        circuit = self._circuits[name]
        old_state = circuit["state"]
        circuit["state"] = new_state
        if new_state == HALF_OPEN:
            circuit["half_open_attempts"] = 0
        logger.info(
            "Circuit '%s': %s -> %s",
            name,
            old_state,
            new_state,
        )

    def call(self, name: str, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute *fn* through the named circuit breaker."""
        with self._lock:
            self._ensure_registered(name)
            circuit = self._circuits[name]
            state = circuit["state"]

            if state == OPEN:
                elapsed = time.perf_counter() - circuit["last_failure"]
                if elapsed >= circuit["config"]["recovery_timeout"]:
                    self._transition(name, HALF_OPEN)
                else:
                    raise RuntimeError(
                        f"Circuit '{name}' is OPEN, call rejected "
                        f"(retry in {circuit['config']['recovery_timeout'] - elapsed:.1f}s)"
                    )

        # Execute outside the main lock to avoid blocking state reads
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            self._on_failure(name, exc)
            raise
        else:
            self._on_success(name)
            return result

    def _on_failure(self, name: str, exc: Exception) -> None:
        with self._lock:
            circuit = self._circuits[name]
            circuit["last_failure"] = time.perf_counter()

            if circuit["state"] == HALF_OPEN:
                self._transition(name, OPEN)
                logger.warning(
                    "Circuit '%s' reopened from HALF_OPEN: %s",
                    name,
                    exc,
                )
                return

            circuit["failure_count"] += 1
            threshold = circuit["config"]["failure_threshold"]
            if circuit["failure_count"] >= threshold:
                self._transition(name, OPEN)
                logger.warning(
                    "Circuit '%s' opened after %d failures: %s",
                    name,
                    circuit["failure_count"],
                    exc,
                )

    def _on_success(self, name: str) -> None:
        with self._lock:
            circuit = self._circuits[name]
            circuit["last_success"] = time.perf_counter()

            if circuit["state"] == HALF_OPEN:
                circuit["half_open_attempts"] += 1
                max_attempts = circuit["config"]["half_open_max"]
                if circuit["half_open_attempts"] >= max_attempts:
                    circuit["failure_count"] = 0
                    self._transition(name, CLOSED)
                    logger.info("Circuit '%s' closed after %d half-open successes", name, max_attempts)
                return

            # CLOSED path — reset on success
            circuit["failure_count"] = 0

    def get_state(self, name: str) -> str:
        """Return the current state of a circuit."""
        with self._lock:
            self._ensure_registered(name)
            return self._circuits[name]["state"]

    def get_all_states(self) -> dict[str, str]:
        """Return a mapping of circuit name -> state."""
        with self._lock:
            return {name: c["state"] for name, c in self._circuits.items()}

    def reset(self, name: str) -> None:
        """Manually reset a circuit to CLOSED."""
        with self._lock:
            self._ensure_registered(name)
            circuit = self._circuits[name]
            circuit["failure_count"] = 0
            circuit["half_open_attempts"] = 0
            self._transition(name, CLOSED)
            logger.info("Circuit '%s' manually reset to CLOSED", name)

    def is_available(self, name: str) -> bool:
        """Return True if the circuit allows calls (CLOSED or HALF_OPEN)."""
        with self._lock:
            self._ensure_registered(name)
            return self._circuits[name]["state"] != OPEN

    def failures_for(self, name: str) -> int:
        """Return the failure count for a named circuit (read-only)."""
        with self._lock:
            self._ensure_registered(name)
            return self._circuits[name]["failure_count"]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: CircuitBreaker | None = None
_instance_lock = threading.Lock()


def get_circuit_breaker() -> CircuitBreaker:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = CircuitBreaker()
    return _instance
