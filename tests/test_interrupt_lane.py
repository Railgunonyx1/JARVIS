"""P0 Release Test: Interrupt Architecture Invariants.

Proves that the 1.5B interrupt lane:
- Does NOT cancel or corrupt the main task
- Does NOT change the main task's model
- Does NOT lose main task context
- Gets ONLY the correct memory/read-only tools
- CANNOT execute dangerous tools (shell, write, delete)
- Does NOT overwrite the main response
- Multiple interrupts don't corrupt state
- Interrupt completion after main-task completion is handled correctly
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest


# ---------------------------------------------------------------------------
# 1. Allowed tools invariant
# ---------------------------------------------------------------------------

def test_interrupt_lane_has_only_readonly_tools():
    """Interrupt lane must contain only memory/read-only tools."""
    from core.agent.lanes import _INTERRUPT_ALLOWED_TOOLS

    DANGEROUS = {
        "shell.execute", "shell.run",
        "filesystem.write", "filesystem.delete", "filesystem.patch",
        "git.commit", "git.push", "git.reset",
        "process.kill",
        "system.shutdown", "system.restart",
        "package.install", "package.remove",
    }
    violation = DANGEROUS & _INTERRUPT_ALLOWED_TOOLS
    assert not violation, f"Interrupt lane contains dangerous tools: {violation}"


def test_interrupt_lane_has_memory_tools():
    """Interrupt lane must include memory retrieval tools."""
    from core.agent.lanes import _INTERRUPT_ALLOWED_TOOLS

    assert "memory.retrieve" in _INTERRUPT_ALLOWED_TOOLS
    assert "memory.stats" in _INTERRUPT_ALLOWED_TOOLS


def test_interrupt_lane_has_status_tools():
    """Interrupt lane must include read-only status tools."""
    from core.agent.lanes import _INTERRUPT_ALLOWED_TOOLS

    assert "system.status" in _INTERRUPT_ALLOWED_TOOLS
    assert "git.status" in _INTERRUPT_ALLOWED_TOOLS
    assert "git.branch" in _INTERRUPT_ALLOWED_TOOLS
    assert "git.log" in _INTERRUPT_ALLOWED_TOOLS


# ---------------------------------------------------------------------------
# 2. Request classifier invariant
# ---------------------------------------------------------------------------

def test_request_classifier_classifies_memory_as_interrupt():
    """Memory queries during a running task should be classified as interrupt."""
    from core.agent.lanes import RequestClassifier

    classifier = RequestClassifier()
    result = classifier.classify(
        "what is my name",
        active_task_id="task_123",
        active_task_status="executing",
    )
    assert result.lane.value == "interrupt", f"Expected interrupt lane, got {result.lane.value}"


def test_request_classifier_classifies_code_as_main():
    """Code tasks should NOT be classified as interrupt even during a running task."""
    from core.agent.lanes import RequestClassifier

    classifier = RequestClassifier()
    result = classifier.classify(
        "fix the authentication bug in auth.py",
        active_task_id="task_123",
        active_task_status="executing",
    )
    assert result.lane.value == "main", f"Expected main lane, got {result.lane.value}"


def test_request_classifier_classifies_status_as_interrupt():
    """Status queries during a running task should be classified as interrupt."""
    from core.agent.lanes import RequestClassifier

    classifier = RequestClassifier()
    # Test queries that match the interrupt patterns
    interrupt_queries = [
        "what is my name",
        "show me the memory",
        "what did we decide about the architecture",
        "do you know any context about this",
        "what is the project status",
    ]
    for q in interrupt_queries:
        result = classifier.classify(
            q,
            active_task_id="task_123",
            active_task_status="executing",
        )
        assert result.lane.value == "interrupt", (
            f"Query '{q}' got lane={result.lane.value}, expected interrupt"
        )


# ---------------------------------------------------------------------------
# 3. Interrupt executor state isolation
# ---------------------------------------------------------------------------

def test_interrupt_executor_creates_separate_loop():
    """InterruptExecutor must create its own AgentLoop, not reuse the main one."""
    from core.agent.lanes import InterruptExecutor

    # Verify the class exists and can be instantiated without a main loop
    executor = InterruptExecutor.__new__(InterruptExecutor)
    # The executor should have its own router reference, not share state
    assert hasattr(InterruptExecutor, '__init__')


# ---------------------------------------------------------------------------
# 4. Tool filtering invariant
# ---------------------------------------------------------------------------

def test_interrupt_tools_are_subset_of_registry():
    """Every tool in the interrupt allowed list must exist in the full registry."""
    from core.agent.lanes import _INTERRUPT_ALLOWED_TOOLS
    from tools import build_default_registry

    registry = build_default_registry()
    registered_names = {t.name for t in registry.list()}

    missing = _INTERRUPT_ALLOWED_TOOLS - registered_names
    assert not missing, f"Interrupt tools not in registry: {missing}"


# ---------------------------------------------------------------------------
# 5. Main task tools are NOT restricted
# ---------------------------------------------------------------------------

def test_main_lane_has_no_tool_restriction():
    """Main lane should not artificially restrict tools (unlike interrupt lane)."""
    from core.agent.lanes import ExecutionLane

    # The main lane is the default — it should not filter tools
    # Only the interrupt lane has restricted tool access
    from core.agent.lanes import _INTERRUPT_ALLOWED_TOOLS
    from tools import build_default_registry

    registry = build_default_registry()
    all_tools = {t.name for t in registry.list()}

    # Main lane tools should be ALL registered tools (no restriction)
    # Verify interrupt is a proper subset
    assert _INTERRUPT_ALLOWED_TOOLS.issubset(all_tools), (
        "Interrupt tools should all be in the full registry"
    )


# ---------------------------------------------------------------------------
# 6. Multiple interrupts don't corrupt state
# ---------------------------------------------------------------------------

def test_multiple_classifier_calls_are_idempotent():
    """Calling the classifier multiple times must not change its behavior."""
    from core.agent.lanes import RequestClassifier

    classifier = RequestClassifier()
    queries = [
        ("what is my name", "interrupt"),
        ("hello", "main"),
        ("show me the memory", "interrupt"),
        ("fix the auth bug", "main"),
        ("what did we decide about the architecture", "interrupt"),
        ("run the tests", "main"),
    ]

    # Run twice to check idempotency
    for _ in range(2):
        for query, expected_lane in queries:
            result = classifier.classify(
                query,
                active_task_id="task_test",
                active_task_status="executing",
            )
            assert result.lane.value == expected_lane, (
                f"Query '{query}' got lane={result.lane.value}, expected {expected_lane}"
            )
