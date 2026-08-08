"""ContextManager — Headroom facade for the agent runtime.

Prepares a full context bundle (system prompt + tool schemas + memory +
files + messages) against a token budget. Trims whichever sections are over
budget — compacting message history via ``compressor.compress``, truncating
injected memory, and pruning file excerpts via ``selector`` — and reports a
``ContextReport`` so the loop and observer can surface window pressure.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from core.context.budget import (
    DEFAULT_BUDGET,
    ContextBudget,
    ContextReport,
    SectionUsage,
    estimate_tokens,
)
from core.context.compressor import compress, trim_tool_outputs
from core.context.summarizer import SummaryFn, default_summarizer

ReportFn = Callable[[ContextReport], None]


class ContextManager:
    """Token-budget-aware context preparation for agent loop iterations."""

    def __init__(
        self,
        budget: Optional[ContextBudget] = None,
        summarizer: SummaryFn = default_summarizer,
        on_report: Optional[ReportFn] = None,
    ) -> None:
        self.budget = budget or DEFAULT_BUDGET
        self.summarizer = summarizer
        self.on_report = on_report
        self.last_report: Optional[ContextReport] = None

    def report(
        self,
        system_tokens: int,
        messages: List[Dict[str, Any]],
        memory_text: str = "",
        files_text: str = "",
        compacted: bool = False,
    ) -> ContextReport:
        sections = [
            SectionUsage("system", system_tokens, self.budget.system),
            SectionUsage("memory", estimate_tokens(memory_text), self.budget.memory),
            SectionUsage("files", estimate_tokens(files_text), self.budget.files),
            SectionUsage(
                "messages",
                self._messages_tokens(messages),
                self.budget.messages,
            ),
        ]
        report = ContextReport(
            system_tokens=system_tokens,
            memory_tokens=estimate_tokens(memory_text),
            files_tokens=estimate_tokens(files_text),
            messages_tokens=self._messages_tokens(messages),
            budget=self.budget,
            compacted=compacted,
            sections=sections,
        )
        self.last_report = report
        if self.on_report:
            self.on_report(report)
        return report

    def fit(
        self,
        system_tokens: int,
        messages: List[Dict[str, Any]],
        memory_text: str = "",
        files_text: str = "",
    ) -> tuple[List[Dict[str, Any]], ContextReport]:
        """Trim messages/injection to budget; return (messages, report)."""
        compacted = False
        fitted = messages
        if self._messages_tokens(messages) > self.budget.messages:
            fitted = compress(
                messages, self.budget.messages, summarizer=self.summarizer,
            )
            compacted = True
        fitted = trim_tool_outputs(fitted)
        report = self.report(
            system_tokens, fitted, memory_text, files_text, compacted=compacted,
        )
        return fitted, report

    def fit_for_loop(
        self,
        messages: List[Dict[str, Any]],
        system_tokens: int,
    ) -> tuple[List[Dict[str, Any]], ContextReport]:
        """Convenience for the agent loop: fit messages under the window."""
        return self.fit(system_tokens, messages)

    @staticmethod
    def _messages_tokens(messages: Optional[List[Dict[str, Any]]]) -> int:
        from core.context.budget import estimate_messages_tokens
        return estimate_messages_tokens(messages)
