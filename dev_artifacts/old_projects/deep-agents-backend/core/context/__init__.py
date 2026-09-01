"""Headroom — context window manager for the JARVIS MK-X agent runtime.

Never send the whole repo or the entire conversation. Budget each section of
the context window, keep the goal and recent turns verbatim, fold old turns
into a summary, and rank injected files/memory by relevance.

Modules:
    budget       — token estimation + per-section budgets
    compressor   — /compact behaviour: fold old turns, trim tool results
    selector     — relevance ranking for files/memory before injection
    summarizer   — deterministic turn folding (LLM summarizer swappable)
    manager      — ContextManager facade used by the agent loop
"""

from core.context.budget import (
    DEFAULT_BUDGET,
    ContextBudget,
    ContextReport,
    SectionUsage,
    estimate_messages_tokens,
    estimate_tokens,
)
from core.context.compressor import compress, trim_tool_outputs
from core.context.manager import ContextManager
from core.context.selector import rank, score, select_files
from core.context.summarizer import (
    default_summarizer,
    summarize_text,
    summarize_turns,
)

__all__ = [
    "ContextManager",
    "ContextBudget",
    "ContextReport",
    "SectionUsage",
    "DEFAULT_BUDGET",
    "estimate_tokens",
    "estimate_messages_tokens",
    "compress",
    "trim_tool_outputs",
    "rank",
    "score",
    "select_files",
    "summarize_text",
    "summarize_turns",
    "default_summarizer",
]
