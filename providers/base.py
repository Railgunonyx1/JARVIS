"""Abstract base class for LLM providers in JARVIS MK-X."""

import importlib
import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from providers.types import LLMResponse

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

    def record_rate_limit(self):
        """Record a rate limit/quota hit WITHOUT penalizing provider health.

        Rate limits are transient and handled by key rotation / backoff, so
        they must not feed the consecutive-failure counter that disables a
        provider (is_available=False) after 5 failures.
        """
        self._requests_today += 1
        self._requests_this_minute += 1
        # Full jitter cooldown to prevent synchronized retry bursts across
        # multiple instances requesting the same provider.
        cooldown = random.uniform(0, min(120, 10 * (2 ** self.health.consecutive_failures)))
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
