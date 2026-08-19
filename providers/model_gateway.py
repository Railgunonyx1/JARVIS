"""Sprint 16 -- Model Gateway: capability-aware routing, health/failover, session affinity, combos.

The gateway sits above ProviderRouter and decides WHICH provider/model combo
to use based on task requirements, provider health, session affinity, and
user-defined combos.

Architecture:
    AgentLoop -> ModelGateway -> ProviderRouter -> Provider
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("jarvis.model_gateway")


class Capability(Enum):
    REASONING = "reasoning"
    CODING = "coding"
    VISION = "vision"
    TOOL_USE = "tool_use"
    FAST = "fast"
    CHEAP = "cheap"
    PRIVACY = "privacy"  # runs locally


@dataclass(frozen=True)
class ModelProfile:
    """Capability and cost profile for a model."""
    name: str
    provider: str
    capabilities: tuple[Capability, ...] = ()
    context_window: int = 128000
    cost_per_1k_tokens: float = 0.0
    avg_latency_ms: float = 500.0
    reliability: float = 1.0  # 0.0–1.0, updated by health tracking


@dataclass
class ProviderHealth:
    """Mutable health tracking for a provider."""
    healthy: bool = True
    consecutive_failures: int = 0
    last_failure_at: float = 0.0
    cooldown_until: float = 0.0
    total_requests: int = 0
    total_failures: int = 0
    avg_latency_ms: float = 0.0

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_failures / self.total_requests

    @property
    def is_in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until


@dataclass
class Combo:
    """A named fallback chain for a specific use-case."""
    name: str
    models: tuple[ModelProfile, ...]
    description: str = ""


class ModelGateway:
    """Capability-aware model router with health tracking and session affinity.

    The gateway decides which model to use based on:
    1. Task capabilities (coding, reasoning, vision, etc.)
    2. Provider health (consecutive failures, cooldown, error rate)
    3. Session affinity (stick with same model unless failure)
    4. Cost/latency optimization
    5. Named combos (coding-fast, reasoning-premium, etc.)

    Usage::

        gateway = ModelGateway()
        gateway.register_model(ModelProfile(
            name="gemini-2.5-pro", provider="gemini",
            capabilities=(Capability.CODING, Capability.REASONING),
        ))
        gateway.register_combo(Combo(
            name="coding-fast",
            models=(
                ModelProfile(name="groq/llama-3", provider="groq", capabilities=(Capability.FAST,)),
                ModelProfile(name="gemini-2.5-pro", provider="gemini", capabilities=(Capability.CODING,)),
            ),
        ))
        best = gateway.select(requirements={Capability.CODING, Capability.REASONING})
    """

    COOLDOWN_BASE_SECONDS = 60.0
    COOLDOWN_MAX_SECONDS = 600.0
    FAILURE_THRESHOLD_FOR_COOLDOWN = 3

    def __init__(self) -> None:
        self._models: dict[str, ModelProfile] = {}
        self._combos: dict[str, Combo] = {}
        self._health: dict[str, ProviderHealth] = {}
        self._session_affinity: dict[str, str] = {}  # session_id -> model_name

    def register_model(self, profile: ModelProfile) -> None:
        key = f"{profile.provider}/{profile.name}"
        self._models[key] = profile
        if profile.provider not in self._health:
            self._health[profile.provider] = ProviderHealth()

    def register_combo(self, combo: Combo) -> None:
        self._combos[combo.name] = combo

    def get_health(self, provider: str) -> ProviderHealth:
        if provider not in self._health:
            self._health[provider] = ProviderHealth()
        return self._health[provider]

    def record_success(self, provider: str, latency_ms: float) -> None:
        h = self.get_health(provider)
        h.total_requests += 1
        h.consecutive_failures = 0
        h.healthy = True
        n = h.total_requests
        h.avg_latency_ms = h.avg_latency_ms * ((n - 1) / n) + latency_ms / n

    def record_failure(self, provider: str) -> None:
        h = self.get_health(provider)
        h.total_requests += 1
        h.total_failures += 1
        h.consecutive_failures += 1
        h.last_failure_at = time.time()
        if h.consecutive_failures >= self.FAILURE_THRESHOLD_FOR_COOLDOWN:
            backoff = min(
                self.COOLDOWN_BASE_SECONDS * (2 ** (h.consecutive_failures - self.FAILURE_THRESHOLD_FOR_COOLDOWN)),
                self.COOLDOWN_MAX_SECONDS,
            )
            h.cooldown_until = time.time() + backoff
            h.healthy = False
            logger.warning(
                "Provider %s cooldown for %.0fs after %d failures",
                provider, backoff, h.consecutive_failures,
            )

    def select(
        self,
        requirements: set[Capability] | None = None,
        session_id: str | None = None,
        combo_name: str | None = None,
        exclude_providers: set[str] | None = None,
    ) -> ModelProfile | None:
        """Select the best model given requirements and current health.

        Priority:
        1. Session affinity (if model is still healthy)
        2. Combo (if specified)
        3. Capability matching + health scoring
        """
        exclude = exclude_providers or set()

        # 1. Session affinity
        if session_id and session_id in self._session_affinity:
            preferred = self._session_affinity[session_id]
            if preferred in self._models:
                prof = self._models[preferred]
                h = self.get_health(prof.provider)
                if h.healthy and not h.is_in_cooldown and prof.provider not in exclude:
                    return prof

        # 2. Named combo
        if combo_name and combo_name in self._combos:
            combo = self._combos[combo_name]
            for prof in combo.models:
                h = self.get_health(prof.provider)
                if h.healthy and not h.is_in_cooldown and prof.provider not in exclude:
                    if self._matches(prof, requirements):
                        if session_id:
                            self._session_affinity[session_id] = f"{prof.provider}/{prof.name}"
                        return prof
            # Fallback: any healthy model in the combo
            for prof in combo.models:
                h = self.get_health(prof.provider)
                if h.healthy and not h.is_in_cooldown and prof.provider not in exclude:
                    if session_id:
                        self._session_affinity[session_id] = f"{prof.provider}/{prof.name}"
                    return prof

        # 3. Score all models
        candidates = []
        for key, prof in self._models.items():
            h = self.get_health(prof.provider)
            if not h.healthy or h.is_in_cooldown or prof.provider in exclude:
                continue
            if requirements and not self._matches(prof, requirements):
                continue
            score = self._score(prof, h, requirements)
            candidates.append((score, prof))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        best = candidates[0][1]
        if session_id:
            self._session_affinity[session_id] = f"{best.provider}/{best.name}"
        return best

    def _matches(self, prof: ModelProfile, requirements: set[Capability] | None) -> bool:
        if not requirements:
            return True
        return requirements.issubset(set(prof.capabilities))

    def _score(self, prof: ModelProfile, health: ProviderHealth,
               requirements: set[Capability] | None) -> float:
        score = 100.0
        # Capability overlap bonus
        if requirements:
            overlap = len(requirements & set(prof.capabilities))
            score += overlap * 20
        # Reliability
        score *= prof.reliability
        score *= (1.0 - health.error_rate)
        # Latency penalty (prefer fast)
        if prof.avg_latency_ms > 0:
            score -= prof.avg_latency_ms / 100.0
        # Cost penalty
        score -= prof.cost_per_1k_tokens * 10
        return score

    def clear_affinity(self, session_id: str) -> None:
        self._session_affinity.pop(session_id, None)

    def status(self) -> dict[str, Any]:
        return {
            "models": {
                k: {
                    "provider": p.provider,
                    "capabilities": [c.value for c in p.capabilities],
                    "reliability": p.reliability,
                }
                for k, p in self._models.items()
            },
            "health": {
                name: {
                    "healthy": h.healthy,
                    "error_rate": round(h.error_rate, 3),
                    "consecutive_failures": h.consecutive_failures,
                    "is_in_cooldown": h.is_in_cooldown,
                    "avg_latency_ms": round(h.avg_latency_ms, 1),
                }
                for name, h in self._health.items()
            },
            "combos": {
                name: [f"{m.provider}/{m.name}" for m in c.models]
                for name, c in self._combos.items()
            },
            "sessions": len(self._session_affinity),
        }
