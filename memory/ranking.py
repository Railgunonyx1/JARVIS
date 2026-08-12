"""Importance engine and hybrid retrieval ranking (Stage 1E/1F).

- ``ImportanceScorer`` decides *what matters*: explicit saves, repetition,
  project relation, high-signal language, numeric specificity, and (negative)
  staleness.
- ``HybridRanker`` answers *what is relevant right now* by blending semantic
  similarity, keyword overlap, importance, recency, project scope and prior
  usefulness into a single 0..1 score.
"""

from __future__ import annotations

import re
import threading
import time

from memory.models import MemoryItem

# HybridRanker signal weights (sum = 1.0)
SEMANTIC_W = 0.35   # vector similarity — "what is similar?"
LEXICAL_W = 0.25    # keyword overlap — "what mentions the words?"
IMPORTANCE_W = 0.20 # metadata importance — "what matters?"
RECENCY_W = 0.10    # metadata last_used — "what is fresh?"
PROJECT_W = 0.05    # project scope match — "what belongs here?"
USEFULNESS_W = 0.05 # metadata access_count — "what was useful before?"

RECENCY_HALF_LIFE_DAYS = 30.0
USEFULNESS_SATURATION = 10  # access counts beyond this stop adding signal


class ImportanceScorer:
    """Heuristic importance scoring for text being stored."""

    HIGH_SIGNAL = re.compile(
        r"\b(i (love|hate|need|want|will|won't|must|promise|swear|always|never|miss|prefer))\b",
        re.IGNORECASE,
    )
    IDENTITY_MARKERS = re.compile(
        r"\b(my name|i am|i'm from|i work|my job|my birthday|i live|my family|i have a)\b",
        re.IGNORECASE,
    )
    PROJECT_MARKERS = re.compile(
        r"\b(project|refactor|optimize|optimiz|architecture|benchmark|bug|fix|memory|vector|retrieval|agent)\b",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self._seen_phrases: dict[str, int] = {}
        self._lock = threading.Lock()

    def score(self, text: str) -> float:
        """Importance 0..1 for a piece of text (base + signal bonuses)."""
        score = 0.3
        words = text.split()
        if len(words) > 20:
            score += 0.1
        if self.HIGH_SIGNAL.search(text):
            score += 0.25
        if self.IDENTITY_MARKERS.search(text):
            score += 0.2
        if self.PROJECT_MARKERS.search(text):
            score += 0.1
        if re.search(r"\b\d+[-/]\d+", text):
            score += 0.1
        norm = text.lower().strip()
        with self._lock:
            key = norm[:60]
            count = self._seen_phrases.get(key, 0)
            self._seen_phrases[key] = count + 1
            if count == 1:
                score += 0.15
            elif count >= 2:
                score += 0.05
        return min(score, 1.0)

    def merge(self, existing: float, candidate: float) -> float:
        """Blend an existing importance with a new signal (does not fully decay)."""
        return round(min(1.0, max(existing, candidate) * 0.8 + candidate * 0.2), 3)


class HybridRanker:
    """Combine partial retrieval signals into one relevance score."""

    def __init__(
        self,
        semantic_w: float = SEMANTIC_W,
        lexical_w: float = LEXICAL_W,
        importance_w: float = IMPORTANCE_W,
        recency_w: float = RECENCY_W,
        project_w: float = PROJECT_W,
        usefulness_w: float = USEFULNESS_W,
        recency_half_life_days: float = RECENCY_HALF_LIFE_DAYS,
    ) -> None:
        weights = (semantic_w + lexical_w + importance_w + recency_w + project_w + usefulness_w)
        self._w = {
            "semantic": semantic_w / weights,
            "lexical": lexical_w / weights,
            "importance": importance_w / weights,
            "recency": recency_w / weights,
            "project": project_w / weights,
            "usefulness": usefulness_w / weights,
        }
        self._half_life = recency_half_life_days * 86400.0

    def _recency(self, last_accessed: float, now: float) -> float:
        return max(0.0, min(1.0, 2.0 ** (-(now - last_accessed) / self._half_life)))

    def _usefulness(self, access_count: int) -> float:
        return min(1.0, access_count / USEFULNESS_SATURATION)

    def _project(self, item_project: str, query_project: str) -> float:
        if not item_project or not query_project:
            return 0.5  # neutral when scope is unknown
        return 1.0 if item_project == query_project else 0.15

    def score(
        self,
        item: MemoryItem,
        query: str,
        query_project: str = "",
        semantic: float = 0.0,
        lexical: float = 0.0,
        now: float | None = None,
    ) -> float:
        """Final 0..1 hybrid relevance for one candidate."""
        now = now or time.time()
        importance = max(0.0, min(1.0, item.importance))
        return round(
            self._w["semantic"] * max(0.0, min(1.0, semantic))
            + self._w["lexical"] * max(0.0, min(1.0, lexical))
            + self._w["importance"] * importance
            + self._w["recency"] * self._recency(item.last_accessed, now)
            + self._w["project"] * self._project(item.project, query_project)
            + self._w["usefulness"] * self._usefulness(item.access_count),
            4,
        )


def decay_importance(importance: float, age_days: float, half_life_days: float = 90.0) -> float:
    """Importance decay for old, rarely-touched memories (1F negative signal)."""
    return round(importance * (2.0 ** (-age_days / half_life_days)), 3)
