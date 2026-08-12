"""Token budget for the agent context window (Headroom).

The model has a fixed context window; every section — system prompt, tool
schemas, injected memory, file excerpts, and message history — competes for
it. The budget reserves headroom so a single section can never starve the
response or overflow the window.

Token estimation uses the len/4 heuristic (approximately 4 chars/token), so
it is deterministic, dependency-free, and testable offline. Providers that
report exact token usage (see AgentState.tokens_used) are trusted for the
audit trail; this estimator is for pre-flight budgeting only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str | None) -> int:
    """Estimate tokens in a string using the 4-char heuristic."""
    if not text:
        return 0
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def estimate_messages_tokens(messages: list[dict[str, Any]] | None) -> int:
    """Estimate tokens across a list of chat messages."""
    if not messages:
        return 0
    total = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total += estimate_tokens(part.get("text") or "")
        total += estimate_tokens(str(message.get("role") or ""))
    return total


@dataclass
class ContextBudget:
    """Per-section token allocation for the context window.

    Mirrors the Headroom design: reserve budget for each section instead of
    filling the whole window. Sections are trimmed independently so one
    runaway section cannot evict the rest.
    """

    system: int = 10_000      # system prompt + tool schemas
    memory: int = 15_000      # injected project/user memory
    files: int = 30_000       # file excerpts and search results
    messages: int = 30_000    # conversation + tool results
    response: int = 10_000    # reserved for the model's output

    @property
    def total(self) -> int:
        return self.system + self.memory + self.files + self.messages + self.response

    def section(self, name: str) -> int:
        return getattr(self, name, 0)

    def to_dict(self) -> dict[str, int]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


DEFAULT_BUDGET = ContextBudget()


@dataclass
class SectionUsage:
    """Token usage for one context section against its budget."""

    section: str
    tokens: int
    budget: int

    @property
    def over(self) -> bool:
        return self.tokens > self.budget

    @property
    def ratio(self) -> float:
        if self.budget <= 0:
            return 1.0 if self.tokens else 0.0
        return round(self.tokens / self.budget, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "tokens": self.tokens,
            "budget": self.budget,
            "over": self.over,
            "ratio": self.ratio,
        }


@dataclass
class ContextReport:
    """Full usage report for a prepared context bundle."""

    system_tokens: int = 0
    memory_tokens: int = 0
    files_tokens: int = 0
    messages_tokens: int = 0
    budget: ContextBudget = field(default_factory=ContextBudget)
    compacted: bool = False
    sections: list[SectionUsage] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return (self.system_tokens + self.memory_tokens
                + self.files_tokens + self.messages_tokens)

    @property
    def total_budget(self) -> int:
        return self.budget.total

    @property
    def any_over(self) -> bool:
        return any(s.over for s in self.sections)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "total_budget": self.total_budget,
            "system_tokens": self.system_tokens,
            "memory_tokens": self.memory_tokens,
            "files_tokens": self.files_tokens,
            "messages_tokens": self.messages_tokens,
            "compacted": self.compacted,
            "budget": self.budget.to_dict(),
            "sections": [s.to_dict() for s in self.sections],
        }
