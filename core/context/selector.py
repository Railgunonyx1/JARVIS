"""Relevance selection for injected context (Headroom).

Picks which file excerpts / memory records actually earn their tokens before
they go into the window. Uses dependency-free lexical scoring now; the M3
code index (ast → sqlite) plugs into the same interface later with semantic
retrieval.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

from core.context.budget import estimate_tokens

_QUERY_WORDS = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{1,}")


def _tokenize(text: str) -> set[str]:
    return set(_QUERY_WORDS.findall(text.lower()))


def score(text: str, query: str) -> float:
    """Lexical overlap score (0..1) between a document and the query."""
    if not query:
        return 0.0
    doc_words = _tokenize(text)
    if not doc_words:
        return 0.0
    query_words = _tokenize(query)
    if not query_words:
        return 0.0
    overlap = len(doc_words & query_words)
    return round(overlap / len(query_words), 3)


def rank(candidates: Iterable[tuple[str, str]], query: str) -> list[tuple[str, float]]:
    """Rank (key, content) candidates by relevance to the query."""
    scored = [(key, score(content, query)) for key, content in candidates]
    return sorted(scored, key=lambda item: item[1], reverse=True)


def select_files(
    files: Sequence[dict[str, Any]],
    query: str,
    top_k: int = 5,
    max_tokens: int = 30_000,
) -> list[dict[str, Any]]:
    """Choose the most relevant file excerpts that fit the token budget.

    ``files`` items are dicts with at least ``path`` and ``content``.
    """
    ranked = rank([(f.get("path", ""), f.get("content", "")) for f in files], query)
    selected: list[dict[str, Any]] = []
    used_tokens = 0
    for path, relevance in ranked:
        if relevance <= 0.0:
            continue
        source = next(f for f in files if f.get("path") == path)
        tokens = estimate_tokens(source.get("content", ""))
        if used_tokens + tokens > max_tokens:
            continue
        selected.append({**source, "relevance": relevance})
        used_tokens += tokens
        if len(selected) >= top_k:
            break
    return selected
