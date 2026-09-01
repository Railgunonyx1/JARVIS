"""Quality Evaluator — lets the cheap model answer first, evaluates
confidence, and escalates to a stronger model if uncertain.

Flow:
  1. Cheap/fast model answers
  2. Evaluator scores the answer (keyword signals, refusal patterns,
     length heuristics, hedging language)
  3. If score < threshold, re-route to reasoning model

This is NOT a separate LLM call — it's a rule-based heuristic that
runs in <1ms. The actual re-routing uses the model gateway's
confidence-based stepping.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("jarvis.quality_evaluator")

_REFUSAL_PATTERNS = [
    re.compile(r"\b(I('m| am) not (sure|certain|able to|confident))\b", re.I),
    re.compile(r"\b(I (can'?t|cannot|won'?t) (help|do|complete|finish))\b", re.I),
    re.compile(r"\b(I (don'?t|do not) (know|understand|have))\b", re.I),
    re.compile(r"\b(unclear|ambiguous|uncertain|insufficient)\b", re.I),
]

_HEDGE_PATTERNS = [
    re.compile(r"\b(perhaps|maybe|might|possibly|could be|it depends)\b", re.I),
    re.compile(r"\b(I (think|believe|guess|assume))\b", re.I),
    re.compile(r"\b(generally|usually|typically|often|sometimes)\b", re.I),
]

_QUALITY_SIGNALS = [
    re.compile(r"\b(specific|precise|exactly|definitely|certainly)\b", re.I),
    re.compile(r"\b(the solution|the answer|the fix|here('s| is))\b", re.I),
    re.compile(r"\b`\w+`"),  # inline code references
    re.compile(r"```"),  # code blocks
]


@dataclass
class QualityResult:
    score: float  # 0.0 (low quality) to 1.0 (high quality)
    should_escalate: bool
    signals: list[str]
    refusal_count: int
    hedge_count: int
    quality_count: int


class QualityEvaluator:
    """Rule-based evaluator for small-model answers."""

    def __init__(self, threshold: float = 0.4):
        self._threshold = threshold
        self._history: list[QualityResult] = []

    def evaluate(self, answer: str, question: str = "") -> QualityResult:
        if not answer or not answer.strip():
            return QualityResult(
                score=0.0, should_escalate=True,
                signals=["empty_answer"], refusal_count=0,
                hedge_count=0, quality_count=0,
            )

        refusals = sum(1 for p in _REFUSAL_PATTERNS if p.search(answer))
        hedges = sum(1 for p in _HEDGE_PATTERNS if p.search(answer))
        quality = sum(1 for p in _QUALITY_SIGNALS if p.search(answer))

        signals: list[str] = []

        length = len(answer.split())
        if length < 5:
            signals.append("too_short")
        elif length > 50:
            signals.append("detailed")

        if question:
            stop_q = {"the", "a", "an", "is", "are", "what", "how", "why",
                      "do", "does", "can", "could"}
            stop_a = {"the", "a", "an", "is", "are", "it", "to", "and",
                      "of", "in", "for"}
            q_words = set(question.lower().split()) - stop_q
            a_words = set(answer.lower().split()) - stop_a
            overlap = len(q_words & a_words)
            if overlap > 0:
                signals.append(f"keyword_overlap_{overlap}")

        score = 0.5
        score -= refusals * 0.2
        score -= hedges * 0.08
        score += quality * 0.1
        if length >= 10:
            score += 0.1
        if length >= 30:
            score += 0.1
        if any(s.startswith("keyword_overlap") for s in signals):
            score += 0.1
        score = max(0.0, min(1.0, score))

        if refusals > 0:
            signals.append(f"refusals_{refusals}")
        if hedges > 2:
            signals.append(f"heavy_hedging_{hedges}")
        if quality > 0:
            signals.append(f"quality_signals_{quality}")

        result = QualityResult(
            score=score,
            should_escalate=score < self._threshold,
            signals=signals,
            refusal_count=refusals,
            hedge_count=hedges,
            quality_count=quality,
        )
        self._history.append(result)
        return result

    def get_stats(self) -> dict[str, Any]:
        if not self._history:
            return {"evaluations": 0}
        scores = [r.score for r in self._history]
        escalations = sum(1 for r in self._history if r.should_escalate)
        return {
            "evaluations": len(self._history),
            "avg_score": round(sum(scores) / len(scores), 3),
            "escalation_rate": round(escalations / len(self._history), 3),
            "total_escalations": escalations,
        }
