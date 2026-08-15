"""
JARVIS MK-X view-model schemas.

Backend owns state and decisions.
Renderer only displays snapshots of these models.
Never put agent logic in the UI layer.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Execution modes (real policies, not cosmetic labels)
# ---------------------------------------------------------------------------

class Mode(str, Enum):
    AGENT = "AGENT"           # full autonomous execution
    PLAN = "PLAN"             # analyze + build/update plan only; no side effects
    CONTROLLED = "CONTROLLED" # ask before any consequential action
    SMART = "SMART"           # dynamically choose autonomy by risk + context


MODE_HELP = {
    Mode.AGENT: "Autonomous execution",
    Mode.PLAN: "Plan only — no side effects",
    Mode.CONTROLLED: "Confirm every consequential action",
    Mode.SMART: "Dynamic autonomy based on risk",
}


# ---------------------------------------------------------------------------
# Plan (stateful, owned by backend)
# ---------------------------------------------------------------------------

class StepStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    id: str
    description: str
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    related_event_ids: List[str] = field(default_factory=list)

    @staticmethod
    def new(description: str, status: StepStatus = StepStatus.PENDING) -> "PlanStep":
        return PlanStep(id=str(uuid.uuid4())[:8], description=description, status=status)


@dataclass
class Plan:
    id: str
    goal: str
    steps: List[PlanStep] = field(default_factory=list)
    revision: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @staticmethod
    def new(goal: str, step_descriptions: List[str]) -> "Plan":
        steps = [PlanStep.new(d) for d in step_descriptions]
        if steps:
            steps[0].status = StepStatus.ACTIVE
            steps[0].started_at = time.time()
        return Plan(id=str(uuid.uuid4())[:8], goal=goal, steps=steps)

    def advance(self, step_id: str, to: StepStatus) -> None:
        """Backend calls this. UI never mutates plan logic."""
        for s in self.steps:
            if s.id == step_id:
                s.status = to
                if to == StepStatus.ACTIVE:
                    s.started_at = time.time()
                elif to in (StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED):
                    s.completed_at = time.time()
                self.updated_at = time.time()
                self.revision += 1
                return


# ---------------------------------------------------------------------------
# Activity = live structured agent event stream
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    TOOL = "tool"
    PLANNER = "planner"
    SYSTEM = "system"
    MEMORY = "memory"
    SECURITY = "security"
    PROVIDER = "provider"


class EventStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"
    CANCELLED = "cancelled"


@dataclass
class AgentEvent:
    """
    Structured event. Activity panel renders a live stream of these.
    Not a free-form log line.
    """
    event_id: str
    timestamp: float
    type: EventType
    status: EventStatus
    tool: Optional[str] = None
    arguments: str = ""
    result: str = ""
    duration_s: Optional[float] = None
    parent_run_id: Optional[str] = None
    exit_code: Optional[int] = None
    expanded: bool = False
    full_output: str = ""

    @staticmethod
    def tool_start(tool: str, arguments: str = "", parent_run_id: Optional[str] = None) -> "AgentEvent":
        return AgentEvent(
            event_id=str(uuid.uuid4())[:8],
            timestamp=time.time(),
            type=EventType.TOOL,
            status=EventStatus.RUNNING,
            tool=tool,
            arguments=arguments,
            parent_run_id=parent_run_id,
        )

    def complete(self, result: str = "", duration_s: Optional[float] = None, exit_code: Optional[int] = None) -> None:
        self.status = EventStatus.COMPLETED
        self.result = result
        self.duration_s = duration_s
        self.exit_code = exit_code

    def fail(self, result: str = "", duration_s: Optional[float] = None, exit_code: Optional[int] = None) -> None:
        self.status = EventStatus.FAILED
        self.result = result
        self.duration_s = duration_s
        self.exit_code = exit_code


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------

@dataclass
class Message:
    role: str  # user | agent | system
    content: str
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Security confirmation (policy-backed, never bare y/N only)
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class ConfirmationRequest:
    operation: str
    risk: RiskLevel
    scope: str
    reversible: bool
    details: str = ""
    # UI options: once / this-run / deny
    # Decision is returned to the security/policy layer, not decided by UI.


# ---------------------------------------------------------------------------
# Code / Memory / Audit view models (workspaces)
# ---------------------------------------------------------------------------

@dataclass
class CodeFile:
    path: str
    modified: bool = False
    selected: bool = False


@dataclass
class MemoryHit:
    score: float
    title: str
    date: str
    snippet: str = ""


@dataclass
class AuditSection:
    title: str
    items: List[tuple]  # (status_symbol_key, label, detail)


# ---------------------------------------------------------------------------
# Top-level AppState — pure snapshot for the renderer
# ---------------------------------------------------------------------------

@dataclass
class AppState:
    mode: Mode = Mode.AGENT
    model: str = "—"
    tokens_used: int = 0
    tokens_limit: int = 32000
    tools_active: int = 0
    memory_enabled: bool = False
    connection: str = "ONLINE"

    plan: Optional[Plan] = None
    messages: List[Message] = field(default_factory=list)
    events: List[AgentEvent] = field(default_factory=list)  # Activity stream

    # Workspaces
    workspace: str = "chat"  # chat | plan | code | activity | memory | audit
    code_files: List[CodeFile] = field(default_factory=list)
    code_path: str = ""
    code_content: str = ""
    code_language: str = "python"
    code_loc: int = 0
    code_modified: bool = False

    memory_query: str = ""
    memory_hits: List[MemoryHit] = field(default_factory=list)

    audit_sections: List[AuditSection] = field(default_factory=list)

    pending_confirmation: Optional[ConfirmationRequest] = None
    status_message: str = ""
