"""Adaptive Degradation — Gracefully reduce quality under resource pressure.

Instead of slowing everything, selectively degrade non-critical subsystems
to preserve latency for voice and interaction.
"""
import logging
import time
import threading
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum, auto

logger = logging.getLogger("systems.adaptive_degradation")


class DegradationLevel(Enum):
    FULL = 0        # Everything running at full quality
    LIGHT = 1       # Minor reductions (lower polling rates)
    MODERATE = 2    # Disable background tasks
    HEAVY = 3       # Core-only mode
    EMERGENCY = 4   # Minimal functionality


class Subsystem(Enum):
    VOICE = "voice"
    LLM = "llm"
    VISION = "vision"
    INDEXING = "indexing"
    TELEMETRY = "telemetry"
    PREFETCH = "prefetch"
    CONTEXT_ENRICHMENT = "context_enrichment"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    GPU = "gpu"


@dataclass
class SubsystemConfig:
    """Configuration for a subsystem at a given degradation level."""
    name: str
    enabled: bool = True
    quality: float = 1.0     # 0.0 to 1.0
    rate_limit: float = 0.0  # 0 = no limit
    timeout_ms: float = 0.0  # 0 = default


class AdaptiveDegradation:
    """Monitors system resources and degrades subsystems to preserve core latency.

    Priority order (never degrade below these):
    1. Voice input/output — ALWAYS preserved
    2. LLM inference — preserve unless emergency
    3. Tool execution — preserve unless heavy
    4. Everything else — degradable
    """

    DEGRADATION_PROFILES = {
        DegradationLevel.FULL: {
            Subsystem.VISION: SubsystemConfig("vision", quality=1.0, rate_limit=0),
            Subsystem.INDEXING: SubsystemConfig("indexing", quality=1.0),
            Subsystem.TELEMETRY: SubsystemConfig("telemetry", quality=1.0),
            Subsystem.PREFETCH: SubsystemConfig("prefetch", enabled=True),
            Subsystem.CONTEXT_ENRICHMENT: SubsystemConfig("context", quality=1.0),
            Subsystem.KNOWLEDGE_GRAPH: SubsystemConfig("kg", quality=1.0),
            Subsystem.GPU: SubsystemConfig("gpu", quality=1.0),
        },
        DegradationLevel.LIGHT: {
            Subsystem.VISION: SubsystemConfig("vision", quality=0.8, rate_limit=2.0),
            Subsystem.INDEXING: SubsystemConfig("indexing", quality=0.8),
            Subsystem.TELEMETRY: SubsystemConfig("telemetry", quality=0.5),
            Subsystem.PREFETCH: SubsystemConfig("prefetch", enabled=True),
            Subsystem.CONTEXT_ENRICHMENT: SubsystemConfig("context", quality=0.7),
            Subsystem.KNOWLEDGE_GRAPH: SubsystemConfig("kg", quality=0.8),
            Subsystem.GPU: SubsystemConfig("gpu", quality=0.9),
        },
        DegradationLevel.MODERATE: {
            Subsystem.VISION: SubsystemConfig("vision", quality=0.5, rate_limit=1.0),
            Subsystem.INDEXING: SubsystemConfig("indexing", enabled=False),
            Subsystem.TELEMETRY: SubsystemConfig("telemetry", enabled=False),
            Subsystem.PREFETCH: SubsystemConfig("prefetch", enabled=False),
            Subsystem.CONTEXT_ENRICHMENT: SubsystemConfig("context", quality=0.4),
            Subsystem.KNOWLEDGE_GRAPH: SubsystemConfig("kg", quality=0.5),
            Subsystem.GPU: SubsystemConfig("gpu", quality=0.7),
        },
        DegradationLevel.HEAVY: {
            Subsystem.VISION: SubsystemConfig("vision", enabled=False),
            Subsystem.INDEXING: SubsystemConfig("indexing", enabled=False),
            Subsystem.TELEMETRY: SubsystemConfig("telemetry", enabled=False),
            Subsystem.PREFETCH: SubsystemConfig("prefetch", enabled=False),
            Subsystem.CONTEXT_ENRICHMENT: SubsystemConfig("context", enabled=False),
            Subsystem.KNOWLEDGE_GRAPH: SubsystemConfig("kg", enabled=False),
            Subsystem.GPU: SubsystemConfig("gpu", quality=0.5),
        },
        DegradationLevel.EMERGENCY: {
            Subsystem.VISION: SubsystemConfig("vision", enabled=False),
            Subsystem.INDEXING: SubsystemConfig("indexing", enabled=False),
            Subsystem.TELEMETRY: SubsystemConfig("telemetry", enabled=False),
            Subsystem.PREFETCH: SubsystemConfig("prefetch", enabled=False),
            Subsystem.CONTEXT_ENRICHMENT: SubsystemConfig("context", enabled=False),
            Subsystem.KNOWLEDGE_GRAPH: SubsystemConfig("kg", enabled=False),
            Subsystem.GPU: SubsystemConfig("gpu", enabled=False),
        },
    }

    def __init__(self):
        self._level = DegradationLevel.FULL
        self._configs: Dict[Subsystem, SubsystemConfig] = {}
        self._callbacks: List[Callable] = []
        self._lock = threading.Lock()
        self._level_history: List[Dict[str, Any]] = []
        self._apply_profile(DegradationLevel.FULL)

    def _apply_profile(self, level: DegradationLevel) -> None:
        profile = self.DEGRADATION_PROFILES.get(level, {})
        for subsystem, config in profile.items():
            self._configs[subsystem] = SubsystemConfig(
                name=config.name,
                enabled=config.enabled,
                quality=config.quality,
                rate_limit=config.rate_limit,
                timeout_ms=config.timeout_ms,
            )

    def evaluate_and_adapt(self, cpu_percent: float = 0, ram_percent: float = 0,
                           gpu_percent: float = 0) -> DegradationLevel:
        """Evaluate current resources and adjust degradation level."""
        new_level = DegradationLevel.FULL

        if cpu_percent > 95 or ram_percent > 90:
            new_level = DegradationLevel.EMERGENCY
        elif cpu_percent > 85 or ram_percent > 80:
            new_level = DegradationLevel.HEAVY
        elif cpu_percent > 70 or ram_percent > 70:
            new_level = DegradationLevel.MODERATE
        elif cpu_percent > 55 or ram_percent > 60:
            new_level = DegradationLevel.LIGHT

        if new_level != self._level:
            self.set_level(new_level)

        return self._level

    def set_level(self, level: DegradationLevel) -> None:
        with self._lock:
            old_level = self._level
            self._level = level
            self._apply_profile(level)

        self._level_history.append({
            "from": old_level.name,
            "to": level.name,
            "ts": time.time(),
        })
        if len(self._level_history) > 100:
            self._level_history = self._level_history[-100:]

        if old_level != level:
            logger.info("Degradation level: %s -> %s", old_level.name, level.name)
            for cb in self._callbacks:
                try:
                    cb(old_level, level)
                except Exception:
                    pass

    def is_enabled(self, subsystem: Subsystem) -> bool:
        config = self._configs.get(subsystem)
        return config.enabled if config else True

    def get_quality(self, subsystem: Subsystem) -> float:
        config = self._configs.get(subsystem)
        return config.quality if config else 1.0

    def get_config(self, subsystem: Subsystem) -> SubsystemConfig:
        return self._configs.get(subsystem, SubsystemConfig(name=subsystem.value))

    def on_level_change(self, callback: Callable) -> None:
        self._callbacks.append(callback)

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "level": self._level.name,
                "level_value": self._level.value,
                "subsystems": {
                    sub.value: {
                        "enabled": cfg.enabled,
                        "quality": cfg.quality,
                    }
                    for sub, cfg in self._configs.items()
                },
                "recent_changes": self._level_history[-10:],
            }


_degradation_instance: Optional[AdaptiveDegradation] = None


def get_adaptive_degradation() -> AdaptiveDegradation:
    global _degradation_instance
    if _degradation_instance is None:
        _degradation_instance = AdaptiveDegradation()
    return _degradation_instance
