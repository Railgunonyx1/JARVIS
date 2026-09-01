"""Context Condensation for Memory Retrieval.

Compresses multiple memory items into a concise summary suitable for
injection into the LLM context window. Saves tokens while preserving
key information.

Architecture:
    Memories (top 3) → [1B Condense] → Concise Summary (≤500 chars)
"""

from __future__ import annotations

import logging
from typing import Any

from memory.llm.common import (
    CONDENSE_TIMEOUT,
    MODEL_NAME,
    ensure_model,
    query_ollama,
)

logger = logging.getLogger("jarvis.memory.llm.condense")

# System prompt for condensation
_CONDENSE_SYSTEM = (
    "You are a memory condenser. Compress the following memories into a "
    "concise summary suitable for an AI system prompt. "
    "Keep key facts, preferences, and identity information. "
    "Remove redundancy. Output 2-4 bullet points. "
    "Return ONLY the condensed text, nothing else."
)


def condense_memories(
    memories: list[dict[str, Any]],
    query: str = "",
    model: str = MODEL_NAME,
    max_chars: int = 500,
) -> str:
    """Condense multiple memory items into a concise summary.

    Used to compress retrieved memories before injecting into the LLM
    context window. Saves tokens while preserving key information.
    Falls back to plain concatenation if the 1B model fails.

    Args:
        memories: List of memory dicts (with 'content' or 'value' key)
        query: Original query (for context)
        model: Ollama model to use
        max_chars: Maximum characters in output

    Returns:
        Condensed text (bullet points or plain text)
    """
    if not memories:
        return ""

    # Build plain text fallback
    plain_lines = []
    for m in memories:
        content = m.get("content", m.get("value", ""))
        if content:
            plain_lines.append(f"- {content[:200]}")
    plain_text = "\n".join(plain_lines)

    # If short enough, return as-is
    if len(plain_text) <= max_chars:
        return plain_text

    # Use 1B model to condense
    if ensure_model(model):
        memories_text = "\n".join(plain_lines)
        prompt = f"Condense these memories{f' about: {query}' if query else ''}:\n{memories_text}"

        result = query_ollama(
            model,
            prompt,
            system=_CONDENSE_SYSTEM,
            timeout=CONDENSE_TIMEOUT,
            max_tokens=256,
        )

        if result and len(result) > 20:
            logger.debug(
                "Condensed %d memories (%d chars -> %d chars)",
                len(memories),
                len(plain_text),
                len(result),
            )
            return result[:max_chars]

    return plain_text[:max_chars]
