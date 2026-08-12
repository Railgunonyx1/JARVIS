"""AgentState — mutable per-task state for the agent loop."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    """Live state for one agent task run."""

    task_id: str
    goal: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    tokens_used: int = 0
    start_time: float = field(default_factory=time.time)
    iteration: int = 0
    provider: str = ""
    model: str = ""
    context_usage: dict[str, Any] = field(default_factory=dict)

    def record_tool(self, name: str, tool_call_id: str, success: bool,
                    duration_ms: float, output: str = "", error: str = "",
                    metadata: dict[str, Any] | None = None) -> None:
        entry = {
            "id": tool_call_id,
            "name": name,
            "success": success,
            "duration_ms": round(duration_ms, 1),
            "output": (output or "")[:160],
        }
        diff = (metadata or {}).get("diff")
        if diff:
            entry["diff"] = diff[:800]
        self.tool_calls.append(entry)
        if not success and error:
            self.errors.append(error)

    def add_tokens(self, prompt: int, completion: int) -> None:
        self.tokens_used += prompt + completion

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "tool_calls": self.tool_calls,
            "files_changed": self.files_changed,
            "errors": self.errors,
            "tokens_used": self.tokens_used,
            "iteration": self.iteration,
            "provider": self.provider,
            "model": self.model,
            "context_usage": self.context_usage,
            "duration_ms": round((time.time() - self.start_time) * 1000, 1),
        }
