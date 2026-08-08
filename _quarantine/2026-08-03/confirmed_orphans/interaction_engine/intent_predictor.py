"""Intent Predictor — N-gram frequency-based next-intent prediction with pattern mining."""

import time
import math
import logging
import threading
from typing import Optional
from collections import Counter, defaultdict

logger = logging.getLogger("jarvis.interaction_engine.intent_predictor")


class IntentPredictor:
    """Predicts next intents using n-gram frequency analysis over observed intent sequences."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sequences: list[list[str]] = []
        self._pattern_cache: dict[str, list[dict]] = {}
        self._predictions_made: int = 0
        self._predictions_correct: int = 0
        self._recent_predictions: list[dict] = []
        self._ngram_counts: dict[tuple, Counter] = defaultdict(Counter)
        self._context_counts: dict[str, Counter] = defaultdict(Counter)

    def predict_next(self, current_intent: str, history: list, context: dict = None) -> list[dict]:
        """Return top-3 predicted next intents with probabilities."""
        context = context or {}
        ngram_predictions = self._ngram_predictions(current_intent, history)
        context_predictions = self._context_predictions(current_intent, context)
        frequency_predictions = self._frequency_predictions(history)

        combined: dict[str, float] = {}
        reasons: dict[str, str] = {}

        for pred in ngram_predictions:
            intent = pred["intent"]
            combined[intent] = combined.get(intent, 0.0) + pred["probability"] * 0.5
            reasons[intent] = pred["reason"]

        for pred in context_predictions:
            intent = pred["intent"]
            combined[intent] = combined.get(intent, 0.0) + pred["probability"] * 0.3
            if intent not in reasons:
                reasons[intent] = pred["reason"]

        for pred in frequency_predictions:
            intent = pred["intent"]
            combined[intent] = combined.get(intent, 0.0) + pred["probability"] * 0.2
            if intent not in reasons:
                reasons[intent] = pred["reason"]

        ranked = sorted(combined.items(), key=lambda x: -x[1])[:3]

        total = sum(prob for _, prob in ranked) or 1.0
        results = []
        for intent, raw_prob in ranked:
            normalized = raw_prob / total if total > 0 else 0.0
            results.append({
                "intent": intent,
                "probability": round(min(normalized, 1.0), 4),
                "reason": reasons.get(intent, "statistical pattern"),
            })

        if not results:
            results = [{"intent": "general.chat", "probability": 1.0, "reason": "default fallback"}]

        with self._lock:
            self._predictions_made += 1
            if results:
                self._recent_predictions.append({
                    "predicted": [r["intent"] for r in results],
                    "timestamp": time.time(),
                })
                if len(self._recent_predictions) > 200:
                    self._recent_predictions = self._recent_predictions[-200:]

        return results

    def _ngram_predictions(self, current_intent: str, history: list) -> list[dict]:
        """Use bigram/trigram patterns from historical sequences."""
        results = []
        with self._lock:
            for (n, prefix), counter in self._ngram_counts.items():
                if n == 2:
                    if len(history) >= 1 and history[-1] == prefix:
                        total = sum(counter.values()) or 1
                        for intent, count in counter.most_common(3):
                            results.append({
                                "intent": intent,
                                "probability": count / total,
                                "reason": f"bigram({history[-1]} -> ?)",
                            })
                elif n == 3:
                    if len(history) >= 2 and history[-2] == prefix[0] and history[-1] == prefix[1]:
                        total = sum(counter.values()) or 1
                        for intent, count in counter.most_common(3):
                            results.append({
                                "intent": intent,
                                "probability": count / total,
                                "reason": f"trigram({prefix[0]},{prefix[1]} -> ?)",
                            })
        return results

    def _context_predictions(self, current_intent: str, context: dict) -> list[dict]:
        """Use context keys (time_of_day, mode, etc.) to predict."""
        results = []
        with self._lock:
            for key, value in context.items():
                context_key = f"{key}:{value}"
                counter = self._context_counts.get(context_key)
                if counter:
                    total = sum(counter.values()) or 1
                    for intent, count in counter.most_common(2):
                        results.append({
                            "intent": intent,
                            "probability": count / total,
                            "reason": f"context({context_key})",
                        })
        return results

    def _frequency_predictions(self, history: list) -> list[dict]:
        """Fallback: predict based on overall frequency of intents seen after current."""
        if not history:
            return []
        last = history[-1]
        with self._lock:
            counter = self._context_counts.get(f"last:{last}")
            if counter:
                total = sum(counter.values()) or 1
                return [
                    {"intent": intent, "probability": count / total, "reason": f"frequency({last})"}
                    for intent, count in counter.most_common(3)
                ]
        return []

    def record_sequence(self, intents: list) -> None:
        """Record an intent sequence for pattern mining and n-gram updates."""
        if len(intents) < 2:
            return

        with self._lock:
            self._sequences.append(list(intents))
            if len(self._sequences) > 5000:
                self._sequences = self._sequences[-5000:]

            self._pattern_cache.clear()

            for i in range(len(intents) - 1):
                bigram_key = (2, intents[i])
                self._ngram_counts[bigram_key][intents[i + 1]] += 1

            for i in range(len(intents) - 2):
                trigram_key = (3, (intents[i], intents[i + 1]))
                self._ngram_counts[trigram_key][intents[i + 2]] += 1

            for i, intent in enumerate(intents):
                if i < len(intents) - 1:
                    self._context_counts[f"last:{intent}"][intents[i + 1]] += 1

    def record_with_context(self, intent: str, context: dict) -> None:
        """Record an intent with its context for context-based prediction."""
        with self._lock:
            for key, value in context.items():
                context_key = f"{key}:{value}"
                self._context_counts[context_key][intent] += 1

    def get_patterns(self, min_length: int = 2, min_support: int = 2) -> list[dict]:
        """Return frequent intent patterns (sequences) meeting min_length and min_support."""
        cache_key = f"{min_length}:{min_support}"
        with self._lock:
            if cache_key in self._pattern_cache:
                return self._pattern_cache[cache_key]

        pattern_counter: dict[tuple, int] = Counter()

        with self._lock:
            for seq in self._sequences:
                if len(seq) < min_length:
                    continue
                for start in range(len(seq) - min_length + 1):
                    sub = tuple(seq[start:start + min_length])
                    pattern_counter[sub] += 1

        results = []
        for pattern_tuple, count in pattern_counter.most_common(50):
            if count >= min_support:
                # Compute confidence: support(pattern) / support(prefix)
                prefix = pattern_tuple[:-1]
                prefix_count = 0
                with self._lock:
                    for seq in self._sequences:
                        for start in range(len(seq) - len(prefix) + 1):
                            if tuple(seq[start:start + len(prefix)]) == prefix:
                                prefix_count += 1

                confidence = count / prefix_count if prefix_count > 0 else 0.0
                results.append({
                    "pattern": list(pattern_tuple),
                    "support": count,
                    "confidence": round(confidence, 4),
                    "length": len(pattern_tuple),
                })

        with self._lock:
            self._pattern_cache[cache_key] = results

        return results

    def record_prediction_outcome(self, predicted_intents: list, actual_intent: str) -> None:
        """Record whether a prediction was correct for accuracy tracking."""
        with self._lock:
            self._predictions_correct += 1 if actual_intent in predicted_intents else 0
            if self._recent_predictions:
                self._recent_predictions[-1]["actual"] = actual_intent
                self._recent_predictions[-1]["correct"] = actual_intent in predicted_intents

    def get_prediction_accuracy(self) -> dict:
        """Return recent prediction stats."""
        with self._lock:
            total = self._predictions_made
            correct = self._predictions_correct
            recent = self._recent_predictions[-50:] if self._recent_predictions else []

            recent_correct = sum(1 for p in recent if p.get("correct", False))
            recent_total = len(recent) if recent else 0

        return {
            "total_predictions": total,
            "correct_predictions": correct,
            "overall_accuracy": round(correct / total, 4) if total > 0 else 0.0,
            "recent_accuracy": round(recent_correct / recent_total, 4) if recent_total > 0 else 0.0,
            "recent_sample_size": recent_total,
            "total_sequences_recorded": len(self._sequences),
        }

    def get_stats(self) -> dict:
        """Return internal statistics for debugging."""
        with self._lock:
            ngram_count = len(self._ngram_counts)
            context_count = len(self._context_counts)
        return {
            "sequences": len(self._sequences),
            "ngram_entries": ngram_count,
            "context_entries": context_count,
            "pattern_cache_size": len(self._pattern_cache),
        }


_instance: Optional[IntentPredictor] = None
_instance_lock = threading.Lock()


def get_intent_predictor() -> IntentPredictor:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = IntentPredictor()
    return _instance
