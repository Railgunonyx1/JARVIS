"""Partial-STT Router — handles incomplete speech-to-text transcriptions
that arrive as partial results before the final utterance.

Strategy:
  1. On each partial text, run intent classifier for fast-path detection
  2. If confidence is high enough, prepare the action speculatively
  3. When final text arrives, verify against speculation
  4. For low-confidence partials, do nothing (wait for completion)

This avoids wasted work on partials like "op" (from "open chrome") while
catching early signals like "git sta" (from "git status").
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from core.agent.intent import Intent, IntentClassifier

logger = logging.getLogger("jarvis.partial_stt")


@dataclass
class PartialPrediction:
    text: str
    intent: Intent
    confidence: float
    tool_name: str | None
    ready: bool = False


class PartialSTTRouter:
    """Routes partial STT text to intent classifier for early detection."""

    MIN_CONFIDENCE = 0.7
    MIN_LENGTH = 3

    def __init__(self, classifier: IntentClassifier):
        self._classifier = classifier
        self._history: list[PartialPrediction] = []

    def on_partial(self, text: str) -> PartialPrediction | None:
        if not text or len(text.strip()) < self.MIN_LENGTH:
            return None

        result = self._classifier.classify(text)

        prediction = PartialPrediction(
            text=text,
            intent=result.intent,
            confidence=result.confidence,
            tool_name=result.tool_name,
            ready=(result.intent == Intent.INSTANT and result.confidence >= self.MIN_CONFIDENCE),
        )

        if prediction.ready:
            logger.debug("Partial-STT ready: %s → %s (%.0f%%)",
                         text[:30], result.tool_name, result.confidence * 100)

        self._history.append(prediction)
        return prediction

    def on_final(self, text: str) -> PartialPrediction | None:
        result = self._classifier.classify(text)

        prediction = PartialPrediction(
            text=text,
            intent=result.intent,
            confidence=result.confidence,
            tool_name=result.tool_name,
            ready=(result.intent == Intent.INSTANT),
        )
        return prediction

    def get_stats(self) -> dict[str, Any]:
        if not self._history:
            return {"partials": 0}
        ready_count = sum(1 for p in self._history if p.ready)
        return {
            "partials": len(self._history),
            "ready_count": ready_count,
            "ready_rate": round(ready_count / len(self._history), 3),
            "avg_confidence": round(
                sum(p.confidence for p in self._history) / len(self._history), 3
            ),
        }
