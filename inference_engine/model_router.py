"""Model Router — intelligent query-to-model selection with performance tracking."""

import re
import time
import threading
import logging
from typing import Dict, Optional

logger = logging.getLogger("jarvis.inference_engine.model_router")

_TECHNICAL_TERMS = re.compile(
    r"\b(algorithm|function|class|variable|api|database|sql|regex|compile|debug|"
    r"refactor|implement|deploy|kubernetes|docker|nginx|ssh|git|ci/cd|pipeline|"
    r"encrypt|authenticate|payload|endpoint|middleware|binary|kernel|thread|"
    r"concurrency|mutex|semaphore|stack|heap|pointer|array|loop| recursion)\b",
    re.IGNORECASE,
)

_CREATIVE_TERMS = re.compile(
    r"\b(write|compose|draft|story|poem|creative|brainstorm|imagine|design|"
    r"narrative|dialogue|character|plot|metaphor|analogy|slogan|tagline|"
    r"advertising|copywriting|marketing|blog|article|essay|summary|tone|"
    r"rewrite|rephrase|paraphrase|synonym|fluent)\b",
    re.IGNORECASE,
)

_CODE_PATTERNS = re.compile(
    r"(def |class |import |from |return |if |for |while |try:|except|raise |"
    r"lambda |async |await |yield |\{|\}|\[.*\]\s*=|=>|->|#include|#define)",
)

_SIMPLE_PATTERNS = re.compile(
    r"^(what|who|when|where|how much|how many|is|are|can you|define|"
    r"translate|convert|calculate|sum of|date|time|weather|time)\b",
    re.IGNORECASE,
)


class ModelRouter:
    """Selects the optimal model/provider for a given query based on complexity heuristics."""

    _MODEL_MAP = {
        "simple": ("ollama", "llama3.2:latest", "Local model for trivial queries"),
        "medium": ("groq", "llama-3.1-70b-versatile", "Fast cloud model for moderate tasks"),
        "complex": ("gemini", "gemini-2.0-flash", "High-capability model for complex reasoning"),
        "creative": ("openrouter", "mistralai/mistral-7b-instruct", "Creative model for open-ended tasks"),
    }

    def __init__(self) -> None:
        self._stats: Dict[str, dict] = {}
        self._preference: str = "balanced"
        self._lock = threading.Lock()

    def select_model(self, query: str, context: dict = None) -> dict:
        """Return the recommended provider, model, and routing reason for *query*."""
        category = self._classify(query, context)
        provider, model, default_reason = self._MODEL_MAP[category]

        with self._lock:
            stats = self._stats.get(f"{provider}/{model}", {})

        boosted_reason = default_reason
        if self._preference == "speed":
            if category != "simple":
                boosted_reason += " (preference: speed → prefer fast provider)"
        elif self._preference == "quality":
            if category == "simple":
                provider, model, default_reason = self._MODEL_MAP["medium"]
                boosted_reason = "Upgraded for quality preference"

        return {
            "provider": provider,
            "model": model,
            "category": category,
            "reason": boosted_reason,
        }

    def _classify(self, query: str, context: dict = None) -> str:
        """Classify query complexity into simple/medium/complex/creative."""
        words = query.split()
        word_count = len(words)

        if _CREATIVE_TERMS.search(query):
            return "creative"

        code_hits = len(_CODE_PATTERNS.findall(query))
        tech_hits = len(_TECHNICAL_TERMS.findall(query))

        if word_count <= 6 and _SIMPLE_PATTERNS.match(query):
            return "simple"

        if code_hits >= 2 or tech_hits >= 3 or word_count > 40:
            return "complex"

        if word_count > 15 or tech_hits >= 1:
            return "medium"

        if context and context.get("task_type") == "creative":
            return "creative"

        return "medium"

    def record_outcome(
        self,
        provider: str,
        model: str,
        latency_ms: float,
        success: bool,
        tokens: int = 0,
    ) -> None:
        """Record the outcome of a request to a specific model for routing decisions."""
        key = f"{provider}/{model}"
        with self._lock:
            if key not in self._stats:
                self._stats[key] = {
                    "total": 0,
                    "successes": 0,
                    "failures": 0,
                    "total_latency_ms": 0.0,
                    "total_tokens": 0,
                }
            s = self._stats[key]
            s["total"] += 1
            s["total_latency_ms"] += latency_ms
            s["total_tokens"] += tokens
            if success:
                s["successes"] += 1
            else:
                s["failures"] += 1

    def get_model_stats(self) -> dict:
        """Return per-model success rate, average latency, and usage count."""
        with self._lock:
            snapshot = dict(self._stats)
        result: dict = {}
        for key, s in snapshot.items():
            total = s["total"]
            result[key] = {
                "usage_count": total,
                "success_rate": s["successes"] / total if total else 0.0,
                "avg_latency_ms": s["total_latency_ms"] / total if total else 0.0,
                "total_tokens": s["total_tokens"],
            }
        return result

    def setPreference(self, preference: str) -> None:
        """Set routing preference: 'speed', 'quality', or 'balanced'."""
        if preference not in ("speed", "quality", "balanced"):
            raise ValueError(f"Invalid preference: {preference!r}. Use 'speed', 'quality', or 'balanced'.")
        self._preference = preference
        logger.info("Model preference set to %s", preference)


_model_router: Optional[ModelRouter] = None
_model_router_lock = threading.Lock()


def get_model_router() -> ModelRouter:
    global _model_router
    if _model_router is None:
        with _model_router_lock:
            if _model_router is None:
                _model_router = ModelRouter()
    return _model_router
