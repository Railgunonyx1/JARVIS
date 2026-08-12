"""Performance Monitor — SQLite-backed metric tracking with regression detection."""

import logging
import math
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.self_evolution.performance_monitor")

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "self_evolution.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    timestamp REAL NOT NULL,
    tags TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_metrics_name_ts ON metrics(name, timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(timestamp);
"""

_REGRESSION_SQL = """
WITH recent AS (
    SELECT value FROM metrics
    WHERE name = ? AND timestamp >= ?
),
baseline AS (
    SELECT value FROM metrics
    WHERE name = ? AND timestamp >= ? AND timestamp < ?
)
SELECT AVG(r.value) AS recent_avg, AVG(b.value) AS baseline_avg,
       -- stddev of recent
       CASE WHEN COUNT(r.value) > 1 THEN
           (SELECT AVG((r2.value - AVG(r2.value)) * (r2.value - AVG(r2.value)))
            FROM recent r2) ELSE 0 END AS recent_var,
       CASE WHEN COUNT(r.value) > 1 THEN COUNT(r.value) ELSE 0 END AS recent_n,
       CASE WHEN COUNT(b.value) > 1 THEN
           (SELECT AVG((b2.value - AVG(b2.value)) * (b2.value - AVG(b2.value)))
            FROM baseline b2) ELSE 0 END AS baseline_var,
       CASE WHEN COUNT(b.value) > 1 THEN COUNT(b.value) ELSE 0 END AS baseline_n
FROM recent r, baseline b
"""


@dataclass
class MetricPoint:
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: dict[str, str] = field(default_factory=dict)


class PerformanceMonitor:
    """Records metrics, computes stats, detects regressions, and identifies bottlenecks."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or _DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_CREATE_SQL)
        self._conn.commit()
        logger.info("PerformanceMonitor initialized (db=%s)", self._db_path)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_metric(self, name: str, value: float, tags: dict[str, str] | None = None, timestamp: float | None = None) -> None:
        """Record a single metric point."""
        import json as _json
        point = MetricPoint(name=name, value=value, timestamp=timestamp or time.time(), tags=tags or {})
        with self._lock:
            self._conn.execute(
                "INSERT INTO metrics (name, value, timestamp, tags) VALUES (?, ?, ?, ?)",
                (point.name, point.value, point.timestamp, _json.dumps(point.tags)),
            )
            self._conn.commit()

    def record_metrics(self, points: list[MetricPoint]) -> None:
        """Batch-record multiple metric points."""
        import json as _json
        with self._lock:
            self._conn.executemany(
                "INSERT INTO metrics (name, value, timestamp, tags) VALUES (?, ?, ?, ?)",
                [(p.name, p.value, p.timestamp, _json.dumps(p.tags)) for p in points],
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_metric_stats(self, name: str, window_hours: float = 24.0) -> dict[str, Any]:
        """Return avg, p50, p95, p99, min, max, count for a metric within the window."""
        cutoff = time.time() - window_hours * 3600
        with self._lock:
            rows = self._conn.execute(
                "SELECT value FROM metrics WHERE name = ? AND timestamp >= ? ORDER BY value",
                (name, cutoff),
            ).fetchall()

        if not rows:
            return {"name": name, "count": 0, "avg": None, "p50": None, "p95": None, "p99": None, "min": None, "max": None}

        values = [r[0] for r in rows]
        n = len(values)
        avg = sum(values) / n

        def _percentile(pct: float) -> float:
            idx = min(int(math.ceil(pct / 100.0 * n)) - 1, n - 1)
            return values[max(idx, 0)]

        return {
            "name": name,
            "count": n,
            "avg": round(avg, 4),
            "p50": round(_percentile(50), 4),
            "p95": round(_percentile(95), 4),
            "p99": round(_percentile(99), 4),
            "min": round(values[0], 4),
            "max": round(values[-1], 4),
        }

    # ------------------------------------------------------------------
    # Regression detection (Z-score based)
    # ------------------------------------------------------------------

    def detect_regression(
        self,
        metric: str,
        window_hours: float = 24.0,
        z_threshold: float = 2.5,
    ) -> bool:
        """Return True if the metric shows a statistically significant regression.

        Compares recent window against the preceding baseline window of equal length.
        Uses a two-sample Z-test assuming unequal variances.
        """
        now = time.time()
        recent_start = now - window_hours * 3600
        baseline_start = recent_start - window_hours * 3600

        with self._lock:
            recent_rows = self._conn.execute(
                "SELECT value FROM metrics WHERE name = ? AND timestamp >= ?",
                (metric, recent_start),
            ).fetchall()
            baseline_rows = self._conn.execute(
                "SELECT value FROM metrics WHERE name = ? AND timestamp >= ? AND timestamp < ?",
                (metric, baseline_start, recent_start),
            ).fetchall()

        if len(recent_rows) < 3 or len(baseline_rows) < 3:
            return False

        def _stats(rows: list[tuple[float]]) -> tuple[float, float, int]:
            vals = [r[0] for r in rows]
            n = len(vals)
            mean = sum(vals) / n
            var = sum((v - mean) ** 2 for v in vals) / (n - 1) if n > 1 else 0.0
            return mean, var, n

        r_mean, r_var, r_n = _stats(recent_rows)
        b_mean, b_var, b_n = _stats(baseline_rows)

        se = math.sqrt(r_var / r_n + b_var / b_n)
        if se < 1e-12:
            return False

        z = (r_mean - b_mean) / se
        return z > z_threshold

    # ------------------------------------------------------------------
    # Bottleneck detection
    # ------------------------------------------------------------------

    def get_bottlenecks(self, top_n: int = 10, window_hours: float = 24.0) -> list[dict[str, Any]]:
        """Identify the slowest / highest-value metrics as bottlenecks."""
        cutoff = time.time() - window_hours * 3600
        with self._lock:
            rows = self._conn.execute(
                """SELECT name, AVG(value) AS avg_val, COUNT(*) AS cnt
                   FROM metrics WHERE timestamp >= ?
                   GROUP BY name ORDER BY avg_val DESC LIMIT ?""",
                (cutoff, top_n),
            ).fetchall()

        return [
            {"name": r[0], "avg_value": round(r[1], 4), "sample_count": r[2]}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_summary(self, window_hours: float = 24.0) -> dict[str, Any]:
        """Overall performance summary across all tracked metrics."""
        cutoff = time.time() - window_hours * 3600
        with self._lock:
            rows = self._conn.execute(
                """SELECT name, COUNT(*), AVG(value), MIN(value), MAX(value)
                   FROM metrics WHERE timestamp >= ?
                   GROUP BY name ORDER BY name""",
                (cutoff,),
            ).fetchall()

        metrics: dict[str, dict[str, Any]] = {}
        for r in rows:
            stats = self.get_metric_stats(r[0], window_hours)
            metrics[r[0]] = stats

        return {
            "window_hours": window_hours,
            "total_metric_names": len(metrics),
            "metrics": metrics,
            "generated_at": time.time(),
        }

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    def purge(self, older_than_hours: float = 168.0) -> int:
        """Remove metric points older than the given window (default 7 days)."""
        cutoff = time.time() - older_than_hours * 3600
        with self._lock:
            cur = self._conn.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff,))
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
