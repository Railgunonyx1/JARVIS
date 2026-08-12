"""Runtime Kernel Fusion — Conceptual framework for fusing GPU operations.

Fuse LayerNorm + MatMul + Activation into single kernel.
Reduces memory transfers and improves throughput.
"""
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("gpu_optimization.kernel_fusion")


@dataclass
class KernelOperation:
    """A single kernel operation."""
    name: str
    input_size: int = 0
    output_size: int = 0
    estimated_ms: float = 0.0


@dataclass
class FusionGroup:
    """A group of operations that can be fused."""
    operations: list[KernelOperation] = field(default_factory=list)
    fused_name: str = ""
    original_ms: float = 0.0
    fused_ms: float = 0.0
    speedup: float = 1.0


class KernelFusionOptimizer:
    """Identify and fuse compatible GPU operations.

    Fusable patterns:
    - LayerNorm → MatMul → Activation (attention block)
    - Conv → BatchNorm → ReLU (common in vision)
    - Embedding → LayerNorm (transformer input)

    On actual GPU, these would be compiled into fused CUDA kernels.
    On CPU/Python, we simulate the speedup estimation.
    """

    FUSABLE_PATTERNS = [
        ["layernorm", "matmul", "activation"],
        ["conv", "batchnorm", "relu"],
        ["embedding", "layernorm"],
        ["matmul", "bias_add", "activation"],
        ["softmax", "matmul", "scaling"],
    ]

    def __init__(self):
        self._operations: list[KernelOperation] = []
        self._fusion_groups: list[FusionGroup] = []
        self._lock = threading.Lock()
        self._total_fusions = 0
        self._total_speedup_ms = 0.0

    def add_operation(self, name: str, input_size: int = 0, estimated_ms: float = 1.0) -> None:
        with self._lock:
            self._operations.append(KernelOperation(
                name=name.lower(), input_size=input_size, estimated_ms=estimated_ms
            ))

    def find_fusion_opportunities(self) -> list[FusionGroup]:
        """Analyze current operations and find fusion opportunities."""
        groups = []
        ops = [op.name for op in self._operations]

        for pattern in self.FUSABLE_PATTERNS:
            for i in range(len(ops) - len(pattern) + 1):
                if ops[i:i + len(pattern)] == pattern:
                    matched_ops = self._operations[i:i + len(pattern)]
                    group = FusionGroup(
                        operations=list(matched_ops),
                        fused_name="_".join(pattern) + "_fused",
                        original_ms=sum(op.estimated_ms for op in matched_ops),
                    )
                    # Fused kernel is ~60-80% of original (eliminates memory transfers)
                    group.fused_ms = group.original_ms * 0.3
                    group.speedup = group.original_ms / max(group.fused_ms, 0.001)
                    groups.append(group)

        self._fusion_groups = groups
        return groups

    def get_total_speedup(self) -> dict[str, Any]:
        """Calculate total speedup from all fusion opportunities."""
        self.find_fusion_opportunities()
        total_original = sum(g.original_ms for g in self._fusion_groups)
        total_fused = sum(g.fused_ms for g in self._fusion_groups)

        return {
            "fusion_groups": len(self._fusion_groups),
            "total_original_ms": round(total_original, 2),
            "total_fused_ms": round(total_fused, 2),
            "speedup_ratio": round(total_original / max(total_fused, 0.001), 2),
            "estimated_savings_ms": round(total_original - total_fused, 2),
        }

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_operations": len(self._operations),
                "fusion_groups": len(self._fusion_groups),
                "total_fusions": self._total_fusions,
            }


_kernel_fusion_instance: KernelFusionOptimizer | None = None


def get_kernel_fusion_optimizer() -> KernelFusionOptimizer:
    global _kernel_fusion_instance
    if _kernel_fusion_instance is None:
        _kernel_fusion_instance = KernelFusionOptimizer()
    return _kernel_fusion_instance
