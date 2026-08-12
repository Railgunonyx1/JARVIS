"""Unified provider types for JARVIS MK-X.

Single source of truth for tool-calling and response models so provider
specifics never leak into the agent runtime. All providers normalize their
SDK output into these shapes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A normalized function-call request from an LLM."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str = ""


@dataclass
class Usage:
    """Token usage across providers."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider.

    ``tool_calls`` is populated when the model requested function execution.
    The agent loop executes those calls; a final answer arrives with empty
    ``tool_calls`` and populated ``text``.
    """

    text: str
    model: str
    provider: str
    tokens_used: int = 0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    tool_calls: list[ToolCall] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


def openai_tools_param(tools: list | None) -> list | None:
    """Return OpenAI-style tools (the canonical form) or None when empty."""
    return tools or None


def parse_openai_tool_calls(choice_message) -> list[ToolCall]:
    """Extract ToolCalls from an OpenAI-style chat completion message."""
    calls: list[ToolCall] = []
    raw = getattr(choice_message, "tool_calls", None) or []
    for entry in raw:
        fn = getattr(entry, "function", None)
        if fn is None or not getattr(fn, "name", ""):
            continue
        try:
            arguments = json.loads(fn.arguments or "{}")
            if not isinstance(arguments, dict):
                arguments = {"value": arguments}
        except (TypeError, ValueError):
            arguments = {}
        calls.append(ToolCall(name=fn.name, arguments=arguments, id=getattr(entry, "id", "") or ""))
    return calls


def parse_ollama_tool_calls(message: dict) -> list[ToolCall]:
    """Extract ToolCalls from an Ollama message dict."""
    calls: list[ToolCall] = []
    for entry in (message.get("tool_calls") or []):
        fn = entry.get("function", {}) if isinstance(entry, dict) else {}
        name = fn.get("name", "")
        if name:
            calls.append(ToolCall(name=name, arguments=fn.get("arguments") or {}, id=name))
    return calls


def to_gemini_tools(tools: list | None) -> list | None:
    """Convert OpenAI-style tool schemas to Gemini function_declarations."""
    if not tools:
        return None
    declarations = []
    for entry in tools:
        fn = entry.get("function", entry) if isinstance(entry, dict) else entry
        declarations.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return [{"function_declarations": declarations}]


def parse_gemini_function_calls(response) -> list[ToolCall]:
    """Extract ToolCalls from a Gemini generate_content response."""
    calls: list[ToolCall] = []
    try:
        for candidate in response.candidates:
            for part in candidate.content.parts:
                fc = getattr(part, "function_call", None)
                if fc is not None and getattr(fc, "name", ""):
                    calls.append(ToolCall(name=fc.name, arguments=dict(fc.args or {}), id=fc.name))
    except Exception:
        pass
    return calls


def json_args(arguments_json: str) -> dict[str, Any]:
    """Safely parse a JSON-encoded arguments string into a dict."""
    try:
        parsed = json.loads(arguments_json or "{}")
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except (TypeError, ValueError):
        return {}
