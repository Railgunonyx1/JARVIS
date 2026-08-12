"""HyperResourcePredictor — Predicts resource exhaustion before it happens."""

import logging
import threading
import time
from collections import deque

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

logger = logging.getLogger("jarvis.hyper_opt.resource_predictor")


class HyperResourcePredictor:
    def __init__(self):
        self._history: deque = deque(maxlen=2000)
        self._predictions: dict = {}
        self._thresholds: dict = {
            "ram_percent": {"warning": 70, "critical": 85, "limit_mb": 7500},
            "cpu_percent": {"warning": 70, "critical": 90, "limit_percent": 95},
            "disk_percent": {"warning": 80, "critical": 95, "limit_percent": 98},
        }
        self._lock: threading.RLock = threading.RLock()
        self._collection_interval: float = 2.0
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._snapshots_collected: int = 0
        self._predictions_made: int = 0
        self._alerts_triggered: int = 0

    def collect_snapshot(self) -> dict:
        if psutil is None:
            logger.warning("psutil not installed; returning synthetic snapshot")
            snapshot = {
                "timestamp": time.time(),
                "cpu_percent": 0.0,
                "ram_percent": 0.0,
                "ram_used_mb": 0.0,
                "disk_percent": 0.0,
                "disk_io_read_bytes": 0,
                "disk_io_write_bytes": 0,
                "network_io_sent_bytes": 0,
                "network_io_recv_bytes": 0,
            }
        else:
            vm = psutil.virtual_memory()
            disk = psutil.disk_io_counters() or psutil._common.sdiskio(0, 0, 0, 0, 0, 0)
            net = psutil.net_io_counters() or psutil._common.snetio(0, 0, 0, 0, 0, 0, 0, 0)
            snapshot = {
                "timestamp": time.time(),
                "cpu_percent": psutil.cpu_percent(interval=0),
                "ram_percent": vm.percent,
                "ram_used_mb": vm.used / (1024 * 1024),
                "disk_percent": psutil.disk_usage("/").percent if hasattr(psutil, "disk_usage") else 0.0,
                "disk_io_read_bytes": disk.read_bytes,
                "disk_io_write_bytes": disk.write_bytes,
                "network_io_sent_bytes": net.bytes_sent,
                "network_io_recv_bytes": net.bytes_recv,
            }
        with self._lock:
            self._history.append(snapshot)
            self._snapshots_collected += 1
        return snapshot

    def predict(self, resource_name: str, horizon_seconds: float = 60) -> dict:
        with self._lock:
            self._predictions_made += 1
            history = list(self._history)

        if len(history) < 3:
            return {
                "resource": resource_name,
                "value": None,
                "confidence": 0.0,
                "time_to_limit": None,
                "error": "insufficient_data",
            }

        key_map = {
            "cpu_percent": "cpu_percent",
            "ram_percent": "ram_percent",
            "disk_percent": "disk_percent",
            "ram_used_mb": "ram_used_mb",
        }
        key = key_map.get(resource_name, resource_name)
        values = [(s["timestamp"], s.get(key)) for s in history if key in s]
        if len(values) < 3:
            return {
                "resource": resource_name,
                "value": None,
                "confidence": 0.0,
                "time_to_limit": None,
                "error": "resource_not_tracked",
            }

        n = len(values)
        ts = [v[0] for v in values]
        ys = [v[1] for v in values]
        base_t = ts[0]
        x = [(t - base_t) for t in ts]
        y = list(ys)

        mean_x = sum(x) / n
        mean_y = sum(y) / n
        ss_xy = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        ss_xx = sum((x[i] - mean_x) ** 2 for i in range(n))

        if ss_xx == 0:
            slope = 0.0
            intercept = mean_y
        else:
            slope = ss_xy / ss_xx
            intercept = mean_y - slope * mean_x

        last_x = x[-1]
        predicted_value = intercept + slope * (last_x + horizon_seconds)

        residuals = [y[i] - (intercept + slope * x[i]) for i in range(n)]
        sse = sum(r ** 2 for r in residuals)
        variance = max(mean_y ** 2, 1e-9)
        r_squared = max(0.0, 1.0 - sse / (n * variance))

        volatility = (sum(r ** 2 for r in residuals) / n) ** 0.5
        stability = max(0.0, 1.0 - min(volatility / max(abs(mean_y), 1e-9), 1.0))
        confidence = round((r_squared * 0.6 + stability * 0.4) * 100, 1)

        thresholds = self._thresholds.get(resource_name, {})
        limit_value = thresholds.get("limit_percent", thresholds.get("limit_mb", None))
        time_to_limit = None
        if limit_value is not None and slope > 0:
            seconds_to_limit = (limit_value - y[-1]) / slope
            if seconds_to_limit > 0:
                time_to_limit = round(seconds_to_limit, 1)

        clamped_value = max(0.0, predicted_value) if predicted_value is not None else None
        result = {
            "resource": resource_name,
            "value": round(clamped_value, 2) if clamped_value is not None else None,
            "confidence": confidence,
            "time_to_limit": time_to_limit,
            "current": round(y[-1], 2),
            "slope_per_second": round(slope, 6),
        }

        with self._lock:
            self._predictions[resource_name] = result
        return result

    def predict_all(self, horizon_seconds: float = 60) -> dict:
        resources = ["cpu_percent", "ram_percent", "disk_percent", "ram_used_mb"]
        return {r: self.predict(r, horizon_seconds) for r in resources}

    def get_time_to_limit(self, resource_name: str) -> float | None:
        prediction = self.predict(resource_name, horizon_seconds=300)
        ttl = prediction.get("time_to_limit")
        return ttl

    def should_throttle(self) -> dict:
        with self._lock:
            history = list(self._history)

        if not history:
            return {"should": False, "reason": "no_data", "severity": "none"}

        latest = history[-1]
        for resource, thresholds in self._thresholds.items():
            key = resource
            current_value = latest.get(key)
            if current_value is None:
                continue

            critical = thresholds.get("critical", 999)
            warning = thresholds.get("warning", 999)

            if resource == "ram_percent" and "limit_mb" in thresholds:
                if latest.get("ram_used_mb", 0) >= thresholds["limit_mb"]:
                    return {
                        "should": True,
                        "reason": f"{resource} over memory limit",
                        "severity": "critical",
                    }

            if current_value >= critical:
                return {
                    "should": True,
                    "reason": f"{resource} at {current_value:.1f}% (critical >= {critical}%)",
                    "severity": "critical",
                }

            if current_value >= warning:
                return {
                    "should": True,
                    "reason": f"{resource} at {current_value:.1f}% (warning >= {warning}%)",
                    "severity": "warning",
                }

        prediction = self.predict("cpu_percent", horizon_seconds=30)
        ttl = prediction.get("time_to_limit")
        if ttl is not None and ttl < 10:
            return {
                "should": True,
                "reason": f"CPU limit estimated in {ttl:.1f}s",
                "severity": "warning",
            }

        return {"should": False, "reason": "all_resources_nominal", "severity": "none"}

    def get_recommendations(self) -> list:
        recommendations = []
        with self._lock:
            history = list(self._history)

        if len(history) < 5:
            return [{"priority": "info", "message": "Collecting data for recommendations..."}]

        latest = history[-1]
        for resource, thresholds in self._thresholds.items():
            current_value = latest.get(resource)
            if current_value is None:
                continue

            warning = thresholds.get("warning", 999)
            critical = thresholds.get("critical", 999)

            if current_value >= critical:
                recommendations.append({
                    "priority": "critical",
                    "resource": resource,
                    "message": f"{resource} is critically high ({current_value:.1f}%). "
                               f"Consider reducing workload immediately.",
                })
            elif current_value >= warning:
                recommendations.append({
                    "priority": "warning",
                    "resource": resource,
                    "message": f"{resource} is elevated ({current_value:.1f}%). "
                               f"Monitor closely and prepare mitigation.",
                })

        cpu_pred = self.predict("cpu_percent", horizon_seconds=60)
        if cpu_pred.get("time_to_limit") is not None and cpu_pred["time_to_limit"] < 30:
            recommendations.append({
                "priority": "warning",
                "resource": "cpu_percent",
                "message": f"CPU predicted to hit limit in {cpu_pred['time_to_limit']:.1f}s. "
                           f"Consider deferring non-critical tasks.",
            })

        ram_pred = self.predict("ram_percent", horizon_seconds=120)
        if ram_pred.get("time_to_limit") is not None and ram_pred["time_to_limit"] < 60:
            recommendations.append({
                "priority": "warning",
                "resource": "ram_percent",
                "message": f"RAM predicted to hit limit in {ram_pred['time_to_limit']:.1f}s. "
                           f"Consider releasing cached objects.",
            })

        if not recommendations:
            recommendations.append({
                "priority": "info",
                "message": "All resources nominal. No action required.",
            })

        return recommendations

    def get_trend(self, resource_name: str, window: int = 50) -> dict:
        with self._lock:
            history = list(self._history)

        key_map = {
            "cpu_percent": "cpu_percent",
            "ram_percent": "ram_percent",
            "disk_percent": "disk_percent",
            "ram_used_mb": "ram_used_mb",
        }
        key = key_map.get(resource_name, resource_name)
        values = [s.get(key) for s in history[-window:] if key in s]

        if len(values) < 3:
            return {"direction": "unknown", "slope": 0.0, "volatility": 0.0}

        n = len(values)
        x = list(range(n))
        mean_x = sum(x) / n
        mean_y = sum(values) / n
        ss_xy = sum((x[i] - mean_x) * (values[i] - mean_y) for i in range(n))
        ss_xx = sum((x[i] - mean_x) ** 2 for i in range(n))

        if ss_xx == 0:
            slope = 0.0
        else:
            slope = ss_xy / ss_xx

        residuals = [values[i] - (mean_y + slope * (x[i] - mean_x)) for i in range(n)]
        volatility = (sum(r ** 2 for r in residuals) / n) ** 0.5

        if slope > 0.05:
            direction = "increasing"
        elif slope < -0.05:
            direction = "decreasing"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "slope": round(slope, 6),
            "volatility": round(volatility, 4),
        }

    def _monitoring_loop(self):
        while self._running:
            snapshot = self.collect_snapshot()
            throttle = self.should_throttle()
            if throttle["should"]:
                with self._lock:
                    self._alerts_triggered += 1
                logger.warning("Throttle recommended: %s", throttle["reason"])
            time.sleep(self._collection_interval)

    def start_monitoring(self, interval_seconds: float = 2.0):
        with self._lock:
            if self._running:
                logger.warning("Monitoring already running")
                return
            self._collection_interval = interval_seconds
            self._running = True
            self._thread = threading.Thread(
                target=self._monitoring_loop,
                name="hyper-resource-predictor",
                daemon=True,
            )
            self._thread.start()
            logger.info("Resource monitoring started (interval=%.1fs)", interval_seconds)

    def stop_monitoring(self):
        with self._lock:
            if not self._running:
                return
            self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
            logger.info("Resource monitoring stopped")

    def get_current(self) -> dict:
        return self.collect_snapshot()

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "snapshots_collected": self._snapshots_collected,
                "predictions_made": self._predictions_made,
                "alerts_triggered": self._alerts_triggered,
                "history_size": len(self._history),
                "monitoring_active": self._running,
            }

    def get_health_score(self) -> int:
        with self._lock:
            history = list(self._history)

        if not history:
            return 100

        latest = history[-1]
        scores = []

        for resource, thresholds in self._thresholds.items():
            current_value = latest.get(resource)
            if current_value is None:
                continue

            warning = thresholds.get("warning", 70)
            critical = thresholds.get("critical", 90)
            if critical <= warning:
                critical = warning + 20

            if current_value <= warning:
                score = 100 - (current_value / warning) * 20
            elif current_value <= critical:
                score = 80 - ((current_value - warning) / (critical - warning)) * 50
            else:
                score = max(0, 30 - (current_value - critical) / (100 - critical) * 30)

            scores.append(score)

        if not scores:
            return 100

        overall = int(round(sum(scores) / len(scores)))
        return max(0, min(100, overall))


_predictor_instance: HyperResourcePredictor | None = None
_predictor_lock = threading.Lock()


def get_hyper_resource_predictor() -> HyperResourcePredictor:
    global _predictor_instance
    if _predictor_instance is None:
        with _predictor_lock:
            if _predictor_instance is None:
                _predictor_instance = HyperResourcePredictor()
                logger.info("HyperResourcePredictor singleton created")
    return _predictor_instance
