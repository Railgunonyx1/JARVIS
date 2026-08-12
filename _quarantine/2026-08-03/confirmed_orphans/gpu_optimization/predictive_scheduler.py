"""Predictive GPU Scheduling — Queue next inference before GPU becomes idle.

Keep GPU utilization above 90% by predicting when current job finishes.
"""
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("gpu_optimization.predictive_scheduling")


@dataclass
class GPUJob:
    """A job queued for GPU execution."""
    job_id: str
    name: str
    estimated_ms: float
    priority: int = 5
    queued_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    result: Any = None

    def __post_init__(self):
        if self.queued_at == 0.0:
            self.queued_at = time.time()


class PredictiveGPUScheduler:
    """Schedule GPU jobs to maintain high utilization.

    Predicts when current job finishes and queues next job
    so there's no idle gap between jobs.
    """

    def __init__(self, latency_buffer_ms: float = 5.0):
        self._latency_buffer_ms = latency_buffer_ms
        self._queue: list[GPUJob] = []
        self._completed: deque = deque(maxlen=200)
        self._current_job: GPUJob | None = None
        self._lock = threading.Lock()
        self._job_counter = 0
        self._total_jobs = 0
        self._avg_job_ms = 100.0

    def submit(self, name: str, estimated_ms: float = 100, priority: int = 5) -> str:
        """Submit a GPU job."""
        self._job_counter += 1
        job_id = f"gpu_{self._job_counter}"
        job = GPUJob(
            job_id=job_id, name=name,
            estimated_ms=estimated_ms, priority=priority,
        )
        with self._lock:
            self._queue.append(job)
            self._queue.sort(key=lambda j: (j.priority, j.queued_at))
        return job_id

    def get_next_job(self) -> GPUJob | None:
        """Get the next job to execute, pre-fetched before GPU is idle."""
        with self._lock:
            if self._queue:
                return self._queue[0]
        return None

    def start_job(self, job_id: str) -> GPUJob | None:
        """Mark a job as started."""
        with self._lock:
            for i, job in enumerate(self._queue):
                if job.job_id == job_id:
                    self._queue.pop(i)
                    job.started_at = time.time()
                    self._current_job = job
                    return job
        return None

    def complete_job(self, job_id: str, result: Any = None) -> None:
        """Mark a job as completed."""
        with self._lock:
            if self._current_job and self._current_job.job_id == job_id:
                self._current_job.completed_at = time.time()
                self._current_job.result = result
                self._completed.append(self._current_job)
                elapsed_ms = (self._current_job.completed_at - self._current_job.started_at) * 1000
                n = self._total_jobs
                self._avg_job_ms = (self._avg_job_ms * n + elapsed_ms) / (n + 1)
                self._total_jobs += 1
                self._current_job = None

    def predict_completion_ms(self) -> float:
        """Predict when current job will complete."""
        if self._current_job:
            elapsed = (time.time() - self._current_job.started_at) * 1000
            remaining = max(0, self._current_job.estimated_ms - elapsed)
            return remaining
        return 0.0

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "queue_size": len(self._queue),
                "total_jobs": self._total_jobs,
                "avg_job_ms": round(self._avg_job_ms, 1),
                "current_job": self._current_job.name if self._current_job else None,
                "estimated_completion_ms": round(self.predict_completion_ms(), 1),
            }


_gpu_scheduler_instance: PredictiveGPUScheduler | None = None


def get_predictive_gpu_scheduler() -> PredictiveGPUScheduler:
    global _gpu_scheduler_instance
    if _gpu_scheduler_instance is None:
        _gpu_scheduler_instance = PredictiveGPUScheduler()
    return _gpu_scheduler_instance
