"""Dynamic Precision — Automatically select inference precision.

FP32 → FP16 → INT8 → INT4 based on task requirements and hardware.
"""
import logging
import threading
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("ai_runtime.dynamic_precision")


class PrecisionLevel(Enum):
    FP32 = "fp32"
    FP16 = "fp16"
    INT8 = "int8"
    INT4 = "int4"


@dataclass
class PrecisionConfig:
    """Configuration for a precision level."""
    level: PrecisionLevel
    memory_multiplier: float  # Relative to FP32
    speed_multiplier: float   # Relative to FP32
    quality_loss: float       # 0-1, quality degradation
    min_vram_gb: float


PRECISION_CONFIGS = {
    PrecisionLevel.FP32: PrecisionConfig(PrecisionLevel.FP32, 1.0, 1.0, 0.0, 8.0),
    PrecisionLevel.FP16: PrecisionConfig(PrecisionLevel.FP16, 0.5, 1.5, 0.01, 4.0),
    PrecisionLevel.INT8: PrecisionConfig(PrecisionLevel.INT8, 0.25, 2.0, 0.03, 2.0),
    PrecisionLevel.INT4: PrecisionConfig(PrecisionLevel.INT4, 0.125, 3.0, 0.08, 1.0),
}

TASK_PRECISION_MAP = {
    "math": PrecisionLevel.FP32,
    "coding": PrecisionLevel.FP16,
    "conversation": PrecisionLevel.INT8,
    "classification": PrecisionLevel.INT8,
    "creative": PrecisionLevel.FP16,
    "embedding": PrecisionLevel.INT8,
    "default": PrecisionLevel.FP16,
}


class DynamicPrecisionSelector:
    """Select optimal inference precision based on task and hardware."""

    def __init__(self, available_vram_gb: float = 2.0):
        self._vram_gb = available_vram_gb
        self._current_precision = PrecisionLevel.FP16
        self._lock = threading.Lock()
        self._selections: Dict[str, int] = {}

    def select(self, task_type: str = "default") -> PrecisionLevel:
        """Select the optimal precision for a task type."""
        ideal = TASK_PRECISION_MAP.get(task_type, PrecisionLevel.FP16)

        # Check if hardware supports the ideal precision
        config = PRECISION_CONFIGS[ideal]
        if config.min_vram_gb <= self._vram_gb:
            selected = ideal
        else:
            # Fall back to lower precision (prefer highest quality that fits)
            for level in [PrecisionLevel.FP16, PrecisionLevel.INT8, PrecisionLevel.INT4]:
                if PRECISION_CONFIGS[level].min_vram_gb <= self._vram_gb:
                    selected = level
                    break
            else:
                selected = PrecisionLevel.INT4

        with self._lock:
            self._current_precision = selected
            self._selections[selected.value] = self._selections.get(selected.value, 0) + 1

        return selected

    def get_config(self, level: PrecisionLevel = None) -> PrecisionConfig:
        level = level or self._current_precision
        return PRECISION_CONFIGS[level]

    def get_memory_estimate(self, model_params_b: float, level: PrecisionLevel = None) -> float:
        """Estimate VRAM usage in GB for a model at given precision."""
        level = level or self._current_precision
        config = PRECISION_CONFIGS[level]
        return model_params_b * config.memory_multiplier * 2  # 2 bytes per param baseline

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "current_precision": self._current_precision.value,
                "available_vram_gb": self._vram_gb,
                "selection_distribution": dict(self._selections),
            }


_precision_instance: Optional[DynamicPrecisionSelector] = None


def get_dynamic_precision(vram_gb: float = 2.0) -> DynamicPrecisionSelector:
    global _precision_instance
    if _precision_instance is None:
        _precision_instance = DynamicPrecisionSelector(available_vram_gb=vram_gb)
    return _precision_instance
