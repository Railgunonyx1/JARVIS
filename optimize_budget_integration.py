#!/usr/bin/env python
"""Mode-specific context budget integration.

Provides mode-aware ContextBudget selection based on the execution mode.
Defaults to the full ContextBudget for agent mode, with reduced budgets
for plan/controlled/smart modes to improve first-response time.
"""
import sys
sys.path.insert(0, '.')
from core.context.budget import ContextBudget, DEFAULT_BUDGET, ContextReport, SectionUsage, estimate_tokens


# Mode-specific budget presets (reduced for non-agent modes)
_MODE_BUDGETS = {
    'plan': ContextBudget(
        system=8000,      # Reduced system prompt + tool schemas
        memory=8000,      # Reduced memory loading
        files=20000,      # Fewer file excerpts
        messages=15000,
        response=10000,
    ),
    'controlled': ContextBudget(
        system=9000,
        memory=12000,
        files=25000,
        messages=15000,
        response=10000,
    ),
    'smart': ContextBudget(
        system=9500,
        memory=14000,
        files=28000,
        messages=15000,
        response=10000,
    ),
    'agent': ContextBudget(
        system=10000,
        memory=15000,
        files=30000,
        messages=15000,
        response=10000,
    ),
    'default': DEFAULT_BUDGET,
}


def get_budget(mode: str = 'default') -> ContextBudget:
    """Get the appropriate ContextBudget for the given mode.
    
    Args:
        mode: Execution mode ('plan', 'controlled', 'smart', 'agent', or 'default')
    
    Returns:
        ContextBudget configured for the specified mode
    """
    return _MODE_BUDGETS.get(mode, DEFAULT_BUDGET)


def report(system_tokens: int, messages: list, memory_text: str = "",
           files_text: str = "", mode: str = 'default', compacted: bool = False) -> ContextReport:
    """Create a ContextReport using mode-aware budgeting.
    
    Args:
        system_tokens: Estimated tokens for system prompt
        messages: List of message dicts
        memory_text: Injected memory text
        files_text: File excerpts text
        mode: Execution mode for budget selection
        compacted: Whether context was compacted
    
    Returns:
        ContextReport with budget-aware section usage
    """
    budget = get_budget(mode)
    
    sections = [
        SectionUsage("system", system_tokens, budget.system),
        SectionUsage("memory", estimate_tokens(memory_text), budget.memory),
        SectionUsage("files", estimate_tokens(files_text), budget.files),
        SectionUsage("messages", estimate_tokens(messages) if messages else 0, budget.messages),
    ]
    
    report = ContextReport(
        system_tokens=system_tokens,
        memory_tokens=estimate_tokens(memory_text),
        files_tokens=estimate_tokens(files_text),
        messages_tokens=estimate_tokens(messages) if messages else 0,
        budget=budget,
        compacted=compacted,
        sections=sections,
    )
    return report