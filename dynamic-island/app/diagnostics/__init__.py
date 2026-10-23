"""Performance diagnostics package.

Measure CPU/RAM usage, voice latency, gesture FPS, and 3D workspace FPS
against the master plan §10 performance budget.
"""

from app.diagnostics.monitor import BenchmarkResult, PerformanceBenchmarker, PerformanceMonitor, PerformanceSnapshot

__all__ = [
    "PerformanceMonitor",
    "PerformanceBenchmarker",
    "BenchmarkResult",
    "PerformanceSnapshot",
]
