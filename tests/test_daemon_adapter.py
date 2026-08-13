"""Tests for the JARVIS daemon WebSocket message handlers."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from jarvis_memory.daemon_adapter import (
    JarvisDaemon,
    STATUS_COMPLETED,
    STATE_IDLE,
)


class FakeWebSocket:
    """Minimal websocket stand-in that captures sent messages."""

    def __init__(self):
        self.sent = []

    async def send(self, message: str):
        self.sent.append(json.loads(message))


@pytest.fixture
def daemon(tmp_path):
    d = JarvisDaemon()
    # Point memory at a temp db so tests never touch the real store
    d.memory = type(d.memory).__new__(type(d.memory))
    from jarvis_memory.daemon_adapter import MemoryManager
    d.memory = MemoryManager(os.path.join(str(tmp_path), "test_memory.db"))
    return d


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def last(ws):
    return ws.sent[-1]


def test_get_status_handler(daemon):
    ws = FakeWebSocket()
    run(daemon._handle_get_status(ws, {"agent_id": "a1"}))
    resp = last(ws)
    assert resp["type"] == "status_response"
    assert resp["state"] == STATE_IDLE


def test_set_state_broadcast(daemon):
    ws = FakeWebSocket()
    daemon.ws_manager.clients.add(ws)
    run(daemon._handle_set_state(ws, {"agent_id": "a1", "state": "running"}))
    assert daemon.agent_manager.get_agent_state("a1") == "running"
    assert any(r["type"] == "state_updated" for r in ws.sent)


def test_execute_task_completes_and_remembers(daemon):
    ws = FakeWebSocket()
    run(daemon._handle_execute_task(ws, {"task_id": "t9", "goal": "say hi"}))
    resp = last(ws)
    assert resp["type"] == "task_completed"
    assert resp["status"] == STATUS_COMPLETED
    stats = daemon.memory.stats()
    assert stats.get("total_memories", 0) >= 1


def test_remember_recall_forget_roundtrip(daemon):
    ws = FakeWebSocket()

    run(daemon._handle_remember(ws, {
        "type": "remember",
        "memory_type": "fact",
        "content": "JARVIS runs on a 512 MB constraint",
        "subject": "JARVIS",
        "predicate": "runs_on",
        "object": "512MB",
        "importance": 0.8,
    }))
    mid = last(ws)["memory_id"]
    assert mid

    run(daemon._handle_recall(ws, {"memory_id": mid}))
    assert last(ws)["record"]["content"] == "JARVIS runs on a 512 MB constraint"

    run(daemon._handle_memory_search(ws, {"query": "512"}))
    assert last(ws)["count"] >= 1

    run(daemon._handle_forget(ws, {"memory_id": mid}))
    assert last(ws)["forgotten"] is True

    run(daemon._handle_recall(ws, {"memory_id": mid}))
    assert last(ws)["record"] is None


def test_semantic_search_uses_real_query(daemon):
    ws = FakeWebSocket()
    run(daemon._handle_remember(ws, {
        "type": "remember",
        "memory_type": "fact",
        "content": "sqlite powers the vector store",
        "importance": 0.7,
    }))
    run(daemon._handle_semantic_search(ws, {"query": "sqlite", "k": 5}))
    resp = last(ws)
    assert resp["type"] == "semantic_search_response"
    assert resp["query"] == "sqlite"
    assert len(resp["results"]) >= 1


def test_memory_stats(daemon):
    ws = FakeWebSocket()
    run(daemon._handle_memory_stats(ws, {}))
    resp = last(ws)
    assert resp["type"] == "memory_stats_response"
    assert "total_memories" in resp["stats"]


def test_consolidate(daemon):
    ws = FakeWebSocket()
    run(daemon._handle_consolidate(ws, {}))
    resp = last(ws)
    assert resp["type"] == "consolidate_response"
    assert resp["result"]["status"] in ("completed", "failed", "noop")


def test_ping(daemon):
    ws = FakeWebSocket()
    run(daemon._handle_ping(ws, {}))
    resp = last(ws)
    assert resp["type"] == "pong"
    assert resp["memory_backend"] in ("fabric", "vector_fallback")


def test_unknown_message_is_logged_not_raised(daemon):
    ws = FakeWebSocket()
    # _handle_message is async and should swallow unknown types
    run(daemon._handle_message(ws, json.dumps({"type": "bogus"})))
    assert ws.sent == []
