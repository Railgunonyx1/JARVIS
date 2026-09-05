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

    ``engine`` is a :class:`jbrowser_bridge.engine.StreamEngine` (the default
    kernel engine is :class:`ModelGatewayEngine`, which routes chat through
    ProviderRouter.complete_stream with budgets). With no engine attached,
    ``stream_chat`` produces a clear "not attached" notice so the browser AI
    layer still functions as a UX before a kernel is wired.
    """

    name = "kernel"

    def __init__(self, engine=None) -> None:
        self._engine = engine

    @property
    def engine(self):
        return self._engine

    def status(self) -> dict[str, Any]:
        payload = {
            "ok": True,
            "backend": self.name,
            "name": "JBrowserBridge",
            "version": "0.1.0",
            "streaming": True,
        }
        if self._engine is None:
            payload["kernel"] = "offline"
            payload["note"] = "kernel engine not attached"
        else:
            payload["kernel"] = "online"
            payload["engine"] = self._engine.name
        return payload

    def _not_attached(self, session_id: str, emit: Emitter) -> str:
        emit({"type": "start", "session_id": session_id, "backend": self.name})
        note = (
            "The JARVIS kernel is not attached to this bridge yet. "
            "Start the bridge with a kernel engine (see docs/jbrowser/) to "
            "enable live intelligence for the browser."
        )
        emit({"type": "delta", "text": note})
        emit({"type": "done", "id": session_id, "backend": self.name})
        return note

    def stream_chat(self, session_id: str, messages: list[dict[str, Any]],
                    page: dict[str, Any] | None, emit: Emitter) -> None:
        if self._engine is not None:
            self._engine.stream_chat(session_id, messages, page, emit)
            return
        self._not_attached(session_id, emit)


def make_backend(kind: str | None = None, engine=None) -> Backend:
    kind = (kind or "echo").lower()
    if kind == "kernel":
        return KernelBackend(engine=engine)
    return EchoBackend()
