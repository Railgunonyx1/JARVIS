"""Performance diagnostics package.

Measure CPU/RAM usage, voice latency, gesture FPS, and 3D workspace FPS
against the master plan §10 performance budget.
"""

from app.diagnostics.monitor import PerformanceMonitor, PerformanceBenchmarker, BenchmarkResult, PerformanceSnapshot

__all__ = [
    "PerformanceMonitor",
    "PerformanceBenchmarker",
    "BenchmarkResult",
    "PerformanceSnapshot",
]
