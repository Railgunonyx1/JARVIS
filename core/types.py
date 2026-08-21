"""Immutable event-sourced types for the JARVIS core.

Architecture contract:
    Event → State Store → pure reducers → immutable SessionState → Rich Renderer

SessionState is a frozen snapshot.  Reducers produce new instances; nobody
mutates in place.  The renderer is a pure function of SessionState.

All event-sourced types live here.  CLI view-models (cli/models.py) remain
separate — they are richer, mutable, and owned by the renderer.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskStatus(StrEnum):
    CREATED = "created"
    CLASSIFYING = "classifying"
    PLANNING = "planning"
    EXECUTING = "executing"
    OBSERVING = "observing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


class FailureClass(StrEnum):
    """Deterministic failure classification with explicit precedence."""
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    MALFORMED_TOOL = "malformed_tool"
    CONTEXT_OVERFLOW = "context_overflow"
    PROVIDER_FAILURE = "provider_failure"
    MODEL_FAILURE = "model_failure"
    TOOL_FAILURE = "tool_failure"


class StepStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VerificationStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


class Mode(StrEnum):
    AGENT = "agent"
    PLAN = "plan"
    CONTROLLED = "controlled"
    SMART = "smart"


# ---------------------------------------------------------------------------
# Frozen value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanStep:
    id: str
    description: str
    status: StepStatus = StepStatus.PENDING
    started_at: float | None = None
    completed_at: float | None = None
    related_event_ids: tuple[str, ...] = ()

    @staticmethod
    def new(description: str, status: StepStatus = StepStatus.PENDING) -> PlanStep:
        return PlanStep(id=str(uuid.uuid4())[:8], description=description, status=status)


@dataclass(frozen=True)
class Plan:
    id: str
    goal: str
    steps: tuple[PlanStep, ...] = ()
    revision: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @staticmethod
    def new(goal: str, step_descriptions: tuple[str, ...] = ()) -> Plan:
        steps: list[PlanStep] = []
        for i, desc in enumerate(step_descriptions):
            status = StepStatus.ACTIVE if i == 0 else StepStatus.PENDING
            steps.append(PlanStep.new(desc, status=status))
        return Plan(
            id=str(uuid.uuid4())[:8],
            goal=goal,
            steps=tuple(steps),
        )

    def with_step(self, step_id: str, status: StepStatus) -> Plan:
        """Return a new Plan with the given step updated.  Pure — no mutation."""
        new_steps = []
        for step in self.steps:
            if step.id == step_id:
                if status == StepStatus.ACTIVE:
                    step = PlanStep(
                        id=step.id, description=step.description, status=status,
                        started_at=time.time(), completed_at=None,
                        related_event_ids=step.related_event_ids,
                    )
                elif status in (StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED):
                    step = PlanStep(
                        id=step.id, description=step.description, status=status,
                        started_at=step.started_at, completed_at=time.time(),
                        related_event_ids=step.related_event_ids,
                    )
                else:
                    step = PlanStep(
                        id=step.id, description=step.description, status=status,
                        started_at=step.started_at, completed_at=step.completed_at,
                        related_event_ids=step.related_event_ids,
                    )
            new_steps.append(step)
        return Plan(
            id=self.id, goal=self.goal, steps=tuple(new_steps),
            revision=self.revision + 1,
            created_at=self.created_at, updated_at=time.time(),
        )


@dataclass(frozen=True)
class ToolCallRecord:
    """Immutable record of one tool invocation."""
    id: str
    name: str
    arguments: str = ""
    success: bool = True
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class VerificationStep:
    """One step in a verification gate."""
    name: str
    command: str = ""
    passed: bool = False
    running: bool = False
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    summary: str = ""
    error: str = ""
    duration_ms: float = 0.0


@dataclass(frozen=True)
class Message:
    """One conversation turn.  Immutable."""
    role: str  # "user" | "agent" | "system"
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ConfirmationRequest:
    """A permission request from the engine.  Policy decides; UI renders."""
    operation: str
    risk: RiskLevel = RiskLevel.MEDIUM
    scope: str = ""
    reversible: bool = True
    details: str = ""


# ---------------------------------------------------------------------------
# SessionState — the single immutable snapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionState:
    """Immutable snapshot of an agent session.  Produced by pure reducers.

    The renderer is a pure function of this type.  No field is ever mutated
    in place — reducers return a new SessionState.
    """

    # Identity
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    task_id: str = ""
    goal: str = ""

    # State machine
    status: TaskStatus = TaskStatus.CREATED
    failure_class: FailureClass | None = None

    # Configuration
    mode: Mode = Mode.AGENT
    model: str = ""
    provider: str = ""

    # Plan
    plan: Plan | None = None

    # Conversation
    messages: tuple[Message, ...] = ()

    # Tool execution
    tool_calls: tuple[ToolCallRecord, ...] = ()
    files_changed: tuple[str, ...] = ()
    iteration: int = 0

    # Verification
    verification_status: VerificationStatus = VerificationStatus.IDLE
    verification_steps: tuple[VerificationStep, ...] = ()

    # Recovery
    recovery_active: bool = False
    recovery_attempt: int = 0
    recovery_error: str = ""

    # Tokens / context
    tokens_used: int = 0
    tokens_limit: int = 32_000
    context_usage_pct: float = 0.0

    # Permissions
    pending_confirmation: ConfirmationRequest | None = None

    # Status
    status_message: str = ""
    connection: str = "online"

    # Timestamps
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Event log seq (monotonic, for replay ordering)
    seq: int = 0
