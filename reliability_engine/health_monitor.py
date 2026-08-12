"""Health Monitor — runs periodic background health checks and tracks system status."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("jarvis.reliability.health_monitor")


class HealthMonitor:
    """Background health-check orchestrator with callback support."""

    def __init__(self) -> None:
        self._checks: dict[str, dict] = {}
        self._results: dict[str, dict] = {}
        self._callbacks: dict[str, list[Callable]] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_run: float = 0.0

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_check(
        self,
        name: str,
        check_fn: Callable[[], bool],
        interval_seconds: float = 30.0,
        timeout: float = 5.0,
    ) -> None:
        """Register a periodic health check.

        *check_fn* should return ``True`` when healthy, ``False`` otherwise.
        A string return value is treated as the message.
        """
        with self._lock:
            self._checks[name] = {
                "check_fn": check_fn,
                "interval": interval_seconds,
                "timeout": timeout,
                "last_run": 0.0,
            }
            logger.info(
                "Health check '%s' registered (interval=%.0fs, timeout=%.0fs)",
                name,
                interval_seconds,
                timeout,
            )

    def on_unhealthy(self, name: str, callback: Callable[[str, dict], None]) -> None:
        """Register a callback invoked when *name* becomes unhealthy."""
        with self._lock:
            self._callbacks.setdefault(name, []).append(callback)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Health monitor started")

    def stop(self) -> None:
        """Stop the background monitoring thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        logger.info("Health monitor stopped")

    def _monitor_loop(self) -> None:
        while self._running:
            now = time.perf_counter()
            with self._lock:
                snapshot = dict(self._checks)

            for name, cfg in snapshot.items():
                if now - cfg["last_run"] < cfg["interval"]:
                    continue
                self._run_single_check(name, cfg)

            self._last_run = time.perf_counter()
            time.sleep(1.0)

    # ------------------------------------------------------------------
    # Check execution
    # ------------------------------------------------------------------

    def _run_single_check(self, name: str, cfg: dict) -> None:
        """Run a single check with timeout support."""
        start = time.perf_counter()
        ok = True
        message = ""

        result_box: list[Any] = [None]
        exc_box: list[Exception | None] = [None]

        def _target() -> None:
            try:
                result_box[0] = cfg["check_fn"]()
            except Exception as exc:
                exc_box[0] = exc

        t = threading.Thread(target=_target, daemon=True)
        t.start()
        t.join(timeout=cfg["timeout"])

        if t.is_alive():
            ok = False
            message = "Timed out"
        elif exc_box[0] is not None:
            ok = False
            message = str(exc_box[0])
        else:
            raw = result_box[0]
            if isinstance(raw, bool):
                ok = raw
                message = "OK" if raw else "Check returned False"
            elif isinstance(raw, str):
                ok = True
                message = raw
            else:
                ok = bool(raw) if raw is not None else True
                message = "OK" if ok else "Check failed"

        latency_ms = (time.perf_counter() - start) * 1000.0

        entry = {
            "ok": ok,
            "message": message,
            "latency_ms": round(latency_ms, 2),
            "last_run": time.perf_counter(),
        }

        with self._lock:
            self._results[name] = entry
            self._checks[name]["last_run"] = time.perf_counter()

        if not ok:
            logger.warning("Health check '%s' FAILED: %s", name, message)
            self._fire_callbacks(name, entry)

    def _fire_callbacks(self, name: str, entry: dict) -> None:
        with self._lock:
            callbacks = list(self._callbacks.get(name, []))
        for cb in callbacks:
            try:
                cb(name, entry)
            except Exception:
                logger.exception("Error in unhealthy callback for '%s'", name)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_health(self) -> dict:
        """Return aggregate health status.

        Returns:
            dict with keys ``status``, ``checks``, and ``last_run``.
        """
        with self._lock:
            results = dict(self._results)
            last_run = self._last_run

        if not results:
            return {"status": "unknown", "checks": {}, "last_run": 0.0}

        failed = [n for n, r in results.items() if not r["ok"]]
        total = len(results)

        if not failed:
            status = "healthy"
        elif len(failed) < total:
            status = "degraded"
        else:
            status = "unhealthy"

        return {
            "status": status,
            "checks": results,
            "last_run": last_run,
        }

    def get_check_result(self, name: str) -> dict:
        """Return the last result for a specific check."""
        with self._lock:
            if name not in self._results:
                return {"ok": False, "message": "Not yet run", "latency_ms": 0.0, "last_run": 0.0}
            return dict(self._results[name])


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: HealthMonitor | None = None
_instance_lock = threading.Lock()


def get_health_monitor() -> HealthMonitor:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = HealthMonitor()
    return _instance
