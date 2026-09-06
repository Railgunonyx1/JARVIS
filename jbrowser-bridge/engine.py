"""Kernel engine seam for the J-Browser bridge (Phase C G7).

The bridge stays thin: ``KernelBackend`` only knows how to pump events to a
client. The intelligence lives behind a :class:`StreamEngine`, which the
backend is handed at construction time (``serve(..., engine=...)``).

``ModelGatewayEngine`` is the default kernel engine: it routes a chat through
the JARVIS provider layer (ProviderRouter.complete_stream — capability-aware
ModelGateway selection with automatic fallback), with a browser-agent system
prompt and the caller's page context folded in. Budgets bound BOTH directions:

* input — the message window is trimmed to ``Budget.max_messages`` and a
  ``max_input_tokens`` cap (oldest non-system turns dropped first);
* output — the stream is truncated at ``max_output_chars`` so a runaway reply
  can never flood the SSE client.

The streamer callable is injectable, so the engine and the whole bridge are
testable hermetically without a provider/API key. Import of the real provider
stack is lazy: ``#!/usr/bin/env python`` servers that only use the ``echo``
backend never pay for it.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

Emitter = Callable[[dict], None]


@dataclass(frozen=True)
class Budget:
    """Bidirectional budget for a browser chat turn."""

    max_messages: int = 10
    max_input_tokens: int = 6000
    max_output_chars: int = 8000


def _estimate_tokens(text: str) -> int:
    try:
        from core.context.budget import estimate_tokens  # type: ignore
        return estimate_tokens(text)
    except Exception:
        return len(text or "") // 4


def trim_messages(messages: list[dict], budget: Budget) -> list[dict]:
    """Trim a chat window to the budget (system message always kept first)."""
    msgs = [m for m in (messages or []) if isinstance(m, dict) and m.get("content")]
    if not msgs:
        return []

    head: list[dict] = []
    if msgs and (str(msgs[0].get("role")) == "system"):
        head, msgs = [msgs[0]], msgs[1:]

    if budget.max_messages > 0 and len(head) + len(msgs) > budget.max_messages:
        keep = max(1, budget.max_messages - len(head))
        msgs = msgs[-keep:]

    if budget.max_input_tokens > 0:
        total = _estimate_tokens(json.dumps(head, default=str)) + \
            _estimate_tokens(json.dumps(msgs, default=str))
        while msgs and total > budget.max_input_tokens:
            dropped = msgs.pop(0)
            total -= _estimate_tokens(json.dumps(dropped, default=str))
    return head + msgs


class StreamEngine(ABC):
    """A kernel-side intelligence that can answer a browser chat turn."""

    name: str = "engine"

    @abstractmethod
    def stream_chat(self, session_id: str, messages: list[dict],
                    page: dict | None, emit: Emitter) -> str:
        """Pump SSE events (start/delta/done/error) and return the final text."""


# Async streamer compatible with ProviderRouter.complete_stream.
Streamer = Callable[[list[dict], str, int], AsyncIterator[str]]


def _get_router():
    """Lazily build (and cache) the real provider router."""
    global _router_cache
    if _router_cache is None:
        from runtime.kernel import _load_api_keys, _load_models_config
        from providers.router import ProviderRouter
        _router_cache = ProviderRouter(_load_models_config(), _load_api_keys())
    return _router_cache


_router_cache = None


class ModelGatewayEngine(StreamEngine):
    """Stream a browser-agent reply through the JARVIS kernel/model gateway."""

    name = "model_gateway"

    def __init__(self, streamer: Streamer | None = None,
                 budget: Budget | None = None,
                 system_prompt: str | None = None,
                 max_tokens: int = 2048) -> None:
        self._streamer = streamer or self._default_streamer
        self.budget = budget or Budget()
        self.system_prompt = system_prompt or (
            "You are the JARVIS Orbit browsing assistant embedded in a "
            "Chromium-based browser. Answer concisely using the page context "
            "provided. Never claim to have taken browser actions you did not "
            "perform; browser control happens only through JARVIS tools."
        )
        self.max_tokens = max_tokens

    @staticmethod
    def _default_streamer(messages, system_prompt, max_tokens):
        """Real path: ProviderRouter.complete_stream with automatic fallback."""
        router = _get_router()

        async def stream():
            async for chunk in router.complete_stream(
                messages,
                system_prompt,
                max_tokens=max_tokens,
                preferred_provider=None,
                preferred_model=None,
            ):
                yield chunk

        return stream()

    def _build_prompt(self, messages: list[dict], page: dict | None) -> list[dict]:
        window = trim_messages(messages, self.budget)
        if page:
            bits: list[str] = []
            if page.get("title"):
                bits.append(f"Page title: {page['title']}")
            if page.get("url"):
                bits.append(f"Page URL: {page['url']}")
            selection = str(page.get("selection") or "").strip()
            if selection:
                bits.append(f"User selection: {selection[:600]}")
            if bits:
                window = window + [{
                    "role": "system",
                    "content": "Current page context:\n" + "\n".join(bits),
                }]
        if not window:
            window = [{"role": "user", "content": "(empty request)"}]
        return window

    def stream_chat(self, session_id: str, messages: list[dict],
                    page: dict | None, emit: Emitter) -> str:
        prompt = self._build_prompt(messages, page)
        emit({"type": "start", "session_id": session_id, "backend": self.name})
        out: list[str] = []
        limit = self.budget.max_output_chars
        try:
            async def _stream() -> str:
                async for chunk in self._streamer(
                    prompt, self.system_prompt, self.max_tokens,
                ):
                    remaining = limit - len("".join(out))
                    if remaining <= 0:
                        break
                    piece = chunk if len(chunk) <= remaining else chunk[:remaining]
                    out.append(piece)
                    emit({"type": "delta", "text": piece})
                return "".join(out)

            text = asyncio.run(_stream())
        except Exception as exc:  # noqa: BLE001 - the bridge must never crash
            emit({"type": "error", "message": str(exc)[:500], "code": "engine_error"})
            return ""
        emit({"type": "done", "id": session_id, "backend": self.name})
        return text


__all__ = ["Budget", "ModelGatewayEngine", "StreamEngine", "trim_messages"]