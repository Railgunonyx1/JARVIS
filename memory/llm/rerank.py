"""Memory Reranking using the 1B Model.

Scores and filters retrieved memory candidates for relevance.
After initial retrieval (vector + lexical), the 1B model acts as a
lightweight cross-encoder to select the most relevant memories.

Architecture:
    Candidates (top 8) → [1B Score] → Relevance Scores (0-10) → [Sort] → Top 3
"""

from __future__ import annotations

import json
import logging
from typing import Any

from memory.llm.common import (
    MODEL_NAME,
    RERANK_TIMEOUT,
    ensure_model,
    query_ollama,
)

logger = logging.getLogger("jarvis.memory.llm.rerank")

# System prompt for reranking
_RERANK_SYSTEM = (
    "You are a memory relevance scorer. Given a user query and a list of "
    "memory items, return a JSON array of scores (0-10) for each item. "
    "Return ONLY the JSON array, nothing else. "
    "Score 10 = perfectly relevant, 0 = completely irrelevant."
)


def rerank_memories(
    query: str,
    memories: list[dict[str, Any]],
    model: str = MODEL_NAME,
    max_results: int = 3,
) -> list[dict[str, Any]]:
    """Rerank memory candidates using the 1B model.

    Takes the original query and candidate memories, returns the most
    relevant ones sorted by 1B-assigned relevance score.
    Falls back to original order if the 1B model fails.

    Args:
        query: Original user query
        memories: Candidate memories (list of dicts with 'content' key)
        model: Ollama model to use
        max_results: Maximum results to return

    Returns:
        Reranked list of memories (most relevant first)
    """
    if not memories or len(memories) <= 1:
        return memories

    # Limit candidates for 1B model (it's small, don't overload)
    candidates = memories[:8]

    # Format candidates for the 1B model
    items_text = "\n".join(
        f"{i+1}. [{m.get('type', '?')}] {m.get('content', m.get('value', ''))[:100]}"
        for i, m in enumerate(candidates)
    )
    prompt = f"Query: {query}\n\nMemories:\n{items_text}\n\nScores (JSON array):"

    # Try 1B reranking
    if ensure_model(model):
        result = query_ollama(
            model,
            prompt,
            system=_RERANK_SYSTEM,
            timeout=RERANK_TIMEOUT,
            max_tokens=128,
        )

        if result:
            try:
                # Extract JSON array from response
                start = result.find("[")
                end = result.rfind("]") + 1
                if start >= 0 and end > start:
                    scores = json.loads(result[start:end])
                    if len(scores) == len(candidates):
                        # Apply scores and re-sort
                        scored = list(zip(scores, candidates, strict=True))
                        scored.sort(key=lambda x: x[0], reverse=True)
                        reranked = [m for _, m in scored[:max_results]]
                        # Add remaining memories (unscored) after scored ones
                        reranked.extend(memories[8:])
                        logger.debug(
                            "Reranked %d -> %d memories (scores: %s)",
                            len(memories),
                            len(reranked),
                            [round(s, 1) for s, _ in scored[:max_results]],
                        )
                        return reranked
            except (json.JSONDecodeError, ValueError):
                pass

    # Fallback: return original order (truncated)
    return memories[:max_results]
