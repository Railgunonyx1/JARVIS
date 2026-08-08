"""Performance Analyzer Engine — metric recording, trend analysis, and health scoring."""

import time
import math
import threading
import logging
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.evolution_engine.performance_analyzer")

_MAX_HISTORY = 10000


class PerformanceAnalyzerEngine:
    """Records metrics, computes trends, and derives a holistic health score."""

    def __init__(self) -> None:
        self._metrics_history: Dict[str, deque] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_metric(self, name: str, value: float) -> None:
        """Record a single metric data point."""
        with self._lock:
            if name not in self._metrics_history:
                self._metrics_history[name] = deque(maxlen=_MAX_HISTORY)
            self._metrics_history[name].append((time.time(), value))

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze(self) -> Dict[str, Any]:
        """Return a comprehensive analysis across all recorded metrics."""
        with self._lock:
            snapshot = {k: list(v) for k, v in self._metrics_history.items()}

        latency_metrics = {k: v for k, v in snapshot.items() if "latency" in k or "ms" in k or "time" in k}
        throughput_metrics = {k: v for k, v in snapshot.items() if "throughput" in k or "rate" in k or "count" in k}
        error_metrics = {k: v for k, v in snapshot.items() if "error" in k or "fail" in k}

        latency_summary = self._summarise_category(latency_metrics)
        throughput_summary = self._summarise_category(throughput_metrics)
        error_summary = self._summarise_category(error_metrics)

        recommendations = self._build_recommendations(
            latency_summary, throughput_summary, error_summary
        )

        return {
            "latency": latency_summary,
            "throughput": throughput_summary,
            "errors": error_summary,
            "recommendations": recommendations,
            "total_metric_names": len(snapshot),
            "generated_at": time.time(),
        }

    def get_trend(self, metric: str, window: int = 100) -> Dict[str, Any]:
        """Return trend data for *metric* over the last *window* data points.

        ``direction`` is ``"improving"``, ``"stable"``, or ``"degrading"``.
        ``slope`` is the ordinary-least-squares slope per sample index.
        """
        with self._lock:
            series = self._metrics_history.get(metric)
            if series is None or len(series) < 2:
                return {"direction": "stable", "slope": 0.0, "data": []}

            data = list(series)[-window:]
            values = [d[1] for d in data]

        n = len(values)
        if n < 2:
            return {"direction": "stable", "slope": 0.0, "data": values}

        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n

        num = 0.0
        den = 0.0
        for i, y in enumerate(values):
            num += (i - x_mean) * (y - y_mean)
            den += (i - x_mean) ** 2

        slope = num / den if den != 0 else 0.0

        if abs(slope) < abs(y_mean) * 0.001 if y_mean != 0 else abs(slope) < 1e-6:
            direction = "stable"
        elif slope < 0:
            direction = "improving"
        else:
            direction = "degrading"

        return {"direction": direction, "slope": round(slope, 6), "data": values}

    def compare_periods(self, period1_ms: float, period2_ms: float) -> Dict[str, Any]:
        """Compare two time periods and return relative change info."""
        if period1_ms == 0:
            return {
                "period1": period1_ms,
                "period2": period2_ms,
                "change_pct": 0.0,
                "improved": False,
                "summary": "No baseline for comparison.",
            }

        change_pct = ((period2_ms - period1_ms) / period1_ms) * 100
        improved = period2_ms < period1_ms

        if abs(change_pct) < 1.0:
            summary = "Negligible change (< 1%)."
        elif improved:
            summary = f"Improved by {abs(change_pct):.1f}%."
        else:
            summary = f"Degraded by {abs(change_pct):.1f}%."

        return {
            "period1": round(period1_ms, 3),
            "period2": round(period2_ms, 3),
            "change_pct": round(change_pct, 2),
            "improved": improved,
            "summary": summary,
        }

    def get_health_score(self) -> int:
        """Return a 0-100 health score based on latency trend, error rate, throughput, memory."""
        scores: List[float] = []

        with self._lock:
            snapshot = {k: list(v) for k, v in self._metrics_history.items()}

        latency_metrics = {k: v for k, v in snapshot.items() if "latency" in k or "ms" in k}
        if latency_metrics:
            trend_scores = []
            for metric, series in latency_metrics.items():
                trend = self.get_trend(metric, window=100)
                if trend["direction"] == "improving":
                    trend_scores.append(80.0)
                elif trend["direction"] == "stable":
                    trend_scores.append(60.0)
                else:
                    trend_scores.append(30.0)
            if trend_scores:
                scores.append(sum(trend_scores) / len(trend_scores))

        error_metrics = {k: v for k, v in snapshot.items() if "error" in k or "fail" in k}
        if error_metrics:
            total_points = 0
            total_errors = 0
            for series in error_metrics.values():
                total_points += len(series)
                total_errors += sum(1 for _, v in series if v > 0)
            error_rate = total_errors / total_points if total_points > 0 else 0.0
            error_score = max(0.0, 100.0 - error_rate * 200)
            scores.append(error_score)
        else:
            scores.append(75.0)

        throughput_metrics = {k: v for k, v in snapshot.items() if "throughput" in k or "rate" in k}
        if throughput_metrics:
            latest_values = []
            for series in throughput_metrics.values():
                if series:
                    latest_values.append(series[-1][1])
            if latest_values:
                avg_throughput = sum(latest_values) / len(latest_values)
                if avg_throughput > 100:
                    scores.append(90.0)
                elif avg_throughput > 50:
                    scores.append(70.0)
                elif avg_throughput > 10:
                    scores.append(50.0)
                else:
                    scores.append(30.0)
        else:
            scores.append(70.0)

        memory_metrics = {k: v for k, v in snapshot.items() if "memory" in k or "mem" in k}
        if memory_metrics:
            latest_mem = []
            for series in memory_metrics.values():
                if series:
                    latest_mem.append(series[-1][1])
            if latest_mem:
                avg_mem = sum(latest_mem) / len(latest_mem)
                if avg_mem < 300:
                    scores.append(90.0)
                elif avg_mem < 500:
                    scores.append(70.0)
                elif avg_mem < 800:
                    scores.append(50.0)
                else:
                    scores.append(25.0)
        else:
            scores.append(70.0)

        if not scores:
            return 70

        health = int(sum(scores) / len(scores))
        return max(0, min(100, health))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _summarise_category(self, metrics: Dict[str, list]) -> Dict[str, Any]:
        if not metrics:
            return {"count": 0, "avg": None, "min": None, "max": None}

        all_values: List[float] = []
        per_metric: Dict[str, dict] = {}
        for name, series in metrics.items():
            values = [v for _, v in series]
            all_values.extend(values)
            n = len(values)
            per_metric[name] = {
                "count": n,
                "avg": round(sum(values) / n, 3) if n else 0.0,
                "min": round(min(values), 3) if n else 0.0,
                "max": round(max(values), 3) if n else 0.0,
            }

        total = len(all_values)
        return {
            "count": total,
            "avg": round(sum(all_values) / total, 3) if total else None,
            "min": round(min(all_values), 3) if total else None,
            "max": round(max(all_values), 3) if total else None,
            "per_metric": per_metric,
        }

    def _build_recommendations(
        self,
        latency: Dict[str, Any],
        throughput: Dict[str, Any],
        errors: Dict[str, Any],
    ) -> List[str]:
        recommendations: List[str] = []

        if latency.get("avg") is not None and latency["avg"] > 500:
            recommendations.append(
                f"Average latency is high ({latency['avg']:.0f}ms). "
                "Consider caching frequent queries or parallelising pipeline stages."
            )

        if latency.get("max") is not None and latency["max"] > 2000:
            recommendations.append(
                f"P99+ latency spikes to {latency['max']:.0f}ms. "
                "Investigate outliers — possible resource contention or cold starts."
            )

        if errors.get("count") is not None and errors["count"] > 0:
            error_avg = errors.get("avg", 0) or 0
            if error_avg > 0.1:
                recommendations.append(
                    f"Error rate is elevated (avg {error_avg:.2f}). "
                    "Review error logs and add retry/fallback logic where appropriate."
                )

        if throughput.get("count") is not None and throughput["count"] > 0:
            avg_tp = throughput.get("avg", 0) or 0
            if avg_tp < 10:
                recommendations.append(
                    f"Throughput is low (avg {avg_tp:.1f}/s). "
                    "Consider batch processing or increasing concurrency."
                )

        if not recommendations:
            recommendations.append("All metrics are within healthy thresholds. No action needed.")

        return recommendations


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_instance: Optional[PerformanceAnalyzerEngine] = None
_lock = threading.Lock()


def get_performance_analyzer_engine() -> PerformanceAnalyzerEngine:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = PerformanceAnalyzerEngine()
    return _instance
