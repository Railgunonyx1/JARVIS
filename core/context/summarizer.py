"""Context summarization (Headroom).

Deterministic, dependency-free folding of older conversation turns into a
compact summary. An LLM-based summarizer can swap in later behind the same
``SummaryFn`` signature without changing callers.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

SummaryFn = Callable[[List[Dict[str, Any]]], str]


def summarize_text(text: str, max_chars: int = 120) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def summarize_turns(
    turns: List[Dict[str, Any]],
    max_chars: int = 1200,
    per_turn_chars: int = 120,
) -> str:
    """Fold turns into a single compact summary string."""
    parts = []
    for message in turns:
        role = message.get("role", "")
        content = message.get("content") or ""
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        if not isinstance(content, str):
            content = json.dumps(content, default=str)[:per_turn_chars]
        label = "user" if role == "user" else role
        parts.append(f"[{label}] {summarize_text(str(content), per_turn_chars)}")
    joined = " | ".join(parts)
    return joined[:max_chars]


def default_summarizer(turns: List[Dict[str, Any]], max_chars: int = 1200) -> str:
    """The standard folding summarizer used by the compressor."""
    return summarize_turns(turns, max_chars=max_chars)
