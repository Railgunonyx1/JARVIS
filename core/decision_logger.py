"""DecisionLogger — records every request/tool decision for auditability.

Bridges the two existing stores that were previously unwired:

  - EventStore (events.db): coarse decision timeline (request -> completion).
  - AuditLog  (audit.db):  per-tool execution record (allowed / success / ms).

Wiring points: core/jarvis.py (process_text, process_text_streaming,
_handle_action) and the quarantined _quarantine/core/executor.py (AgentExecutor).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from typing import Any

from core.event_store import get_event_store
from security.audit import AuditEntry, get_audit_log

logger = logging.getLogger("jarvis.decision_logger")


def _params_hash(params: dict[str, Any]) -> str:
    """Stable short hash of tool parameters; raw values never hit the audit store."""
    try:
        import orjson
        raw = orjson.dumps(params or {}, default=str)
    except Exception:
        raw = str(sorted((params or {}).items())).encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()[:12]


def _scrub_params_values(text: str, params: dict[str, Any]) -> str:
    """Strip any argument values that leaked into a persisted message.

    Defense-in-depth for the audit store: reasons, errors, and other
    diagnostics may embed parameter values (e.g. a URL in a sensitive-site
    denial). Raw values never reach the store — only the params_hash does.
    """
    if not text:
        return text
    for value in (params or {}).values():
        if isinstance(value, str) and len(value) >= 3 and value in text:
            text = text.replace(value, f"<redacted:{len(value)}>")
    return text


class DecisionLogger:
    """Lazy-singleton facade over EventStore + AuditLog."""

    def __init__(self) -> None:
        self._events: Any = None
        self._audit: Any = None

    @property
    def events(self):
        if self._events is None:
            self._events = get_event_store()
        return self._events

    @property
    def audit(self):
        if self._audit is None:
            self._audit = get_audit_log()
        return self._audit

    # -- task lifecycle -----------------------------------------------------
    def begin_task(self, request: str, source: str = "") -> str:
        """Open a trace for a user request. Returns the trace_id."""
        trace_id = uuid.uuid4().hex[:12]
        try:
            self.events.store(
                "request.received",
                {"request": request[:200], "source": source},
                source="core",
                trace_id=trace_id,
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("begin_task failed: %s", e)
        return trace_id

    # -- event store ---------------------------------------------------------
    def record(self, trace_id: str, name: str, data: dict[str, Any] | None = None,
               **extra) -> None:
        """Synchronous event write (safe for executor's thread).

        Accepts either a positional dict or keyword data.
        """
        if not trace_id:
            return
        if data is None:
            data = extra
        elif extra:
            data = {**data, **extra}
        try:
            self.events.store(name, data, source="core", trace_id=trace_id)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("Event record failed: %s", e)

    async def record_async(self, trace_id: str, name: str, data: dict[str, Any] | None = None,
                           **extra) -> None:
        """Off-thread event write for the async request path."""
        if not trace_id:
            return
        if data is None:
            data = extra
        elif extra:
            data = {**data, **extra}
        try:
            await asyncio.to_thread(self.events.store, name, data, "core", trace_id)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("Event record failed: %s", e)

    # -- audit store ----------------------------------------------------------
    def record_tool(self, trace_id: str, tool: str, params: dict[str, Any],
                    allowed: bool = True, success: bool = True,
                    duration_ms: float = 0.0, error: str | None = None,
                    mode: str = "", session_id: str = "") -> None:
        """Write a tool.executed audit entry (buffered AuditLog write)."""
        if not trace_id:
            return
        try:
            entry = AuditEntry(
                session_id=session_id,
                action="tool.executed",
                tool=tool,
                permission_level=1 if allowed else 0,
                allowed=allowed,
                duration_ms=round(duration_ms, 1),
                success=success,
                error=_scrub_params_values(
                    (error or "")[:300], params or {},
                ),
                params_hash=_params_hash(params or {}),
                mode=mode,
                trace_id=trace_id,
            )
            self.audit.log(entry)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("Audit record failed: %s", e)

    def flush(self) -> None:
        try:
            self.audit.flush()
        except Exception:  # pragma: no cover - defensive
            pass


_logger: DecisionLogger | None = None


def get_decision_logger() -> DecisionLogger:
    global _logger
    if _logger is None:
        _logger = DecisionLogger()
    return _logger
