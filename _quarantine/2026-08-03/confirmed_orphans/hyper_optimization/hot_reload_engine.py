"""JARVIS MK-X Hyper-Optimization Engine — Hot reload engine."""

from __future__ import annotations

import hashlib
import importlib
import logging
import os
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("jarvis.hyper_opt.hot_reload_engine")


def _file_hash(path: str) -> str:
    """Compute SHA-256 hash of a file's contents."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


class HotReloadEngine:
    """Reload modules without restarting the system by monitoring file changes."""

    def __init__(self) -> None:
        self._watched: dict[str, dict[str, Any]] = {}
        self._callbacks: dict[str, list[Callable[..., Any]]] = {}
        self._lock = threading.RLock()
        self._reload_log: deque = deque(maxlen=100)
        self._auto_reload: bool = False
        self._auto_thread: threading.Thread | None = None
        self._auto_interval: float = 5.0
        self._stop_event = threading.Event()
        self._stats: dict[str, int] = {
            "total_watches": 0,
            "total_checks": 0,
            "total_reloads": 0,
            "total_errors": 0,
        }

    def watch(
        self,
        module_name: str,
        file_path: str,
        callback: Callable[..., Any] | None = None,
    ) -> None:
        """Watch a module file for changes."""
        abs_path = os.path.abspath(file_path)
        current_hash = _file_hash(abs_path)
        with self._lock:
            self._watched[module_name] = {
                "file_path": abs_path,
                "last_hash": current_hash,
                "last_mtime": os.path.getmtime(abs_path) if os.path.exists(abs_path) else 0.0,
                "reload_count": 0,
                "last_reload_time": 0.0,
            }
            if callback is not None:
                self._callbacks.setdefault(module_name, []).append(callback)
            self._stats["total_watches"] += 1
        logger.info(
            "Watching module '%s' (%s)", module_name, abs_path
        )

    def unwatch(self, module_name: str) -> bool:
        """Stop watching a module. Returns True if found."""
        with self._lock:
            if module_name not in self._watched:
                return False
            del self._watched[module_name]
            self._callbacks.pop(module_name, None)
            logger.info("Stopped watching module '%s'", module_name)
            return True

    def check_for_changes(self) -> list[str]:
        """Check all watched files for changes. Returns list of changed module names."""
        changed: list[str] = []
        with self._lock:
            watched_copy = dict(self._watched)
        self._stats["total_checks"] += 1
        for module_name, info in watched_copy.items():
            abs_path = info["file_path"]
            if not os.path.exists(abs_path):
                continue
            try:
                current_mtime = os.path.getmtime(abs_path)
            except OSError:
                continue
            if current_mtime <= info["last_mtime"]:
                continue
            current_hash = _file_hash(abs_path)
            if current_hash != info["last_hash"]:
                with self._lock:
                    if module_name in self._watched:
                        self._watched[module_name]["last_mtime"] = current_mtime
                        self._watched[module_name]["last_hash"] = current_hash
                changed.append(module_name)
                logger.info("Change detected in module '%s'", module_name)
        return changed

    def reload(self, module_name: str) -> dict[str, Any]:
        """Reload a specific module. Returns result dict."""
        with self._lock:
            info = self._watched.get(module_name)
        if info is None:
            return {
                "success": False,
                "module": module_name,
                "error": "Module not watched",
                "reload_ms": 0.0,
            }
        old_hash = info["last_hash"]
        start = time.perf_counter()
        success = False
        error_msg = ""
        try:
            module = sys.modules.get(module_name)
            if module is not None:
                importlib.reload(module)
                success = True
            else:
                importlib.import_module(module_name)
                success = True
        except Exception as exc:
            error_msg = str(exc)
            self._stats["total_errors"] += 1
            logger.error(
                "Failed to reload module '%s': %s", module_name, exc
            )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        new_hash = _file_hash(info["file_path"])
        with self._lock:
            if module_name in self._watched:
                self._watched[module_name]["reload_count"] += 1
                self._watched[module_name]["last_hash"] = new_hash
                self._watched[module_name]["last_mtime"] = (
                    os.path.getmtime(info["file_path"])
                    if os.path.exists(info["file_path"])
                    else 0.0
                )
                self._watched[module_name]["last_reload_time"] = time.perf_counter()
        if success:
            self._stats["total_reloads"] += 1
            self._fire_callbacks(module_name)
        log_entry = {
            "module": module_name,
            "success": success,
            "old_hash": old_hash[:16],
            "new_hash": new_hash[:16],
            "reload_ms": round(elapsed_ms, 3),
            "timestamp": time.time(),
            "error": error_msg or None,
        }
        self._reload_log.append(log_entry)
        logger.info(
            "Reload '%s': success=%s (%.2f ms)",
            module_name,
            success,
            elapsed_ms,
        )
        return {
            "success": success,
            "module": module_name,
            "old_hash": old_hash,
            "new_hash": new_hash,
            "reload_ms": round(elapsed_ms, 3),
            "error": error_msg or None,
        }

    def _fire_callbacks(self, module_name: str) -> None:
        """Invoke registered callbacks for a module."""
        with self._lock:
            cbs = list(self._callbacks.get(module_name, []))
        for cb in cbs:
            try:
                cb(module_name)
            except Exception:
                logger.exception(
                    "Callback error for module '%s'", module_name
                )

    def reload_all_changed(self) -> list[dict[str, Any]]:
        """Check and reload all changed modules. Returns list of results."""
        changed = self.check_for_changes()
        results: list[dict[str, Any]] = []
        for name in changed:
            result = self.reload(name)
            results.append(result)
        if results:
            logger.info(
                "Reloaded %d/%d changed modules",
                sum(1 for r in results if r["success"]),
                len(results),
            )
        return results

    def enable_auto_reload(self, interval_seconds: float = 5.0) -> None:
        """Enable automatic background checking and reloading."""
        with self._lock:
            if self._auto_reload and self._auto_thread is not None and self._auto_thread.is_alive():
                logger.info("Auto-reload already enabled")
                return
            self._auto_interval = max(0.5, interval_seconds)
            self._auto_reload = True
            self._stop_event.clear()

        def _auto_loop() -> None:
            logger.info(
                "Auto-reload enabled (interval=%.1f s)", self._auto_interval
            )
            while not self._stop_event.is_set():
                try:
                    self.reload_all_changed()
                except Exception:
                    logger.exception("Error in auto-reload loop")
                self._stop_event.wait(timeout=self._auto_interval)
            logger.info("Auto-reload thread stopped")

        t = threading.Thread(
            target=_auto_loop, name="hot-reload-auto", daemon=True
        )
        self._auto_thread = t
        t.start()

    def disable_auto_reload(self) -> None:
        """Disable automatic reloading."""
        with self._lock:
            if not self._auto_reload:
                return
            self._auto_reload = False
            self._stop_event.set()
        if self._auto_thread is not None and self._auto_thread.is_alive():
            self._auto_thread.join(timeout=5.0)
            self._auto_thread = None
        logger.info("Auto-reload disabled")

    def get_status(self) -> dict[str, Any]:
        """Returns watched_count, reload_count, last_reload, auto_reload_enabled."""
        with self._lock:
            total_reload_count = sum(
                info["reload_count"] for info in self._watched.values()
            )
            last_reload = 0.0
            for info in self._watched.values():
                if info["last_reload_time"] > last_reload:
                    last_reload = info["last_reload_time"]
            watched_details: dict[str, dict[str, Any]] = {}
            for name, info in self._watched.items():
                watched_details[name] = {
                    "file_path": info["file_path"],
                    "reload_count": info["reload_count"],
                    "last_reload_time": round(
                        info["last_reload_time"], 3
                    )
                    if info["last_reload_time"] > 0
                    else None,
                }
        return {
            "watched_count": len(self._watched),
            "total_reload_count": total_reload_count,
            "last_reload": round(last_reload, 3) if last_reload > 0 else None,
            "auto_reload_enabled": self._auto_reload,
            "auto_reload_interval_s": self._auto_interval,
            "log_size": len(self._reload_log),
            "total_checks": self._stats["total_checks"],
            "total_errors": self._stats["total_errors"],
            "watched": watched_details,
        }

    def get_reload_log(self, limit: int = 20) -> list[dict[str, Any]]:
        """Returns recent reload history entries."""
        with self._lock:
            entries = list(self._reload_log)
        entries = entries[-limit:]
        return [
            {
                "module": e["module"],
                "success": e["success"],
                "old_hash": e["old_hash"],
                "new_hash": e["new_hash"],
                "reload_ms": e["reload_ms"],
                "timestamp": e["timestamp"],
                "error": e["error"],
            }
            for e in entries
        ]

    def register_callback(
        self, module_name: str, callback: Callable[..., Any]
    ) -> None:
        """Register a callback to run after a module is reloaded."""
        with self._lock:
            self._callbacks.setdefault(module_name, []).append(callback)
        logger.debug(
            "Registered callback for module '%s'", module_name
        )

    def get_watched_modules(self) -> list[str]:
        """Return list of watched module names."""
        with self._lock:
            return list(self._watched.keys())


_instance: HotReloadEngine | None = None
_instance_lock = threading.RLock()


def get_hot_reload_engine() -> HotReloadEngine:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = HotReloadEngine()
            logger.info("Created HotReloadEngine singleton")
        return _instance
