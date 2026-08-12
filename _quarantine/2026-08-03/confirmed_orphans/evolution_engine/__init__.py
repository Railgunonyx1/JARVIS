"""Evolution Engine — JARVIS MK-X Part 85.

Performance analysis, automatic optimization, and regression guarding.
"""

from evolution_engine.auto_optimizer import AutoOptimizer, get_auto_optimizer
from evolution_engine.performance_analyzer import PerformanceAnalyzerEngine, get_performance_analyzer_engine
from evolution_engine.regression_guard import RegressionGuard, get_regression_guard

__all__ = [
    "PerformanceAnalyzerEngine", "get_performance_analyzer_engine",
    "AutoOptimizer", "get_auto_optimizer",
    "RegressionGuard", "get_regression_guard",
]
