"""Intelligent Context Pruning — Score and keep only relevant context.

Before inference, score every memory and keep only active/relevant/recent.
Discard unrelated/obsolete context to reduce token count.
"""
import logging
import time
import threading
import math
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("ai_runtime.context_pruning")


@dataclass
class ContextItem:
    """A single context item for scoring."""
    content: str
    source: str = ""
    timestamp: float = 0.0
    relevance_score: float = 0.0
    recency_score: float = 0.0
    importance_score: float = 0.0
    combined_score: float = 0.0
    tokens: int = 0

    def __post_init__(self):
        if self.tokens == 0:
            self.tokens = max(len(self.content.split()), 1)


class IntelligentContextPruner:
    """Score and prune context before inference.

    Scoring factors:
    1. Recency: newer items score higher
    2. Relevance: keyword overlap with current query
    3. Importance: user-flagged or frequently accessed items
    4. Diversity: penalize similar items
    """

    def __init__(self, max_tokens: int = 8000, keep_recent: int = 5):
        self._max_tokens = max_tokens
        self._keep_recent = keep_recent
        self._history: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def prune(self, items: List[ContextItem], current_query: str = "") -> List[ContextItem]:
        """Prune context items to fit within token budget."""
        if not items:
            return []

        now = time.time()

        # Score each item
        for item in items:
            item.recency_score = self._score_recency(item.timestamp, now)
            item.relevance_score = self._score_relevance(item.content, current_query)
            item.importance_score = self._score_importance(item)
            item.combined_score = (
                0.3 * item.recency_score +
                0.4 * item.relevance_score +
                0.3 * item.importance_score
            )

        # Always keep the most recent items
        sorted_items = sorted(items, key=lambda x: x.timestamp, reverse=True)
        kept = list(sorted_items[:self._keep_recent])
        remaining = sorted_items[self._keep_recent:]

        # Fill budget with highest-scoring remaining items
        total_tokens = sum(i.tokens for i in kept)
        for item in sorted(remaining, key=lambda x: x.combined_score, reverse=True):
            if total_tokens + item.tokens <= self._max_tokens:
                kept.append(item)
                total_tokens += item.tokens

        self._history.append({
            "input_count": len(items),
            "output_count": len(kept),
            "tokens_saved": sum(i.tokens for i in items) - total_tokens,
        })

        return kept

    def _score_recency(self, timestamp: float, now: float) -> float:
        if timestamp == 0:
            return 0.1
        age_hours = (now - timestamp) / 3600
        return max(0.1, math.exp(-age_hours / 24))

    def _score_relevance(self, content: str, query: str) -> float:
        if not query:
            return 0.5
        content_lower = content.lower()
        query_words = set(query.lower().split())
        content_words = set(content_lower.split())
        if not query_words:
            return 0.5
        overlap = len(query_words & content_words) / len(query_words)
        return min(overlap + 0.1, 1.0)

    def _score_importance(self, item: ContextItem) -> float:
        score = 0.5
        if item.source in ("user_input", "system", "memory_store"):
            score += 0.2
        if len(item.content) > 100:
            score += 0.1
        return min(score, 1.0)

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._history)
        avg_saved = sum(h["tokens_saved"] for h in self._history) / max(total, 1)
        return {
            "pruning_count": total,
            "avg_tokens_saved": round(avg_saved, 0),
        }


_pruner_instance: Optional[IntelligentContextPruner] = None


def get_context_pruner() -> IntelligentContextPruner:
    global _pruner_instance
    if _pruner_instance is None:
        _pruner_instance = IntelligentContextPruner()
    return _pruner_instance
