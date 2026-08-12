"""Speculative Executor — runs primary with speculative fallback and predicts follow-ups."""

import logging
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any

logger = logging.getLogger("jarvis.inference_engine.speculative_executor")

_FOLLOWUP_PATTERNS: list[tuple] = [
    (re.compile(r"(?:what|who) is (.+)", re.IGNORECASE), ["tell me more about {0}", "how does {0} work"]),
    (re.compile(r"(?:how to|how do I) (.+)", re.IGNORECASE), ["what tools do I need for {0}", "give an example of {0}"]),
    (re.compile(r"explain (.+)", re.IGNORECASE), ["give a practical example of {0}", "what are the use cases of {0}"]),
    (re.compile(r"(?:compare|difference between) (.+) and (.+)", re.IGNORECASE), [
        "which is better for my use case {0} or {1}",
        "what are the pros and cons of {0} vs {1}",
    ]),
    (re.compile(r"(?:write|create|generate) (.+)", re.IGNORECASE), ["add tests for {0}", "optimize {0}"]),
    (re.compile(r"(?:debug|fix|resolve) (.+)", re.IGNORECASE), ["what caused {0}", "how to prevent {0} in the future"]),
    (re.compile(r"(?:install|setup|configure) (.+)", re.IGNORECASE), ["verify {0} is working", "how to update {0}"]),
    (re.compile(r"(?:why|reason) (.+)", re.IGNORECASE), ["what are the alternatives", "how to fix {0}"]),
]


class SpeculativeExecutor:
    """Executes primary call with speculative fallback on timeout and predicts follow-ups."""

    def __init__(self) -> None:
        self._predictions_cache: dict[str, Any] = {}
        self._thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="spec-exec")
        self._lock = threading.Lock()
        self._speculative_wins: int = 0
        self._speculative_losses: int = 0
        self._predictions_made: int = 0

    def speculative(self, primary_fn: Callable[[], Any], speculative_fn: Callable[[], Any], timeout: float = 2.0) -> Any:
        """Run *primary_fn*, falling back to *speculative_fn* if it exceeds *timeout* seconds.

        Both functions must be synchronous callables that take no arguments.
        """
        primary_future = self._thread_pool.submit(primary_fn)
        try:
            result = primary_future.result(timeout=timeout)
            return result
        except FuturesTimeout:
            logger.warning("Primary exceeded %.1fs timeout, trying speculative", timeout)
            primary_future.cancel()
            spec_future = self._thread_pool.submit(speculative_fn)
            try:
                result = spec_future.result(timeout=timeout)
                with self._lock:
                    self._speculative_wins += 1
                logger.info("Speculative fallback succeeded")
                return result
            except (FuturesTimeout, Exception) as exc:
                with self._lock:
                    self._speculative_losses += 1
                logger.error("Speculative fallback also failed: %s", exc)
                raise RuntimeError(f"Both primary and speculative failed: {exc}") from exc
        except Exception as exc:
            logger.warning("Primary failed: %s, trying speculative", exc)
            spec_future = self._thread_pool.submit(speculative_fn)
            try:
                result = spec_future.result(timeout=timeout)
                with self._lock:
                    self._speculative_wins += 1
                return result
            except (FuturesTimeout, Exception) as spec_exc:
                with self._lock:
                    self._speculative_losses += 1
                raise RuntimeError(f"Both primary and speculative failed. Primary: {exc}, Speculative: {spec_exc}") from spec_exc

    def predict_next(self, queries: list) -> list:
        """Predict likely follow-up queries based on patterns from *queries*."""
        all_predictions: list[str] = []
        for query in queries:
            cache_key = query.strip().lower()
            with self._lock:
                if cache_key in self._predictions_cache:
                    all_predictions.extend(self._predictions_cache[cache_key])
                    continue

            predictions: list[str] = []
            for pattern, templates in _FOLLOWUP_PATTERNS:
                match = pattern.search(query)
                if match:
                    groups = match.groups()
                    for template in templates:
                        try:
                            predictions.append(template.format(*groups))
                        except (IndexError, KeyError):
                            continue
                    break

            if not predictions:
                predictions = [
                    "can you elaborate on that",
                    "give me an example",
                    "what are the alternatives",
                ]

            all_predictions.extend(predictions)
            with self._lock:
                self._predictions_cache[cache_key] = predictions

        with self._lock:
            self._predictions_made += len(all_predictions)

        return all_predictions

    def precompute(self, predictions: list) -> None:
        """Pre-compute predictions in background threads."""
        for prediction in predictions:
            self._thread_pool.submit(self._run_precompute, prediction)

    def _run_precompute(self, prediction: str) -> None:
        """Mark a prediction as precomputed in the cache."""
        key = f"precomputed:{prediction.strip().lower()}"
        with self._lock:
            self._predictions_cache[key] = {"prediction": prediction, "precomputed_at": time.time()}

    def get_stats(self) -> dict:
        """Return speculative execution statistics."""
        with self._lock:
            return {
                "speculative_wins": self._speculative_wins,
                "speculative_losses": self._speculative_losses,
                "predictions_made": self._predictions_made,
                "cached_predictions": len(self._predictions_cache),
            }


_speculative_executor: SpeculativeExecutor | None = None
_speculative_executor_lock = threading.Lock()


def get_speculative_executor() -> SpeculativeExecutor:
    global _speculative_executor
    if _speculative_executor is None:
        with _speculative_executor_lock:
            if _speculative_executor is None:
                _speculative_executor = SpeculativeExecutor()
    return _speculative_executor
