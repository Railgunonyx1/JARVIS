"""Complexity Analyzer — scores text complexity and caches results for repeated queries."""

import hashlib
import logging
import re
import threading
import time

logger = logging.getLogger("jarvis.inference_engine.complexity_analyzer")

_CACHE_TTL = 600.0

_CODE_KEYWORDS = re.compile(
    r"\b(def|class|import|return|if|for|while|try|except|raise|lambda|async|await|"
    r"function|const|let|var|interface|type|struct|enum|public|private|static|void|"
    r"new|this|self|print|log|console)\b",
    re.IGNORECASE,
)

_TECHNICAL_KEYWORDS = re.compile(
    r"\b(algorithm|implementation|architecture|infrastructure|authentication|"
    r"encryption|optimization|refactoring|serialization|deserialization|"
    r"microservice|kubernetes|distributed|concurrent|asynchronous|latency|"
    r"throughput|scalability|idempotent|deterministic|polymorphism)\b",
    re.IGNORECASE,
)

_QUESTION_MARKERS = re.compile(
    r"^(what|why|how|when|where|who|which|explain|describe|compare|contrast|"
    r"analyze|evaluate|discuss|justify|critique|propose|design|implement)\b",
    re.IGNORECASE,
)


class ComplexityAnalyzer:
    """Scores input text on a 0–1 complexity scale with factor breakdown and result caching."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple] = {}
        self._lock = threading.Lock()
        self._analyzed_count: int = 0
        self._category_counts: dict[str, int] = {
            "trivial": 0,
            "simple": 0,
            "moderate": 0,
            "complex": 0,
            "expert": 0,
        }

    def analyze(self, text: str) -> dict:
        """Analyze text complexity and return score (0-1), contributing factors, and category."""
        now = time.perf_counter()
        text_hash = self._hash(text)

        with self._lock:
            cached = self._cache.get(text_hash)
            if cached is not None:
                result, expiry = cached
                if now < expiry:
                    return result

        factors: list[dict] = []
        score = 0.0

        words = text.split()
        word_count = len(words)
        sentences = re.split(r"[.!?]+", text)
        sentence_count = max(len([s for s in sentences if s.strip()]), 1)
        avg_words_per_sentence = word_count / sentence_count

        wc_score = min(word_count / 100.0, 1.0)
        factors.append({"factor": "word_count", "value": word_count, "contribution": round(wc_score * 0.15, 4)})
        score += wc_score * 0.15

        sentence_score = min(avg_words_per_sentence / 25.0, 1.0)
        factors.append({
            "factor": "sentence_complexity",
            "value": round(avg_words_per_sentence, 1),
            "contribution": round(sentence_score * 0.15, 4),
        })
        score += sentence_score * 0.15

        tech_matches = _TECHNICAL_KEYWORDS.findall(text)
        tech_score = min(len(tech_matches) / 8.0, 1.0)
        factors.append({
            "factor": "technical_terms",
            "value": len(tech_matches),
            "contribution": round(tech_score * 0.25, 4),
        })
        score += tech_score * 0.25

        code_matches = _CODE_KEYWORDS.findall(text)
        code_score = min(len(code_matches) / 10.0, 1.0)
        factors.append({
            "factor": "code_patterns",
            "value": len(code_matches),
            "contribution": round(code_score * 0.25, 4),
        })
        score += code_score * 0.25

        is_question = bool(_QUESTION_MARKERS.match(text.strip()))
        question_bonus = 0.15 if is_question and word_count > 10 else 0.0
        if is_question:
            question_bonus += min(word_count / 50.0, 0.15)
        question_bonus = min(question_bonus, 0.20)
        factors.append({
            "factor": "question_type",
            "value": "complex_question" if is_question and word_count > 10 else ("question" if is_question else "statement"),
            "contribution": round(question_bonus, 4),
        })
        score += question_bonus

        nesting = text.count("{") + text.count("(") + text.count("[")
        nesting_score = min(nesting / 15.0, 0.15)
        if nesting > 0:
            factors.append({
                "factor": "structural_nesting",
                "value": nesting,
                "contribution": round(nesting_score, 4),
            })
            score += nesting_score

        score = round(min(score, 1.0), 4)
        category = self._score_to_category(score)

        result = {"score": score, "factors": factors, "category": category}

        with self._lock:
            self._analyzed_count += 1
            self._category_counts[category] = self._category_counts.get(category, 0) + 1
            self._cache[text_hash] = (result, time.perf_counter() + _CACHE_TTL)

        return result

    def is_cached(self, text: str) -> dict | None:
        """Return cached analysis result if available and not expired, else None."""
        text_hash = self._hash(text)
        now = time.perf_counter()
        with self._lock:
            cached = self._cache.get(text_hash)
            if cached is None:
                return None
            result, expiry = cached
            if now >= expiry:
                del self._cache[text_hash]
                return None
            return result

    def get_stats(self) -> dict:
        """Return analysis statistics including total count and category distribution."""
        with self._lock:
            return {
                "analyzed_count": self._analyzed_count,
                "category_distribution": dict(self._category_counts),
                "cache_size": len(self._cache),
            }

    def _score_to_category(self, score: float) -> str:
        if score < 0.2:
            return "trivial"
        if score < 0.4:
            return "simple"
        if score < 0.6:
            return "moderate"
        if score < 0.8:
            return "complex"
        return "expert"

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


_complexity_analyzer: ComplexityAnalyzer | None = None
_complexity_analyzer_lock = threading.Lock()


def get_complexity_analyzer() -> ComplexityAnalyzer:
    global _complexity_analyzer
    if _complexity_analyzer is None:
        with _complexity_analyzer_lock:
            if _complexity_analyzer is None:
                _complexity_analyzer = ComplexityAnalyzer()
    return _complexity_analyzer
