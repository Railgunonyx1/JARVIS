"""Lightweight kernel-boot helper (no typer/rich CLI imports)."""
from __future__ import annotations


def build_loop(mode: str = "agent",
               max_iterations: int = 10,
               max_tokens: int | None = None,
               project_dir: str | None = None,
               confirmation_handler=None):
    """Assemble and return the AgentLoop.

    Defers heavy imports (runtime.kernel, cli.startup_profile) to call time so
    callers like ``cli.fast`` avoid pulling in the typer/rich CLI stack.
    """
    from cli.startup_profile import get_profiler

    profiler = get_profiler()
    profiler.begin_trace()
    try:
        from runtime.kernel import build_kernel
        with profiler.phase("kernel.build"):
            runtime = build_kernel(
                mode=mode,
                max_iterations=max_iterations,
                max_tokens=max_tokens,
                project_dir=project_dir,
                confirmation_handler=confirmation_handler,
            )
        return runtime.agent_loop
    finally:
        profiler.end_trace()
