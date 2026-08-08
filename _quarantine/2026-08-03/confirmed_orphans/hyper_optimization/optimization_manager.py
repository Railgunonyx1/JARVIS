"""JARVIS MK-X Hyper-Optimization Engine — Central Optimization Manager.

Coordinates all hyper-optimization subsystems, enforces latency budgets,
and maintains a full optimization history with improvement tracking.
"""

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.hyper_opt.optimization_manager")


class OptimizationManager:
    """Central coordinator for all hyper-optimization subsystems."""

    def __init__(self):
        self._engines: Dict[str, Any] = {}
        self._optimization_history: List[Dict[str, Any]] = []
        self._latency_budgets: Dict[str, float] = {
            "voice": 80,
            "memory": 40,
            "planning": 30,
            "inference": 250,
            "execution": 70,
            "speech": 80,
        }
        self._budget_violations: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self._initialization_time = time.perf_counter()
        logger.info("OptimizationManager initialized")

    def register_engine(self, name: str, engine: Any) -> None:
        """Register a hyper-optimization engine."""
        with self._lock:
            if name in self._engines:
                logger.warning("Overwriting existing engine '%s'", name)
            self._engines[name] = engine
            logger.info("Registered engine '%s': %s", name, type(engine).__name__)

    def unregister_engine(self, name: str) -> bool:
        """Remove a registered engine. Returns True if found and removed."""
        with self._lock:
            if name not in self._engines:
                logger.warning("Engine '%s' not found for unregistration", name)
                return False
            del self._engines[name]
            logger.info("Unregistered engine '%s'", name)
            return True

    def get_engine(self, name: str) -> Optional[Any]:
        """Retrieve a registered engine by name."""
        with self._lock:
            return self._engines.get(name)

    def get_overall_health(self) -> Dict[str, Any]:
        """Returns aggregate metrics from all engines."""
        with self._lock:
            engine_health: Dict[str, Any] = {}
            total_score = 0.0
            engine_count = 0

            for name, engine in self._engines.items():
                health = self._extract_engine_health(name, engine)
                engine_health[name] = health
                total_score += health.get("score", 0.0)
                engine_count += 1

            avg_score = total_score / engine_count if engine_count > 0 else 0.0
            uptime_s = time.perf_counter() - self._initialization_time

            return {
                "overall_score": round(avg_score, 2),
                "engine_count": engine_count,
                "engines": engine_health,
                "uptime_seconds": round(uptime_s, 2),
                "budget_violations": len(self._budget_violations),
                "optimizations_applied": len(self._optimization_history),
                "status": "healthy" if avg_score >= 70 else "degraded" if avg_score >= 40 else "critical",
            }

    def _extract_engine_health(self, name: str, engine: Any) -> Dict[str, Any]:
        """Extract health metrics from an engine via standard interface."""
        try:
            if hasattr(engine, "get_stats"):
                stats = engine.get_stats()
                if isinstance(stats, dict):
                    return {"score": stats.get("score", 50.0), "details": stats}
            if hasattr(engine, "get_accuracy"):
                acc = engine.get_accuracy()
                if isinstance(acc, dict):
                    return {"score": acc.get("accuracy", 50.0) * 100, "details": acc}
            if hasattr(engine, "get_profile"):
                prof = engine.get_profile()
                if isinstance(prof, dict):
                    score = max(0, min(100, 100 - prof.get("p95", 50)))
                    return {"score": score, "details": prof}
        except Exception as exc:
            logger.error("Failed to extract health from engine '%s': %s", name, exc)
        return {"score": 50.0, "details": {"note": "no standard health interface"}}

    def get_latency_budgets(self) -> Dict[str, float]:
        """Returns current latency budgets per stage."""
        with self._lock:
            return dict(self._latency_budgets)

    def set_latency_budget(self, stage: str, budget_ms: float) -> None:
        """Update the latency budget for a specific stage."""
        with self._lock:
            old = self._latency_budgets.get(stage)
            self._latency_budgets[stage] = budget_ms
            logger.info("Latency budget for '%s': %s ms -> %s ms", stage, old, budget_ms)

    def enforce_budget(self, stage: str, actual_ms: float) -> Dict[str, Any]:
        """Check if stage exceeded budget, return degradation suggestion."""
        with self._lock:
            budget = self._latency_budgets.get(stage, 100.0)
            overage = actual_ms - budget
            within_budget = actual_ms <= budget

            result: Dict[str, Any] = {
                "stage": stage,
                "budget_ms": budget,
                "actual_ms": round(actual_ms, 3),
                "overage_ms": round(max(0, overage), 3),
                "within_budget": within_budget,
                "utilization_pct": round((actual_ms / budget) * 100, 1) if budget > 0 else 100.0,
                "suggestion": None,
            }

            if not within_budget:
                violation = {
                    "stage": stage,
                    "budget_ms": budget,
                    "actual_ms": actual_ms,
                    "timestamp": time.time(),
                }
                self._budget_violations.append(violation)
                if len(self._budget_violations) > 1000:
                    self._budget_violations = self._budget_violations[-500:]

                ratio = actual_ms / budget if budget > 0 else float("inf")
                if ratio > 3.0:
                    result["suggestion"] = f"CRITICAL: {stage} is {ratio:.1f}x over budget. Consider caching, async offload, or disabling."
                elif ratio > 2.0:
                    result["suggestion"] = f"SEVERE: {stage} is {ratio:.1f}x over budget. Enable aggressive sampling reduction."
                elif ratio > 1.5:
                    result["suggestion"] = f"WARNING: {stage} is {ratio:.1f}x over budget. Reduce profile sampling rate."
                else:
                    result["suggestion"] = f"MINOR: {stage} slightly over budget ({ratio:.1f}x). Monitor for trends."

                logger.warning(
                    "Budget violation on '%s': %.1f ms (budget %.1f ms, overage %.1f ms)",
                    stage, actual_ms, budget, overage,
                )

            return result

    def get_violations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns recent budget violations, most recent first."""
        with self._lock:
            return list(reversed(self._budget_violations[-limit:]))

    def get_optimization_report(self) -> Dict[str, Any]:
        """Full system report with all metrics."""
        with self._lock:
            health = self.get_overall_health()
            violations_summary: Dict[str, int] = {}
            for v in self._budget_violations:
                stage = v["stage"]
                violations_summary[stage] = violations_summary.get(stage, 0) + 1

            improvement_total = 0.0
            for opt in self._optimization_history:
                before = opt.get("before_ms", 0)
                after = opt.get("after_ms", 0)
                if before > 0:
                    improvement_total += before - after

            return {
                "health": health,
                "latency_budgets": self.get_latency_budgets(),
                "violations_summary": violations_summary,
                "total_violations": len(self._budget_violations),
                "optimizations_applied": len(self._optimization_history),
                "total_improvement_ms": round(improvement_total, 3),
                "recent_optimizations": self._optimization_history[-10:],
            }

    def record_optimization(
        self,
        name: str,
        before: float,
        after: float,
        description: str = "",
    ) -> None:
        """Record an applied optimization."""
        with self._lock:
            entry = {
                "name": name,
                "before_ms": round(before, 3),
                "after_ms": round(after, 3),
                "improvement_ms": round(before - after, 3),
                "improvement_pct": round(((before - after) / before) * 100, 1) if before > 0 else 0.0,
                "description": description,
                "timestamp": time.time(),
            }
            self._optimization_history.append(entry)
            if len(self._optimization_history) > 500:
                self._optimization_history = self._optimization_history[-250:]

            logger.info(
                "Optimization '%s': %.1f ms -> %.1f ms (%.1f%% improvement)",
                name, before, after, entry["improvement_pct"],
            )

    def get_improvements(self) -> List[Dict[str, Any]]:
        """Returns list of applied optimizations with gains."""
        with self._lock:
            return list(self._optimization_history)

    def get_top_improvements(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns top improvements sorted by absolute time saved."""
        with self._lock:
            sorted_opts = sorted(
                self._optimization_history,
                key=lambda x: x.get("improvement_ms", 0),
                reverse=True,
            )
            return sorted_opts[:limit]

    def reset(self) -> None:
        """Reset all tracking data."""
        with self._lock:
            self._optimization_history.clear()
            self._budget_violations.clear()
            self._initialization_time = time.perf_counter()
            logger.info("OptimizationManager reset")


_manager_instance: Optional[OptimizationManager] = None
_manager_lock = threading.RLock()


def get_optimization_manager() -> OptimizationManager:
    """Singleton accessor for OptimizationManager."""
    global _manager_instance
    with _manager_lock:
        if _manager_instance is None:
            _manager_instance = OptimizationManager()
        return _manager_instance
