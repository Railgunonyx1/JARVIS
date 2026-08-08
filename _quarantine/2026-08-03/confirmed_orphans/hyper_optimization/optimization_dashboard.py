"""OptimizationDashboard — Aggregates all hyper-optimization metrics into a comprehensive dashboard."""

from collections import deque
from typing import Optional
import json
import logging
import threading
import time

logger = logging.getLogger("jarvis.hyper_opt.optimization_dashboard")


class OptimizationDashboard:
    def __init__(self):
        self._metrics: dict = {}
        self._alerts: deque = deque(maxlen=100)
        self._lock: threading.RLock = threading.RLock()
        self._collect_start: float = 0.0
        self._collect_count: int = 0

    def collect_all_metrics(self) -> None:
        self._collect_start = time.perf_counter()
        with self._lock:
            self._collect_count += 1

        modules = {
            "optimization_manager": "hyper_optimization.optimization_manager",
            "adaptive_profiler": "hyper_optimization.adaptive_profiler",
            "pipeline_fusion": "hyper_optimization.pipeline_fusion",
            "branch_predictor": "hyper_optimization.branch_predictor",
            "cache_predictor": "hyper_optimization.cache_predictor",
            "zero_copy_manager": "hyper_optimization.zero_copy_manager",
            "object_pool": "hyper_optimization.object_pool",
            "memory_allocator": "hyper_optimization.memory_allocator",
            "cpu_affinity": "hyper_optimization.cpu_affinity",
            "lock_optimizer": "hyper_optimization.lock_optimizer",
            "gpu_scheduler": "hyper_optimization.gpu_scheduler",
            "io_optimizer": "hyper_optimization.io_optimizer",
            "startup_optimizer": "hyper_optimization.startup_optimizer",
            "hot_reload_engine": "hyper_optimization.hot_reload_engine",
            "resource_predictor": "hyper_optimization.resource_predictor",
            "speculative_executor": "hyper_optimization.speculative_executor",
            "prefetch_engine": "hyper_optimization.prefetch_engine",
            "scheduler_optimizer": "hyper_optimization.scheduler_optimizer",
        }

        for name, module_path in modules.items():
            try:
                import importlib
                mod = importlib.import_module(module_path)

                getter_names = [
                    f"get_{name}",
                    f"get_{name.replace('_', ' ').strip().replace(' ', '_')}",
                ]
                stats = None
                for getter_name in getter_names:
                    fn = getattr(mod, getter_name, None)
                    if fn is not None and callable(fn):
                        instance = fn()
                        if hasattr(instance, "get_stats") and callable(instance.get_stats):
                            stats = instance.get_stats()
                            break
                        elif isinstance(instance, dict):
                            stats = instance
                            break

                if stats is None and hasattr(mod, "get_stats"):
                    stats = mod.get_stats()

                if stats is not None and isinstance(stats, dict):
                    for key, value in stats.items():
                        metric_name = f"{name}.{key}"
                        if isinstance(value, (int, float)):
                            self._safe_record(metric_name, float(value), "", name)
                        elif isinstance(value, bool):
                            self._safe_record(metric_name, 1.0 if value else 0.0, "bool", name)
            except ImportError:
                logger.debug("Subsystem %s not importable, skipping", name)
            except Exception as exc:
                logger.debug("Error collecting from %s: %s", name, exc)

        self._collect_system_metrics()
        elapsed = time.perf_counter() - self._collect_start
        logger.debug("Dashboard collection completed in %.2fms", elapsed * 1000)

    def _collect_system_metrics(self) -> None:
        try:
            import psutil
            vm = psutil.virtual_memory()
            self._safe_record("system.cpu_percent", psutil.cpu_percent(interval=0), "percent", "system")
            self._safe_record("system.ram_percent", vm.percent, "percent", "system")
            self._safe_record("system.ram_used_mb", vm.used / (1024 * 1024), "MB", "system")
            self._safe_record("system.ram_total_mb", vm.total / (1024 * 1024), "MB", "system")
            disk = psutil.disk_usage("/")
            self._safe_record("system.disk_percent", disk.percent, "percent", "system")
            try:
                gpu = [p for p in psutil.process_iter(["name"]) if "gpu" in (p.info.get("name") or "").lower()]
                self._safe_record("system.gpu_active", 1.0 if gpu else 0.0, "bool", "system")
            except Exception:
                self._safe_record("system.gpu_active", 0.0, "bool", "system")
        except ImportError:
            self._safe_record("system.cpu_percent", 0.0, "percent", "system")
            self._safe_record("system.ram_percent", 0.0, "percent", "system")
            self._safe_record("system.gpu_active", 0.0, "bool", "system")

    def _safe_record(self, name: str, value: float, unit: str, category: str) -> None:
        with self._lock:
            old = self._metrics.get(name, {})
            old_value = old.get("value", None)
            trend = "stable"
            if old_value is not None and isinstance(old_value, (int, float)):
                diff = value - old_value
                if abs(diff) > old_value * 0.1 + 0.01:
                    trend = "increasing" if diff > 0 else "decreasing"
            self._metrics[name] = {
                "value": value,
                "unit": unit,
                "timestamp": time.time(),
                "trend": trend,
                "category": category,
            }

    def get_dashboard(self) -> dict:
        with self._lock:
            metrics_snapshot = dict(self._metrics)
            alerts_snapshot = list(self._alerts)

        categories = {
            "performance": {},
            "memory": {},
            "io": {},
            "prediction": {},
            "reliability": {},
            "system": {},
            "general": {},
        }

        category_map = {
            "optimization_manager": "performance",
            "adaptive_profiler": "performance",
            "pipeline_fusion": "performance",
            "branch_predictor": "prediction",
            "cache_predictor": "prediction",
            "speculative_executor": "prediction",
            "prefetch_engine": "prediction",
            "zero_copy_manager": "memory",
            "object_pool": "memory",
            "memory_allocator": "memory",
            "cpu_affinity": "performance",
            "lock_optimizer": "reliability",
            "scheduler_optimizer": "performance",
            "gpu_scheduler": "performance",
            "io_optimizer": "io",
            "startup_optimizer": "performance",
            "hot_reload_engine": "reliability",
            "resource_predictor": "prediction",
            "system": "system",
        }

        for name, metric_data in metrics_snapshot.items():
            prefix = name.split(".")[0] if "." in name else "general"
            cat = category_map.get(prefix, metric_data.get("category", "general"))
            if cat not in categories:
                cat = "general"
            categories[cat][name] = metric_data

        return {
            "timestamp": time.time(),
            "categories": {k: v for k, v in categories.items() if v},
            "alerts": alerts_snapshot[-20:],
            "total_metrics": len(metrics_snapshot),
            "collect_count": self._collect_count,
            "performance_score": self.get_performance_score(),
            "status": self.get_status_summary(),
        }

    def get_text_dashboard(self) -> str:
        dashboard = self.get_dashboard()
        metrics = self._metrics
        w = 52

        def _mv(key: str, default: str = "N/A") -> str:
            m = metrics.get(key)
            if m is None:
                return default
            v = m["value"]
            u = m.get("unit", "")
            if isinstance(v, float):
                if u == "percent":
                    return f"{v:.0f}%"
                elif u == "MB":
                    return f"{v:.0f} MB"
                elif u == "ms":
                    return f"{v:.1f}ms"
                elif u == "bool":
                    return "Yes" if v >= 1.0 else "No"
                elif v == int(v):
                    return str(int(v))
                return f"{v:.1f}{u}"
            return str(v)

        def _pad(label: str, width: int = 20) -> str:
            return label.ljust(width)

        lines = []
        lines.append("\u2550" * w)
        lines.append(" JARVIS MK-X HYPER-OPTIMIZATION DASHBOARD".center(w))
        lines.append("\u2550" * w)

        lines.append(" PIPELINE")
        lines.append(f"  {_pad('Pipeline Overlap:')}    {_mv('pipeline_fusion.overlap_percent', 'N/A')}")
        lines.append(f"  {_pad('Fusion Count:')}        {_mv('pipeline_fusion.fusion_count', '0')}")
        lines.append(f"  {_pad('Avg Time Saved:')}      {_mv('pipeline_fusion.avg_time_saved_ms', 'N/A')}")

        lines.append(" PREDICTION")
        lines.append(f"  {_pad('Prediction Accuracy:')}  {_mv('branch_predictor.accuracy_percent', _mv('cache_predictor.accuracy_percent', 'N/A'))}")
        lines.append(f"  {_pad('Cache Hit Rate:')}      {_mv('cache_predictor.hit_rate_percent', 'N/A')}")
        lines.append(f"  {_pad('Speculative Hits:')}    {_mv('speculative_executor.successful_speculations', '0')}")

        lines.append(" MEMORY")
        lines.append(f"  {_pad('Zero-Copy Usage:')}     {_mv('zero_copy_manager.zero_copy_percent', 'N/A')}")
        lines.append(f"  {_pad('GC Disabled:')}         {_mv('memory_allocator.gc_disabled', 'No')}")
        lines.append(f"  {_pad('Memory Used:')}         {_mv('system.ram_used_mb', 'N/A')}")

        lines.append(" THREADS")
        lines.append(f"  {_pad('Thread Efficiency:')}   {_mv('lock_optimizer.efficiency_percent', 'N/A')}")
        lines.append(f"  {_pad('Lock Contention:')}     {_mv('lock_optimizer.contention_percent', 'N/A')}")
        lines.append(f"  {_pad('Active Threads:')}      {_mv('scheduler_optimizer.active_threads', '0')}")

        lines.append(" SYSTEM")
        lines.append(f"  {_pad('CPU:')}                 {_mv('system.cpu_percent', 'N/A')}")
        lines.append(f"  {_pad('RAM:')}                 {_mv('system.ram_percent', 'N/A')}")
        lines.append(f"  {_pad('GPU:')}                 {'Active' if metrics.get('system.gpu_active', {}).get('value', 0) >= 1.0 else 'N/A'}")
        lines.append(f"  {_pad('Avg Response:')}        {_mv('optimization_manager.avg_response_ms', 'N/A')}")
        lines.append(f"  {_pad('Perceived Response:')}  {_mv('adaptive_profiler.perceived_response_ms', 'N/A')}")

        status = self.get_status_summary()
        lines.append(f" STATUS: {status}")
        lines.append("\u2550" * w)

        alerts = self._alerts
        if alerts:
            lines.append(" RECENT ALERTS")
            for alert in list(alerts)[-5:]:
                sev = alert.get("severity", "info").upper()
                msg = alert.get("message", "")
                lines.append(f"  [{sev}] {msg[:44]}")

        return "\n".join(lines)

    def record_metric(self, name: str, value: float, unit: str = "", category: str = "general") -> None:
        self._safe_record(name, value, unit, category)

    def get_alerts(self, limit: int = 20) -> list:
        with self._lock:
            return list(self._alerts)[-limit:]

    def add_alert(self, severity: str, message: str) -> None:
        alert = {
            "severity": severity,
            "message": message,
            "timestamp": time.time(),
        }
        with self._lock:
            self._alerts.append(alert)
        if severity == "critical":
            logger.critical("ALERT: %s", message)
        elif severity == "warning":
            logger.warning("ALERT: %s", message)
        else:
            logger.info("ALERT: %s", message)

    def get_performance_score(self) -> int:
        with self._lock:
            metrics_snapshot = dict(self._metrics)

        if not metrics_snapshot:
            return 50

        score_components = []

        cpu = metrics_snapshot.get("system.cpu_percent", {}).get("value")
        if cpu is not None:
            score_components.append(max(0, 100 - cpu))

        ram = metrics_snapshot.get("system.ram_percent", {}).get("value")
        if ram is not None:
            score_components.append(max(0, 100 - ram))

        overlap = metrics_snapshot.get("pipeline_fusion.overlap_percent", {}).get("value")
        if overlap is not None:
            score_components.append(overlap)

        efficiency = metrics_snapshot.get("lock_optimizer.efficiency_percent", {}).get("value")
        if efficiency is not None:
            score_components.append(efficiency)

        hit_rate = metrics_snapshot.get("cache_predictor.hit_rate_percent", {}).get("value")
        if hit_rate is not None:
            score_components.append(hit_rate)

        contention = metrics_snapshot.get("lock_optimizer.contention_percent", {}).get("value")
        if contention is not None:
            score_components.append(max(0, 100 - contention))

        if not score_components:
            return 50

        return max(0, min(100, int(round(sum(score_components) / len(score_components)))))

    def get_status_summary(self) -> str:
        score = self.get_performance_score()
        if score >= 90:
            return "MAXIMUM PERFORMANCE"
        elif score >= 70:
            return "OPTIMIZED"
        elif score >= 40:
            return "DEGRADED"
        return "CRITICAL"

    def export_json(self) -> str:
        with self._lock:
            metrics_snapshot = dict(self._metrics)
            alerts_snapshot = list(self._alerts)

        data = {
            "timestamp": time.time(),
            "metrics": {
                k: {
                    "value": v["value"],
                    "unit": v.get("unit", ""),
                    "trend": v.get("trend", "stable"),
                    "category": v.get("category", "general"),
                    "timestamp": v.get("timestamp", 0),
                }
                for k, v in metrics_snapshot.items()
            },
            "alerts": alerts_snapshot,
            "performance_score": self.get_performance_score(),
            "status": self.get_status_summary(),
            "collect_count": self._collect_count,
        }

        return json.dumps(data, indent=2, default=str)


_dashboard_instance: Optional[OptimizationDashboard] = None
_dashboard_lock = threading.Lock()


def get_optimization_dashboard() -> OptimizationDashboard:
    global _dashboard_instance
    if _dashboard_instance is None:
        with _dashboard_lock:
            if _dashboard_instance is None:
                _dashboard_instance = OptimizationDashboard()
                logger.info("OptimizationDashboard singleton created")
    return _dashboard_instance
