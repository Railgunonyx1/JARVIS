"""Shared data models for API v1 — stable contracts, not tied to internal types."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MemoryItem:
    key: str
    value: str
    tags: List[str] = field(default_factory=list)
    source: str = ""
    timestamp: float = 0.0
    ttl: Optional[float] = None


@dataclass
class EventRecord:
    name: str
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    trace_id: str = ""


@dataclass
class CapabilityInfo:
    name: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
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
    handler: Optional[str] = None
