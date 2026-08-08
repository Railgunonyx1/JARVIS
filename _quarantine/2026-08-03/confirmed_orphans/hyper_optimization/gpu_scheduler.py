"""JARVIS MK-X Hyper-Optimization Engine — GPU workload scheduler."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.hyper_opt.gpu_scheduler")


class GPUScheduler:
    """Manages GPU workload scheduling across multiple priority-based streams."""

    def __init__(self) -> None:
        self._streams: Dict[str, Dict[str, Any]] = {}
        self._gpu_available: bool = False
        self._gpu_name: str = "none"
        self._gpu_memory_mb: float = 0.0
        self._cuda_device_count: int = 0
        self._lock = threading.RLock()
        self._stats: Dict[str, Any] = {
            "tasks_scheduled": 0,
            "tasks_completed": 0,
            "total_gpu_ms": 0.0,
            "streams_used": 0,
        }
        self._check_gpu()

    def _check_gpu(self) -> None:
        """Check if GPU is available via torch or pynvml."""
        try:
            import torch

            if torch.cuda.is_available():
                self._gpu_available = True
                self._cuda_device_count = torch.cuda.device_count()
                if self._cuda_device_count > 0:
                    self._gpu_name = torch.cuda.get_device_name(0)
                    props = torch.cuda.get_device_properties(0)
                    self._gpu_memory_mb = props.total_mem / (1024 * 1024)
                logger.info(
                    "CUDA GPU detected: %s (%d device(s), %.0f MB)",
                    self._gpu_name,
                    self._cuda_device_count,
                    self._gpu_memory_mb,
                )
                return
        except ImportError:
            pass
        except Exception:
            logger.debug("torch CUDA check failed", exc_info=True)

        try:
            import pynvml

            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            if count > 0:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                name_bytes = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name_bytes, bytes):
                    name_bytes = name_bytes.decode("utf-8", errors="replace")
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                self._gpu_available = True
                self._gpu_name = name_bytes
                self._cuda_device_count = count
                self._gpu_memory_mb = mem_info.total / (1024 * 1024)
                logger.info(
                    "NVIDIA GPU detected: %s (%d device(s), %.0f MB)",
                    self._gpu_name,
                    count,
                    self._gpu_memory_mb,
                )
                return
        except ImportError:
            pass
        except Exception:
            logger.debug("pynvml check failed", exc_info=True)

        logger.info("No GPU detected — scheduler running in CPU-fallback mode")

    def create_stream(self, stream_id: str, name: str, priority: int = 5) -> None:
        """Create a GPU compute stream with a given priority (1=highest, 10=lowest)."""
        priority = max(1, min(10, priority))
        with self._lock:
            if stream_id in self._streams:
                logger.warning("Stream '%s' already exists — updating priority", stream_id)
                self._streams[stream_id]["priority"] = priority
                self._streams[stream_id]["name"] = name
                return
            self._streams[stream_id] = {
                "name": name,
                "priority": priority,
                "queue": deque(),
                "active": False,
                "tasks_dispatched": 0,
                "tasks_completed": 0,
                "created_at": time.perf_counter(),
            }
            self._stats["streams_used"] = len(self._streams)
            logger.info(
                "Created stream '%s' (id=%s, priority=%d)", name, stream_id, priority
            )

    def submit(
        self,
        stream_id: str,
        task_fn: Callable[..., Any],
        task_args: Optional[tuple] = None,
        task_kwargs: Optional[dict] = None,
        priority: int = 5,
    ) -> None:
        """Submit a task to a GPU stream."""
        if task_args is None:
            task_args = ()
        if task_kwargs is None:
            task_kwargs = {}
        with self._lock:
            if stream_id not in self._streams:
                logger.warning(
                    "Stream '%s' not found — creating default stream", stream_id
                )
                self.create_stream(stream_id, stream_id, priority=5)
            task_priority = max(1, min(10, priority))
            task_entry = {
                "fn": task_fn,
                "args": task_args,
                "kwargs": task_kwargs,
                "priority": task_priority,
                "submitted_at": time.perf_counter(),
            }
            self._streams[stream_id]["queue"].append(task_entry)
            self._stats["tasks_scheduled"] += 1
            logger.debug(
                "Task submitted to stream '%s' (queue_depth=%d)",
                stream_id,
                len(self._streams[stream_id]["queue"]),
            )

    def get_queue_status(self) -> Dict[str, Dict[str, Any]]:
        """Returns per-stream queue depths and active status."""
        with self._lock:
            status: Dict[str, Dict[str, Any]] = {}
            for sid, stream in self._streams.items():
                status[sid] = {
                    "name": stream["name"],
                    "queue_depth": len(stream["queue"]),
                    "active": stream["active"],
                    "priority": stream["priority"],
                    "tasks_dispatched": stream["tasks_dispatched"],
                    "tasks_completed": stream["tasks_completed"],
                }
            return status

    def get_next_task(self) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Get the highest-priority task across all streams. Returns (stream_id, task) or None."""
        with self._lock:
            best_task: Optional[Tuple[str, Dict[str, Any]]] = None
            best_priority = 11
            for sid, stream in self._streams.items():
                if not stream["queue"]:
                    continue
                task = stream["queue"][0]
                effective_priority = stream["priority"] + task["priority"]
                if effective_priority < best_priority:
                    best_priority = effective_priority
                    best_task = (sid, task)
            return best_task

    def pop_next_task(self) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Pop the highest-priority task from its stream queue."""
        with self._lock:
            result = self.get_next_task()
            if result is None:
                return None
            sid, task = result
            self._streams[sid]["queue"].popleft()
            self._streams[sid]["active"] = True
            self._streams[sid]["tasks_dispatched"] += 1
            logger.debug(
                "Popped task from stream '%s' (remaining=%d)",
                sid,
                len(self._streams[sid]["queue"]),
            )
            return sid, task

    def record_completion(self, stream_id: str, gpu_ms: float) -> None:
        """Record that a task completed on a stream."""
        with self._lock:
            if stream_id in self._streams:
                self._streams[stream_id]["tasks_completed"] += 1
                if not self._streams[stream_id]["queue"]:
                    self._streams[stream_id]["active"] = False
            self._stats["tasks_completed"] += 1
            self._stats["total_gpu_ms"] += gpu_ms
            logger.debug(
                "Task completed on stream '%s' (%.2f ms GPU time)", stream_id, gpu_ms
            )

    def get_stats(self) -> Dict[str, Any]:
        """Returns aggregate scheduler statistics."""
        with self._lock:
            completed = self._stats["tasks_completed"]
            total_ms = self._stats["total_gpu_ms"]
            avg_ms = total_ms / completed if completed > 0 else 0.0
            active_streams = sum(
                1 for s in self._streams.values() if s["active"]
            )
            total_streams = len(self._streams)
            utilization = (
                active_streams / total_streams if total_streams > 0 else 0.0
            )
            return {
                "tasks_scheduled": self._stats["tasks_scheduled"],
                "tasks_completed": completed,
                "avg_gpu_ms": round(avg_ms, 3),
                "total_gpu_ms": round(total_ms, 3),
                "gpu_available": self._gpu_available,
                "gpu_name": self._gpu_name,
                "gpu_memory_mb": round(self._gpu_memory_mb, 1),
                "stream_utilization": round(utilization, 4),
                "active_streams": active_streams,
                "total_streams": total_streams,
            }

    def suggest_parallelism(self) -> Dict[str, Any]:
        """Suggest optimal concurrency based on GPU capability."""
        with self._lock:
            if not self._gpu_available:
                return {
                    "recommended_streams": 1,
                    "reason": "No GPU detected — CPU fallback",
                    "gpu_available": False,
                }
            queue_depths = {
                sid: len(s["queue"]) for sid, s in self._streams.items()
            }
            total_queued = sum(queue_depths.values())
            if total_queued == 0:
                return {
                    "recommended_streams": 1,
                    "reason": "No pending tasks",
                    "gpu_available": True,
                }
            if self._gpu_memory_mb > 24000:
                base = 4
            elif self._gpu_memory_mb > 12000:
                base = 3
            elif self._gpu_memory_mb > 6000:
                base = 2
            else:
                base = 1
            device_factor = min(self._cuda_device_count, base)
            queued_streams = sum(1 for d in queue_depths.values() if d > 0)
            recommended = min(device_factor, queued_streams, 8)
            recommended = max(1, recommended)
            return {
                "recommended_streams": recommended,
                "queued_tasks": total_queued,
                "queued_streams": queued_streams,
                "gpu_available": True,
                "gpu_memory_mb": round(self._gpu_memory_mb, 1),
            }

    def should_use_gpu(self, task_type: str) -> bool:
        """Determine if a task type should run on GPU or fall back to CPU."""
        gpu_friendly = {
            "matrix_multiply",
            "convolution",
            "inference",
            "training",
            "embedding",
            "attention",
            "softmax",
            "batch_norm",
            "layer_norm",
            "transpose",
            "fft",
            "image_process",
            "vector_search",
            "gemm",
            "reduction",
        }
        with self._lock:
            if not self._gpu_available:
                return False
            normalized = task_type.lower().strip().replace("-", "_").replace(" ", "_")
            if normalized in gpu_friendly:
                return True
            gpu_heavy = {
                "large_batch",
                "high_dimensional",
                "parallel_compute",
                "neural_net",
                "deep_learning",
                "gpu_compute",
            }
            if normalized in gpu_heavy:
                return True
            cpu_preferred = {
                "io_bound",
                "file_read",
                "file_write",
                "network_io",
                "sequential",
                "small_scalar",
                "string_process",
            }
            if normalized in cpu_preferred:
                return False
            return True

    def remove_stream(self, stream_id: str) -> bool:
        """Remove a stream. Returns True if found and removed."""
        with self._lock:
            if stream_id not in self._streams:
                return False
            remaining = len(self._streams[stream_id]["queue"])
            del self._streams[stream_id]
            self._stats["streams_used"] = len(self._streams)
            logger.info(
                "Removed stream '%s' (dropped %d queued tasks)", stream_id, remaining
            )
            return True

    def clear_stream(self, stream_id: str) -> int:
        """Clear all tasks from a stream. Returns count of dropped tasks."""
        with self._lock:
            if stream_id not in self._streams:
                return 0
            count = len(self._streams[stream_id]["queue"])
            self._streams[stream_id]["queue"].clear()
            self._streams[stream_id]["active"] = False
            logger.info("Cleared stream '%s' (%d tasks dropped)", stream_id, count)
            return count


_instance: Optional[GPUScheduler] = None
_instance_lock = threading.RLock()


def get_gpu_scheduler() -> GPUScheduler:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = GPUScheduler()
            logger.info("Created GPUScheduler singleton")
        return _instance
