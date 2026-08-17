"""Sprint 9A — Frozen terminal domain types.

Every type is frozen (immutable) so the store can safely share snapshots
across threads.  Mutations go through reducers that return new instances.
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> float:
    return time.time()


# ── Enums ───────────────────────────────────────────────────────────────


class SessionStatus(enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_CONFIRM = "waiting_confirm"
    PAUSED = "paused"
    ERROR = "error"


class StepStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class LayoutMode(enum.Enum):
    MINIMAL = "minimal"
    NORMAL = "normal"
    FOCUS = "focus"
    PLAN = "plan"
    ACTIVITY = "activity"
    CODE = "code"
    MEMORY = "memory"
    AUDIT = "audit"


class RiskLevel(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Core domain types ───────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolRun:
    id: str = field(default_factory=_uuid)
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: str = ""
    error: str = ""
    started_at: float = field(default_factory=_now)
    finished_at: float | None = None
    duration_ms: float = 0.0


@dataclass(frozen=True)
class PlanStep:
    id: str = field(default_factory=_uuid)
    description: str = ""
    status: StepStatus = StepStatus.PENDING
    tool_runs: tuple[ToolRun, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class Plan:
    goal: str = ""
    steps: tuple[PlanStep, ...] = ()
    created_at: float = field(default_factory=_now)


@dataclass(frozen=True)
class Message:
    id: str = field(default_factory=_uuid)
    role: str = "user"
    content: str = ""
    timestamp: float = field(default_factory=_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfirmationRequest:
    id: str = field(default_factory=_uuid)
    tool_name: str = ""
    description: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    created_at: float = field(default_factory=_now)


@dataclass(frozen=True)
class CodeFile:
    path: str = ""
    language: str = ""
    content: str = ""
    diff: str = ""


@dataclass(frozen=True)
class MemoryHit:
    source: str = ""
    content: str = ""
    score: float = 0.0


@dataclass(frozen=True)
class ActivityEvent:
    id: str = field(default_factory=_uuid)
    name: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=_now)
    provider: str = ""
    model: str = ""


# ── Top-level session state ─────────────────────────────────────────────


@dataclass(frozen=True)
class SessionState:
    """Immutable snapshot of the entire terminal state.

    Every mutation creates a new SessionState via a reducer.
    """
    status: SessionStatus = SessionStatus.IDLE
    layout: LayoutMode = LayoutMode.NORMAL
    model: str = ""
    provider: str = ""
    tokens_prompt: int = 0
    tokens_completion: int = 0
    latency_ms: float = 0.0
    plan: Plan = field(default_factory=Plan)
    messages: tuple[Message, ...] = ()
    activity: tuple[ActivityEvent, ...] = ()
    code_files: tuple[CodeFile, ...] = ()
    memory_hits: tuple[MemoryHit, ...] = ()
    pending_confirmation: ConfirmationRequest | None = None
    error: str = ""
    input_buffer: str = ""
    cursor_pos: int = 0
    history_index: int = -1
    session_id: str = field(default_factory=_uuid)
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
