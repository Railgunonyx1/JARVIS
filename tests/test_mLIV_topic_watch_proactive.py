"""Tests for the Mark-LIV-derived modules: topic watch + proactive engine.

Hermetic: news fetching is monkeypatched (no network), state files are
redirected into tmp_path via ProjectContext, and the proactive engine uses an
injected clock. Verifies the guardrail, dedup, gating, rotation, and
registration contracts.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import build_default_registry  # noqa: E402
from tools import proactive  # noqa: E402
from tools import topic_watch as tw  # noqa: E402
from tools.schema import ToolResult  # noqa: E402


# ------------------------------------------------------------------ fixtures

@pytest.fixture()
def tw_state(tmp_path, monkeypatch):
    """Redirect topic-watch state into tmp_path."""
    mem = tmp_path / "memory"
    mem.mkdir(exist_ok=True)
    monkeypatch.setattr(tw, "_STATE_FILE", mem / "topic_watch_state.json", raising=False)
    monkeypatch.setattr(tw, "_state_path", lambda: mem / "topic_watch_state.json")
    return mem / "topic_watch_state.json"


@pytest.fixture()
def clock():
    t = [1000.0]
    return t


@pytest.fixture()
def engine(clock, monkeypatch):
    eng = proactive.ProactiveEngine(min_silence_secs=10, check_cooldown=20, clock=lambda: clock[0])
    monkeypatch.setattr(proactive, "_engine", eng)
    return eng


# --------------------------------------------------------------- topic watch

def test_topic_watch_registered():
    tool = build_default_registry().get("topic.watch")
    assert tool is not None and tool.handler is not None


def test_add_requires_topic(tw_state):
    res = tw.add_topic({})
    assert res.success is False


def test_add_blocked_category(tw_state):
    """Mark-LIV guardrail: crypto/finance topics are refused, any phrasing."""
    for topic in ("Bitcoin price", "best NFT projects", "kripto para", "DeFi yields"):
        res = tw.add_topic({"topic": topic})
        assert res.success is False, topic
        assert "crypto" in res.error.lower() or "financial" in res.error.lower()


def test_add_and_list(tw_state):
    assert tw.add_topic({"topic": "Mars exploration"}).success is True
    assert tw.add_topic({"topic": "mars exploration"}).success is False  # dup slug
    res = tw.list_topics({})
    assert "Mars exploration" in res.output


def test_remove_partial_match(tw_state):
    tw.add_topic({"topic": "James Webb discoveries"})
    res = tw.remove_topic({"topic": "webb"})
    assert res.success is True
    assert "No topics" in tw.list_topics({}).output


def test_max_topics_cap(tw_state):
    for i in range(tw._MAX_TOPICS):
        assert tw.add_topic({"topic": f"topic number {i}"}).success is True
    res = tw.add_topic({"topic": "one too many"})
    assert res.success is False and "full" in res.error.lower()


def test_check_alerts_only_on_headline_change(tw_state, monkeypatch):
    tw.add_topic({"topic": "fusion energy"})
    headlines = {"t": [{"title": "Net-positive shot achieved", "source": "Reuters"}]}

    monkeypatch.setattr(tw, "_news_for", lambda topic, max_results: headlines["t"])

    first = tw.check_topics({})
    assert "Net-positive shot achieved" in first.output

    # Same headline later the same day → silence, not a repeat alert.
    again = tw.check_topics({})
    assert "No new headlines" in again.output

    # Different top headline → alert again.
    headlines["t"] = [{"title": "Second reactor repeats the result", "source": "AP"}]
    monkeypatch.setattr(tw, "_today", lambda: "2031-01-02")  # next day
    third = tw.check_topics({})
    assert "Second reactor repeats the result" in third.output


def test_check_survives_network_error(tw_state, monkeypatch):
    tw.add_topic({"topic": "asteroid missions"})

    def boom(topic, max_results):
        raise OSError("network down")

    monkeypatch.setattr(tw, "_news_for", boom)
    res = tw.check_topics({})
    assert res.success is True  # check recorded, no crash


def test_check_no_topics(tw_state):
    assert "No topics" in tw.check_topics({}).output


# ---------------------------------------------------------- proactive engine

def test_engine_quiet_without_baseline(engine):
    assert engine.should_trigger(None) is False


def test_engine_silence_gate(engine, clock):
    engine.note_activity()
    clock[0] += 5
    assert engine.should_trigger(engine._last_activity) is False  # too soon
    clock[0] += 10
    assert engine.should_trigger(engine._last_activity) is True


def test_engine_cooldown_gate(engine, clock):
    engine.note_activity()
    clock[0] += 30
    engine.mark_triggered()
    assert engine.should_trigger(engine._last_activity) is False  # cooling down
    clock[0] += 30
    assert engine.should_trigger(engine._last_activity) is True


def test_engine_user_speech_resets(engine, clock):
    engine.note_activity()
    clock[0] += 30
    assert engine.should_trigger(engine._last_activity) is True
    engine.note_activity()  # user spoke
    clock[0] += 5
    assert engine.should_trigger(engine._last_activity) is False


def test_prompt_rotation_differs(engine, clock):
    engine.note_activity()
    p1 = engine.build_prompt("profile")
    engine.mark_triggered()
    p2 = engine.build_prompt("profile")
    engine.mark_triggered()
    p3 = engine.build_prompt("profile")
    assert len({p1, p2, p3}) == 3  # three distinct focuses


def test_prompt_honesty_rules(engine):
    engine.note_activity()
    p = engine.build_prompt("likes chess")
    assert "[PROACTIVE_CHECK]" in p
    assert "chess" in p
    assert "Never default to English" in p
    assert "stay silent" in p  # silence is a valid answer
    assert "Do NOT call any tools" in p


def test_prompt_includes_monitors(engine):
    engine.note_activity()
    p = engine.build_prompt("", monitors=["fusion energy", "Mars"])
    assert "fusion energy" in p and "Mars" in p


def test_module_singletons(clock, monkeypatch):
    monkeypatch.setattr(proactive, "_engine", None)
    a = proactive.get_engine()
    b = proactive.get_engine()
    assert a is b
