"""Orchestration Engine — JARVIS MK-X Part 84.

Pipeline optimization, dependency resolution, and prefetch management.
"""

from orchestration_engine.pipeline_optimizer import PipelineOptimizer, get_pipeline_optimizer
from orchestration_engine.prefetch_engine import PrefetchEngine, get_prefetch_engine

__all__ = [
    "PipelineOptimizer", "get_pipeline_optimizer",
    "PrefetchEngine", "get_prefetch_engine",
]
