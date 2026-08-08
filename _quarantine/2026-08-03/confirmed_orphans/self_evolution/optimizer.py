"""Self-Optimizer — Analyzes performance, applies safe optimizations with rollback."""

import time
import json
import copy
import sqlite3
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from self_evolution.performance_monitor import PerformanceMonitor

logger = logging.getLogger("jarvis.self_evolution.optimizer")

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "self_evolution.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS optimization_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suggestion_id TEXT UNIQUE NOT NULL,
    area TEXT NOT NULL,
    suggestion TEXT NOT NULL,
    impact TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    action TEXT NOT NULL DEFAULT '',
    config_snapshot TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'suggested',
    created_at REAL NOT NULL,
    applied_at REAL DEFAULT NULL,
    rolled_back_at REAL DEFAULT NULL,
    result_notes TEXT DEFAULT ''
);
"""


@dataclass
class OptimizationSuggestion:
    area: str
    suggestion: str
    impact: str
    confidence: float
    suggestion_id: str = ""
    action: str = ""
    status: str = "suggested"
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.suggestion_id:
            self.suggestion_id = f"opt_{int(self.created_at * 1000)}"


class SelfOptimizer:
    """Analyzes system performance and suggests/applies optimizations safely."""

    def __init__(
        self,
        monitor: PerformanceMonitor,
        db_path: Optional[Path] = None,
    ):
        self._monitor = monitor
        self._db_path = db_path or _DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_CREATE_SQL)
        self._conn.commit()

        self._config_versions: dict[str, list[dict]] = {}
        logger.info("SelfOptimizer initialized")

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze_performance(self, window_hours: float = 24.0) -> list[OptimizationSuggestion]:
        """Analyze current metrics and produce optimization suggestions."""
        summary = self._monitor.get_summary(window_hours)
        bottlenecks = self._monitor.get_bottlenecks(top_n=5, window_hours=window_hours)
        suggestions: list[OptimizationSuggestion] = []

        for b in bottlenecks:
            name = b["name"]
            avg = b["avg_value"]
            stats = summary.get("metrics", {}).get(name, {})
            p95 = stats.get("p95") or avg
            regresses = self._monitor.detect_regression(name, window_hours)

            if regresses:
                suggestions.append(OptimizationSuggestion(
                    area=name,
                    suggestion=f"Regression detected in '{name}': p95={p95} avg={avg}. Investigate root cause.",
                    impact="high",
                    confidence=0.8,
                    action="flag_regression",
                ))

            if p95 > avg * 2 and avg > 0:
                suggestions.append(OptimizationSuggestion(
                    area=name,
                    suggestion=f"High variance in '{name}': p95 ({p95}) > 2x avg ({avg}). Consider caching or batching.",
                    impact="medium",
                    confidence=0.6,
                    action="optimize_variance",
                ))

            if avg > 0 and p95 > 1000:
                suggestions.append(OptimizationSuggestion(
                    area=name,
                    suggestion=f"Slow operation '{name}' (avg {avg}ms, p95 {p95}ms). Consider async processing.",
                    impact="high",
                    confidence=0.7,
                    action="make_async",
                ))

        if not suggestions:
            suggestions.append(OptimizationSuggestion(
                area="system",
                suggestion="All metrics within acceptable thresholds.",
                impact="none",
                confidence=0.9,
            ))

        for s in suggestions:
            self._store_suggestion(s)

        return suggestions

    # ------------------------------------------------------------------
    # Apply / Rollback
    # ------------------------------------------------------------------

    def apply_suggestion(self, suggestion_id: str) -> bool:
        """Mark a suggestion as applied and snapshot current config state."""
        with self._lock:
            row = self._conn.execute(
                "SELECT suggestion_id, status, area, action FROM optimization_history WHERE suggestion_id = ?",
                (suggestion_id,),
            ).fetchone()

            if not row:
                logger.warning("Suggestion %s not found", suggestion_id)
                return False

            if row[1] != "suggested":
                logger.warning("Suggestion %s is in state '%s', cannot apply", suggestion_id, row[1])
                return False

            snapshot = json.dumps(self._snapshot_config(row[2]))
            now = time.time()

            self._conn.execute(
                """UPDATE optimization_history
                   SET status = 'applied', applied_at = ?, config_snapshot = ?
                   WHERE suggestion_id = ?""",
                (now, snapshot, suggestion_id),
            )
            self._conn.commit()

        logger.info("Applied optimization %s", suggestion_id)
        return True

    def rollback_suggestion(self, suggestion_id: str) -> bool:
        """Rollback an applied suggestion using its config snapshot."""
        with self._lock:
            row = self._conn.execute(
                "SELECT suggestion_id, status, config_snapshot, area FROM optimization_history WHERE suggestion_id = ?",
                (suggestion_id,),
            ).fetchall()

            if not row:
                logger.warning("Suggestion %s not found", suggestion_id)
                return False

            _, status, snapshot_json, area = row[0]

            if status not in ("applied", "regression_detected"):
                logger.warning("Cannot rollback suggestion %s (status=%s)", suggestion_id, status)
                return False

            snapshot = json.loads(snapshot_json) if snapshot_json else {}
            self._restore_config(area, snapshot)

            self._conn.execute(
                "UPDATE optimization_history SET status = 'rolled_back', rolled_back_at = ? WHERE suggestion_id = ?",
                (time.time(), suggestion_id),
            )
            self._conn.commit()

        logger.info("Rolled back optimization %s", suggestion_id)
        return True

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_optimization_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent optimization history entries."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT suggestion_id, area, suggestion, impact, confidence,
                          status, created_at, applied_at, rolled_back_at, result_notes
                   FROM optimization_history ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()

        return [
            {
                "suggestion_id": r[0],
                "area": r[1],
                "suggestion": r[2],
                "impact": r[3],
                "confidence": r[4],
                "status": r[5],
                "created_at": r[6],
                "applied_at": r[7],
                "rolled_back_at": r[8],
                "result_notes": r[9],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Regression monitoring
    # ------------------------------------------------------------------

    def check_applied_regressions(self, window_hours: float = 12.0) -> list[str]:
        """Check all applied suggestions for regressions and auto-rollback if needed."""
        rolled_back: list[str] = []
        with self._lock:
            rows = self._conn.execute(
                "SELECT suggestion_id, area FROM optimization_history WHERE status = 'applied'"
            ).fetchall()

        for sid, area in rows:
            if self._monitor.detect_regression(area, window_hours):
                with self._lock:
                    self._conn.execute(
                        """UPDATE optimization_history
                           SET status = 'regression_detected', result_notes = 'Auto-flagged regression'
                           WHERE suggestion_id = ?""",
                        (sid,),
                    )
                    self._conn.commit()
                self.rollback_suggestion(sid)
                rolled_back.append(sid)
                logger.warning("Auto-rolled back %s due to regression in %s", sid, area)

        return rolled_back

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _store_suggestion(self, s: OptimizationSuggestion) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO optimization_history
                   (suggestion_id, area, suggestion, impact, confidence, action, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (s.suggestion_id, s.area, s.suggestion, s.impact, s.confidence, s.action, s.status, s.created_at),
            )
            self._conn.commit()

    def _snapshot_config(self, area: str) -> dict[str, Any]:
        """Capture a snapshot of the relevant config area for rollback."""
        try:
            from core.config import Config
            cfg = Config.instance()
            return {area: cfg.get(area)}
        except Exception:
            return {}

    def _restore_config(self, area: str, snapshot: dict[str, Any]) -> None:
        """Restore a previously captured config snapshot."""
        if not snapshot or area not in snapshot:
            logger.info("No config snapshot to restore for area '%s'", area)
            return
        try:
            from core.config import Config
            cfg = Config.instance()
            cfg.set(area, snapshot[area])
            logger.info("Restored config area '%s'", area)
        except Exception as e:
            logger.error("Failed to restore config area '%s': %s", area, e)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
