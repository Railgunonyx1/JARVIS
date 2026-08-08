"""AI Runtime Dashboard — Real-time performance overview.

Shows: First Token, Token Rate, GPU Util, CPU Util, KV Cache Hit,
Prompt Compression, Pipeline Overlap, Average Response, Status.
"""
import logging
import time
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger("inference_optimization.runtime_dashboard")


class AIRuntimeDashboard:
    """Real-time AI runtime performance dashboard.

    Aggregates metrics from all subsystems into a single view.
    """

    def __init__(self):
        self._metrics: Dict[str, Any] = {}
        self._history: list = []
        self._lock = threading.lock() if hasattr(threading, 'lock') else threading.Lock()
        self._last_update = 0.0

    def update_metric(self, key: str, value: Any) -> None:
        with self._lock:
            self._metrics[key] = value
            self._last_update = time.time()

    def update_metrics(self, metrics: Dict[str, Any]) -> None:
        with self._lock:
            self._metrics.update(metrics)
            self._last_update = time.time()

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._metrics)

    def get_text_dashboard(self) -> str:
        """Generate a text-based dashboard display."""
        m = self._metrics
        lines = [
            "=" * 40,
            "  AI RUNTIME DASHBOARD",
            "=" * 40,
            f"  First Token:        {m.get('first_token_ms', 'N/A')} ms",
            f"  Average Token:      {m.get('avg_token_ms', 'N/A')} ms",
            f"  GPU Utilisation:    {m.get('gpu_util_pct', 'N/A')}%",
            f"  CPU Utilisation:    {m.get('cpu_util_pct', 'N/A')}%",
            f"  KV Cache Hit:       {m.get('kv_cache_hit_pct', 'N/A')}%",
            f"  Prompt Compression: {m.get('prompt_compression_pct', 'N/A')}%",
            f"  Pipeline Overlap:   {m.get('pipeline_overlap_pct', 'N/A')}%",
            f"  Average Response:   {m.get('avg_response_ms', 'N/A')} ms",
            f"  Status:             {m.get('status', 'UNKNOWN')}",
            "=" * 40,
        ]
        return "\n".join(lines)

    def get_status_summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "metrics_count": len(self._metrics),
                "last_update": self._last_update,
                "metrics": dict(self._metrics),
            }


_dashboard_instance: Optional[AIRuntimeDashboard] = None


def get_runtime_dashboard() -> AIRuntimeDashboard:
    global _dashboard_instance
    if _dashboard_instance is None:
        _dashboard_instance = AIRuntimeDashboard()
    return _dashboard_instance
