"""Kernel construction for JARVIS MK-X.

``build_kernel`` is the single factory the CLI, the persistent daemon, and
tests use to assemble a ready-to-run :class:`core.agent.loop.AgentLoop`:
config + tool registry + project context + provider router + memory. It lives
in ``runtime`` (not ``cli``) so the daemon can boot a kernel without importing
the typer CLI.

The legacy :class:`JarvisKernel` OS-style skeleton is kept for compatibility.
"""

import asyncio
import atexit
from typing import Optional

from runtime.startup_profile import get_profiler

__all__ = ["build_kernel", "close_kernel", "JarvisKernel"]


def _telemetry():
    """Lazily resolve the telemetry singleton; None when unavailable."""
    try:
        from runtime.telemetry import telemetry

        return telemetry
    except Exception:  # pragma: no cover - optional subsystem
        return None


def build_kernel(mode: str = "agent", max_iterations: int = 10,
                 max_tokens: Optional[int] = None,
                 project_dir: Optional[str] = None):
    """Assemble a ready AgentLoop (config, tools, project, router, memory)."""
    profiler = get_profiler()
    with profiler.phase("import.config"):
        from core.config import Config
        from core.project import ProjectContext
    with profiler.phase("import.tools"):
        from tools import build_default_registry
    with profiler.phase("import.providers"):
        from providers.router import ProviderRouter
    with profiler.phase("import.memory"):
        from memory.mem import get_mem
    with profiler.phase("import.agent"):
        from core.agent.loop import AgentLoop
    with profiler.phase("config"):
        config = Config.instance()
    with profiler.phase("tools.registry"):
        registry = build_default_registry()
    with profiler.phase("project.discover"):
        project = (ProjectContext.discover(project_dir) if project_dir
                   else ProjectContext.discover())
    with profiler.phase("providers.router"):
        router = ProviderRouter(config.get_section("models"), config.api_keys)
    with profiler.phase("memory.open"):
        mem = get_mem()
    with profiler.phase("memory.docs"):
        mem.import_project_docs(str(project.root_path), project.root_path)
    if not getattr(build_kernel, "_mem_cleanup_registered", False):
        build_kernel._mem_cleanup_registered = True
        atexit.register(mem.close)
    return AgentLoop(
        router=router,
        registry=registry,
        project=project,
        mode=mode,
        max_iterations=max_iterations,
        max_tokens=max_tokens,
        mem=mem,
    )


def close_kernel(loop) -> None:
    """Flush logs and close the memory store for a kernel built by build_kernel."""
    try:
        loop.logger.flush()
    except Exception:
        pass
    try:
        if loop.mem is not None:
            loop.mem.close()
    except Exception:
        pass


class JarvisKernel:
    """Core kernel that boots the JARVIS OS-like runtime.

    It loads configuration, registers core services, starts the event bus and
    runs the main async loop awaiting shutdown signals.
    """

    def __init__(self):
        self.config = {}
        self.container = None
        self.event_bus = None
        self._shutdown_event = asyncio.Event()

    async def load_config(self, config_path: str = "config.yaml") -> None:
        """Load configuration from a YAML file (placeholder implementation)."""
        self.config = {"config_path": str(config_path)}

    def register_services(self) -> None:
        """Register core services into the DI container (placeholder)."""

    async def start_services(self) -> None:
        """Start all registered services concurrently (placeholder)."""

    async def stop_services(self) -> None:
        """Stop all services in reverse registration order (placeholder)."""

    async def run_event_loop(self) -> None:
        """Run the main event loop until a shutdown is requested."""
        await self._shutdown_event.wait()

    async def start(self) -> None:
        """Boot the kernel: load config, register and start services, then run loop."""
        await self.load_config()
        self.register_services()
        await self.start_services()
        telemetry = _telemetry()
        if telemetry is not None:
            await telemetry.start()
        await self.run_event_loop()

    async def shutdown(self) -> None:
        """Signal shutdown and stop services gracefully."""
        self._shutdown_event.set()
        await self.stop_services()
        telemetry = _telemetry()
        if telemetry is not None:
            await telemetry.shutdown()


if __name__ == "__main__":

    async def _main():
        kernel = JarvisKernel()
        await kernel.start()

    asyncio.run(_main())
