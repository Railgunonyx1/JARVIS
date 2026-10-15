"""Memory consolidation — mem0-style write-time deduplication.

Research basis (mem0 arXiv:2504.19413, Zep/Graphiti arXiv:2501.13956):

mem0's core insight is that a memory layer is not an append-only log. Every
candidate memory runs through an ADD / UPDATE / NO-OP decision against what
is already stored; otherwise near-duplicates accumulate until retrieval
drowns in stale variants of the same fact. JARVIS UPDATE semantics follow
mem0's: the fact is replaced IN PLACE under its stable key, so references
in prompts and code stay valid. Zep's tombstone pattern (superseded_by)
is supported at the metadata/retrieval layer for flows that hard-delete.

JARVIS adaptation (LLM-free, synchronous, cheap enough for the chat path):

- Near-duplicate detection by token Jaccard (content words carry the
  signal) with an optional vector-score blend when a vector store is
  attached.
- Decision: NO-OP (identical content) / UPDATE (rephrase, in place,
  stable key) / ADD (new fact). Episodic memories are exempt — events
  are append-only; identity/decision keys are canonical.
"""

from __future__ import annotations

import re
from typing import Any

# Over this Jaccard the candidate is a duplicate; below is a distinct fact.
DUP_THRESHOLD = 0.72
# Words too generic to identify a fact's subject. Deliberately minimal:
# content words like "user"/"prefers" carry the comparison signal —
# stripping them collapsed distinct-vs-duplicate discrimination.
_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "my", "i", "im", "i'm",
    "me", "and", "or", "to", "of", "in", "on", "at", "for", "with",
    "has", "have", "had", "it", "this", "that", "be", "been", "being",
}

_WORD_RE = re.compile(r"[a-z0-9']+")


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(text.lower()) if t not in _STOP}


def jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def is_tombstone(item_or_meta: Any) -> bool:
    """True when a MemoryItem (or metadata row) marks a superseded fact."""
    if item_or_meta is None:
        return False
    if isinstance(item_or_meta, dict):
        return bool(item_or_meta.get("superseded_by"))
    return bool(getattr(item_or_meta, "metadata", None)
                and item_or_meta.metadata.get("superseded_by"))


def find_duplicate(
    new_content: str,
    existing: list[dict[str, Any]],
    *,
    threshold: float = DUP_THRESHOLD,
    vector_assist: bool = False,
) -> dict[str, Any] | None:
    """Return the best matching existing memory dict, or None.

    ``existing`` rows need ``key`` + ``content``; optional ``score`` is a
    precomputed similarity (0..1). With ``vector_assist`` rows carrying a
    ``score`` get a Jaccard blend so vector near-misses still surface.
    """
    best: dict[str, Any] | None = None
    best_sim = 0.0
    for row in existing or []:
        if is_tombstone(row):
            continue
        sim = jaccard(new_content, row.get("content", ""))
        if vector_assist and row.get("score") is not None:
            sim = max(sim, 0.5 * sim + 0.5 * float(row["score"]))
        if sim >= threshold and sim > best_sim:
            best = row
            best_sim = sim
    return best


def supersede_tombstone(old_key: str, new_key: str) -> dict[str, Any]:
    """Metadata marking ``old_key`` as replaced by ``new_key``."""
    return {"superseded_by": new_key, "superseded_at": _now()}


def _now() -> float:
    import time
    return time.time()


__all__ = [
    "DUP_THRESHOLD",
    "find_duplicate",
    "is_tombstone",
    "jaccard",
    "supersede_tombstone",
]
