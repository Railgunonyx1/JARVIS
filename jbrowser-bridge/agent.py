"""G8 — end-to-end vertical slice: bridge /v1/agent -> AgentEngine -> AgentLoop
-> ToolExecutionService -> orbit.* tools -> BrowserController -> CDP.

``AgentEngine`` implements the same :class:`engine.StreamEngine` contract as
``ModelGatewayEngine``, but each turn runs a real :class:`AgentLoop` tasked
with the caller's request. Because the loop streams model tokens through
``on_chunk``, the bridge client sees the agent's final answer incrementally.

The single-tool-boundary invariant holds: the loop's ToolExecutionService is
the only path to browser actions, and every ``orbit.*`` tool routes through
``get_orbit_controller()`` -> CDP. High/critical browser mutations (click,
type, submit, execute_script) and sensitive-site navigation require explicit
operator consent; with no consent channel wired they are **denied** (fail
closed) exactly like the rest of JARVIS.

The loop factory is injectable so the hermetic suite can drive a fake
provider + fake CDP transport; the production factory
(:func:`build_orbit_agent_loop`) builds the real ProviderRouter from
``config/models.toml`` and is used only when a real kernel is attached.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

from engine import Budget, StreamEngine

AgentLoop = Any  # real import happens inside factories (lazy)

Factory = Callable[[], AgentLoop]


def build_orbit_agent_loop(
    *,
    confirmation_handler: Callable[[str, dict[str, Any]], str] | None = None,
    max_iterations: int = 6,
) -> AgentLoop:
    """Build a real AgentLoop whose only tools are the ``orbit.*`` catalog.

    Attempts the heavy kernel imports lazily so stdlib-only servers that never
    serve an agent task pay nothing. Uses the configured provider chain
    (ModelGateway -> ProviderRouter fallback) for reasoning; navigation /
    read tools auto-approve at low/medium risk, mutations require consent
    (denied without a confirmation handler).
    """
    from core.agent.loop import AgentLoop as _AgentLoop
    from core.agent.permissions import PermissionEngine
    from core.decision_logger import get_decision_logger
    from core.harness import Harness, HarnessConfig, HarnessType
    from providers.router import ProviderRouter
    from runtime.kernel import _load_api_keys, _load_models_config
    from tools.registry import ToolRegistry

    from orbit.tools import build_orbit_tools

    registry = ToolRegistry()
    registry.register_many(build_orbit_tools())

    logger = get_decision_logger()
    permissions = PermissionEngine(
        logger,
        mode="agent",
        confirmation_handler=confirmation_handler,
        fail_closed_risky=True,
    )
    _verified = os.environ.get("JARVIS_ORBIT_VERIFY", "0") in ("1", "true")
    harness = Harness(HarnessConfig(
        harness_type=HarnessType.MINIMAL,
        enable_verification=_verified,
        max_iterations=max_iterations,
        temperature=0.3,
        max_tool_calls_per_step=4,
    ))
    return _AgentLoop(
        router=ProviderRouter(_load_models_config(), _load_api_keys()),
        registry=registry,
        decision_logger=logger,
        harness=harness,
        confirmation_handler=confirmation_handler,
    )


class AgentEngine(StreamEngine):
    """Run one agent task per bridge turn (safe for concurrent threads)."""

    name = "agent_loop"

    def __init__(self,
                 loop_factory: Factory | None = None,
                 budget: Budget | None = None,
                 system_prompt: str | None = None,
                 confirmation_handler: Callable[[str, dict[str, Any]], str] | None = None,
                 max_iterations: int = 6) -> None:
        self._loop_factory = loop_factory or (
            lambda: build_orbit_agent_loop(
                confirmation_handler=confirmation_handler,
                max_iterations=max_iterations,
            )
        )
        self.budget = budget or Budget()
        self.system_prompt = system_prompt or (
            "You are JARVIS Orbit, the browsing agent inside a Chromium-based "
            "browser. Use the orbit.browser.* tools to inspect and navigate "
            "pages. Answer the user concisely. Never claim an action you did "
            "not execute. If an action needs approval you will not take it."
        )
        self._confirmation_handler = confirmation_handler

    def _goal(self, messages: list[dict], page: dict | None) -> str:
        goal = ""
        for m in reversed(messages or []):
            if isinstance(m, dict) and m.get("role") == "user" and m.get("content"):
                goal = str(m["content"])
                break
        if not goal and messages:
            goal = "Handle this request."
        if page:
            extra = []
            if page.get("title"):
                extra.append(f"page title is {page['title']!r}")
            if page.get("url"):
                extra.append(f"current URL is {page['url']}")
            if extra:
                goal = f"{goal}\nContext: {', '.join(extra)}."
        return goal

    def stream_chat(self, session_id: str, messages: list[dict],
                    page: dict | None, emit: Callable[[dict], None]) -> str:
        goal = self._goal(messages, page)
        emit({"type": "start", "session_id": session_id,
              "backend": self.name, "task": goal[:200]})
        loop = self._loop_factory()

        async def _on_chunk(chunk: str) -> None:
            emit({"type": "delta", "text": chunk})

        try:
            result = asyncio.run(
                loop.run(goal, session_id=session_id, on_chunk=_on_chunk)
            )
        except Exception as exc:  # noqa: BLE001 - the bridge must never crash
            emit({"type": "error", "message": str(exc)[:500], "code": "agent_error"})
            return ""
        payload = {
            "type": "done" if result.success else "error",
            "id": session_id,
            "backend": self.name,
            "success": result.success,
            "iterations": result.state.iteration,
            "tokens": result.state.tokens_used,
            "provider": result.state.provider,
            "model": result.state.model,
        }
        if result.success:
            payload["response"] = result.response
        else:
            payload["code"] = "task_failed"
            payload["message"] = str(result.error or "agent task failed")[:500]
        emit(payload)
        return result.response


__all__ = ["AgentEngine", "Factory", "build_orbit_agent_loop"]