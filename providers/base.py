"""Abstract base class for LLM providers in JARVIS MK-X."""

import importlib
import json
import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from providers.types import LLMResponse, ToolCall

logger = logging.getLogger("jarvis.providers")

# Backwards-compatible re-export: LLMResponse now lives in providers.types.
__all__ = ["LLMProvider", "LLMResponse", "ProviderHealth"]


@dataclass
class ProviderHealth:
    """Health status of a provider."""
    available: bool = True
    latency_ms: float = 0.0
    error_rate: float = 0.0
    last_error: str | None = None
    last_check: float = 0.0
    consecutive_failures: int = 0
    cooldown_until: float = 0.0


class LLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.health = ProviderHealth()
        self._requests_today = 0
        self._requests_this_minute = 0
        self._minute_window_start = time.time()
        self._package_ok = True
        self._package_error = ""
        self._sdk_package: str | None = None
        # Set True by OpenAI-compatible providers whose complete_stream can
        # capture tool calls from streamed deltas (enables answer streaming
        # without breaking multi-step tool loops). Only assigned when the
        # subclass doesn't declare it, so the class attribute wins.
        if not getattr(self.__class__, "captures_stream_tool_calls", False):
            self.captures_stream_tool_calls = False
        self._stream_tool_calls: dict[int, dict] = {}
        self._rate_limit_count = 0

    def _check_package(self) -> bool:
        """Override in subclasses to verify the backend package is importable."""
        return True

    def _warm(self) -> None:
        """Pre-import the SDK package (background) so the first request is fast.

        Must not create clients or touch async state — only the import.
        """
        if self._sdk_package:
            try:
                importlib.import_module(self._sdk_package)
            except Exception:
                pass

    # ── streamed tool-call capture (OpenAI-compatible deltas) ─────────────

    def _init_stream_tool_calls(self) -> None:
        self._stream_tool_calls = {}

    def _merge_tool_call_delta(self, deltas) -> None:
        """Merge a streamed ``delta.tool_calls`` list into the accumulator."""
        for tc in deltas or []:
            try:
                idx = int(getattr(tc, "index", 0))
            except (TypeError, ValueError):
                idx = 0
            slot = self._stream_tool_calls.setdefault(idx, {"id": "", "name": "", "args": []})
            tc_id = getattr(tc, "id", "") or ""
            if tc_id:
                slot["id"] = tc_id
            fn = getattr(tc, "function", None)
            if fn is not None:
                name = getattr(fn, "name", "") or ""
                args = getattr(fn, "arguments", "") or ""
                if name:
                    slot["name"] = name
                if args:
                    slot["args"].append(args)

    def _stream_tool_call_results(self) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for idx in sorted(self._stream_tool_calls):
            slot = self._stream_tool_calls[idx]
            raw = "".join(slot.get("args", []))
            try:
                arguments = json.loads(raw) if raw.strip() else {}
                if not isinstance(arguments, dict):
                    arguments = {"value": arguments}
            except (TypeError, ValueError):
                arguments = {}
            calls.append(ToolCall(name=slot.get("name", ""), arguments=arguments, id=slot.get("id", "")))
        return calls

    @property
    def model(self) -> str:
        return self.config.get("model", "unknown")

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
    ) -> LLMResponse:
        """Send a chat completion request.

        ``tools`` is an OpenAI-style tools list (JSON schema function
        definitions). Providers convert it to their native schema and parse
        any function calls into ``LLMResponse.tool_calls``.
        """
        ...

    @abstractmethod
    async def complete_stream(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
    ) -> AsyncIterator[str]:
        """Stream a chat completion response."""
        ...

    def check_quota(self) -> bool:
        """Check if this provider has remaining quota."""
        now = time.time()

        # Reset minute window
        if now - self._minute_window_start > 60:
            self._requests_this_minute = 0
            self._minute_window_start = now

        rpm = self.config.get("requests_per_minute", 999)
        rpd = self.config.get("requests_per_day", 999999)

        if self._requests_this_minute >= rpm:
            logger.warning("%s: Rate limit (RPM) reached", self.name)
            return False
        if self._requests_today >= rpd:
            logger.warning("%s: Daily quota reached", self.name)
            return False
        if now < self.health.cooldown_until:
            logger.info("%s: In cooldown until %.0f", self.name, self.health.cooldown_until)
            return False
        return True

    def record_success(self, latency_ms: float):
        """Record a successful request."""
        self._requests_today += 1
        self._requests_this_minute += 1
        self.health.available = True
        self.health.latency_ms = latency_ms
        self.health.consecutive_failures = 0
        self.health.last_error = None
        self._rate_limit_count = 0

    def record_rate_limit(self):
        """Record a rate limit/quota hit WITHOUT penalizing provider health.

        Rate limits are transient and handled by key rotation / backoff, so
        they must not feed the consecutive-failure counter that disables a
        provider (is_available=False) after 5 failures.

        Rejected requests do NOT increment request counters — a 429 means
        the request was not processed, so it shouldn't count against
        JARVIS's own RPM/RPD tracking.

        Cooldown uses a fixed base (not consecutive_failures) so that a
        provider with prior health failures doesn't get an excessively long
        cooldown just because it hit a rate limit.
        """
        self._rate_limit_count += 1
        base = min(60, 5 * (2 ** min(self._rate_limit_count - 1, 4)))
        cooldown = random.uniform(base * 0.5, base)
        self.health.cooldown_until = time.time() + cooldown
        self.health.last_error = "rate_limited"

    def record_failure(self, error: str):
        """Record a failed request."""
        self.health.consecutive_failures += 1
        self.health.last_error = error
        self.health.error_rate = min(1.0, self.health.error_rate * 0.9 + 0.1)

        # Full jitter cooldown to prevent synchronized retry bursts.
        # Exponential base: 0s < 60s < 300s across 3+ failures.
        if self.health.consecutive_failures >= 3:
            cooldown = random.uniform(0, min(300, 30 * (2 ** (self.health.consecutive_failures - 3))))
            self.health.cooldown_until = time.time() + cooldown
            logger.warning(
                "%s: %d consecutive failures, cooling down for %ds",
                self.name, self.health.consecutive_failures, int(cooldown)
            )
        if self.health.consecutive_failures >= 5:
            self.health.available = False
            logger.error("%s: Marked unavailable after %d failures", self.name, self.health.consecutive_failures)

    @property
    def is_available(self) -> bool:
        if not self._package_ok:
            return False
        return self.health.available and self.check_quota()

    def reset(self):
        """Reset provider health and quotas."""
        self.health = ProviderHealth()
        self._requests_today = 0
        self._requests_this_minute = 0
