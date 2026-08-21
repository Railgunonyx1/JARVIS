"""Unified provider types for JARVIS MK-X.

Single source of truth for tool-calling and response models so provider
specifics never leak into the agent runtime. All providers normalize their
SDK output into these shapes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

_TOOL_NAME_SAFE = re.compile(r"[^a-zA-Z0-9_-]")


# ── Error types ────────────────────────────────────────────────────────

class ProviderError(Exception):
    """Base error for all provider failures."""

    def __init__(self, provider: str, message: str, *, retryable: bool = False):
        self.provider = provider
        self.retryable = retryable
        super().__init__(f"[{provider}] {message}")


class RateLimitError(ProviderError):
    """Provider returned a 429 / rate-limit / quota error."""

    def __init__(self, provider: str, message: str = "rate limit exceeded"):
        super().__init__(provider, message, retryable=True)


class ProviderTimeoutError(ProviderError):
    """Provider request exceeded its configured timeout."""

    def __init__(self, provider: str, timeout_s: float):
        super().__init__(provider, f"timeout after {timeout_s}s", retryable=True)
        self.timeout_s = timeout_s


class ProviderAuthError(ProviderError):
    """Provider rejected the API key / credentials."""

    def __init__(self, provider: str, message: str = "authentication failed"):
        super().__init__(provider, message, retryable=False)


class ProviderUnavailableError(ProviderError):
    """Provider is not reachable or package is missing."""

    def __init__(self, provider: str, message: str = "provider unavailable"):
        super().__init__(provider, message, retryable=True)


# ── Structured error classification ───────────────────────────────────

from enum import StrEnum


class ErrorKind(StrEnum):
    """Classification of provider errors for router decision-making."""
    RATE_LIMIT = "rate_limit"           # 429 / temporary throttling
    QUOTA_EXHAUSTED = "quota_exhausted"  # daily/monthly quota hit
    AUTH = "auth"                       # bad API key
    INVALID_REQUEST = "invalid_request" # malformed request
    TIMEOUT = "timeout"                 # request timed out
    OVERLOADED = "overloaded"           # 503 / server overloaded
    NETWORK = "network"                 # connection error
    SERVER_ERROR = "server_error"       # other 5xx
    UNKNOWN = "unknown"


def classify_provider_error(error_str: str, status_code: int | None = None) -> ErrorKind:
    """Classify an error string into a structured ErrorKind.

    Uses status codes when available, falls back to substring matching.
    Separates temporary throttling from permanent quota exhaustion.
    """
    lower = error_str.lower()

    # Status code takes priority
    if status_code == 429:
        # Distinguish temporary from permanent
        if any(m in lower for m in ("daily", "monthly", "permanently", "exceeded quota")):
            return ErrorKind.QUOTA_EXHAUSTED
        return ErrorKind.RATE_LIMIT
    if status_code == 401 or status_code == 403:
        return ErrorKind.AUTH
    if status_code == 400 or status_code == 422:
        return ErrorKind.INVALID_REQUEST
    if status_code == 504:
        return ErrorKind.TIMEOUT
    if status_code == 503:
        return ErrorKind.OVERLOADED
    if status_code and status_code >= 500:
        return ErrorKind.SERVER_ERROR

    # Substring fallback
    if any(m in lower for m in ("429", "rate limit", "too many requests", "throttl", "tokens per minute", "requests per minute", "request limit")):
        if any(m in lower for m in ("daily", "monthly", "permanently")):
            return ErrorKind.QUOTA_EXHAUSTED
        return ErrorKind.RATE_LIMIT
    if any(m in lower for m in ("quota exhausted", "daily quota", "credits", "billing")):
        return ErrorKind.QUOTA_EXHAUSTED
    if any(m in lower for m in ("resource_exhausted",)):
        # resource_exhausted can be temporary or permanent
        if any(m in lower for m in ("retry", "try again", "seconds")):
            return ErrorKind.RATE_LIMIT
        return ErrorKind.QUOTA_EXHAUSTED
    if any(m in lower for m in ("timeout", "timed out")):
        return ErrorKind.TIMEOUT
    if any(m in lower for m in ("connection", "connect", "network", "dns")):
        return ErrorKind.NETWORK
    if any(m in lower for m in ("overloaded", "capacity", "503", "service unavailable")):
        return ErrorKind.OVERLOADED
    if any(m in lower for m in ("unauthorized", "invalid key", "bad key", "authentication")):
        return ErrorKind.AUTH
    if any(m in lower for m in ("invalid", "malformed", "bad request")):
        return ErrorKind.INVALID_REQUEST

    return ErrorKind.UNKNOWN


def parse_retry_after(error_str: str) -> float | None:
    """Extract retry-after delay from error text. Returns seconds or None."""
    import re
    m = re.search(r"try again in ([\d.]+)\s*s", error_str, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    m = re.search(r"retry after ([\d.]+)\s*s", error_str, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def is_rate_limit_error(error_str: str) -> bool:
    """Return True if the error string indicates a transient rate limit."""
    kind = classify_provider_error(error_str)
    return kind in (ErrorKind.RATE_LIMIT, ErrorKind.OVERLOADED)


def sanitize_tools(tools: list | None) -> tuple[list | None, dict[str, str]]:
    """Replace illegal characters in tool names for strict upstreams.

    OpenAI-compatible gateways (Nvidia via OpenRouter, opencode_zen/Console)
    reject function names outside ``[a-zA-Z0-9_-]`` — JARVIS tools like
    ``filesystem.write`` violate that. Returns ``(sanitized_tools, name_map)``
    where ``name_map`` maps sanitized -> original; use :func:`restore_tool_names`
    on the model's replies so the agent loop still resolves real tool names.
    """
    if not tools:
        return tools, {}
    name_map: dict[str, str] = {}
    out: list[dict] = []
    for entry in tools:
        fn = entry.get("function", entry) if isinstance(entry, dict) else entry
        name = str(fn.get("name", ""))
        safe = _TOOL_NAME_SAFE.sub("_", name)
        if safe != name:
            name_map[safe] = name
        if isinstance(entry, dict) and "function" in entry:
            out.append({**entry, "function": {**fn, "name": safe}})
        else:
            out.append({**entry, "name": safe})
    return out, name_map


def restore_tool_names(tool_calls: list[ToolCall], name_map: dict[str, str]) -> list[ToolCall]:
    """Map model-returned (sanitized) tool names back to real JARVIS names."""
    for call in tool_calls:
        if call.name in name_map:
            call.name = name_map[call.name]
    return tool_calls


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
    """Return OpenAI-style tools (the canonical form) or None when empty.

    Schemas are compressed before sending: property-level descriptions are
    dropped (kept names/types/enums/required) and tool descriptions are
    truncated to ~60 chars. Cuts ~800 tokens off the 16-tool catalog (~1900
    tokens), which keeps calls under provider TPM budgets (e.g. Groq's
    6000/min) so the fast provider isn't abandoned after one request.
    """
    return _compress_tools(tools) if tools else None


def _compress_tools(tools: list) -> list:
    out: list[dict] = []
    for entry in tools:
        fn = entry.get("function", entry) if isinstance(entry, dict) else entry
        name = str(fn.get("name", ""))
        desc = str(fn.get("description", "") or "")
        if len(desc) > 60:
            desc = desc[:57].rstrip() + "..."
        params = fn.get("parameters") or {}
        props = {}
        for pname, pval in (params.get("properties") or {}).items():
            prop = {"type": pval.get("type", "string")}
            if isinstance(pval.get("items"), dict) and pval["items"].get("type"):
                prop["items"] = {"type": pval["items"]["type"]}
            if pval.get("enum") is not None:
                prop["enum"] = pval["enum"]
            props[pname] = prop
        compressed = {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": list(params.get("required") or []),
                },
            },
        }
        out.append(compressed)
    return out


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


def parse_ollama_tool_calls(message) -> list[ToolCall]:
    """Extract ToolCalls from an Ollama message (dict or Pydantic object).

    Ollama doesn't provide unique tool-call IDs like OpenAI does, so we
    generate sequential ones (``ollama_0``, ``ollama_1``, ...) to avoid
    collisions when the model returns multiple calls in one response.
    """
    calls: list[ToolCall] = []
    # Handle both dict and Pydantic Message objects
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls is None and isinstance(message, dict):
        tool_calls = message.get("tool_calls") or []
    for i, entry in enumerate(tool_calls or []):
        # Handle both dict entries and Pydantic ToolCall objects
        if isinstance(entry, dict):
            fn = entry.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (TypeError, ValueError):
                    args = {}
        else:
            fn = getattr(entry, "function", None)
            name = getattr(fn, "name", "") if fn else ""
            args = getattr(fn, "arguments", {}) if fn else {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (TypeError, ValueError):
                    args = {}
        if name:
            calls.append(ToolCall(name=name, arguments=args or {}, id=f"ollama_{i}"))
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
            "parameters": _gemini_safe_schema(
                fn.get("parameters") or {"type": "object", "properties": {}}
            ),
        })
    return [{"function_declarations": declarations}]


# Keys google-genai's GenerateContentConfig pydantic schema rejects.
_GEMINI_FORBIDDEN_KEYS = frozenset({"oneOf", "anyOf", "allOf", "not", "const"})


def _gemini_safe_schema(node):
    """Recursively strip union/composition keywords Gemini can't validate."""
    if isinstance(node, dict):
        cleaned = {}
        for key, value in node.items():
            if key in _GEMINI_FORBIDDEN_KEYS:
                continue
            cleaned[key] = _gemini_safe_schema(value)
        return cleaned
    if isinstance(node, list):
        return [_gemini_safe_schema(item) for item in node]
    return node


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
