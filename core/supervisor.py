"""Service Supervisor — Erlang OTP-style service monitoring and auto-restart.

Watches registered services, detects failures (crashes, unresponsiveness),
and restarts with configurable backoff. Integrates with ServiceRegistry,
StateMachine, and EventBus.
"""

import time
import asyncio
import logging
from typing import Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger("jarvis.core.supervisor")


@dataclass
class ServiceSpec:
    """Specification for a supervised service."""
    name: str
    start: Callable
    stop: Optional[Callable] = None
    health_check: Optional[Callable] = None
    restart_policy: str = "permanent"  # permanent | temporary | never
    max_restarts: int = 5
    backoff_base: float = 1.0
    backoff_max: float = 60.0
    health_interval: float = 10.0


@dataclass
class ServiceInstance:
    spec: ServiceSpec
    state: str = "idle"  # idle | starting | running | stopping | dead
    restarts: int = 0
    last_start: float = 0.0
    last_failure: float = 0.0
    error: str = ""
    task: Optional[asyncio.Task] = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class Supervisor:
    """Supervises services — starts, monitors, restarts on failure.

    Usage:
        async def my_service():
            while True:
                await asyncio.sleep(1)

        sup = Supervisor()
        sup.add(ServiceSpec(name="my_svc", start=my_service))
        await sup.start()
    """

    def __init__(self, event_bus=None):
        self._services: dict[str, ServiceInstance] = {}
        self._event_bus = event_bus
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    def add(self, spec: ServiceSpec):
        if spec.name in self._services:
            logger.warning("Service %s already supervised, replacing", spec.name)
        self._services[spec.name] = ServiceInstance(spec=spec)
        logger.info("Supervisor: added %s (policy=%s, max_restarts=%d)",
                     spec.name, spec.restart_policy, spec.max_restarts)

    async def _start_one(self, inst: ServiceInstance):
        async with inst._lock:
            if inst.state != "idle":
                return
            inst.state = "starting"
            inst.last_start = time.time()
        try:
            task = asyncio.create_task(inst.spec.start())
            inst.task = task
            async with inst._lock:
                inst.state = "running"
            logger.info("Service %s started", inst.spec.name)
            self._emit("service_started", {"name": inst.spec.name})
            await task
        except asyncio.CancelledError:
            async with inst._lock:
                inst.state = "stopping"
            raise
        except Exception as e:
            async with inst._lock:
                inst.state = "dead"
                inst.restarts += 1
                inst.last_failure = time.time()
                inst.error = str(e)
            logger.error("Service %s crashed: %s", inst.spec.name, e)
            self._emit("service_crashed", {"name": inst.spec.name, "error": str(e)})
            await self._maybe_restart(inst)

    async def _maybe_restart(self, inst: ServiceInstance):
        policy = inst.spec.restart_policy
        if policy == "never":
            logger.info("Service %s: policy=never, not restarting", inst.spec.name)
            return
        if policy == "temporary" and inst.restarts > inst.spec.max_restarts:
            logger.info("Service %s: max_restarts (%d) reached, not restarting",
                        inst.spec.name, inst.spec.max_restarts)
            return
        if policy == "permanent" and inst.restarts > inst.spec.max_restarts:
            logger.warning("Service %s: max_restarts (%d) reached, giving up",
                           inst.spec.name, inst.spec.max_restarts)
            self._emit("service_gave_up", {"name": inst.spec.name})
            return

        # Exponential backoff
        delay = min(
            inst.spec.backoff_base * (2 ** (inst.restarts - 1)),
            inst.spec.backoff_max,
        )
        logger.info("Service %s: restarting in %.1fs (attempt %d/%d)",
                    inst.spec.name, delay, inst.restarts, inst.spec.max_restarts)
        self._emit("service_restarting", {
            "name": inst.spec.name,
            "delay": delay,
            "attempt": inst.restarts,
        })
        await asyncio.sleep(delay)

        async with inst._lock:
            inst.state = "idle"
        await self._start_one(inst)

    async def _health_check(self):
        while self._running:
            for inst in list(self._services.values()):
                async with inst._lock:
                    if inst.state != "running" or inst.spec.health_check is None:
                        continue
                try:
                    ok = inst.spec.health_check()
                    if not ok:
                        logger.warning("Service %s: health check failed", inst.spec.name)
                        if inst.task:
                            inst.task.cancel()
                except Exception as e:
                    logger.warning("Service %s: health check error: %s", inst.spec.name, e)
            await asyncio.sleep(5)

    async def start(self):
        self._running = True
        for inst in self._services.values():
            asyncio.create_task(self._start_one(inst))
        self._monitor_task = asyncio.create_task(self._health_check())
        logger.info("Supervisor: started %d services", len(self._services))

    async def stop(self):
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
        for inst in self._services.values():
            async with inst._lock:
                if inst.task and not inst.task.done():
                    inst.task.cancel()
                if inst.spec.stop:
                    try:
                        inst.spec.stop()
                    except Exception as e:
                        logger.warning("Service %s: stop error: %s", inst.spec.name, e)
                inst.state = "stopping"
        logger.info("Supervisor: stopped all services")

    def get_status(self) -> dict:
        result = {}
        for name, inst in self._services.items():
            result[name] = {
                "state": inst.state,
                "restarts": inst.restarts,
                "last_failure": inst.last_failure,
                "error": inst.error,
                "policy": inst.spec.restart_policy,
                "uptime": time.time() - inst.last_start if inst.state == "running" else 0,
            }
        return result

    def _emit(self, event: str, data: dict):
        if self._event_bus:
            try:
                self._event_bus.publish(f"supervisor.{event}", data)
            except Exception:
                pass
