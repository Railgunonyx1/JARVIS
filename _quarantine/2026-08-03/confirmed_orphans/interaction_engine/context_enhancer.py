"""Context Enhancer — Enriches raw context with knowledge graph, user preferences, and system state."""

import time
import logging
import threading
from typing import Optional
from datetime import datetime
from collections import Counter

logger = logging.getLogger("jarvis.interaction_engine.context_enhancer")


class ContextEnhancer:
    """Enriches raw context dictionaries with relevant knowledge, preferences, and system data."""

    def __init__(self):
        self._lock = threading.Lock()
        self._context_cache: dict[str, tuple] = {}
        self._cache_ttl: float = 30.0
        self._start_time: float = time.time()
        self._recent_summaries: list[str] = []
        self._keyword_index: dict[str, list[int]] = {}
        self._context_items: list[dict] = []

    def enhance_context(self, raw_context: dict, user_input: str) -> dict:
        """Enrich raw_context with relevant data from all subsystems."""
        cache_key = f"{hash(str(sorted(raw_context.items())))}:{hash(user_input)}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        enhanced = dict(raw_context)

        enhanced["recent_conversation_summary"] = self._get_conversation_summary()
        enhanced["relevant_knowledge_graph_nodes"] = self._get_kg_nodes(user_input)
        enhanced["user_preferences"] = self._get_user_preferences()
        enhanced["time_context"] = self._get_time_context()
        enhanced["system_state"] = self.build_system_context()

        self._put_cache(cache_key, enhanced)

        return enhanced

    def get_relevant_context(self, user_input: str, max_items: int = 5) -> list[dict]:
        """Return the most relevant context items for a given user input."""
        scored_items = []
        with self._lock:
            for item in self._context_items:
                score = self.score_relevance(item, user_input)
                if score > 0.0:
                    scored_items.append((score, item))

        scored_items.sort(key=lambda x: -x[0])
        return [{"score": round(score, 4), **item} for score, item in scored_items[:max_items]]

    def score_relevance(self, item: dict, query: str) -> float:
        """Score relevance of a context item to a query string (0.0 to 1.0)."""
        if not query or not item:
            return 0.0

        query_lower = query.lower()
        query_tokens = set(self._tokenize(query_lower))

        if not query_tokens:
            return 0.0

        item_text = self._item_to_text(item).lower()
        item_tokens = set(self._tokenize(item_text))

        if not item_tokens:
            return 0.0

        intersection = query_tokens & item_tokens
        if not intersection:
            return 0.0

        # Jaccard-like similarity weighted by token overlap
        overlap_ratio = len(intersection) / len(query_tokens)

        # Boost for exact substring match
        substring_boost = 0.2 if query_lower in item_text or item_text in query_lower else 0.0

        score = min(overlap_ratio * 0.8 + substring_boost, 1.0)
        return round(score, 4)

    def build_system_context(self) -> dict:
        """Return system-level context information."""
        now = datetime.now()
        uptime = time.time() - self._start_time
        return {
            "time": now.strftime("%H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "day_of_week": now.strftime("%A"),
            "hour": now.hour,
            "minute": now.minute,
            "uptime_seconds": round(uptime, 1),
            "uptime_formatted": self._format_uptime(uptime),
            "timestamp": time.time(),
        }

    def add_context_item(self, item: dict) -> None:
        """Add a context item to the searchable index."""
        with self._lock:
            idx = len(self._context_items)
            self._context_items.append(item)

            tokens = set(self._tokenize(self._item_to_text(item).lower()))
            for token in tokens:
                if token not in self._keyword_index:
                    self._keyword_index[token] = []
                self._keyword_index[token].append(idx)

            if len(self._context_items) > 1000:
                self._context_items = self._context_items[-500:]
                self._rebuild_keyword_index()

    def remove_context_item(self, index: int) -> None:
        """Remove a context item by index."""
        with self._lock:
            if 0 <= index < len(self._context_items):
                self._context_items.pop(index)
                self._rebuild_keyword_index()

    def clear_context(self) -> None:
        """Clear all stored context items."""
        with self._lock:
            self._context_items.clear()
            self._keyword_index.clear()
            self._context_cache.clear()
            self._recent_summaries.clear()

    def add_conversation_summary(self, summary: str) -> None:
        """Store a recent conversation summary for context enrichment."""
        with self._lock:
            self._recent_summaries.append(summary)
            if len(self._recent_summaries) > 20:
                self._recent_summaries = self._recent_summaries[-20:]

    def _get_conversation_summary(self) -> str:
        """Build a summary of recent conversation context."""
        with self._lock:
            summaries = list(self._recent_summaries[-5:])
        if not summaries:
            return "No recent conversation context."
        return "; ".join(summaries[-3:])

    def _get_kg_nodes(self, user_input: str) -> list[dict]:
        """Retrieve relevant knowledge graph nodes for the user input."""
        nodes = []
        try:
            from knowledge_graph.graph import get_knowledge_graph
            kg = get_knowledge_graph()
            keywords = self._tokenize(user_input.lower())
            seen = set()
            for keyword in keywords:
                if len(keyword) < 2:
                    continue
                results = kg.search_entities(keyword, limit=3)
                for entity in results:
                    if entity.id not in seen:
                        seen.add(entity.id)
                        nodes.append({
                            "name": entity.name,
                            "type": entity.entity_type.value,
                            "importance": entity.importance,
                        })
                        if len(nodes) >= 8:
                            return nodes
        except Exception as e:
            logger.debug("KG context unavailable: %s", e)
        return nodes

    def _get_user_preferences(self) -> dict:
        """Retrieve user preferences from the personal intelligence module."""
        prefs = {}
        try:
            from personal_intelligence.user_model import UserModel
            model = UserModel()
            all_prefs = model.get_all_preferences()
            for key, pref in all_prefs.items():
                if not key.startswith("last_intent:"):
                    prefs[key] = pref.value
        except Exception as e:
            logger.debug("User model unavailable: %s", e)
        return prefs

    def _get_time_context(self) -> dict:
        """Build time-based context."""
        now = datetime.now()
        hour = now.hour
        if 0 <= hour < 6:
            period = "late_night"
        elif 6 <= hour < 12:
            period = "morning"
        elif 12 <= hour < 17:
            period = "afternoon"
        elif 17 <= hour < 21:
            period = "evening"
        else:
            period = "night"

        return {
            "period": period,
            "hour": hour,
            "is_weekend": now.weekday() >= 5,
            "day_of_week": now.strftime("%A"),
        }

    def _get_cached(self, key: str) -> Optional[dict]:
        """Return cached result if still valid."""
        with self._lock:
            if key in self._context_cache:
                result, timestamp = self._context_cache[key]
                if time.time() - timestamp < self._cache_ttl:
                    return result
                del self._context_cache[key]
        return None

    def _put_cache(self, key: str, value: dict) -> None:
        """Store a result in the cache."""
        with self._lock:
            self._context_cache[key] = (value, time.time())
            if len(self._context_cache) > 200:
                oldest_keys = sorted(self._context_cache, key=lambda k: self._context_cache[k][1])[:100]
                for k in oldest_keys:
                    self._context_cache.pop(k, None)

    def _tokenize(self, text: str) -> list[str]:
        """Simple word tokenization."""
        import re
        return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1]

    def _item_to_text(self, item: dict) -> str:
        """Convert a context item dict to searchable text."""
        parts = []
        for value in item.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, (int, float)):
                parts.append(str(value))
            elif isinstance(value, list):
                parts.extend(str(v) for v in value)
        return " ".join(parts)

    def _format_uptime(self, seconds: float) -> str:
        """Format seconds into a human-readable uptime string."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    def _rebuild_keyword_index(self) -> None:
        """Rebuild the keyword index from scratch."""
        self._keyword_index.clear()
        for idx, item in enumerate(self._context_items):
            tokens = set(self._tokenize(self._item_to_text(item).lower()))
            for token in tokens:
                if token not in self._keyword_index:
                    self._keyword_index[token] = []
                self._keyword_index[token].append(idx)


_instance: Optional[ContextEnhancer] = None
_instance_lock = threading.Lock()


def get_context_enhancer() -> ContextEnhancer:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ContextEnhancer()
    return _instance
