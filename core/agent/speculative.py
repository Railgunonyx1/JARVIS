"""Speculative Intent Executor — prepare actions during partial STT.

While speech-to-text is still producing partial text, this module predicts
the likely intent and prepares the tool call. When transcription finishes,
verification confirms the prediction before execution.

Latency savings: overlaps STT with intent classification + tool prep.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from core.agent.intent import Intent, IntentClassifier

logger = logging.getLogger("jarvis.speculative")


@dataclass
class SpeculativePrediction:
    """A predicted intent from partial text."""
    text: str
    classifier_result: Any = None
    prepared: bool = False
    confidence: float = 0.0


class SpeculativeExecutor:
    """Feeds partial STT text into the intent classifier and prepares
    tool calls speculatively.

    Usage:
        spec = SpeculativeExecutor(classifier)
        spec.on_partial("open chro")
        spec.on_partial("open chrome")
        prediction = spec.verify("open chrome")
        if prediction and prediction.classifier_result.tool_name:
            # Execute immediately — no LLM needed
    """

    def __init__(self, classifier: IntentClassifier):
        self._classifier = classifier
        self._current: SpeculativePrediction | None = None
        self._prepared_tool_call: Any = None

    def on_partial(self, partial_text: str) -> SpeculativePrediction | None:
        """Called as STT produces partial text. Returns prediction if confident."""
        if not partial_text or len(partial_text.strip()) < 3:
            return None

        result = self._classifier.classify(partial_text)
        prediction = SpeculativePrediction(
            text=partial_text,
            classifier_result=result,
            confidence=result.confidence,
        )

        if result.intent == Intent.INSTANT and result.tool_name:
            prediction.prepared = True
            logger.debug("Speculative: prepared %s for '%s'", result.tool_name, partial_text[:30])

        self._current = prediction
        return prediction

    def verify(self, final_text: str) -> SpeculativePrediction | None:
        """Called when STT finishes. Verifies the speculation matches."""
        if self._current is None:
            return None

        final_result = self._classifier.classify(final_text)

        if (self._current.classifier_result.intent == final_result.intent
                and self._current.classifier_result.tool_name == final_result.tool_name):
            self._current.classifier_result = final_result
            return self._current

        self._current = None
        return None

    def cancel(self) -> None:
        """Cancel speculation (e.g., STT was interrupted)."""
        self._current = None
        self._prepared_tool_call = None
