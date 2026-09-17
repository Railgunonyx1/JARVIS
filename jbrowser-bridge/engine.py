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
import threading
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass


def _split_model_choice(model: str | None) -> tuple[str | None, str | None]:
    """Split a UI model choice into (provider, model).

    Accepts ``"groq/llama-3.3-70b"`` (preferred), a bare model id (routed to
    whichever provider claims it, Ollama tags always match locally), or a
    provider name alone (that provider's configured model).
    """
    if not model:
        return None, None
    choice = str(model).strip()
    if "/" in choice:
        provider, _, model_id = choice.partition("/")
        return provider or None, model_id or None
    if choice in _PROVIDER_NAMES():
        return choice, None
    return None, choice


def _PROVIDER_NAMES() -> set[str]:
    """Provider names known to the router config (lazy, never raises)."""
    try:
        router = _get_router()
        return set(getattr(router, "_providers", {}).keys())
    except Exception:  # noqa: BLE001
        return set()

Emitter = Callable[[dict], None]


# ── Shared event loop (latency) ──────────────────────────────────
# asyncio.run() per message tears down every pooled HTTP connection and pays
# a fresh TCP+TLS handshake to each provider on every hello (~1s+ of pure
# latency). One persistent background loop keeps provider clients and their
# connection pools warm across requests.
_shared_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()

# Upper bound on a single chat turn: a hung provider (SDK default is 120s)
# must not pin the handler thread — the shared loop is the only one.
_MSG_TIMEOUT_S = 30.0


def _get_shared_loop() -> asyncio.AbstractEventLoop:
    """Return the persistent loop, creating it exactly once.

    Check-then-act is guarded so concurrent first-hello requests cannot spawn
    two ``bridge-async-loop`` threads (loops and their connection pools would
    split and leak).
    """
    global _shared_loop
    if _shared_loop is not None and not _shared_loop.is_closed():
        return _shared_loop
    with _loop_lock:
        if _shared_loop is None or _shared_loop.is_closed():
            loop = asyncio.new_event_loop()
            threading.Thread(
                target=loop.run_forever, daemon=True, name="bridge-async-loop",
            ).start()
            _shared_loop = loop
    return _shared_loop


def _run_on_shared_loop(coro):
    """Run ``coro`` on the persistent loop; block the caller until done.

    Bounded by ``_MSG_TIMEOUT_S`` — a provider that hangs (or an SDK whose
    default timeout is 120s) cannot pin the handler thread forever.
    """
    future = asyncio.run_coroutine_threadsafe(coro, _get_shared_loop())
    return future.result(timeout=_MSG_TIMEOUT_S)


# ── First-token race (latency) ───────────────────────────────────
# Reduced from 3 to 1: when the router's availability check says a provider
# is healthy, don't race it against 2 others on every short request. The
# availability check already filtered out the down providers; racing healthy
# ones in parallel is what burned rate limits on hello-scale requests. A
# single first-healthy probe keeps the fallback safety (the router still
# falls back on transient errors) without paying 3x connect/timeout on each
# turn.
_RACE_MAX_PROBES = 1


def _make_think_filter():
    """Stateful <think>-block filter (reasoning models stream their
    thoughts first; users see only the answer). Returns (filter, flush).
    Tag boundaries straddling chunks are handled by holding back the longest
    buffer suffix that is a prefix of the tag."""
    state = {"in": False, "buf": ""}
    OPEN, CLOSE = "<think>", "</think>"

    def _feed(piece: str) -> str:
        state["buf"] += piece
        out: list[str] = []
        while state["buf"]:
            if state["in"]:
                end = state["buf"].find(CLOSE)
                if end == -1:
                    state["buf"] = state["buf"][-(len(CLOSE) - 1):]
                    break
                state["buf"] = state["buf"][end + len(CLOSE):]
                state["in"] = False
            else:
                start = state["buf"].find(OPEN)
                if start == -1:
                    hold = 0
                    for k in range(min(len(state["buf"]), len(OPEN) - 1), 0, -1):
                        if state["buf"].endswith(OPEN[:k]):
                            hold = k
                            break
                    emit_from = len(state["buf"]) - hold
                    if emit_from > 0:
                        out.append(state["buf"][:emit_from])
                        state["buf"] = state["buf"][emit_from:]
                    break
                if start > 0:
                    out.append(state["buf"][:start])
                state["buf"] = state["buf"][start + len(OPEN):]
                state["in"] = True
        return "".join(out)

    def _flush() -> str:
        tail = state["buf"]
        state["buf"] = ""
        return "" if state["in"] else tail

    return _feed, _flush


_sticky_winner: str | None = None


def _race_providers(router, messages, system_prompt, max_tokens,
                    model: str | None = None):
    """Async generator fed by the first provider to emit a VISIBLE token.

    Sequential fallback chains serialize every dead provider ahead of the
    live one: a hello pays each unhealthy provider's connect/timeout before
    the first token arrives. Healthy providers (top of the fallback chain,
    capped at ``_RACE_MAX_PROBES``) start in parallel; the first to produce
    a visible chunk wins (reasoning models' <think> preamble does NOT win —
    the user wants the answer, not the thoughts) and the losers are
    cancelled mid-flight. Down providers are filtered by the router's
    availability check, so the steady state is a single warm connection.

    Sticky winner: the provider that won the last race leads the next one.
    A 429ing chain head no longer costs its losers' connections on every
    turn — the proven-fast provider gets retried first alone; only if it
    fails does the full race re-form.
    """
    global _sticky_winner
    full_chain = router._get_available_chain()
    if _sticky_winner and _sticky_winner in full_chain:
        chain = [_sticky_winner] + \
            [n for n in full_chain if n != _sticky_winner][:_RACE_MAX_PROBES - 1]
    else:
        chain = full_chain[:_RACE_MAX_PROBES]
    if not chain:
        raise RuntimeError("No LLM providers available.")

    async def _stream():
        if len(chain) == 1:
            global _sticky_winner
            feed, flush = _make_think_filter()
            winner_provider = router._providers[chain[0]]
            produced_any = False
            try:
                async for chunk in winner_provider.complete_stream(
                    messages, system_prompt, max_tokens,
                ):
                    visible = feed(chunk)
                    if visible:
                        # Keep meta-event provenance identical to the race path.
                        router._last_provider = chain[0]
                        router._last_model = winner_provider.model
                        produced_any = True
                        yield visible
                tail = flush()
                if tail:
                    yield tail
                # Single-probe still remembers the winner: with _RACE_MAX_PROBES
                # low, the race branch is rarely reached, so sticky is armed
                # here instead of never.
                if produced_any:
                    _sticky_winner = chain[0]
                return
            except Exception:
                if produced_any:
                    raise  # mid-stream failure cannot be replayed elsewhere
                # Sticky winner / chain head dead before the first token:
                # unstick and walk the FULL router chain (remaining healthy
                # providers) instead of failing the turn.
                _sticky_winner = None
                walked = False
                async for chunk in router.complete_stream(
                    messages, system_prompt, max_tokens,
                ):
                    visible = feed(chunk)
                    if visible:
                        walked = True
                        yield visible
                tail = flush()
                if tail:
                    walked = True
                    yield tail
                # The fallback walk found a live provider: remember it so the
                # next turn probes it first instead of re-paying the dead head.
                if walked and router._last_provider:
                    _sticky_winner = router._last_provider
                return

        queue: asyncio.Queue = asyncio.Queue()

        async def _pump(name: str) -> None:
            provider = router._providers[name]
            feed, _flush = _make_think_filter()
            try:
                async for chunk in provider.complete_stream(
                    messages, system_prompt, max_tokens,
                ):
                    visible = feed(chunk)
                    if visible:
                        # Provenance: report the winner for the meta event
                        # (the race bypasses router.complete_stream, which
                        # would normally track _last_provider/_last_model).
                        router._last_provider = name
                        router._last_model = provider.model
                        await queue.put(("chunk", name, visible))
            except Exception:
                pass  # a loser dying is expected; the race resolves regardless
            finally:
                tail = _flush()
                if tail:
                    await queue.put(("chunk", name, tail))
                # put_nowait: unbounded queue, and a cancelled task's finally
                # must never re-suspend (that would swallow the cancellation).
                queue.put_nowait(("done", name, None))

        task_by_name = {
            name: asyncio.ensure_future(_pump(name)) for name in chain
        }
        winner: str | None = None
        failures = 0
        try:
            while True:
                kind, name, payload = await queue.get()
                if kind == "done":
                    if winner is None:
                        failures += 1
                        if failures == len(chain):
                            # Nobody produced a visible token: unstick so the
                            # next turn re-forms the full race from scratch.
                            _sticky_winner = None
                            raise RuntimeError(
                                "All LLM providers failed to stream a reply."
                            )
                    elif name == winner:
                        return  # winner finished: the reply is complete
                    continue
                # chunk
                if winner is None:
                    winner = name
                    _sticky_winner = name
                    # Cancel only the losers — the winner's own task must keep
                    # producing its remaining chunks.
                    for loser, t in task_by_name.items():
                        if loser != winner and not t.done():
                            t.cancel()
                if name == winner:
                    yield payload
                # losers' stray in-flight chunks are dropped by name check
        finally:
            for t in task_by_name.values():
                if not t.done():
                    t.cancel()

    return _stream()


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


def _msg_tokens(msg: dict) -> int:
    """Cheap token estimate for one message — length math, no JSON round-trip.

    The old path serialized the whole window (and each dropped message) with
    ``json.dumps`` just to run the same ``len(content) / 4`` heuristic — an
    O(n^2) cost on the shared loop for a bound that only needs character
    counts. Estimating from the string fields is equivalent for the /4 rule
    and constant-time.
    """
    content = msg.get("content")
    if isinstance(content, str):
        return max(1, len(content) // 4)
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, dict):
                for key in ("text", "content"):
                    val = part.get(key)
                    if isinstance(val, str):
                        total += len(val)
                        break
            elif isinstance(part, str):
                total += len(part)
        return max(1, total // 4)
    return max(1, len(str(content)) // 4)


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
        total = sum(_msg_tokens(m) for m in head) + sum(_msg_tokens(m) for m in msgs)
        while msgs and total > budget.max_input_tokens:
            dropped = msgs.pop(0)
            total -= _msg_tokens(dropped)
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
    """Lazily build (and cache) the real provider router.

    Locked so a chat arriving before the boot warmup completes cannot build a
    second router (an unlocked check-then-act here raced the warmup thread and
    doubled the ~3s router build + ~8s SDK import on cold start).
    """
    global _router_cache
    if _router_cache is not None:
        return _router_cache
    with _router_lock:
        if _router_cache is None:
            _ensure_repo_root_imports()
            from core.api_keys import router_api_keys
            from providers.router import ProviderRouter
            from runtime.kernel import _load_models_config
            # Single shared normalization (see core.api_keys.router_api_keys):
            # maps "<provider>_api_key" (+ numbered extras) to the plain shape
            # ProviderRouter expects, so keyed cloud providers initialize.
            _router_cache = ProviderRouter(_load_models_config(), router_api_keys())
    return _router_cache


def _ensure_repo_root_imports() -> None:
    """Make the JARVIS repo root importable regardless of launch mode.

    ``runtime`` / ``providers`` live at the repo root; a server run as
    ``python jbrowser-bridge/server.py`` has only ``jbrowser-bridge`` on
    ``sys.path``. Insert the repo root once when the provider stack is first
    needed (lazy path, so echo-only servers never pay for it).
    """
    import os
    import sys as _sys
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _sys.path[0] != repo_root and os.path.isdir(os.path.join(repo_root, "runtime")):
        _sys.path.insert(0, repo_root)


_router_cache = None
_router_lock = threading.Lock()


# ── Exact-match response cache ─────────────────────────────────
# Identical chat turns (same trimmed prompt window, system prompt, model)
# return the cached answer instantly — 0ms vs 200ms+. Correctness guard:
# a cache entry is invalidated whenever any session sends a *new* message
# shape (session content hash changes), so follow-ups never hit stale
# text. Only short replies are cached (long/creative answers are not
# worth the staleness risk).
_RESPONSE_CACHE: dict[str, str] = {}
_RESPONSE_CACHE_LOCK = threading.Lock()
_RESPONSE_CACHE_MAX = 64
_RESPONSE_CACHE_TTL_S = 300.0
_RESPONSE_CACHE_MAX_LEN = 1200


def _response_cache_key(prompt: list[dict], system_prompt: str,
                        model: str | None) -> str | None:
    """Cache key from the exact prompt window. None ⇒ do not cache."""
    import hashlib
    try:
        # Only cache short, single-turn exchanges: long histories make
        # exact-match hits rare and stale-hit risk higher.
        user_msgs = [m for m in prompt if m.get("role") == "user"]
        if len(user_msgs) != 1 or len(prompt) > 4:
            return None
        body = repr((prompt, system_prompt, model or ""))
        return hashlib.sha256(body.encode("utf-8", "replace")).hexdigest()
    except Exception:  # noqa: BLE001 - cache must never break chat
        return None


def _response_cache_get(key: str | None) -> str | None:
    if not key:
        return None
    with _RESPONSE_CACHE_LOCK:
        entry = _RESPONSE_CACHE.get(key)
    if not entry:
        return None
    stored_at, text = entry.split("|", 1)
    import time
    if time.time() - float(stored_at) > _RESPONSE_CACHE_TTL_S:
        with _RESPONSE_CACHE_LOCK:
            _RESPONSE_CACHE.pop(key, None)
        return None
    return text


def _response_cache_put(key: str | None, text: str) -> None:
    if not key or not text or len(text) > _RESPONSE_CACHE_MAX_LEN:
        return
    import time
    with _RESPONSE_CACHE_LOCK:
        if len(_RESPONSE_CACHE) >= _RESPONSE_CACHE_MAX:
            # drop the oldest entry (dict preserves insertion order)
            _RESPONSE_CACHE.pop(next(iter(_RESPONSE_CACHE)), None)
        _RESPONSE_CACHE[key] = f"{time.time()}|{text}"


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
            "You are JARVIS, the assistant built into the Orbit browser. "
            "Answer the user's question directly and conversationally in a "
            "few sentences. Do NOT output plans, numbered steps, or task "
            "breakdowns unless the user explicitly asks for a plan. Do not "
            "claim to have taken browser actions you did not perform; "
            "browser control happens only through JARVIS tools."
        )
        self.max_tokens = max_tokens

    @staticmethod
    def _default_streamer(messages, system_prompt, max_tokens,
                          model: str | None = None):
        """Real path: ProviderRouter.complete_stream with automatic fallback.

        ``model`` is an optional ``"provider/model"`` or bare model id; the
        router resolves which provider owns it and falls back safely. When no
        explicit model is requested the first-token race starts the top
        healthy providers in parallel so a dead one cannot gate the reply.
        """
        router = _get_router()
        preferred_provider, preferred_model = _split_model_choice(model)
        if preferred_provider is None and preferred_model is None:
            return _race_providers(router, messages, system_prompt, max_tokens, None)

        async def stream():
            async for chunk in router.complete_stream(
                messages,
                system_prompt,
                max_tokens=max_tokens,
                preferred_provider=preferred_provider,
                preferred_model=preferred_model,
            ):
                yield chunk

        return stream()

    def _models(self) -> list[dict]:
        """Selectable models across the configured fleet (for /v1/models)."""
        try:
            return _get_router().list_models()
        except Exception:  # noqa: BLE001 - discovery must never break chat
            return []

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

    # First visible token later than this → emit an instant acknowledgment
    # (Mark-LIII "Instant Acknowledgment"): the user hears the assistant
    # picked the message up instead of watching a silent spinner.
    _ACK_AFTER_S = 1.5
    _ACK_TEXT = "On it — working on that now…"

    def stream_chat(self, session_id: str, messages: list[dict],
                    page: dict | None, emit: Emitter,
                    model: str | None = None) -> str:
        prompt = self._build_prompt(messages, page)
        cache_key = _response_cache_key(prompt, self.system_prompt, model)
        cached = _response_cache_get(cache_key)
        if cached:
            emit({"type": "start", "session_id": session_id, "backend": self.name,
                  **({"model": model} if model else {})})
            emit({"type": "delta", "text": cached})
            emit({"type": "meta", "latency_ms": 0, "cached": True})
            emit({"type": "done", "id": session_id, "backend": self.name})
            return cached
        emit({"type": "start", "session_id": session_id, "backend": self.name,
              **({"model": model} if model else {})})
        out: list[str] = []
        produced = 0
        limit = self.budget.max_output_chars
        # Reasoning models (groq qwen3.x, deepseek-reasoner) emit a leading
        # <think>…</think> block; users should never see raw reasoning. The
        # block streams across chunks, so filter statefully: buffer everything
        # until the closing tag, then emit only the visible answer.
        think_state = {"in": False, "buf": ""}

        def _visible(piece: str) -> str:
            st = think_state
            st["buf"] += piece
            out_chunks: list[str] = []
            while st["buf"]:
                if st["in"]:
                    end = st["buf"].find("</think>")
                    if end == -1:
                        # Keep a tail in case the closing tag straddles chunks.
                        st["buf"] = st["buf"][-8:]
                        break
                    st["buf"] = st["buf"][end + 8:]
                    st["in"] = False
                else:
                    start = st["buf"].find("<think>")
                    if start == -1:
                        # No opening tag in the buffer. A partial "<think>" may
                        # still straddle the next chunk: hold back the longest
                        # suffix of the buffer that is a prefix of "<think>"
                        # (tag-prefix overlap, classic KMP-style rule). That
                        # covers any split position without false-holding on
                        # ordinary text like "I <3 thinks".
                        tag = "<think>"
                        hold = 0
                        for k in range(min(len(st["buf"]), len(tag) - 1), 0, -1):
                            if st["buf"].endswith(tag[:k]):
                                hold = k
                                break
                        emit_from = len(st["buf"]) - hold
                        if emit_from > 0:
                            out_chunks.append(st["buf"][:emit_from])
                            st["buf"] = st["buf"][emit_from:]
                        break
                    if start > 0:
                        out_chunks.append(st["buf"][:start])
                    st["buf"] = st["buf"][start + 7:]
                    st["in"] = True
            return "".join(out_chunks)

        try:
            import time as _time
            _turn_t0 = _time.monotonic()
            _acked = False

            async def _stream() -> str:
                nonlocal produced, _acked
                # Streamers predating per-chat model selection take 3 args;
                # try the 4-arg form first, fall back for custom/test streamers.
                try:
                    stream = self._streamer(
                        prompt, self.system_prompt, self.max_tokens, model,
                    )
                except TypeError:
                    stream = self._streamer(
                        prompt, self.system_prompt, self.max_tokens,
                    )
                async for chunk in stream:
                    visible = _visible(chunk)
                    if not visible:
                        # Slow first token: acknowledge before the silence
                        # becomes noticeable, at most once per turn.
                        if (not _acked and not produced
                                and _time.monotonic() - _turn_t0 > self._ACK_AFTER_S):
                            _acked = True
                            emit({"type": "ack", "text": self._ACK_TEXT})
                        continue
                    if not _acked and not produced:
                        _acked = True  # real token arrived: no ack needed
                    remaining = limit - produced
                    if remaining <= 0:
                        break
                    piece = visible if len(visible) <= remaining else visible[:remaining]
                    out.append(piece)
                    produced += len(piece)
                    emit({"type": "delta", "text": piece})
                # Flush anything still buffered (unclosed think block or tail).
                tail = think_state["buf"]
                if tail and not think_state["in"]:
                    out.append(tail)
                    produced += len(tail)
                    emit({"type": "delta", "text": tail})
                return "".join(out)

            text = _run_on_shared_loop(_stream())
            _response_cache_put(cache_key, text)
        except Exception as exc:  # noqa: BLE001 - the bridge must never crash
            emit({"type": "error", "message": str(exc)[:500], "code": "engine_error"})
            return ""
        emit({"type": "done", "id": session_id, "backend": self.name})
        return text


__all__ = ["Budget", "ModelGatewayEngine", "StreamEngine", "trim_messages"]
