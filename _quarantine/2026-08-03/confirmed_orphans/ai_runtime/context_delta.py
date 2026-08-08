"""Context Delta Updates — Only append changes instead of rebuilding prompts.

Previous Prompt → Only append changes.
"""
import logging
import time
import threading
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger("ai_runtime.context_delta")


@dataclass
class ContextDelta:
    """A delta (change) to the context."""
    delta_id: str = ""
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    modified: Dict[str, str] = field(default_factory=dict)
    timestamp: float = 0.0
    token_delta: int = 0


class ContextDeltaManager:
    """Track and apply context changes incrementally.

    Instead of rebuilding the full prompt every time:
    1. Keep the previous prompt
    2. Compute what changed (delta)
    3. Apply only the delta
    """

    def __init__(self):
        self._previous_context: Dict[str, str] = {}
        self._deltas: List[ContextDelta] = []
        self._lock = threading.Lock()
        self._delta_count = 0
        self._total_tokens_saved = 0

    def compute_delta(self, new_context: Dict[str, str]) -> ContextDelta:
        """Compute the delta between previous and new context."""
        self._delta_count += 1
        delta = ContextDelta(
            delta_id=f"delta_{self._delta_count}",
            timestamp=time.time(),
        )

        for key, value in new_context.items():
            if key not in self._previous_context:
                delta.added.append(key)
                delta.token_delta += len(value.split())
            elif self._previous_context[key] != value:
                delta.modified[key] = key
                delta.token_delta += len(value.split())

        for key in self._previous_context:
            if key not in new_context:
                delta.removed.append(key)
                delta.token_delta -= len(self._previous_context[key].split())

        self._deltas.append(delta)
        if len(self._deltas) > 100:
            self._deltas = self._deltas[-100:]

        self._previous_context = dict(new_context)
        return delta

    def apply_delta(self, base_prompt: str, delta: ContextDelta,
                    context: Dict[str, str]) -> str:
        """Apply a delta to the base prompt."""
        lines = base_prompt.split('\n')

        for key in delta.removed:
            lines = [l for l in lines if not l.startswith(f"[{key}]:")]

        for key in delta.added + list(delta.modified.keys()):
            if key in context:
                lines.append(f"[{key}]: {context[key]}")

        return '\n'.join(lines)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_deltas": self._delta_count,
                "avg_token_delta": round(
                    sum(d.token_delta for d in self._deltas) / max(len(self._deltas), 1), 1
                ),
            }


_delta_manager_instance: Optional[ContextDeltaManager] = None


def get_context_delta_manager() -> ContextDeltaManager:
    global _delta_manager_instance
    if _delta_manager_instance is None:
        _delta_manager_instance = ContextDeltaManager()
    return _delta_manager_instance
