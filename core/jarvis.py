"""JARVIS MK-X — Legacy orchestrator (DEPRECATED).

The authoritative agent runtime is ``core.agent.loop.AgentLoop``.
Use ``runtime.kernel.build_kernel()`` to assemble a ready-to-run agent.

This stub preserves ``JarvisMKX`` as an import target for legacy test
scripts only.  It delegates to the active path where possible and
raises ``DeprecationWarning`` on construction.
"""

from __future__ import annotations

import warnings
from typing import Any


class JarvisMKX:
    """Compatibility stub — delegates to the active AgentLoop runtime.

    This class exists solely so legacy test scripts that do
    ``from core.jarvis import JarvisMKX`` do not break with an
    ``ImportError``.  All new code must use ``AgentLoop`` directly.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        warnings.warn(
            "JarvisMKX is deprecated. Use runtime.kernel.build_kernel() "
            "which returns a core.agent.loop.AgentLoop instance.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Lazily build the active kernel so the legacy path still works
        # for smoke tests and old benchmarks.
        from runtime.kernel import build_kernel
        self._runtime = build_kernel()
        self._loop = self._runtime.agent_loop
        self.session_id = getattr(self._loop, "trace_id", "legacy")
        # Expose commonly-used legacy attributes as pass-throughs
        self.router = self._loop.router
        self.registry = self._loop.registry
        self.context = self._loop.context_manager
        self.memory = self._loop.mem

    async def process_text(self, text: str) -> str:  # noqa: D401
        """Legacy one-shot: goal → response string."""
        result = await self._loop.run(text)
        return result.response

    async def classify_intent(self, text: str) -> Any:
        """Legacy intent classification (delegates to intent router)."""
        from core.intent_router import IntentRouter
        router = IntentRouter()
        return router.classify(text)

    def get_status(self) -> dict[str, Any]:
        """Legacy status dict (providers, memory, etc.)."""
        return {
            "providers": self.router.status,
            "session": self.session_id,
        }

    def shutdown(self) -> None:
        """Legacy cleanup."""
        from runtime.kernel import close_kernel
        close_kernel(self._runtime)
