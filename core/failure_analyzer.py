"""FailureAnalyzer — attribute a failed task to the responsible subsystem.

Logic for analyze(trace_id):
  1. Reconstruct the trace timeline via ReplayEngine.
  2. task.completed present      -> status "ok".
  3. task.failed present         -> inspect events preceding it:
       - last failed tool.executed / action.executed -> attribute to that tool
       - otherwise attribute to the last event before the failure
  4. request.received with no completion event -> status "incomplete"
     (reported as a missing completion event / timeout).

Powers GET /api/audit/failure/<trace_id>.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.replay_engine import ReplayEngine

_FAILURE_RECOVERY = {
    "tool.executed": "retry",
    "action.executed": "retry",
    "llm.completed": "replan",
    "permission.checked": "abort",
    "llm.failed": "replan",
}


class FailureAnalyzer:
    def __init__(self) -> None:
        self._replay = ReplayEngine()

    def analyze(self, trace_id: str) -> Dict[str, Any]:
        timeline = self._replay.replay(trace_id)
        if not timeline:
            return {
                "trace_id": trace_id,
                "status": "unknown",
                "reason": "no events recorded for trace",
                "suggested_recovery": "none",
            }

        names = [e["name"] for e in timeline]

        if "task.completed" in names:
            return {
                "trace_id": trace_id,
                "status": "ok",
                "event_count": len(timeline),
                "suggested_recovery": "none",
            }

        failed_idx = names.index("task.failed") if "task.failed" in names else None
        if failed_idx is not None:
            failure_event = self._attribute_failure(timeline, failed_idx, trace_id)
            return {
                "trace_id": trace_id,
                "status": "failed",
                "event_count": len(timeline),
                "failure": failure_event,
                "suggested_recovery": failure_event.get("recovery", "replan"),
            }

        # Started but never completed -> likely crash / timeout / client disconnect.
        last = timeline[-1]
        return {
            "trace_id": trace_id,
            "status": "incomplete",
            "event_count": len(timeline),
            "reason": "missing completion event (timeout or crash)",
            "last_event": last["name"],
            "suggested_recovery": "replan",
        }

    def _attribute_failure(self, timeline: List[Dict[str, Any]],
                           failed_idx: int, trace_id: str) -> Dict[str, Any]:
        prefix = timeline[:failed_idx]
        for e in reversed(prefix):
            data = e["data"] or {}
            if e["name"] in ("tool.executed", "action.executed") and data.get("success") is False:
                return {
                    "subsystem": e["name"],
                    "tool": data.get("tool") or data.get("intent") or "unknown",
                    "error": data.get("error", ""),
                    "latency_ms": data.get("duration_ms"),
                    "recovery": _FAILURE_RECOVERY.get(e["name"], "replan"),
                }
        audit_failure = self._audit_failure(trace_id)
        if audit_failure:
            return audit_failure
        if prefix:
            last = prefix[-1]
            return {
                "subsystem": "core",
                "last_event": last["name"],
                "error": (last["data"] or {}).get("error", ""),
                "recovery": "replan",
            }
        return {
            "subsystem": "core",
            "last_event": "task.failed",
            "error": "",
            "recovery": "replan",
        }

    def _audit_failure(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Fall back to the audit log for the failed tool entry (record_tool path)."""
        if not trace_id:
            return None
        try:
            from security.audit import get_audit_log
            rows = get_audit_log().query_trace(trace_id, limit=50)
        except Exception:
            return None
        for r in reversed(rows):
            if not r.get("success") and r.get("tool"):
                return {
                    "subsystem": "tool.executed",
                    "tool": r["tool"],
                    "error": r.get("error") or "",
                    "latency_ms": r.get("duration_ms"),
                    "recovery": "retry",
                }
        return None
