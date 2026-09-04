"""Pluggable backends for the J-Browser bridge server.

The extension talks to the bridge over HTTP/SSE; the bridge talks to an
intelligence backend. A backend is anything that can answer ``stream_chat``
with SSE events and report a status.

``EchoBackend`` is the default when the JARVIS kernel is not attached — it
produces a deterministic, context-aware reply (with a clear offline notice) so
the browser AI layer is fully functional end-to-end as a UX even before the
kernel is wired. ``KernelBackend`` is the seam for driving the real JARVIS
agent stack (Phase: kernel integration).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

# A callable that emits one SSE event dict to the client.
Emitter = Callable[[dict[str, Any]], None]


class Backend(ABC):
    name: str = "backend"

    @abstractmethod
    def status(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def stream_chat(self, session_id: str, messages: list[dict[str, Any]],
                    page: dict[str, Any] | None, emit: Emitter) -> None:
        ...


class EchoBackend(Backend):
    """Deterministic, context-aware stub. Always healthy; simulates streaming."""

    name = "echo"

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "backend": self.name,
            "kernel": "offline",
            "name": "JBrowserBridge",
            "version": "0.1.0",
            "streaming": True,
        }

    def _page_summary(self, page: dict[str, Any] | None) -> str:
        page = page or {}
        bits = []
        if page.get("title"):
            bits.append(f'title: {page["title"]}')
        if page.get("url"):
            bits.append(f'url: {page["url"]}')
        selection = (page.get("selection") or "").strip()
        if selection:
            bits.append(f'selection: "{selection[:300]}"')
        return "; ".join(bits) or "no page context"

    def stream_chat(self, session_id: str, messages: list[dict[str, Any]],
                    page: dict[str, Any] | None, emit: Emitter) -> None:
        last = messages[-1]["content"] if messages else ""
        page_summary = self._page_summary(page)

        reply = (
            "Hello — this is the JARVIS browser preview, running with the "
            "offline stub backend. The live JARVIS kernel is not attached yet, "
            "so I can't reason for real.\n\n"
            f'You asked: “{last.strip()[:400]}”\n\n'
            f"Page context I received:\n  {page_summary}\n\n"
            "To turn on live intelligence, start the JARVIS bridge with a real "
            "kernel backend (see docs/jbrowser/)."
        )

        emit({"type": "start", "session_id": session_id, "backend": self.name})
        for i in range(0, len(reply), 40):
            emit({"type": "delta", "text": reply[i:i + 40]})
            time.sleep(0.004)
        emit({"type": "done", "id": session_id, "backend": self.name})


class KernelBackend(Backend):
    """Seam for driving the real JARVIS agent stack.

    Not yet wired end-to-end. ``stream_chat`` currently delegates to a thin
    responder and records that kernel integration is pending; replace
    ``_run_engine`` with a call into the JARVIS agent loop (core/agent/loop.py)
    or a streaming model gateway call.
    """

    name = "kernel"

    def __init__(self, engine=None) -> None:
        self._engine = engine

    def status(self) -> dict[str, Any]:
        if self._engine is None:
            return {
                "ok": True,
                "backend": self.name,
                "kernel": "offline",
                "name": "JBrowserBridge",
                "version": "0.1.0",
                "note": "kernel engine not attached",
            }
        return {
            "ok": True,
            "backend": self.name,
            "kernel": "online",
            "name": "JBrowserBridge",
            "version": "0.1.0",
            "streaming": True,
        }

    def _run_engine(self, session_id: str, messages: list[dict[str, Any]],
                    page: dict[str, Any] | None, emit: Emitter) -> None:
        # TODO(Phase kernel): route into the JARVIS agent loop / model gateway
        # and stream tokens via emit({"type":"delta","text": token}).
        emit({"type": "start", "session_id": session_id, "backend": self.name})
        emit({
            "type": "delta",
            "text": "Kernel backend selected, but the engine is not attached yet. "
                    "See docs/jbrowser/ for the kernel integration seam.",
        })
        emit({"type": "done", "id": session_id, "backend": self.name})

    def stream_chat(self, session_id: str, messages: list[dict[str, Any]],
                    page: dict[str, Any] | None, emit: Emitter) -> None:
        self._run_engine(session_id, messages, page, emit)


def make_backend(kind: str | None = None, engine=None) -> Backend:
    kind = (kind or "echo").lower()
    if kind == "kernel":
        return KernelBackend(engine=engine)
    return EchoBackend()
