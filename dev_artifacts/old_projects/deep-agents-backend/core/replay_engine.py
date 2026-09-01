"""ReplayEngine — reconstruct the full decision timeline for a trace_id.

Reads only from EventStore; powers GET /api/audit/task/<trace_id> and the
recent-tasks list on the HUD.
"""
from __future__ import annotations

from typing import Any

from core.event_store import get_event_store

_COMPLETION_NAMES = {
    "task.completed", "task.failed",
}


class ReplayEngine:
    def __init__(self) -> None:
        self._store = get_event_store()

    def replay(self, trace_id: str) -> list[dict[str, Any]]:
        """Ordered timeline of events for a trace (oldest first)."""
        events = self._store.query(trace_id=trace_id, limit=200)
        events.sort(key=lambda e: (e.timestamp, e.name))
        return [
            {
                "name": e.name,
                "timestamp": round(e.timestamp, 3),
                "data": e.data,
                "source": e.source,
            }
            for e in events
        ]

    def recent_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        """Most recent traces with their first/last event summary."""
        traces = self._store.recent_traces(limit=limit)
        tasks = []
        for t in traces:
            timeline = self.replay(t["trace_id"])
            if not timeline:
                continue
            summary = {
                "trace_id": t["trace_id"],
                "last_timestamp": round(t["timestamp"], 3),
                "event_count": len(timeline),
                "first": timeline[0]["name"],
                "last": timeline[-1]["name"],
                "intent": _find_event(timeline, "intent.classified").get("name"),
            }
            completion = _find_completion(timeline)
            if completion:
                summary["status"] = "failed" if completion["name"] == "task.failed" else "completed"
                summary["latency_ms"] = completion.get("latency_ms")
            else:
                summary["status"] = "incomplete"
            tasks.append(summary)
        return tasks


def _find_event(timeline: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for e in timeline:
        if e["name"] == name:
            return e["data"] or {}
    return {}


def _find_completion(timeline: list[dict[str, Any]]) -> dict[str, Any]:
    for e in reversed(timeline):
        if e["name"] in _COMPLETION_NAMES:
            return e["data"] or {}
    return {}
