"""Trust Scorer — computes action trust scores based on history, context, and patterns."""

from __future__ import annotations

import time
import math
import logging
import threading
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.security.trust_scorer")

_BASE_TRUST = 0.7
_HISTORY_LIMIT = 100


class TrustScorer:
    """Thread-safe trust scorer that adapts to action outcomes."""

    def __init__(self) -> None:
        self._trust_data: Dict[str, dict] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score_action(self, action: str, context: Optional[dict] = None) -> dict:
        """Return a trust assessment for *action*.

        Returns dict with keys ``trust_score`` (0-1), ``risk_level``, and
        ``factors`` (list of contributing strings).
        """
        context = context or {}
        factors: List[str] = []

        with self._lock:
            data = self._get_or_create(action)

        score = data["base_score"]
        factors.append(f"base={score:.2f}")

        # Factor: success rate
        total = data["successes"] + data["failures"]
        if total > 0:
            success_rate = data["successes"] / total
            adjustment = (success_rate - 0.5) * 0.3
            score += adjustment
            factors.append(f"success_rate={success_rate:.2f}(adj={adjustment:+.3f})")

        # Factor: time of day
        hour = time.localtime().tm_hour
        if 2 <= hour <= 5:
            score -= 0.1
            factors.append("unusual_hours=-0.10")
        elif 9 <= hour <= 17:
            score += 0.02
            factors.append("business_hours=+0.02")

        # Factor: system state
        throttle = context.get("throttle_level", 0)
        if throttle >= 2:
            score -= 0.1
            factors.append(f"high_load=-0.10(throttle={throttle})")
        elif throttle == 1:
            score -= 0.03
            factors.append(f"moderate_load=-0.03(throttle={throttle})")

        # Factor: recent user overrides
        if context.get("user_override"):
            score -= 0.05
            factors.append("user_override=-0.05")

        score = max(0.0, min(1.0, score))
        risk_level = _trust_to_risk(score)

        return {
            "trust_score": round(score, 4),
            "risk_level": risk_level,
            "factors": factors,
        }

    def record_outcome(
        self,
        action: str,
        success: bool,
        user_approved: bool = True,
    ) -> None:
        """Record the outcome of an executed action."""
        with self._lock:
            data = self._get_or_create(action)
            if success:
                data["successes"] += 1
            else:
                data["failures"] += 1

            total = data["successes"] + data["failures"]
            if total > 0:
                success_rate = data["successes"] / total
                data["base_score"] = 0.5 + (success_rate * 0.4)

            if not user_approved:
                data["base_score"] = max(0.1, data["base_score"] - 0.05)

            data["history"].append({
                "timestamp": time.perf_counter(),
                "success": success,
                "user_approved": user_approved,
                "score": data["base_score"],
            })

    def get_trust_history(self, action: str) -> list:
        """Return recent trust score snapshots for *action*."""
        with self._lock:
            if action not in self._trust_data:
                return []
            return list(self._trust_data[action]["history"])

    def adjust_trust(self, action: str, delta: float) -> None:
        """Manually adjust the base trust for an action."""
        with self._lock:
            data = self._get_or_create(action)
            data["base_score"] = max(0.0, min(1.0, data["base_score"] + delta))
            logger.info(
                "Trust for '%s' adjusted by %+.3f -> %.3f",
                action,
                delta,
                data["base_score"],
            )

    def get_overall_trust(self) -> float:
        """Return the average trust across all tracked actions."""
        with self._lock:
            if not self._trust_data:
                return _BASE_TRUST
            total = sum(d["base_score"] for d in self._trust_data.values())
            return round(total / len(self._trust_data), 4)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_or_create(self, action: str) -> dict:
        """Return (or create) the trust data for *action*. Caller must hold lock."""
        if action not in self._trust_data:
            self._trust_data[action] = {
                "base_score": _BASE_TRUST,
                "successes": 0,
                "failures": 0,
                "history": deque(maxlen=_HISTORY_LIMIT),
            }
        return self._trust_data[action]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trust_to_risk(score: float) -> str:
    if score >= 0.8:
        return "low"
    if score >= 0.5:
        return "medium"
    if score >= 0.3:
        return "high"
    return "critical"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[TrustScorer] = None
_instance_lock = threading.Lock()


def get_trust_scorer() -> TrustScorer:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = TrustScorer()
    return _instance
