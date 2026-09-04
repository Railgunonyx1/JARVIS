"""G1 foundation tests: resource locks, ownership, cancellation, approval gate.

Covers the JARVIS Orbit foundation consolidated in ``core/locks.py`` and the
behaviors G1 must guarantee: deterministic RESOURCE_LOCKED signaling, reentrant
same-owner acquisition, cross-agent isolation, real cooperative cancellation,
and the high/critical approval gate wiring.
"""

from __future__ import annotations

import threading
import time

import pytest

from core.locks import (
    OWNER_AGENT,
    OWNER_SYSTEM,
    OWNER_USER,
    ResourceLock,
    ResourceLockedError,
    get_resource_lock,
)


# ── ResourceLock / ownership ────────────────────────────────────────────

def test_acquire_and_release():
    rl = ResourceLock()
    with rl.acquire("tab-1", OWNER_USER) as lease:
        assert rl.owner_of("tab-1") == OWNER_USER
        assert rl.is_locked("tab-1")
        lease.release()
    assert rl.owner_of("tab-1") is None


def test_context_manager_releases():
    rl = ResourceLock()
    with rl.acquire("tab-1", OWNER_AGENT):
        assert rl.is_locked("tab-1")
    assert not rl.is_locked("tab-1")


def test_different_owner_raises_resource_locked():
    rl = ResourceLock()
    rl.acquire("tab-1", OWNER_USER)
    with pytest.raises(ResourceLockedError) as ei:
        rl.acquire("tab-1", OWNER_AGENT)
    assert ei.value.code == "RESOURCE_LOCKED"
    assert ei.value.key == "tab-1"
    assert ei.value.owner == OWNER_USER
    rl.release("tab-1", OWNER_USER)


def test_same_owner_reentrant():
    rl = ResourceLock()
    lease1 = rl.acquire("tab-1", OWNER_AGENT)
    lease2 = rl.acquire("tab-1", OWNER_AGENT)  # reentrant, same owner
    assert lease1.reentrant is False or lease2.reentrant is True
    assert rl.owner_of("tab-1") == OWNER_AGENT
    lease2.release()
    assert rl.owner_of("tab-1") == OWNER_AGENT  # still held by lease1
    lease1.release()
    assert rl.owner_of("tab-1") is None


def test_disjoint_resources_are_independent():
    rl = ResourceLock()
    rl.acquire("tab-1", OWNER_USER)
    # A different owner can take a different tab concurrently.
    with rl.acquire("tab-2", OWNER_AGENT):
        assert rl.owner_of("tab-2") == OWNER_AGENT
        assert rl.owner_of("tab-1") == OWNER_USER
    assert len(rl.locked_keys()) == 1
    rl.release("tab-1", OWNER_USER)


def test_singleton_shared():
    assert get_resource_lock() is get_resource_lock()


def test_concurrent_same_tab_serialized():
    rl = ResourceLock()
    owner = "AGENT-sub1"
    other = "AGENT-sub2"
    entered = []
    barrier = threading.Barrier(2)

    def holder():
        with rl.acquire("tab-1", owner):
            entered.append(owner)
            barrier.wait(timeout=5)
            time.sleep(0.1)
        entered.append("released")

    t = threading.Thread(target=holder)
    t.start()
    barrier.wait(timeout=5)
    # While owner holds, other owner is contested.
    with pytest.raises(ResourceLockedError):
        rl.acquire("tab-1", other)
    t.join(timeout=5)
    assert "released" in entered


# ── Real cancellation (existing cooperative path) ───────────────────────

def test_cooperative_cancellation_event_stops_work():
    """A cancellation Event must propagate to the worker so it stops early."""
    from core.agent.tools import AgentToolExecutor

    cancel = threading.Event()
    hits = {"n": 0, "kept_working": False}

    def long_worker(tool_call_id=""):
        # Cooperative: check the shared cancellation event each iteration.
        for _ in range(1000):
            if cancel.is_set():
                return {"success": False, "error": "cancelled", "cancelled": True}
            hits["n"] += 1
            time.sleep(0.002)
        hits["kept_working"] = True
        return {"success": True}

    def trigger():
        time.sleep(0.02)
        cancel.set()

    threading.Thread(target=trigger, daemon=True).start()
    result = AgentToolExecutor._run_with_cancel(long_worker, {}, cancel, "browser.navigate")
    assert result["cancelled"] is True
    assert result["success"] is False
    assert hits["kept_working"] is False
    assert hits["n"] < 1000


# ── Approval gate for high/critical (answer 4C) ─────────────────────────

def test_risk_gate_requires_confirmation_for_high_risk():
    """High-risk tools must be denied unless the confirmation handler approves."""
    from core.agent.permissions import PermissionEngine
    from core.decision_logger import get_decision_logger
    from core.mode_manager import get_mode_manager
    from tools.schema import Tool

    decisions = []

    def confirm(name, params):
        decisions.append((name, params))
        return "deny"

    pe = PermissionEngine(
        get_decision_logger(),
        mode="agent",
        confirmation_handler=confirm,
    )

    noop = lambda a: None

    happy = Tool(
        name="browser.navigate",
        permission="browser.navigate",
        description="navigate",
        parameters={"type": "object", "properties": {}},
        handler=noop,
        risk="low",
    )
    risky = Tool(
        name="browser.submit",
        permission="browser.submit",
        description="submit form",
        parameters={"type": "object", "properties": {}},
        handler=noop,
        risk="high",
        is_destructive=True,
    )

    # Low risk: no confirmation needed.
    import asyncio
    allow_low, _ = asyncio.run(pe.check(happy, {"url": "https://example.com"}, trace_id="", session_id=""))
    assert allow_low is True
    assert decisions == []

    # High risk with deny decision: blocked.
    allow_high, reason = asyncio.run(pe.check(risky, {}, trace_id="", session_id=""))
    assert allow_high is False
    assert decisions and decisions[0][0] == "browser.submit"
    assert "denied" in reason
