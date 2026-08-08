"""Event name constants shared across the agent runtime and audit stack.

Use these constants everywhere instead of scattered string literals so the
event contract stays in a single place.
"""

REQUEST_RECEIVED = "request.received"
AGENT_REASONING_STARTED = "agent.reasoning.started"
TOOL_REQUESTED = "tool.requested"
PERMISSION_CHECKED = "permission.checked"
TOOL_EXECUTED = "tool.executed"
TOOL_FAILED = "tool.failed"
TASK_COMPLETED = "task.completed"
TASK_FAILED = "task.failed"

# TaskObserver timeline events (core/agent/observer.py)
TASK_STARTED = "task.started"
TASK_FINISHED = "task.finished"
TASK_CANCELLED = "task.cancelled"
STEP_STARTED = "step.started"
STEP_COMPLETED = "step.completed"
STEP_FAILED = "step.failed"
PERMISSION_OBSERVED = "permission.observed"
