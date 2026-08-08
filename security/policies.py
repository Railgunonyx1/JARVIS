"""
Security Policies — Permission rules and policy definitions for JARVIS MK-X.

Defines permission levels, policy rules, and enforcement logic.
Policies are loaded from TOML config files and can be hot-reloaded.
"""

from __future__ import annotations

import re
import json
import logging
import threading
from enum import IntEnum
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("jarvis.security.policies")


class PermissionLevel(IntEnum):
    """Permission levels from most restrictive to least."""
    DENIED = 0
    READ_ONLY = 1
    SAFE = 2
    MODERATE = 3
    ELEVATED = 4
    ADMIN = 5
    UNRESTRICTED = 6


@dataclass
class PolicyRule:
    """A single permission rule."""
    name: str
    pattern: str  # Regex pattern matching tool/capability names
    level: PermissionLevel
    requires_confirmation: bool = False
    max_frequency: int = 0  # 0 = unlimited
    description: str = ""
    _compiled: Optional[re.Pattern] = field(default=None, repr=False)

    def matches(self, tool_name: str) -> bool:
        if self._compiled is None:
            self._compiled = re.compile(self.pattern, re.IGNORECASE)
        return bool(self._compiled.match(tool_name))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "pattern": self.pattern,
            "level": self.level.value,
            "requires_confirmation": self.requires_confirmation,
            "max_frequency": self.max_frequency,
        }


@dataclass
class Policy:
    """A complete security policy (maps to an execution mode)."""
    name: str
    level: PermissionLevel
    rules: List[PolicyRule] = field(default_factory=list)
    default_level: PermissionLevel = PermissionLevel.SAFE
    sandbox_enabled: bool = False
    audit_enabled: bool = True
    max_concurrent_actions: int = 5
    timeout_seconds: int = 300
    metadata: Dict[str, Any] = field(default_factory=dict)

    def check_permission(self, tool_name: str) -> tuple[PermissionLevel, PolicyRule | None]:
        """Check if a tool is allowed. Returns (level, matching_rule)."""
        for rule in self.rules:
            if rule.matches(tool_name):
                return rule.level, rule
        return self.default_level, None

    def is_allowed(self, tool_name: str, required_level: PermissionLevel = PermissionLevel.SAFE) -> bool:
        """Check if a tool meets the required permission level."""
        level, _ = self.check_permission(tool_name)
        return level >= required_level

    def get_confirmation_rules(self, tool_name: str) -> PolicyRule | None:
        """Get the rule that requires confirmation for a tool."""
        level, rule = self.check_permission(tool_name)
        if rule and rule.requires_confirmation:
            return rule
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "level": self.level.value,
            "rules": [r.to_dict() for r in self.rules],
            "default_level": self.default_level.value,
            "sandbox_enabled": self.sandbox_enabled,
            "audit_enabled": self.audit_enabled,
        }


def build_controlled_policy() -> Policy:
    """Build the Controlled mode policy — maximum safety."""
    return Policy(
        name="controlled",
        level=PermissionLevel.SAFE,
        default_level=PermissionLevel.READ_ONLY,
        sandbox_enabled=False,
        audit_enabled=True,
        max_concurrent_actions=3,
        rules=[
            PolicyRule("time_query", r"^query\.(time|date)$", PermissionLevel.READ_ONLY),
            PolicyRule("greeting", r"^meta\.(greet|thanks|goodbye)$", PermissionLevel.READ_ONLY),
            PolicyRule("system_status", r"^query\.status$", PermissionLevel.READ_ONLY),
            PolicyRule("web_search", r"^action\.search$", PermissionLevel.SAFE, requires_confirmation=True),
            PolicyRule("open_app", r"^action\.open$", PermissionLevel.SAFE, requires_confirmation=True),
            PolicyRule("desktop_control", r"^action\.desktop_control$", PermissionLevel.SAFE, requires_confirmation=True),
            PolicyRule("clipboard_read", r"^action\.clipboard\.read$", PermissionLevel.READ_ONLY),
            PolicyRule("screen_analyzer", r"^action\.screen_analyzer$", PermissionLevel.SAFE),
        ],
    )


def build_smart_policy() -> Policy:
    """Build the Smart mode policy — balanced safety and capability."""
    controlled = build_controlled_policy()
    controlled.name = "smart"
    controlled.level = PermissionLevel.MODERATE
    controlled.default_level = PermissionLevel.SAFE
    controlled.max_concurrent_actions = 5
    controlled.rules.extend([
        PolicyRule("file_read", r"^action\.file\.read$", PermissionLevel.SAFE),
        PolicyRule("file_write", r"^action\.file\.(write|create|delete|move|copy)$", PermissionLevel.MODERATE, requires_confirmation=True),
        PolicyRule("shell_safe", r"^action\.shell\.run$", PermissionLevel.MODERATE, requires_confirmation=True),
        PolicyRule("process_list", r"^action\.process\.list$", PermissionLevel.READ_ONLY),
        PolicyRule("process_kill", r"^action\.process\.kill$", PermissionLevel.ELEVATED, requires_confirmation=True),
        PolicyRule("window_manage", r"^action\.window\.\w+$", PermissionLevel.SAFE),
        PolicyRule("memory_store", r"^memory\.\w+$", PermissionLevel.SAFE),
        PolicyRule("browser", r"^action\.browser$", PermissionLevel.SAFE),
        PolicyRule("vector_query", r"^memory\.vector_query$", PermissionLevel.READ_ONLY),
        PolicyRule("network_status", r"^action\.network\.status$", PermissionLevel.READ_ONLY),
        PolicyRule("disk_info", r"^action\.disk\.info$", PermissionLevel.READ_ONLY),
        PolicyRule("audio_devices", r"^action\.audio\.devices$", PermissionLevel.READ_ONLY),
        PolicyRule("fs_read", r"^filesystem\.(read|list)$", PermissionLevel.SAFE),
        PolicyRule("fs_write", r"^filesystem\.(write|delete|move|copy)$", PermissionLevel.MODERATE, requires_confirmation=True),
        PolicyRule("shell_exec", r"^shell\.execute$", PermissionLevel.MODERATE, requires_confirmation=True),
    ])
    return controlled


def build_agent_policy() -> Policy:
    """Build the Agent mode policy — maximum capability with guardrails."""
    smart = build_smart_policy()
    smart.name = "agent"
    smart.level = PermissionLevel.ADMIN
    smart.default_level = PermissionLevel.MODERATE
    smart.sandbox_enabled = True
    smart.max_concurrent_actions = 10
    # Agent mode runs core fs/shell tools elevated but without confirmation.
    # Replace smart's confirmation-gated copies (first-match wins).
    smart.rules[:] = [r for r in smart.rules if r.name not in ("fs_write", "shell_exec")]
    smart.rules.extend([
        PolicyRule("fs_write", r"^filesystem\.(write|delete|move|copy)$", PermissionLevel.ELEVATED),
        PolicyRule("shell_exec", r"^shell\.execute$", PermissionLevel.ELEVATED),
        PolicyRule("shell_full", r"^action\.shell\.\w+$", PermissionLevel.ELEVATED, requires_confirmation=True),
        PolicyRule("process_full", r"^action\.process\.\w+$", PermissionLevel.ELEVATED, requires_confirmation=True),
        PolicyRule("service_manage", r"^action\.service\.\w+$", PermissionLevel.ADMIN, requires_confirmation=True),
        PolicyRule("startup_manage", r"^action\.startup\.\w+$", PermissionLevel.ADMIN, requires_confirmation=True),
        PolicyRule("settings_manage", r"^action\.settings\.\w+$", PermissionLevel.ADMIN, requires_confirmation=True),
        PolicyRule("planner_execute", r"^planner\.execute$", PermissionLevel.ELEVATED),
        PolicyRule("file_full", r"^action\.file\.\w+$", PermissionLevel.ELEVATED, requires_confirmation=True),
        PolicyRule("network_manage", r"^action\.network\.\w+$", PermissionLevel.MODERATE, requires_confirmation=True),
        PolicyRule("input_control", r"^action\.input\.\w+$", PermissionLevel.MODERATE),
        PolicyRule("display_manage", r"^action\.display\.\w+$", PermissionLevel.MODERATE),
        PolicyRule("disk_manage", r"^action\.disk\.\w+$", PermissionLevel.MODERATE, requires_confirmation=True),
        PolicyRule("task_scheduler", r"^action\.tasks\.\w+$", PermissionLevel.MODERATE),
        PolicyRule("fs_read", r"^filesystem\.(read|list)$", PermissionLevel.MODERATE),
    ])
    return smart


# Global policy cache
_policies: Dict[str, Policy] = {}


def get_policy(name: str) -> Policy:
    """Get a cached policy by name."""
    if name not in _policies:
        builders = {
            "controlled": build_controlled_policy,
            "smart": build_smart_policy,
            "agent": build_agent_policy,
        }
        builder = builders.get(name)
        if builder:
            _policies[name] = builder()
        else:
            _policies[name] = build_smart_policy()
    return _policies[name]
