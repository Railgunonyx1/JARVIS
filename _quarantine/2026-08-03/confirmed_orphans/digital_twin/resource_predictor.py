"""Resource Predictor - Predictive analytics for system resources in JARVIS MK-X.

Provides moving average prediction, linear regression trend-based prediction,
z-score anomaly detection, and configurable alert thresholds.
"""

import logging
import math
import threading
from enum import Enum
from typing import Any

logger = logging.getLogger("jarvis.digital_twin.predictor")


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ResourceType(str, Enum):
    CPU = "cpu_usage"
    RAM = "ram_usage"
    DISK_READ = "disk_io_read_bytes"
    DISK_WRITE = "disk_io_write_bytes"
    NET_SENT = "net_io_sent_bytes"
    NET_RECV = "net_io_recv_bytes"
    PROCESS_COUNT = "process_count"


_DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    ResourceType.CPU.value: {"warning": 70.0, "critical": 90.0},
    ResourceType.RAM.value: {"warning": 75.0, "critical": 90.0},
    ResourceType.PROCESS_COUNT.value: {"warning": 400.0, "critical": 600.0},
}


class ResourcePredictor:
    def __init__(self, thresholds: dict[str, dict[str, float]] | None = None):
        self._thresholds = thresholds or dict(_DEFAULT_THRESHOLDS)
        self._lock = threading.Lock()
        self._history_cache: dict[str, list[float]] = {}
        self._cache_timestamps: dict[str, list[float]] = {}
        self._cache_max_age: float = 5.0
        self._cache_set_at: float = 0.0

    def simple_moving_average(
        self, values: list[float], window: int = 10
    ) -> float:
        if not values:
            return 0.0
        w = min(window, len(values))
        return sum(values[:w]) / w

    def weighted_moving_average(
        self, values: list[float], window: int = 10
    ) -> float:
        if not values:
            return 0.0
        w = min(window, len(values))
        total_weight = w * (w + 1) / 2
        weighted_sum = sum(
            values[i] * (w - i) for i in range(w)
        )
        return weighted_sum / total_weight

    def linear_regression_prediction(
        self, timestamps: list[float], values: list[float], seconds_ahead: float = 0
    ) -> dict[str, Any]:
        n = len(values)
        if n < 2:
            return {
                "predicted": values[0] if values else 0.0,
                "slope": 0.0,
                "r_squared": 0.0,
                "confidence": "low",
                "data_points": n,
            }

        x_mean = sum(timestamps) / n
        y_mean = sum(values) / n
        num = sum((timestamps[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        den = sum((timestamps[i] - x_mean) ** 2 for i in range(n))

        if abs(den) < 1e-12:
            slope = 0.0
            intercept = y_mean
        else:
            slope = num / den
            intercept = y_mean - slope * x_mean

        predicted = slope * (timestamps[0] + seconds_ahead) + intercept

        ss_res = sum(
            (values[i] - (slope * timestamps[i] + intercept)) ** 2
            for i in range(n)
        )
        ss_tot = sum((values[i] - y_mean) ** 2 for i in range(n))
        r_squared = 1.0 - (ss_res / ss_tot) if abs(ss_tot) > 1e-12 else 0.0

        confidence = "high"
        if r_squared < 0.5:
            confidence = "low"
        elif r_squared < 0.8:
            confidence = "medium"

        return {
            "predicted": round(predicted, 2),
            "slope": round(slope, 6),
            "intercept": round(intercept, 4),
            "r_squared": round(r_squared, 4),
            "confidence": confidence,
            "data_points": n,
        }

    def detect_anomalies_zscore(
        self, current: float, history: list[float], threshold: float = 2.5
    ) -> dict[str, Any]:
        n = len(history)
        if n < 5:
            return {
                "is_anomaly": False,
                "z_score": 0.0,
                "reason": "insufficient_history",
                "threshold": threshold,
            }

        mean = sum(history) / n
        variance = sum((v - mean) ** 2 for v in history) / n
        std = math.sqrt(variance)

        if std < 1e-12:
            return {
                "is_anomaly": False,
                "z_score": 0.0,
                "reason": "constant_values",
                "threshold": threshold,
            }

        z = (current - mean) / std
        is_anomaly = abs(z) > threshold

        if is_anomaly:
            direction = "above" if z > 0 else "below"
            reason = f"Value {current:.1f} is {direction} normal range (z={z:.2f}, mean={mean:.1f}, std={std:.1f})"
        else:
            reason = "within_normal_range"

        return {
            "is_anomaly": is_anomaly,
            "z_score": round(z, 3),
            "reason": reason,
            "mean": round(mean, 2),
            "std": round(std, 2),
            "threshold": threshold,
            "direction": "above" if z > 0 else "below",
        }

    def detect_anomalies_iqr(
        self, current: float, history: list[float], multiplier: float = 1.5
    ) -> dict[str, Any]:
        n = len(history)
        if n < 10:
            return {
                "is_anomaly": False,
                "reason": "insufficient_history",
            }

        sorted_vals = sorted(history)
        q1_idx = n // 4
        q3_idx = (3 * n) // 4
        q1 = sorted_vals[q1_idx]
        q3 = sorted_vals[q3_idx]
        iqr = q3 - q1

        lower = q1 - multiplier * iqr
        upper = q3 + multiplier * iqr

        is_anomaly = current < lower or current > upper

        if is_anomaly:
            direction = "above" if current > upper else "below"
            reason = f"Value {current:.1f} is {direction} IQR bounds [{lower:.1f}, {upper:.1f}]"
        else:
            reason = "within_normal_range"

        return {
            "is_anomaly": is_anomaly,
            "lower_bound": round(lower, 2),
            "upper_bound": round(upper, 2),
            "q1": round(q1, 2),
            "q3": round(q3, 2),
            "iqr": round(iqr, 2),
            "reason": reason,
        }

    def check_thresholds(self, metric: str, value: float) -> dict[str, Any] | None:
        thresholds = self._thresholds.get(metric)
        if not thresholds:
            return None

        critical = thresholds.get("critical", float("inf"))
        warning = thresholds.get("warning", float("inf"))

        if value >= critical:
            return {
                "metric": metric,
                "value": round(value, 2),
                "severity": AlertSeverity.CRITICAL.value,
                "threshold": critical,
                "message": f"{metric} is at {value:.1f}% (critical threshold: {critical}%)",
            }
        elif value >= warning:
            return {
                "metric": metric,
                "value": round(value, 2),
                "severity": AlertSeverity.WARNING.value,
                "threshold": warning,
                "message": f"{metric} is at {value:.1f}% (warning threshold: {warning}%)",
            }

        return {
            "metric": metric,
            "value": round(value, 2),
            "severity": AlertSeverity.INFO.value,
            "message": f"{metric} is within normal range ({value:.1f}%)",
        }

    def set_threshold(self, metric: str, warning: float, critical: float):
        with self._lock:
            self._thresholds[metric] = {"warning": warning, "critical": critical}

    def get_thresholds(self) -> dict[str, dict[str, float]]:
        with self._lock:
            return dict(self._thresholds)

    def multi_step_forecast(
        self,
        timestamps: list[float],
        values: list[float],
        steps: int = 6,
        step_seconds: float = 300.0,
    ) -> list[dict[str, Any]]:
        if len(timestamps) < 2 or len(values) < 2:
            return []

        forecast = []
        base_time = timestamps[0]

        for i in range(1, steps + 1):
            ahead = step_seconds * i
            result = self.linear_regression_prediction(timestamps, values, ahead)
            forecast.append({
                "step": i,
                "seconds_ahead": ahead,
                "minutes_ahead": round(ahead / 60, 1),
                "predicted_value": result["predicted"],
                "confidence": result["confidence"],
                "r_squared": result["r_squared"],
            })

        return forecast

    def compute_ema(
        self, values: list[float], span: int = 10
    ) -> list[float]:
        if not values:
            return []
        alpha = 2.0 / (span + 1)
        ema = [values[-1]]
        for i in range(len(values) - 2, -1, -1):
            ema.append(values[i] * alpha + ema[-1] * (1 - alpha))
        ema.reverse()
        return ema

    def rate_of_change(
        self, values: list[float], timestamps: list[float] | None = None
    ) -> dict[str, Any]:
        n = len(values)
        if n < 2:
            return {"current_rate": 0.0, "average_rate": 0.0}

        if timestamps and len(timestamps) == n:
            dt = timestamps[0] - timestamps[-1]
            if abs(dt) < 1e-6:
                current_rate = 0.0
            else:
                current_rate = (values[0] - values[-1]) / dt
        else:
            current_rate = values[0] - values[1]

        rates = [
            values[i] - values[i + 1] for i in range(n - 1)
        ]
        avg_rate = sum(rates) / len(rates) if rates else 0.0

        return {
            "current_rate": round(current_rate, 6),
            "average_rate": round(avg_rate, 6),
            "acceleration": round(current_rate - avg_rate, 6),
            "is_accelerating": abs(current_rate) > abs(avg_rate) * 1.5,
        }

    def get_prediction_summary(self, snapshots: list[Any]) -> dict[str, Any]:
        if not snapshots:
            return {"status": "no_data", "predictions": {}}

        timestamps = [s.timestamp for s in snapshots]
        cpu_vals = [s.cpu_usage for s in snapshots]
        ram_vals = [s.ram_usage for s in snapshots]

        cpu_sma = self.simple_moving_average(cpu_vals, window=10)
        ram_sma = self.simple_moving_average(ram_vals, window=10)

        cpu_lr = self.linear_regression_prediction(timestamps, cpu_vals, seconds_ahead=300)
        ram_lr = self.linear_regression_prediction(timestamps, ram_vals, seconds_ahead=300)

        cpu_roc = self.rate_of_change(cpu_vals, timestamps)
        ram_roc = self.rate_of_change(ram_vals, timestamps)

        alerts = []
        for metric, value in [("cpu_usage", cpu_vals[0]), ("ram_usage", ram_vals[0])]:
            alert = self.check_thresholds(metric, value)
            if alert and alert["severity"] != AlertSeverity.INFO.value:
                alerts.append(alert)

        return {
            "status": "ok",
            "data_points": len(snapshots),
            "predictions": {
                "cpu": {
                    "current": round(cpu_vals[0], 1),
                    "sma_10": round(cpu_sma, 1),
                    "predicted_5min": cpu_lr["predicted"],
                    "confidence": cpu_lr["confidence"],
                    "r_squared": cpu_lr["r_squared"],
                    "rate_of_change": cpu_roc["current_rate"],
                },
                "ram": {
                    "current": round(ram_vals[0], 1),
                    "sma_10": round(ram_sma, 1),
                    "predicted_5min": ram_lr["predicted"],
                    "confidence": ram_lr["confidence"],
                    "r_squared": ram_lr["r_squared"],
                    "rate_of_change": ram_roc["current_rate"],
                },
            },
            "alerts": alerts,
        }
