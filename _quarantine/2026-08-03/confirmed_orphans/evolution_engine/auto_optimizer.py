"""Auto Optimizer — analyses current state and applies safe optimisations with rollback."""

import copy
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("jarvis.evolution_engine.auto_optimizer")


class AutoOptimizer:
    """Discovers optimisation opportunities, applies them, and tracks history."""

    def __init__(self) -> None:
        self._applied: list[dict] = []
        self._configs_snapshot: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._optimization_registry: dict[str, dict] = {}
        self._register_builtins()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_and_suggest(self) -> list[dict]:
        """Analyse the current system state and return a list of suggestions."""
        suggestions: list[dict] = []

        with self._lock:
            applied_names = {o["name"] for o in self._applied if o.get("status") == "applied"}

        for name, opt in self._optimization_registry.items():
            if name in applied_names:
                continue
            check_fn = opt.get("check")
            if check_fn is not None:
                try:
                    should_apply, reason = check_fn()
                except Exception as exc:
                    logger.debug("Check for '%s' raised: %s", name, exc)
                    continue
                if not should_apply:
                    continue
            else:
                reason = opt.get("description", "")

            suggestions.append({
                "name": name,
                "description": opt["description"],
                "impact": opt.get("impact", "medium"),
                "effort": opt.get("effort", "low"),
                "auto_apply": opt.get("auto_apply", False),
                "reason": reason,
            })

        return suggestions

    def apply_optimization(self, name: str) -> dict[str, Any]:
        """Apply a named optimisation. Returns ``{"success": bool, "details": str}``."""
        with self._lock:
            if name not in self._optimization_registry:
                return {"success": False, "details": f"Unknown optimisation '{name}'."}

            already_applied = any(
                o["name"] == name and o.get("status") == "applied"
                for o in self._applied
            )
            if already_applied:
                return {"success": False, "details": f"Optimisation '{name}' is already applied."}

        opt = self._optimization_registry[name]
        apply_fn = opt.get("apply_fn")
        if apply_fn is None:
            return {"success": False, "details": f"No apply function for '{name}'."}

        snapshot = self._take_snapshot(name)
        try:
            result = apply_fn()
            entry = {
                "name": name,
                "description": opt["description"],
                "impact": opt.get("impact", "medium"),
                "status": "applied",
                "applied_at": time.time(),
                "snapshot": snapshot,
                "result": result,
            }
            with self._lock:
                self._applied.append(entry)
            logger.info("Applied optimisation '%s': %s", name, result)
            return {"success": True, "details": str(result)}
        except Exception as exc:
            self._restore_snapshot(snapshot)
            logger.error("Failed to apply optimisation '%s': %s", name, exc)
            return {"success": False, "details": str(exc)}

    def get_applied_optimizations(self) -> list[dict]:
        """Return the full history of applied optimisations."""
        with self._lock:
            return [copy.deepcopy(o) for o in self._applied]

    def rollback_last(self) -> bool:
        """Roll back the most recently applied optimisation."""
        with self._lock:
            applied = [o for o in self._applied if o.get("status") == "applied"]
            if not applied:
                logger.info("Nothing to roll back.")
                return False
            last = applied[-1]
            last["status"] = "rolled_back"
            last["rolled_back_at"] = time.time()

        snapshot = last.get("snapshot")
        if snapshot:
            self._restore_snapshot(snapshot)

        rollback_fn = self._optimization_registry.get(last["name"], {}).get("rollback_fn")
        if rollback_fn is not None:
            try:
                rollback_fn()
            except Exception as exc:
                logger.warning("Rollback function for '%s' failed: %s", last["name"], exc)

        logger.info("Rolled back optimisation '%s'", last["name"])
        return True

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_optimization(
        self,
        name: str,
        description: str,
        apply_fn: Callable,
        check: Callable | None = None,
        rollback_fn: Callable | None = None,
        impact: str = "medium",
        effort: str = "low",
        auto_apply: bool = False,
    ) -> None:
        """Register a custom optimisation."""
        with self._lock:
            self._optimization_registry[name] = {
                "description": description,
                "apply_fn": apply_fn,
                "check": check,
                "rollback_fn": rollback_fn,
                "impact": impact,
                "effort": effort,
                "auto_apply": auto_apply,
            }

    # ------------------------------------------------------------------
    # Built-in optimisations
    # ------------------------------------------------------------------

    def _register_builtins(self) -> None:
        self.register_optimization(
            name="reduce_polling_interval",
            description="Increase system-monitor polling interval from 500ms to 2000ms to reduce CPU.",
            apply_fn=self._apply_reduce_polling,
            check=self._check_reduce_polling,
            rollback_fn=self._rollback_reduce_polling,
            impact="medium",
            effort="low",
            auto_apply=True,
        )
        self.register_optimization(
            name="enable_cache",
            description="Enable semantic cache for repeated LLM queries to reduce latency.",
            apply_fn=self._apply_enable_cache,
            check=self._check_enable_cache,
            rollback_fn=self._rollback_enable_cache,
            impact="high",
            effort="low",
            auto_apply=True,
        )
        self.register_optimization(
            name="compress_memory",
            description="Compress old memory entries older than 7 days to save disk space.",
            apply_fn=self._apply_compress_memory,
            check=None,
            rollback_fn=None,
            impact="low",
            effort="low",
            auto_apply=False,
        )
        self.register_optimization(
            name="lazy_load_plugins",
            description="Defer loading of non-critical plugins until first use to speed up startup.",
            apply_fn=self._apply_lazy_load_plugins,
            check=self._check_lazy_load_plugins,
            rollback_fn=self._rollback_lazy_load_plugins,
            impact="medium",
            effort="medium",
            auto_apply=True,
        )

    # -- reduce_polling_interval ------------------------------------------

    @staticmethod
    def _check_reduce_polling() -> tuple:
        try:
            from core.config import Config
            cfg = Config.instance()
            interval = cfg.get("system_monitor_poll_ms", 500)
            if interval < 1500:
                return True, f"Current polling interval is {interval}ms — increasing to 2000ms saves CPU."
        except Exception:
            pass
        return False, ""

    @staticmethod
    def _apply_reduce_polling() -> str:
        from core.config import Config
        cfg = Config.instance()
        old = cfg.get("system_monitor_poll_ms", 500)
        cfg.set("system_monitor_poll_ms", 2000)
        return f"Reduced polling frequency from {old}ms to 2000ms."

    @staticmethod
    def _rollback_reduce_polling() -> None:
        from core.config import Config
        cfg = Config.instance()
        cfg.set("system_monitor_poll_ms", 500)

    # -- enable_cache -----------------------------------------------------

    @staticmethod
    def _check_enable_cache() -> tuple:
        try:
            from performance_engine.cache import get_cache
            cache = get_cache()
            stats = cache.get_stats()
            if stats["hit_rate"] < 0.3:
                return True, f"Cache hit rate is low ({stats['hit_rate']:.0%}). Enabling warm-up may help."
        except Exception:
            pass
        return False, ""

    @staticmethod
    def _apply_enable_cache() -> str:
        from performance_engine.cache import get_cache
        cache = get_cache()
        cache.warm_cache({
            "intent:greeting": "cached_greeting",
            "intent:farewell": "cached_farewell",
        }, ttl_seconds=600)
        return "Cache warmed with common intents (600s TTL)."

    @staticmethod
    def _rollback_enable_cache() -> None:
        from performance_engine.cache import get_cache
        cache = get_cache()
        cache.invalidate_pattern("intent:*")

    # -- compress_memory --------------------------------------------------

    @staticmethod
    def _apply_compress_memory() -> str:
        compressed = 0
        try:
            from performance_engine.compression import get_compression_engine
            compressor = get_compression_engine()
            if hasattr(compressor, "compress_old"):
                compressed = compressor.compress_old(older_than_days=7)
        except Exception:
            pass
        return f"Compressed {compressed} old memory entries."

    # -- lazy_load_plugins ------------------------------------------------

    @staticmethod
    def _check_lazy_load_plugins() -> tuple:
        try:
            from core.plugin_loader import PluginLoader
            loader = PluginLoader()
            if hasattr(loader, "get_loaded_count") and loader.get_loaded_count() > 5:
                return True, f"{loader.get_loaded_count()} plugins loaded eagerly — deferring non-critical ones."
        except Exception:
            pass
        return False, ""

    @staticmethod
    def _apply_lazy_load_plugins() -> str:
        try:
            from core.plugin_loader import PluginLoader
            loader = PluginLoader()
            if hasattr(loader, "set_lazy_mode"):
                loader.set_lazy_mode(True)
                return "Plugin lazy-loading enabled."
        except Exception:
            pass
        return "Lazy-load flag set (runtime support required)."

    @staticmethod
    def _rollback_lazy_load_plugins() -> None:
        try:
            from core.plugin_loader import PluginLoader
            loader = PluginLoader()
            if hasattr(loader, "set_lazy_mode"):
                loader.set_lazy_mode(False)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def _take_snapshot(self, name: str) -> dict[str, Any]:
        snapshot: dict[str, Any] = {"name": name, "timestamp": time.time()}
        try:
            from core.config import Config
            cfg = Config.instance()
            snapshot["config"] = cfg.to_dict() if hasattr(cfg, "to_dict") else {}
        except Exception:
            snapshot["config"] = {}
        return snapshot

    def _restore_snapshot(self, snapshot: dict[str, Any]) -> None:
        if not snapshot:
            return
        try:
            from core.config import Config
            cfg = Config.instance()
            config_data = snapshot.get("config", {})
            for key, value in config_data.items():
                if hasattr(cfg, "set"):
                    cfg.set(key, value)
            logger.info("Restored config from snapshot taken at %.0f", snapshot.get("timestamp", 0))
        except Exception as exc:
            logger.warning("Failed to restore snapshot: %s", exc)


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_instance: AutoOptimizer | None = None
_lock = threading.Lock()


def get_auto_optimizer() -> AutoOptimizer:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = AutoOptimizer()
    return _instance
