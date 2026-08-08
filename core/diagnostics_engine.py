"""Self-diagnostics — provider health, model metrics, system resources."""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelMetrics:
    provider: str
    model: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    avg_latency_ms: float = 0.0
    last_error: Optional[str] = None
    last_used: float = 0.0

    @property
    def error_rate(self) -> float:
        return self.failed_requests / self.total_requests if self.total_requests else 0.0

    @property
    def success_rate(self) -> float:
        return 1.0 - self.error_rate


class DiagnosticsEngine:
    def __init__(self):
        self._metrics: dict[str, ModelMetrics] = {}
        self._start_time = time.time()

    def record_request(self, provider: str, model: str, success: bool, latency_ms: float,
                       tokens_in: int = 0, tokens_out: int = 0, error: Optional[str] = None):
        key = f"{provider}/{model}"
        if key not in self._metrics:
            self._metrics[key] = ModelMetrics(provider=provider, model=model)
        m = self._metrics[key]
        m.total_requests += 1
        m.last_used = time.time()
        if success:
            m.successful_requests += 1
            m.total_tokens_in += tokens_in
            m.total_tokens_out += tokens_out
            n = m.successful_requests
            m.avg_latency_ms = ((m.avg_latency_ms * (n - 1)) + latency_ms) / n
        else:
            m.failed_requests += 1
            m.last_error = error

    def get_provider_summary(self) -> dict:
        return {
            key: {
                "provider": m.provider, "model": m.model, "requests": m.total_requests,
                "success_rate": f"{m.success_rate * 100:.1f}%",
                "avg_latency": f"{m.avg_latency_ms:.0f}ms",
                "tokens_in": m.total_tokens_in, "tokens_out": m.total_tokens_out,
                "last_error": m.last_error,
            }
            for key, m in self._metrics.items()
        }

    def get_uptime(self) -> float:
        return time.time() - self._start_time

    def format_status(self) -> str:
        import psutil
        mem = psutil.virtual_memory()
        lines = [
            f"Uptime: {int(self.get_uptime() / 60)}m",
            f"CPU: {psutil.cpu_percent(interval=None):.1f}%  RAM: {mem.percent:.1f}% "
            f"({mem.used / 1048576:.0f}/{mem.total / 1048576:.0f} MB)",
        ]
        for key, m in self._metrics.items():
            lines.append(f"  {key}: {m.total_requests} reqs, {m.success_rate * 100:.0f}% OK, avg {m.avg_latency_ms:.0f}ms")
        return "\n".join(lines)

    def reset_metrics(self):
        self._metrics.clear()
        self._start_time = time.time()
