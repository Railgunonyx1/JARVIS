"""JARVIS MK-X Hyper-Optimization Engine — Branch Predictor.

Learns user behavior patterns from intent sequences and predicts
likely next actions using n-gram frequency analysis with backoff.
"""

import logging
import threading
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.hyper_opt.branch_predictor")


class BranchPredictor:
    """Learns user behavior patterns to predict next actions."""

    def __init__(self, max_history: int = 500, max_ngram: int = 4):
        self._max_history = max_history
        self._max_ngram = max_ngram
        self._sequences: List[List[str]] = []
        self._ngram_counts: Dict[Tuple[str, ...], Counter] = {}
        self._context_counts: Dict[Tuple[str, ...], Counter] = {}
        self._predictions_made = 0
        self._predictions_correct = 0
        self._recent_predictions: List[Dict[str, Any]] = []
        self._intent_frequencies: Counter = Counter()
        self._lock = threading.RLock()
        logger.info(
            "BranchPredictor initialized (max_history=%d, max_ngram=%d)",
            max_history, max_ngram,
        )

    def record_sequence(self, intents: List[str]) -> None:
        """Record a sequence of intents (last 5-10 actions)."""
        if not intents:
            return

        with self._lock:
            self._sequences.append(list(intents))
            if len(self._sequences) > self._max_history:
                self._sequences = self._sequences[-self._max_history:]

            for intent in intents:
                self._intent_frequencies[intent] += 1

            # Build n-gram counts from this sequence
            for n in range(1, self._max_ngram + 1):
                for i in range(len(intents) - n):
                    context = tuple(intents[i:i + n])
                    next_intent = intents[i + n]
                    if context not in self._ngram_counts:
                        self._ngram_counts[context] = Counter()
                    self._ngram_counts[context][next_intent] += 1

                    # Also track full context (all preceding intents)
                    full_context = tuple(intents[:i + n])
                    if full_context not in self._context_counts:
                        self._context_counts[full_context] = Counter()
                    self._context_counts[full_context][next_intent] += 1

            logger.debug("Recorded sequence of %d intents", len(intents))

    def predict(self, recent_intents: List[str], top_n: int = 5) -> List[Dict[str, Any]]:
        """Predict likely next intents. Returns list of {intent, probability, reason}."""
        if not recent_intents:
            return self._fallback_predictions(top_n)

        with self._lock:
            candidates: Dict[str, Dict[str, Any]] = {}

            # Try longest n-gram first, back off to shorter
            for n in range(min(len(recent_intents), self._max_ngram), 0, -1):
                context = tuple(recent_intents[-n:])
                if context in self._ngram_counts:
                    total = sum(self._ngram_counts[context].values())
                    if total == 0:
                        continue
                    weight = n * 10  # longer context = higher confidence

                    for intent, count in self._ngram_counts[context].most_common(top_n * 2):
                        prob = (count / total) * weight
                        reason = f"n-gram({n}): '{' -> '.join(context)}' -> '{intent}' ({count}/{total})"
                        if intent in candidates:
                            candidates[intent]["probability"] += prob
                            candidates[intent]["reason"] += f"; {reason}"
                        else:
                            candidates[intent] = {
                                "intent": intent,
                                "probability": prob,
                                "reason": reason,
                            }

            # Boost with global frequency
            if self._intent_frequencies:
                total_global = sum(self._intent_frequencies.values())
                for intent in list(candidates.keys()):
                    freq = self._intent_frequencies.get(intent, 0)
                    freq_boost = (freq / total_global) * 2.0 if total_global > 0 else 0
                    candidates[intent]["probability"] += freq_boost

            # Exclude intents already in recent history (avoid repeats)
            recent_set = set(recent_intents[-3:])
            for intent in list(candidates.keys()):
                if intent in recent_set:
                    candidates[intent]["probability"] *= 0.3

            if not candidates:
                return self._fallback_predictions(top_n)

            # Sort by probability and normalize
            sorted_candidates = sorted(
                candidates.values(), key=lambda c: c["probability"], reverse=True,
            )[:top_n]

            max_prob = sorted_candidates[0]["probability"] if sorted_candidates else 1.0
            if max_prob > 0:
                for c in sorted_candidates:
                    c["probability"] = round(c["probability"] / max_prob, 4)

            self._predictions_made += 1
            self._recent_predictions.append({
                "context": recent_intents[-5:],
                "top_prediction": sorted_candidates[0]["intent"] if sorted_candidates else None,
                "timestamp": time.time(),
            })
            if len(self._recent_predictions) > 100:
                self._recent_predictions = self._recent_predictions[-50:]

            return sorted_candidates

    def _fallback_predictions(self, top_n: int) -> List[Dict[str, Any]]:
        """Provide fallback predictions based on global frequency."""
        with self._lock:
            if not self._intent_frequencies:
                return []
            total = sum(self._intent_frequencies.values())
            results = []
            for intent, count in self._intent_frequencies.most_common(top_n):
                results.append({
                    "intent": intent,
                    "probability": round(count / total, 4) if total > 0 else 0.0,
                    "reason": f"global frequency ({count}/{total})",
                })
            if results:
                self._predictions_made += 1
            return results

    def verify_prediction(self, predicted: str, actual: str) -> bool:
        """Verify a prediction was correct. Updates accuracy stats."""
        with self._lock:
            is_correct = predicted == actual
            if is_correct:
                self._predictions_correct += 1
            logger.debug(
                "Prediction verify: predicted='%s', actual='%s', correct=%s",
                predicted, actual, is_correct,
            )
            return is_correct

    def get_accuracy(self) -> Dict[str, Any]:
        """Returns accuracy, total_predictions, correct_predictions."""
        with self._lock:
            total = self._predictions_made
            correct = self._predictions_correct
            accuracy = correct / total if total > 0 else 0.0
            return {
                "accuracy": round(accuracy, 4),
                "accuracy_pct": round(accuracy * 100, 1),
                "total_predictions": total,
                "correct_predictions": correct,
                "missed_predictions": total - correct,
            }

    def get_patterns(self, min_support: int = 3) -> List[Dict[str, Any]]:
        """Returns most frequent behavior patterns (n-grams with sufficient support)."""
        with self._lock:
            patterns: List[Dict[str, Any]] = []
            for context, next_counts in self._ngram_counts.items():
                for intent, count in next_counts.items():
                    if count >= min_support:
                        patterns.append({
                            "context": list(context),
                            "next": intent,
                            "support": count,
                            "confidence": 0.0,
                            "n_gram_size": len(context),
                        })

            # Calculate confidence for each pattern
            for pattern in patterns:
                context = tuple(pattern["context"])
                total_context = sum(self._ngram_counts[context].values())
                pattern["confidence"] = (
                    round(pattern["support"] / total_context, 4) if total_context > 0 else 0.0
                )

            patterns.sort(key=lambda p: (p["support"], p["confidence"]), reverse=True)
            return patterns

    def get_popular_sequences(self, length: int = 3) -> List[Dict[str, Any]]:
        """Returns most common intent sequences of given length."""
        with self._lock:
            seq_counter: Counter = Counter()
            for sequence in self._sequences:
                if len(sequence) >= length:
                    # Count all subsequences of the given length
                    for i in range(len(sequence) - length + 1):
                        subseq = tuple(sequence[i:i + length])
                        seq_counter[subseq] += 1

            results = []
            for seq_tuple, count in seq_counter.most_common(20):
                results.append({
                    "sequence": list(seq_tuple),
                    "count": count,
                    "length": len(seq_tuple),
                })
            return results

    def get_intent_distribution(self) -> Dict[str, int]:
        """Returns the frequency distribution of all observed intents."""
        with self._lock:
            return dict(self._intent_frequencies.most_common())

    def get_recent_predictions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns recent prediction attempts."""
        with self._lock:
            return list(reversed(self._recent_predictions[-limit:]))

    def get_transition_probability(self, from_intent: str, to_intent: str) -> float:
        """Returns P(to_intent | from_intent) across all observed sequences."""
        with self._lock:
            key = (from_intent,)
            if key not in self._ngram_counts:
                return 0.0
            total = sum(self._ngram_counts[key].values())
            if total == 0:
                return 0.0
            return self._ngram_counts[key].get(to_intent, 0) / total

    def get_transition_matrix(self, min_probability: float = 0.05) -> Dict[str, Dict[str, float]]:
        """Returns a transition probability matrix for all intents."""
        with self._lock:
            matrix: Dict[str, Dict[str, float]] = {}
            for context, next_counts in self._ngram_counts.items():
                if len(context) != 1:
                    continue
                from_intent = context[0]
                total = sum(next_counts.values())
                if total == 0:
                    continue
                transitions: Dict[str, float] = {}
                for intent, count in next_counts.most_common():
                    prob = count / total
                    if prob >= min_probability:
                        transitions[intent] = round(prob, 4)
                if transitions:
                    if from_intent not in matrix:
                        matrix[from_intent] = {}
                    matrix[from_intent].update(transitions)
            return matrix

    def reset(self) -> None:
        """Clear all learned patterns."""
        with self._lock:
            self._sequences.clear()
            self._ngram_counts.clear()
            self._context_counts.clear()
            self._predictions_made = 0
            self._predictions_correct = 0
            self._recent_predictions.clear()
            self._intent_frequencies.clear()
            logger.info("BranchPredictor reset")


_predictor_instance: Optional[BranchPredictor] = None
_predictor_lock = threading.RLock()


def get_branch_predictor() -> BranchPredictor:
    """Singleton accessor for BranchPredictor."""
    global _predictor_instance
    with _predictor_lock:
        if _predictor_instance is None:
            _predictor_instance = BranchPredictor()
        return _predictor_instance
