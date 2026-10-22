"""Unit tests for the canonical EventBus (runtime/event_bus.py).

Focuses on behaviors that must survive optimization:
  - exact + wildcard dispatch
  - log capping (bounded memory)
  - TTL eviction
  - recent() ordering
"""

from __future__ import annotations

import time

from runtime.event_bus import (
    EVENT_LOG_TTL_SECONDS,
    BusEvent,
    EventBus,
    _match_pattern,
)


def test_exact_and_wildcard_dispatch():
    bus = EventBus()
    seen = []
    bus.subscribe("agent.response", lambda e: seen.append(e.name))
    bus.subscribe("tool.*", lambda e: seen.append(e.name))
    bus.subscribe("tool.**", lambda e: seen.append(e.name))

    bus.publish(BusEvent(name="agent.response"))
    bus.publish(BusEvent(name="tool.executed"))
    bus.publish(BusEvent(name="tool.a.b"))

    # exact once, tool.* matches executed only, tool.** matches both
    assert seen.count("agent.response") == 1
    assert seen.count("tool.executed") == 2  # tool.* + tool.**
    assert seen.count("tool.a.b") == 1       # tool.** only


def test_match_pattern_single_and_multisegment():
    assert _match_pattern("tool.*", "tool.executed")
    assert not _match_pattern("tool.*", "tool.a.b")
    assert _match_pattern("tool.**", "tool.a.b")
    assert _match_pattern("tool.**", "tool")
    assert _match_pattern("tool.**.done", "tool.done")
    assert _match_pattern("tool.**.done", "tool.a.b.done")


def test_log_is_bounded():
    bus = EventBus()
    for i in range(2000):
        bus.publish(BusEvent(name="x", payload={"i": i}))
    assert len(bus._event_log) == 500


def test_recent_returns_tail_in_order():
    bus = EventBus()
    for i in range(10):
        bus.publish(BusEvent(name="x", payload={"i": i}))
    tail = bus.recent(3)
    assert [e.payload["i"] for e in tail] == [7, 8, 9]
    assert len(bus.recent(100)) == 10


def test_ttl_eviction_removes_old_events():
    bus = EventBus()
    old = BusEvent(name="old", timestamp=time.time() - EVENT_LOG_TTL_SECONDS - 10)
    bus.publish(old)
    for _ in range(150):  # cross the every-100 periodic eviction
        bus.publish(BusEvent(name="fresh"))

    remaining = [e.name for e in bus.recent(500)]
    assert "old" not in remaining


def test_unsubscribe():
    bus = EventBus()
    seen = []

    def handler(e):
        seen.append(e.name)

    bus.subscribe("x", handler)
    bus.publish(BusEvent(name="x"))
    bus.unsubscribe("x", handler)
    bus.publish(BusEvent(name="x"))
    assert seen == ["x"]


def test_handler_error_does_not_break_dispatch():
    bus = EventBus()
    seen = []

    def boom(e):
        raise RuntimeError("nope")

    bus.subscribe("x", boom)
    bus.subscribe("x", lambda e: seen.append(e.name))
    bus.publish(BusEvent(name="x"))
    assert seen == ["x"]
