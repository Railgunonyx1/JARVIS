"""Dependency Injection Container — Typed, scoped, with dependency-ordered startup.

Lifetimes:
  SINGLETON — one instance for the life of the container
  REQUEST  — one instance per scoped request (conversation)
  TRANSIENT — new instance on every resolve

Dependency metadata enables automatic startup ordering and failure isolation.
"""
import logging
import threading
from collections import OrderedDict
from enum import Enum, auto
from typing import (
    Any, Callable, Dict, Generic, List, Optional,
    Set, Tuple, Type, TypeVar, Union,
)

logger = logging.getLogger("jarvis.container")

T = TypeVar("T")


class ServiceLifetime(Enum):
    SINGLETON = auto()
    REQUEST = auto()
    TRANSIENT = auto()


class ServiceState(Enum):
    CREATED = auto()
    INITIALIZING = auto()
    RUNNING = auto()
    DEGRADED = auto()
    STOPPING = auto()
    STOPPED = auto()
    FAILED = auto()

    def can_transition_to(self, target: "ServiceState") -> bool:
        transitions = {
            ServiceState.CREATED: {ServiceState.INITIALIZING, ServiceState.FAILED},
            ServiceState.INITIALIZING: {ServiceState.RUNNING, ServiceState.FAILED, ServiceState.STOPPING},
            ServiceState.RUNNING: {ServiceState.DEGRADED, ServiceState.STOPPING, ServiceState.FAILED},
            ServiceState.DEGRADED: {ServiceState.RUNNING, ServiceState.STOPPING, ServiceState.FAILED},
            ServiceState.STOPPING: {ServiceState.STOPPED, ServiceState.FAILED},
            ServiceState.STOPPED: {ServiceState.CREATED},
            ServiceState.FAILED: {ServiceState.CREATED},
        }
        return target in transitions.get(self, set())


class ServiceRecord:
    __slots__ = ("interface", "implementation", "lifetime", "dependencies",
                 "instance", "state", "scope_owner")

    def __init__(self, interface: Type, implementation: Type,
                 lifetime: ServiceLifetime,
                 dependencies: Optional[List[str]] = None):
        self.interface = interface
        self.implementation = implementation
        self.lifetime = lifetime
        self.dependencies = dependencies or []
        self.instance: Any = None
        self.state = ServiceState.CREATED
        self.scope_owner: Optional[str] = None


class ServiceContainer:
    """Typed DI container with scoping and dependency-ordered lifecycle."""

    def __init__(self, parent: Optional["ServiceContainer"] = None):
        self._parent = parent
        self._services: Dict[str, ServiceRecord] = OrderedDict()
        self._instances: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._scope_name: Optional[str] = None

    # ── Registration ──────────────────────────────────────────────

    def register(self,
                 interface: Type[T],
                 implementation: Optional[Type] = None,
                 *,
                 lifetime: ServiceLifetime = ServiceLifetime.SINGLETON,
                 dependencies: Optional[List[str]] = None,
                 instance: Any = None,
                 ) -> "ServiceContainer":
        key = self._key(interface)
        if instance is not None:
            self._services[key] = ServiceRecord(
                interface=interface,
                implementation=type(instance),
                lifetime=ServiceLifetime.SINGLETON,
            )
            self._services[key].instance = instance
            self._services[key].state = ServiceState.RUNNING
            return self
        impl = implementation or interface
        self._services[key] = ServiceRecord(
            interface=interface,
            implementation=impl,
            lifetime=lifetime,
            dependencies=dependencies,
        )
        logger.debug("Registered %s → %s (%s)", key, impl.__name__, lifetime.name)
        return self

    def register_instance(self, interface: Type[T], instance: T) -> "ServiceContainer":
        return self.register(interface, instance=instance)

    def is_registered(self, interface: Type) -> bool:
        return self._key(interface) in self._services

    # ── Resolution ────────────────────────────────────────────────

    def resolve(self, interface: Type[T]) -> T:
        key = self._key(interface)
        record = self._services.get(key)
        if record is None:
            if self._parent:
                return self._parent.resolve(interface)
            raise KeyError(f"Service not registered: {interface.__name__}")
        if record.lifetime == ServiceLifetime.TRANSIENT:
            return self._create_instance(record)
        if record.lifetime == ServiceLifetime.REQUEST:
            if self._scope_name is None:
                # Fallback: treat as transient outside a scope
                return self._create_instance(record)
            scope_key = f"{key}@{self._scope_name}"
            if scope_key in self._instances:
                return self._instances[scope_key]
            instance = self._create_instance(record)
            self._instances[scope_key] = instance
            return instance
        if record.instance is not None:
            return record.instance
        instance = self._create_instance(record)
        record.instance = instance
        return instance

    def _create_instance(self, record: ServiceRecord) -> Any:
        init = getattr(record.implementation, "__init__", None)
        if init is None:
            return record.implementation()
        import inspect
        sig = inspect.signature(init)
        params = list(sig.parameters.values())[1:]  # skip self
        kwargs = {}
        for p in params:
            if p.annotation is not inspect.Parameter.empty:
                if p.annotation is ServiceContainer:
                    kwargs[p.name] = self
                elif self.is_registered(p.annotation):
                    kwargs[p.name] = self.resolve(p.annotation)
        try:
            instance = record.implementation(**kwargs)
            record.state = ServiceState.RUNNING
            return instance
        except Exception as e:
            record.state = ServiceState.FAILED
            logger.error("Failed to create %s: %s", record.implementation.__name__, e)
            raise

    # ── Scoping ───────────────────────────────────────────────────

    def create_scope(self, name: str) -> "ServiceContainer":
        scope = ServiceContainer(parent=self)
        scope._scope_name = name
        scope._services = self._services
        return scope

    def dispose_scope(self, name: str):
        keys = [k for k in self._instances if k.endswith(f"@{name}")]
        for k in keys:
            del self._instances[k]

    # ── Lifecycle ─────────────────────────────────────────────────

    def start_all(self):
        sorted_services = self._topological_sort()
        for key in sorted_services:
            record = self._services[key]
            if record.state != ServiceState.CREATED:
                continue
            record.state = ServiceState.INITIALIZING
            try:
                self.resolve(record.interface)
                record.state = ServiceState.RUNNING
                logger.info("Started %s", key)
            except Exception as e:
                record.state = ServiceState.FAILED
                logger.error("Failed to start %s: %s", key, e)

    def stop_all(self):
        sorted_services = list(reversed(self._topological_sort()))
        for key in sorted_services:
            record = self._services[key]
            record.state = ServiceState.STOPPING
            record.instance = None
            record.state = ServiceState.STOPPED
            logger.info("Stopped %s", key)

    def _topological_sort(self) -> List[str]:
        visited: Set[str] = set()
        result: List[str] = []

        def _visit(key: str):
            if key in visited:
                return
            visited.add(key)
            record = self._services[key]
            for dep in record.dependencies:
                _visit(dep)
            result.append(key)

        for key in self._services:
            _visit(key)
        return result

    # ── Health ────────────────────────────────────────────────────

    def get_all_states(self) -> Dict[str, str]:
        return {k: v.state.name for k, v in self._services.items()}

    def get_failed(self) -> List[str]:
        return [k for k, v in self._services.items()
                if v.state == ServiceState.FAILED]

    @staticmethod
    def _key(interface: Type) -> str:
        return getattr(interface, "__name__", str(interface))


def get_container() -> ServiceContainer:
    """Initialize the default container with all standard services wired."""
    from core.config import Config
    from core.config_service import ConfigService
    from core.metrics import MetricsCollector
    from core.event_store import EventStore
    from core.service_registry import ServiceRegistry
    from core.state_machine import ServiceState
    from core.task_manager import TaskManager
    from systems.event_bus import EventBus
    from reliability_engine.health_monitor import HealthMonitor
    from reliability_engine.circuit_breaker import CircuitBreaker

    container = ServiceContainer()

    # Foundation services (no dependencies)
    cfg = Config.instance()
    container.register(Config, instance=cfg)
    container.register(ConfigService, ConfigService,
                       lifetime=ServiceLifetime.SINGLETON,
                       dependencies=["Config"])
    container.register(MetricsCollector, MetricsCollector,
                       lifetime=ServiceLifetime.SINGLETON)
    container.register(EventStore, EventStore,
                       lifetime=ServiceLifetime.SINGLETON)
    container.register(ServiceRegistry, ServiceRegistry,
                       lifetime=ServiceLifetime.SINGLETON)

    # EventBus depends on nothing directly
    bus = EventBus()
    container.register(EventBus, instance=bus)

    # Reliability services
    hm = HealthMonitor()
    container.register(HealthMonitor, instance=hm)
    cb = CircuitBreaker()
    container.register(CircuitBreaker, instance=cb)

    # Task management
    container.register(TaskManager, TaskManager,
                       lifetime=ServiceLifetime.SINGLETON)

    return container
