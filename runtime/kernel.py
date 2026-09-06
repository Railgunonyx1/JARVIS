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
from dataclasses import dataclass, field
from typing import Any, Optional

from runtime.startup_profile import get_profiler

__all__ = [
    "build_kernel", "close_kernel", "JarvisKernel", "JarvisRuntime",
]


def _telemetry():
    """Lazily resolve the telemetry singleton; None when unavailable."""
    try:
        from runtime.telemetry import telemetry

        return telemetry
    except Exception:  # pragma: no cover - optional subsystem
        return None


@dataclass
class JarvisRuntime:
    """The fully-wired production runtime graph.

    ``build_kernel`` returns one of these so the CLI, the daemon, and tests
    share a single canonical composition root instead of each assembling its
    own reduced graph.
    """

    config: Any = None
    event_bus: Any = None
    tool_registry: Any = None
    tool_service: Any = None
    model_gateway: Any = None
    harness_selector: Any = None
    provider_router: Any = None
    memory: Any = None
    project: Any = None
    agent_loop: Any = None
    auxiliary: dict[str, Any] = field(default_factory=dict)


def _build_model_gateway_from_config(models_config):
    """Construct the canonical ModelGateway and register configured models.

    The gateway is the single model-selection authority. Models are registered
    from the models TOML (ollama + a fast cloud tier) so harness capability
    selection has real options to choose from.
    """
    from providers.model_gateway import Capability, Combo, ModelGateway, ModelProfile

    gateway = ModelGateway()
    ollama_cfg = models_config.get("ollama") or {}
    default_model = ollama_cfg.get("model") or "qwen2.5:3b"

    profiles: list[ModelProfile] = []
    if default_model:
        profiles.append(ModelProfile(
            name=default_model,
            provider="ollama",
            capabilities=(Capability.CODING, Capability.REASONING, Capability.TOOL_USE, Capability.PRIVACY),
        ))
    fallback = ollama_cfg.get("fallback") or {}
    fb_model = fallback.get("model")
    if fb_model and fb_model != default_model:
        profiles.append(ModelProfile(
            name=fb_model,
            provider="ollama",
            capabilities=(Capability.FAST, Capability.CHEAP, Capability.TOOL_USE, Capability.PRIVACY),
        ))

    for profile in profiles:
        gateway.register_model(profile)

    if len(profiles) >= 2:
        gateway.register_combo(Combo(
            name="ollama-cascade",
            models=tuple(profiles),
            description="Ollama default + fallback cascade",
        ))
    return gateway


def _load_models_config():
    """Load ``config/models.toml`` into a dict (tomllib; returns {} on failure)."""
    import os as _os
    import tomllib as _tomllib
    path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "config", "models.toml")
    try:
        with open(path, "rb") as f:
            return _tomllib.load(f)
    except Exception:
        return {}


def _load_api_keys():
    """Load merged API keys from env/.env/api_keys.json."""
    from core.api_keys import get_all_api_keys
    return get_all_api_keys()


def build_kernel(mode: str = "agent", max_iterations: int = 10,
                 max_tokens: int | None = None,
                 project_dir: str | None = None,
                 confirmation_handler=None):
    """Assemble the canonical JARVIS runtime graph and return it.

    Constructs and wires Config, ToolRegistry, ProjectContext, ProviderRouter,
    EventBus, ModelGateway, HarnessSelector, ToolExecutionService and the
    memory store into a single AgentLoop. The CLI, daemon and tests use this
    as their one composition root.
    """
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
    with profiler.phase("import.events"):
        from runtime.event_bus import get_event_bus
    with profiler.phase("import.harness"):
        from core.harness import HarnessSelector
    with profiler.phase("import.tool_service"):
        from core.agent.tool_service import ToolExecutionService
        from core.agent.permissions import PermissionEngine
        from core.agent.tools import AgentToolExecutor
        from core.decision_logger import get_decision_logger
    with profiler.phase("config"):
        config = Config()
        models_config = _load_models_config()
    with profiler.phase("tools.registry"):
        registry = build_default_registry()
    with profiler.phase("project.discover"):
        project = (ProjectContext.discover(project_dir) if project_dir
                   else ProjectContext.discover())
    with profiler.phase("providers.router"):
        router = ProviderRouter(models_config, _load_api_keys())
    with profiler.phase("events"):
        event_bus = get_event_bus()
    with profiler.phase("model_gateway"):
        model_gateway = _build_model_gateway_from_config(models_config)
    with profiler.phase("harness"):
        harness = HarnessSelector()
    with profiler.phase("tool_service"):
        logger = get_decision_logger()
        permissions = PermissionEngine(logger, mode=mode, confirmation_handler=confirmation_handler)
        executor = AgentToolExecutor(registry, logger)
        tool_service = ToolExecutionService(
            registry=registry,
            permissions=permissions,
            executor=executor,
            decision_logger=logger,
            bus=event_bus,
            mode=mode,
        )
    with profiler.phase("memory.open"):
        mem = get_mem()
    with profiler.phase("memory.docs"):
        mem.import_project_docs(str(project.root_path), project.root_path)
    if not getattr(build_kernel, "_mem_cleanup_registered", False):
        build_kernel._mem_cleanup_registered = True
        atexit.register(mem.close)

    loop = AgentLoop(
        router=router,
        registry=registry,
        project=project,
        mode=mode,
        max_iterations=max_iterations,
        max_tokens=max_tokens,
        mem=mem,
        event_bus=event_bus,
        harness=harness.active,
        model_gateway=model_gateway,
        tool_service=tool_service,
        confirmation_handler=confirmation_handler,
    )

    return JarvisRuntime(
        config=config,
        event_bus=event_bus,
        tool_registry=registry,
        tool_service=tool_service,
        model_gateway=model_gateway,
        harness_selector=harness,
        provider_router=router,
        memory=mem,
        project=project,
        agent_loop=loop,
    )


def close_kernel(kernel) -> None:
    """Flush logs and close resources for a kernel built by build_kernel.

    Accepts either a JarvisRuntime or a raw AgentLoop.
    """
    loop = getattr(kernel, "agent_loop", kernel)
    mem = getattr(getattr(kernel, "memory", None), "close", None)
    try:
        loop.logger.flush()
    except Exception:
        pass
    try:
        if loop.mem is not None:
            loop.mem.close()
    except Exception:
        pass
    try:
        if mem is not None:
            mem()
    except Exception:
        pass
    try:
        from core.event_store import close_event_store

        close_event_store()
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
