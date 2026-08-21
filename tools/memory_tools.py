"""Memory Tools — LLM-callable tools for memory retrieval and storage.

These tools let the LLM actively query and store memories, rather than
relying solely on automatic context injection.

Tool contract:
    memory.retrieve  — semantic search across all memory backends
    memory.remember  — store a new memory (key/value with category)
    memory.forget    — delete a memory by key
"""

from __future__ import annotations

import logging
from typing import Any

from tools.schema import ToolResult, tool_result

logger = logging.getLogger("jarvis.tools.memory")


def memory_retrieve(args: dict[str, Any]) -> ToolResult:
    """Retrieve memories matching a semantic query.

    Searches across KV store, vector embeddings, decision memory,
    and project knowledge. Returns the most relevant results.
    """
    query = str(args.get("query", "")).strip()
    if not query:
        return ToolResult(success=False, error="A 'query' is required.")

    top_k = max(1, min(int(args.get("limit", 5)), 10))
    project = str(args.get("project", "")).strip()

    try:
        from memory.mem import get_mem
        mem = get_mem()
        results = mem.retrieve(query, project=project, top_k=top_k)

        if not results:
            return ToolResult(
                success=True,
                output=f"No memories found matching: {query}",
            )

        lines = [f"Found {len(results)} memories for: {query}"]
        for i, r in enumerate(results, 1):
            source = r.get("source", "unknown")
            score = r.get("score", 0)
            content = str(r.get("content", ""))[:200]
            lines.append(f"{i}. [{source}] (score={score:.2f}) {content}")

        return ToolResult(
            success=True,
            output="\n".join(lines),
            metadata={"count": len(results), "query": query},
        )
    except Exception as e:
        logger.warning("memory.retrieve failed: %s", e)
        return ToolResult(success=False, error=f"Memory retrieval failed: {e}")


def memory_remember(args: dict[str, Any]) -> ToolResult:
    """Store a memory with a key, value, and category.

    Categories: identity, preferences, priorities, notes, projects, decisions.
    """
    key = str(args.get("key", "")).strip()
    value = str(args.get("value", "")).strip()
    category = str(args.get("category", "notes")).strip()

    if not key or not value:
        return ToolResult(success=False, error="Both 'key' and 'value' are required.")

    valid_categories = {"identity", "preferences", "priorities", "notes", "projects", "decisions"}
    if category not in valid_categories:
        return ToolResult(
            success=False,
            error=f"Invalid category '{category}'. Use one of: {', '.join(sorted(valid_categories))}",
        )

    try:
        from memory.mem import get_mem
        mem = get_mem()
        mem.remember(key, value, category=category)
        return ToolResult(
            success=True,
            output=f"Remembered: [{category}] {key} = {value}",
            metadata={"key": key, "value": value, "category": category},
        )
    except Exception as e:
        logger.warning("memory.remember failed: %s", e)
        return ToolResult(success=False, error=f"Memory store failed: {e}")


def memory_forget(args: dict[str, Any]) -> ToolResult:
    """Delete a memory by key."""
    key = str(args.get("key", "")).strip()
    if not key:
        return ToolResult(success=False, error="A 'key' is required.")

    try:
        from memory.mem import get_mem
        mem = get_mem()
        result = mem.forget(key)
        return ToolResult(
            success=True,
            output=f"Forgot: {key}" if result else f"Key not found: {key}",
        )
    except Exception as e:
        logger.warning("memory.forget failed: %s", e)
        return ToolResult(success=False, error=f"Memory delete failed: {e}")


def memory_stats(args: dict[str, Any]) -> ToolResult:
    """Show memory system statistics."""
    try:
        from memory.mem import get_mem
        mem = get_mem()
        stats = mem.get_stats()
        lines = ["Memory system stats:"]
        for k, v in stats.items():
            lines.append(f"  {k}: {v}")
        return ToolResult(success=True, output="\n".join(lines))
    except Exception as e:
        return ToolResult(success=False, error=f"Stats failed: {e}")
