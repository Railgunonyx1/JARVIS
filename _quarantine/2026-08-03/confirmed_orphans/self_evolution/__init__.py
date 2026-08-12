"""Self-Evolution — JARVIS MK-X Part 51.

Performance monitoring, bottleneck detection, and safe self-optimization.
"""

from self_evolution.optimizer import OptimizationSuggestion, SelfOptimizer
from self_evolution.performance_monitor import MetricPoint, PerformanceMonitor

__all__ = [
    "PerformanceMonitor", "MetricPoint",
    "SelfOptimizer", "OptimizationSuggestion",
]
