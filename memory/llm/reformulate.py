"""Query Reformulation for Memory Retrieval.

Rewrites noisy user queries into crisp search terms for the memory database.
Uses a fast regex path for simple queries, falling back to the 1B model
for complex or ambiguous queries.

Architecture:
    User Query → [Regex Filter] → Simple Query
                    ↓ (if too aggressive)
              [1B Reformulate] → Optimized Search Query
"""

from __future__ import annotations

import logging
import re

from memory.llm.common import (
    MODEL_NAME,
    REFORMULATE_TIMEOUT,
    ensure_model,
    query_ollama,
)

logger = logging.getLogger("jarvis.memory.llm.reformulate")

# System prompt for query reformulation
_REFORMULATE_SYSTEM = (
    "You are a search query optimizer. Rewrite the user's message into a "
    "concise search query for a memory database. Return ONLY the search "
    "query, nothing else. Keep it under 20 words. "
    "Remove greetings, filler words, and conversational padding."
)

# Fast regex-based filler word removal
_FILLER_WORDS = frozenset({
    "hello", "hi", "hey", "yo", "sup", "what", "is", "my", "name",
    "can", "you", "tell", "me", "about", "do", "know",
    "remember", "recall", "look", "up", "find", "search",
    "please", "thanks", "thank", "bye", "goodbye",
})

# Pattern: common question starters to strip
_QUESTION_PATTERN = re.compile(
    r"^(what|who|how|when|where|why|can you|could you|do you|tell me|show me|find|search|look up|recall|remember)\s+",
    re.IGNORECASE,
)


def reformulate_query(query: str, model: str = MODEL_NAME) -> str:
    """Reformulate a user query into a crisp search term.

    Uses fast regex first; falls back to 1B model for complex queries.
    Returns the original query if reformulation fails.

    Args:
        query: Raw user query (e.g., "what do you know about my name?")
        model: Ollama model to use for LLM fallback

    Returns:
        Reformulated search query (e.g., "name identity")
    """
    if not query or not query.strip():
        return query

    # Fast path: strip common conversational padding
    cleaned = _QUESTION_PATTERN.sub("", query).strip()
    words = cleaned.lower().split()
    filtered = [w for w in words if w.strip("?.!,;:") not in _FILLER_WORDS]
    simple_query = " ".join(filtered).strip()

    # If we preserved most of the query, use it directly
    if len(simple_query) >= len(words) * 0.4 and len(simple_query) >= 3:
        logger.debug("Reformulated (regex): %r -> %r", query[:50], simple_query[:50])
        return simple_query

    # Complex query — use 1B model for reformulation
    if ensure_model(model):
        result = query_ollama(
            model,
            f"Rewrite this as a search query: {query}",
            system=_REFORMULATE_SYSTEM,
            timeout=REFORMULATE_TIMEOUT,
            max_tokens=64,
        )
        if result and len(result) > 5:
            logger.debug("Reformulated (1B): %r -> %r", query[:50], result[:50])
            return result

    return simple_query or query
