"""Model Residency Scheduler — manages which Ollama models stay loaded in VRAM.

Tiered policy:
  - TIER_1 (always resident): 1.5B — never unloaded
  - TIER_2 (warm):           3B  — kept loaded, evicted under pressure
  - TIER_3 (on-demand):      4B+ — loaded per request, unloaded after
  - TIER_COLD:               7B  — only when explicitly requested

Schedules prewarming and eviction based on usage patterns.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

logger = logging.getLogger("jarvis.model_residency")


class ResidencyTier(IntEnum):
    COLD = 0
    ON_DEMAND = 1
    WARM = 2
    ALWAYS = 3


@dataclass
class ModelProfile:
    model: str
    tier: ResidencyTier
    avg_ttft_ms: float = 0.0
    success_rate: float = 1.0
    total_calls: int = 0
    total_failures: int = 0
    last_used: float = 0.0
    last_prewarmed: float = 0.0

    @property
    def is_healthy(self) -> bool:
        return self.success_rate >= 0.8 or self.total_calls < 5


@dataclass
class ResidencyState:
    loaded_models: dict[str, float] = field(default_factory=dict)
    vram_pressure: float = 0.0


class ModelResidencyScheduler:
    """Decides which models to keep loaded, prewarm, and evict."""

    def __init__(self, ollama_provider=None):
        self._provider = ollama_provider
        self._profiles: dict[str, ModelProfile] = {}
        self._state = ResidencyState()
        self._prewarm_interval = 300.0
        self._last_schedule_time = 0.0
        self._init_default_profiles()

    def _init_default_profiles(self) -> None:
        defaults = [
            ("qwen2.5:1.5b", ResidencyTier.ALWAYS),
            ("qwen2.5:3b", ResidencyTier.WARM),
            ("qwen2.5:4b", ResidencyTier.ON_DEMAND),
            ("qwen2.5:7b", ResidencyTier.COLD),
            ("qwen2.5:14b", ResidencyTier.COLD),
            ("qwen2.5:32b", ResidencyTier.COLD),
            ("qwen2.5:72b", ResidencyTier.COLD),
        ]
        for model, tier in defaults:
            self._profiles[model] = ModelProfile(model=model, tier=tier)

    def record_usage(self, model: str, ttft_ms: float, success: bool) -> None:
        p = self._profiles.get(model)
        if p is None:
            tier = self._classify_unknown(model)
            p = ModelProfile(model=model, tier=tier)
            self._profiles[model] = p
        p.total_calls += 1
        if not success:
            p.total_failures += 1
        p.total_calls = max(p.total_calls, p.total_failures)
        p.success_rate = 1.0 - (p.total_failures / max(p.total_calls, 1))
        n = min(p.total_calls, 20)
        p.avg_ttft_ms = ((n - 1) * p.avg_ttft_ms + ttft_ms) / n
        p.last_used = time.time()

    def _classify_unknown(self, model: str) -> ResidencyTier:
        ml = model.lower()
        if any(s in ml for s in ("1.5b", "1b", "0.5b")):
            return ResidencyTier.ALWAYS
        if any(s in ml for s in ("3b", "4b")):
            return ResidencyTier.WARM
        if any(s in ml for s in ("7b", "8b")):
            return ResidencyTier.ON_DEMAND
        return ResidencyTier.COLD

    def should_prewarm(self, model: str) -> bool:
        p = self._profiles.get(model)
        if p is None:
            return False
        if p.tier >= ResidencyTier.WARM:
            return True
        if p.tier == ResidencyTier.ON_DEMAND and p.total_calls > 3:
            return True
        return False

    def get_prewarm_candidates(self) -> list[str]:
        candidates = []
        now = time.time()
        for model, p in self._profiles.items():
            if self.should_prewarm(model):
                if now - p.last_prewarmed > self._prewarm_interval:
                    candidates.append(model)
        return candidates

    def suggest_eviction(self) -> str | None:
        candidates = []
        for model, p in self._profiles.items():
            if p.tier <= ResidencyTier.ON_DEMAND and p.total_calls > 0:
                idle_time = time.time() - p.last_used if p.last_used > 0 else float("inf")
                candidates.append((idle_time, model))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]

    def schedule(self) -> dict[str, Any]:
        now = time.time()
        if now - self._last_schedule_time < 30.0:
            return {"action": "skip", "reason": "too_soon"}
        self._last_schedule_time = now

        prewarm = self.get_prewarm_candidates()
        eviction = self.suggest_eviction()

        if self._provider is not None:
            for model in prewarm:
                try:
                    self._provider.prewarm(model)
                    p = self._profiles.get(model)
                    if p:
                        p.last_prewarmed = now
                except Exception:
                    pass
            if eviction:
                try:
                    self._provider.unload_model(eviction)
                except Exception:
                    pass

        return {
            "action": "scheduled",
            "prewarm": prewarm,
            "evict": eviction,
            "profiles": {m: {"tier": p.tier.name, "calls": p.total_calls,
                             "ttft": round(p.avg_ttft_ms, 1), "success": round(p.success_rate, 3)}
                         for m, p in self._profiles.items() if p.total_calls > 0},
        }

    def get_model_for_task(self, confidence: float, task_type: str = "") -> str:
        if confidence >= 0.9:
            return "qwen2.5:1.5b"
        if confidence >= 0.7:
            return "qwen2.5:3b"
        if task_type == "coding":
            return "qwen2.5:4b"
        if confidence < 0.4:
            return "qwen2.5:7b"
        return "qwen2.5:3b"
