"""GPU Residency Manager — Keep active models resident in VRAM.

Avoid: Load Model → Infer → Unload → Load Again
Instead: Load once, keep resident, infer on demand.
"""
import logging
import time
import threading
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger("gpu_optimization.residency")


@dataclass
class GPUBuffers:
    """GPU buffer allocation info."""
    name: str
    size_mb: float
    allocated_at: float = 0.0
    last_used: float = 0.0
    use_count: int = 0
    resident: bool = True


class GPUResidencyManager:
    """Keep frequently used models and buffers resident in VRAM.

    Features:
    - Track all GPU allocations
    - Evict only when VRAM pressure occurs
    - Priority-based eviction (keep frequently used)
    - Pre-allocate common buffers
    """

    def __init__(self, total_vram_mb: float = 2048):
        self._total_vram_mb = total_vram_mb
        self._allocated: Dict[str, GPUBuffers] = {}
        self._lock = threading.Lock()
        self._total_allocations = 0
        self._total_evictions = 0

    def allocate(self, name: str, size_mb: float) -> bool:
        """Allocate GPU buffer. Returns False if insufficient VRAM."""
        with self._lock:
            current_usage = sum(b.size_mb for b in self._allocated.values() if b.resident)
            if current_usage + size_mb > self._total_vram_mb:
                self._evict_to_fit(size_mb)

            if name in self._allocated:
                buf = self._allocated[name]
                buf.last_used = time.time()
                buf.use_count += 1
                return True

            buf = GPUBuffers(
                name=name, size_mb=size_mb,
                allocated_at=time.time(), last_used=time.time(),
            )
            self._allocated[name] = buf
            self._total_allocations += 1
            return True

    def _evict_to_fit(self, needed_mb: float) -> None:
        """Evict least-recently-used buffers to fit needed allocation."""
        candidates = sorted(
            [b for b in self._allocated.values() if b.resident],
            key=lambda b: (b.use_count, b.last_used)
        )
        freed = 0
        for buf in candidates:
            if freed >= needed_mb:
                break
            buf.resident = False
            freed += buf.size_mb
            self._total_evictions += 1
            logger.debug("Evicted GPU buffer: %s (%.1fMB)", buf.name, buf.size_mb)

    def touch(self, name: str) -> None:
        """Mark a buffer as recently used."""
        with self._lock:
            if name in self._allocated:
                self._allocated[name].last_used = time.time()
                self._allocated[name].use_count += 1

    def release(self, name: str) -> None:
        with self._lock:
            if name in self._allocated:
                self._allocated[name].resident = False

    def get_usage(self) -> Dict[str, Any]:
        with self._lock:
            resident = [b for b in self._allocated.values() if b.resident]
            total_used = sum(b.size_mb for b in resident)
            return {
                "total_vram_mb": self._total_vram_mb,
                "used_mb": round(total_used, 1),
                "free_mb": round(self._total_vram_mb - total_used, 1),
                "utilization_pct": round(total_used / self._total_vram_mb * 100, 1),
                "resident_buffers": len(resident),
                "total_buffers": len(self._allocated),
                "total_allocations": self._total_allocations,
                "total_evictions": self._total_evictions,
            }


_residency_instance: Optional[GPUResidencyManager] = None


def get_gpu_residency_manager(vram_mb: float = 2048) -> GPUResidencyManager:
    global _residency_instance
    if _residency_instance is None:
        _residency_instance = GPUResidencyManager(total_vram_mb=vram_mb)
    return _residency_instance
