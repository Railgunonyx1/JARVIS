"""
Multi-Agent System — JARVIS MK-X Agent Ecosystem
Centralized agent management, routing, and coordination.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from core.mode_manager import ExecutionMode, get_mode_manager

logger = logging.getLogger("jarvis.agents")


class AgentStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"
    STARTING = "starting"
    STOPPING = "stopping"


class AgentPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class AgentProfile:
    """Defines an agent's identity and capabilities."""
    name: str
    role: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    supported_modes: list[ExecutionMode] = field(default_factory=lambda: [ExecutionMode.SMART, ExecutionMode.AGENT])
    max_concurrent_tasks: int = 1
    timeout_seconds: int = 300
    priority: AgentPriority = AgentPriority.NORMAL
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentTask:
    """A task assigned to an agent."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_name: str = ""
    capability: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    priority: AgentPriority = AgentPriority.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str = "pending"
    result: Any = None
    error: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class AgentState:
    """Runtime state of an agent."""
    name: str
    status: AgentStatus = AgentStatus.IDLE
    current_task: AgentTask | None = None
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_execution_time: float = 0.0
    last_activity: datetime = field(default_factory=datetime.now)
    error_count: int = 0
    last_error: str | None = None


class BaseAgent:
    """Base class for all JARVIS agents."""

    def __init__(self, profile: AgentProfile):
        self.profile = profile
        self.state = AgentState(name=profile.name)
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the agent's task processing loop."""
        if self._running:
            return
        self._running = True
        self.state.status = AgentStatus.IDLE
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info(f"Agent {self.profile.name} started")

    async def stop(self):
        """Stop the agent gracefully."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        self.state.status = AgentStatus.OFFLINE
        logger.info(f"Agent {self.profile.name} stopped")

    async def _worker_loop(self):
        """Main task processing loop."""
        while self._running:
            try:
                task = await asyncio.wait_for(self._task_queue.get(), timeout=1.0)
                await self._execute_task(task)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Agent {self.profile.name} worker error: {e}")

    async def _execute_task(self, task: AgentTask):
        """Execute a single task."""
        async with self._lock:
            if self.state.status == AgentStatus.BUSY:
                # Re-queue if busy
                await self._task_queue.put(task)
                return

            self.state.status = AgentStatus.BUSY
            self.state.current_task = task
            task.started_at = datetime.now()
            task.status = "running"

        start_time = time.time()
        try:
            result = await self.execute(task)
            task.result = result
            task.status = "completed"
            task.completed_at = datetime.now()
            self.state.completed_tasks += 1
            logger.info(f"Agent {self.profile.name} completed task {task.task_id}")
        except Exception as e:
            task.error = str(e)
            task.status = "failed"
            task.completed_at = datetime.now()
            self.state.failed_tasks += 1
            self.state.error_count += 1
            self.state.last_error = str(e)
            logger.error(f"Agent {self.profile.name} task {task.task_id} failed: {e}")
        finally:
            elapsed = time.time() - start_time
            self.state.total_execution_time += elapsed
            self.state.last_activity = datetime.now()
            self.state.current_task = None
            self.state.status = AgentStatus.IDLE

    async def execute(self, task: AgentTask) -> Any:
        """Execute a task. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement execute()")

    async def enqueue_task(self, task: AgentTask):
        """Add a task to the agent's queue."""
        task.agent_name = self.profile.name
        await self._task_queue.put(task)

    def get_status(self) -> dict[str, Any]:
        """Get agent status summary."""
        return {
            "name": self.profile.name,
            "role": self.profile.role,
            "status": self.state.status.value,
            "current_task": self.state.current_task.task_id if self.state.current_task else None,
            "completed_tasks": self.state.completed_tasks,
            "failed_tasks": self.state.failed_tasks,
            "total_time": round(self.state.total_execution_time, 2),
            "error_count": self.state.error_count,
            "last_activity": self.state.last_activity.isoformat(),
        }


class AgentRegistry:
    """Registry of all available agents."""

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}
        self._profiles: dict[str, AgentProfile] = {}

    def register(self, agent: BaseAgent) -> bool:
        """Register an agent."""
        if agent.profile.name in self._agents:
            logger.warning(f"Agent {agent.profile.name} already registered")
            return False
        self._agents[agent.profile.name] = agent
        self._profiles[agent.profile.name] = agent.profile
        logger.info(f"Registered agent: {agent.profile.name} ({agent.profile.role})")
        return True

    def unregister(self, name: str) -> bool:
        """Unregister an agent."""
        if name in self._agents:
            del self._agents[name]
            del self._profiles[name]
            logger.info(f"Unregistered agent: {name}")
            return True
        return False

    def get(self, name: str) -> BaseAgent | None:
        return self._agents.get(name)

    def get_profile(self, name: str) -> AgentProfile | None:
        return self._profiles.get(name)

    def list_agents(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "role": profile.role,
                "status": self._agents[name].state.status.value,
                "capabilities": profile.capabilities,
            }
            for name, profile in self._profiles.items()
        ]

    def get_by_capability(self, capability: str) -> list[BaseAgent]:
        """Find agents that have a specific capability."""
        return [
            agent for name, agent in self._agents.items()
            if capability in agent.profile.capabilities
        ]

    def get_available_agents(self, mode: ExecutionMode | None = None) -> list[BaseAgent]:
        mode = mode or get_mode_manager().get_mode()
        return [
            agent for agent in self._agents.values()
            if mode in agent.profile.supported_modes
        ]


class AgentRouter:
    """Routes tasks to appropriate agents based on capabilities."""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    def route(self, capability: str, mode: ExecutionMode | None = None) -> BaseAgent | None:
        """Find the best agent for a capability."""
        mode = mode or get_mode_manager().get_mode()
        candidates = [
            agent for agent in self.registry.get_available_agents(mode)
            if capability in agent.profile.capabilities
        ]
        if not candidates:
            return None
        # Prefer idle agents, then by priority
        candidates.sort(key=lambda a: (a.state.status != AgentStatus.IDLE, -a.profile.priority.value))
        return candidates[0] if candidates else None

    def route_task(self, task: AgentTask, mode: ExecutionMode | None = None) -> bool:
        """Route a task to an appropriate agent."""
        agent = self.route(task.capability, mode)
        if not agent:
            return False
        asyncio.create_task(agent.enqueue_task(task))
        return True


class TaskAllocator:
    """Allocates tasks to agents based on capabilities and workload."""

    def __init__(self, registry: AgentRegistry, router: AgentRouter):
        self.registry = registry
        self.router = router

    async def allocate(self, tasks: list[AgentTask], mode: ExecutionMode | None = None) -> dict[str, list[AgentTask]]:
        """Allocate tasks to agents."""
        allocation: dict[str, list[AgentTask]] = {}
        mode = mode or get_mode_manager().get_mode()

        for task in tasks:
            agent = self.router.route(task.capability, mode)
            if agent:
                await agent.enqueue_task(task)
                allocation.setdefault(agent.profile.name, []).append(task)
            else:
                logger.warning(f"No agent found for capability: {task.capability}")

        return allocation

    async def allocate_parallel(self, tasks: list[AgentTask], mode: ExecutionMode | None = None):
        """Allocate independent tasks in parallel."""
        return await self.allocate(tasks, mode)


class CollaborationEngine:
    """Manages inter-agent collaboration."""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self._message_queues: dict[str, asyncio.Queue] = {}

    async def send_message(self, sender: str, receiver: str, message: dict[str, Any]) -> bool:
        """Send a message from one agent to another."""
        if receiver not in self._message_queues:
            self._message_queues[receiver] = asyncio.Queue()
        await self._message_queues[receiver].put({
            "from": sender,
            "data": message,
            "timestamp": datetime.now().isoformat()
        })
        return True

    async def receive_message(self, agent_name: str, timeout: float = 5.0) -> dict | None:
        """Receive a message for an agent."""
        if agent_name not in self._message_queues:
            return None
        try:
            return await asyncio.wait_for(
                self._message_queues[agent_name].get(),
                timeout=timeout
            )
        except TimeoutError:
            return None

    async def broadcast(self, sender: str, message: dict[str, Any], exclude: set[str] = None):
        """Broadcast a message to all agents except excluded."""
        exclude = exclude or set()
        for agent_name in self.registry._agents:
            if agent_name != sender and agent_name not in exclude:
                await self.send_message(sender, agent_name, message)


class AgentMonitor:
    """Monitors agent health and performance."""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self._metrics_history: dict[str, list[dict]] = {}

    def collect_metrics(self) -> dict[str, dict]:
        """Collect metrics from all agents."""
        metrics = {}
        for name, agent in self.registry._agents.items():
            state = agent.state
            metrics[name] = {
                "status": state.status.value,
                "completed_tasks": state.completed_tasks,
                "failed_tasks": state.failed_tasks,
                "total_time": round(state.total_execution_time, 2),
                "error_count": state.error_count,
                "success_rate": (
                    state.completed_tasks / (state.completed_tasks + state.failed_tasks)
                    if (state.completed_tasks + state.failed_tasks) > 0 else 0
                ),
                "current_task": state.current_task.capability if state.current_task else None,
            }
            # Store history
            if name not in self._metrics_history:
                self._metrics_history[name] = []
            self._metrics_history[name].append({
                "timestamp": datetime.now().isoformat(),
                **metrics[name]
            })
            # Keep last 100 entries
            if len(self._metrics_history[name]) > 100:
                self._metrics_history[name] = self._metrics_history[name][-100:]
        return metrics

    def get_agent_health(self, name: str) -> dict[str, Any]:
        """Get health status for a specific agent."""
        agent = self.registry.get(name)
        if not agent:
            return {"status": "unknown"}
        state = agent.state
        return {
            "status": state.status.value,
            "healthy": state.status != AgentStatus.ERROR and state.error_count < 5,
            "completed_tasks": state.completed_tasks,
            "failed_tasks": state.failed_tasks,
            "success_rate": (
                state.completed_tasks / (state.completed_tasks + state.failed_tasks)
                if (state.completed_tasks + state.failed_tasks) > 0 else 0
            ),
            "avg_execution_time": (
                state.total_execution_time / state.completed_tasks
                if state.completed_tasks > 0 else 0
            ),
        }


class AgentScheduler:
    """Schedules background and periodic agent tasks."""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self._scheduled_tasks: dict[str, asyncio.Task] = {}
        self._running = False

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False
        for task in self._scheduled_tasks.values():
            task.cancel()
        await asyncio.gather(*self._scheduled_tasks.values(), return_exceptions=True)

    def schedule_periodic(
        self,
        agent_name: str,
        capability: str,
        interval_seconds: float,
        parameters: dict = None,
        priority: AgentPriority = AgentPriority.NORMAL
    ):
        """Schedule a periodic task for an agent."""
        if agent_name in self._scheduled_tasks:
            self._scheduled_tasks[agent_name].cancel()

        async def periodic_task():
            while self._running:
                agent = self.registry.get(agent_name)
                if agent:
                    task = AgentTask(
                        capability=capability,
                        parameters=parameters or {},
                        priority=priority
                    )
                    await agent.enqueue_task(task)
                await asyncio.sleep(interval_seconds)

        task = asyncio.create_task(periodic_task())
        self._scheduled_tasks[agent_name] = task

    def cancel_scheduled(self, agent_name: str):
        if agent_name in self._scheduled_tasks:
            self._scheduled_tasks[agent_name].cancel()
            del self._scheduled_tasks[agent_name]


# Global instances
_agent_registry: AgentRegistry | None = None
_agent_router: AgentRouter | None = None
_task_allocator: TaskAllocator | None = None
_collaboration_engine: CollaborationEngine | None = None
_agent_monitor: AgentMonitor | None = None
_agent_scheduler: AgentScheduler | None = None


def get_agent_registry() -> AgentRegistry:
    global _agent_registry
    if _agent_registry is None:
        _agent_registry = AgentRegistry()
    return _agent_registry


def get_agent_router() -> AgentRouter:
    global _agent_router
    if _agent_router is None:
        _agent_router = AgentRouter(get_agent_registry())
    return _agent_router


def get_task_allocator() -> TaskAllocator:
    global _task_allocator
    if _task_allocator is None:
        _task_allocator = TaskAllocator(get_agent_registry(), get_agent_router())
    return _task_allocator


def get_collaboration_engine() -> CollaborationEngine:
    global _collaboration_engine
    if _collaboration_engine is None:
        _collaboration_engine = CollaborationEngine(get_agent_registry())
    return _collaboration_engine


def get_agent_monitor() -> AgentMonitor:
    global _agent_monitor
    if _agent_monitor is None:
        _agent_monitor = AgentMonitor(get_agent_registry())
    return _agent_monitor


def get_agent_scheduler() -> AgentScheduler:
    global _agent_scheduler
    if _agent_scheduler is None:
        _agent_scheduler = AgentScheduler(get_agent_registry())
    return _agent_scheduler


async def initialize_agent_system():
    """Initialize the agent system."""
    registry = get_agent_registry()
    scheduler = get_agent_scheduler()
    await scheduler.start()
    logger.info("Agent system initialized")
    return registry


async def shutdown_agent_system():
    """Shutdown the agent system."""
    scheduler = get_agent_scheduler()
    await scheduler.stop()
    registry = get_agent_registry()
    for agent in registry._agents.values():
        await agent.stop()
    logger.info("Agent system shutdown complete")


# Pre-built agent profiles
def create_core_agent_profiles() -> dict[str, AgentProfile]:
    """Create standard agent profiles for JARVIS."""
    return {
        "coding_agent": AgentProfile(
            name="coding_agent",
            role="Software Engineer",
            description="Writes, debugs, reviews, and refactors code",
            capabilities=[
                "code_generation", "debugging", "code_review", "refactoring",
                "testing", "architecture_design", "git_operations"
            ],
            required_permissions=["filesystem.read", "filesystem.write", "shell.execute"],
            supported_modes=[ExecutionMode.SMART, ExecutionMode.AGENT],
            max_concurrent_tasks=2,
            priority=AgentPriority.HIGH,
        ),
        "research_agent": AgentProfile(
            name="research_agent",
            role="Research Analyst",
            description="Gathers, analyzes, and synthesizes information",
            capabilities=[
                "web_research", "document_analysis", "paper_analysis",
                "fact_checking", "source_evaluation", "knowledge_synthesis"
            ],
            required_permissions=["web.search", "web.open", "memory.store"],
            supported_modes=[ExecutionMode.SMART, ExecutionMode.AGENT],
            max_concurrent_tasks=3,
            priority=AgentPriority.NORMAL,
        ),
        "vision_agent": AgentProfile(
            name="vision_agent",
            role="Vision Specialist",
            description="Analyzes visual content from screens and cameras",
            capabilities=[
                "screen_capture", "ocr", "object_detection", "ui_analysis",
                "scene_understanding", "visual_reasoning"
            ],
            required_permissions=["screen.capture", "camera.access"],
            supported_modes=[ExecutionMode.SMART, ExecutionMode.AGENT],
            max_concurrent_tasks=1,
            priority=AgentPriority.HIGH,
        ),
        "security_agent": AgentProfile(
            name="security_agent",
            role="Security Guardian",
            description="Monitors threats, validates permissions, audits actions",
            capabilities=[
                "threat_detection", "permission_audit", "vulnerability_scanning",
                "incident_response", "policy_enforcement"
            ],
            required_permissions=["system.query", "security.*"],
            supported_modes=[ExecutionMode.CONTROLLED, ExecutionMode.SMART, ExecutionMode.AGENT],
            max_concurrent_tasks=1,
            priority=AgentPriority.CRITICAL,
        ),
        "system_agent": AgentProfile(
            name="system_agent",
            role="System Administrator",
            description="Manages system resources, processes, and configurations",
            capabilities=[
                "system_monitor", "process_management", "service_management",
                "disk_management", "network_management", "performance_optimization"
            ],
            required_permissions=["system.*", "process.*", "service.*"],
            supported_modes=[ExecutionMode.SMART, ExecutionMode.AGENT],
            max_concurrent_tasks=2,
            priority=AgentPriority.HIGH,
        ),
        "automation_agent": AgentProfile(
            name="automation_agent",
            role="Automation Specialist",
            description="Executes desktop automation and workflow tasks",
            capabilities=[
                "desktop_automation", "file_operations", "window_management",
                "clipboard_management", "input_control", "application_control"
            ],
            required_permissions=["desktop.*", "filesystem.*", "input.*"],
            supported_modes=[ExecutionMode.CONTROLLED, ExecutionMode.SMART, ExecutionMode.AGENT],
            max_concurrent_tasks=1,
            priority=AgentPriority.NORMAL,
        ),
        "testing_agent": AgentProfile(
            name="testing_agent",
            role="Quality Assurance",
            description="Runs tests, validates outputs, checks quality",
            capabilities=[
                "test_generation", "test_execution", "code_review",
                "benchmark_execution", "regression_testing"
            ],
            required_permissions=["filesystem.read", "shell.execute"],
            supported_modes=[ExecutionMode.SMART, ExecutionMode.AGENT],
            max_concurrent_tasks=2,
            priority=AgentPriority.NORMAL,
        ),
        "memory_agent": AgentProfile(
            name="memory_agent",
            role="Memory Curator",
            description="Manages memory storage, retrieval, and optimization",
            capabilities=[
                "vector_search", "memory_compression", "knowledge_graph",
                "context_retrieval", "memory_optimization"
            ],
            required_permissions=["memory.*"],
            supported_modes=[ExecutionMode.SMART, ExecutionMode.AGENT],
            max_concurrent_tasks=1,
            priority=AgentPriority.NORMAL,
        ),
        "optimizer_agent": AgentProfile(
            name="optimizer_agent",
            role="Prompt Optimizer",
            description="Iteratively optimizes LLM prompts using LangSmith evals and error analysis",
            capabilities=[
                "prompt_optimization", "eval_management", "error_analysis",
                "experiment_tracking", "dataset_management"
            ],
            required_permissions=["langsmith.*", "memory.*", "web.search"],
            supported_modes=[ExecutionMode.SMART, ExecutionMode.AGENT],
            max_concurrent_tasks=1,
            priority=AgentPriority.NORMAL,
        ),
    }
