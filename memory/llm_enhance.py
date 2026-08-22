"""1B-powered memory retrieval enhancements (backward-compatible wrapper).

This module is kept for backward compatibility. The actual implementation
is now split into:
- memory/llm/reformulate.py — Query reformulation
- memory/llm/rerank.py — Memory reranking
- memory/llm/condense.py — Context condensation
- memory/llm/common.py — Shared utilities and model management
"""

from memory.llm.common import MODEL_NAME, ensure_model, query_ollama
from memory.llm.condense import condense_memories
from memory.llm.reformulate import reformulate_query
from memory.llm.rerank import rerank_memories

__all__ = [
    "reformulate_query",
    "rerank_memories",
    "condense_memories",
    "ensure_model",
    "query_ollama",
    "MODEL_NAME",
    # Legacy names
    "enhance_retrieval",
]


def enhance_retrieval(
    query: str,
    memories: list[dict],
    model: str = MODEL_NAME,
    do_reformulate: bool = True,
    do_rerank: bool = True,
    do_condense: bool = True,
    max_results: int = 3,
) -> tuple[str, list[dict], str]:
    """Full 1B-enhanced retrieval pipeline (legacy API).

    Returns:
        (reformulated_query, reranked_memories, condensed_context)
    """
    import time

    t0 = time.perf_counter()

    # Step 1: Reformulate query
    if do_reformulate:
        reformulated = reformulate_query(query, model=model)
    else:
        reformulated = query

    # Step 2: Rerank memories
    if do_rerank and memories:
        reranked = rerank_memories(
            reformulated, memories, model=model, max_results=max_results,
        )
    else:
        reranked = memories[:max_results]

    # Step 3: Condense context
    if do_condense and reranked:
        condensed = condense_memories(reranked, query=query, model=model)
    else:
        condensed = "\n".join(
            f"- {m.get('content', m.get('value', ''))[:200]}" for m in reranked
        )

    elapsed = (time.perf_counter() - t0) * 1000
    import logging
    logger = logging.getLogger("jarvis.memory.llm_enhance")
    logger.info(
        "Memory enhancement: %dms (reformulate=%s, rerank=%d->%d, condense=%d chars)",
        elapsed,
        reformulated != query,
        len(memories),
        len(reranked),
        len(condensed),
    )

    return reformulated, reranked, condensed
