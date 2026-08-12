"""Shared data models for API v1 — stable contracts, not tied to internal types."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryItem:
    key: str
    value: str
    tags: list[str] = field(default_factory=list)
    source: str = ""
    timestamp: float = 0.0
    ttl: float | None = None


@dataclass
class EventRecord:
    name: str
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    trace_id: str = ""


@dataclass
class CapabilityInfo:
    name: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    risk: str = "safe"


@dataclass
class PermissionRequest:
    capability: str
    user_input: str = ""
    source: str = ""
    trace_id: str = ""


@dataclass
class PermissionDecision:
    approved: bool
    reason: str = ""
    handler: str | None = None
