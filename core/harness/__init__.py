"""Harness abstraction -- model ≠ harness.

A harness controls HOW the agent reasons, plans, and uses tools.
The same model can behave very differently under different harnesses.

Architecture:
    User -> HarnessSelector -> Harness -> Planner -> Tools
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

# Canonical tool-name aliases so whitelists/blacklists work regardless of
# naming convention. Tool names are dotted-namespaced (e.g. shell.execute),
# but legacy/internal references may use underscore or bare forms. Every
# entry normalizes to the canonical dotted name used by the registry.
_TOOL_NAME_ALIASES: dict[str, str] = {
    "web_search": "web.search",
    "web_search_tool": "web.search",
    "web_fetch": "browser.open",
    "browser_fetch": "browser.open",
    "file_read": "filesystem.read",
    "read_file": "filesystem.read",
    "file_write": "filesystem.write",
    "write_file": "filesystem.write",
    "bash": "shell.execute",
    "shell": "shell.execute",
    "shell_cmd": "shell.execute",
    "shell.cmd": "shell.execute",
    "code_search": "search.code",
    "search_code": "search.code",
    "grep": "search.code",
    "list_files": "filesystem.list",
    "file_list": "filesystem.list",
}


def _canonical_tool_name(name: str) -> str:
    """Resolve a tool name to its canonical dotted form (identity if unknown)."""
    if not name:
        return name
    return _TOOL_NAME_ALIASES.get(name.strip(), name.strip())


class HarnessType(enum.Enum):
    NATIVE = "native"
    CODING = "coding"
    RESEARCH = "research"
    DEBUG = "debug"
    COMPUTER_USE = "computer_use"
    MINIMAL = "minimal"
    AUTO = "auto"


@dataclass(frozen=True)
class HarnessConfig:
    """Configuration for a specific harness."""
    harness_type: HarnessType
    system_prompt_addendum: str = ""
    max_iterations: int = 10
    max_tool_calls_per_step: int = 6
    temperature: float = 0.4
    enable_planning: bool = True
    enable_verification: bool = True
    tool_whitelist: tuple[str, ...] = ()  # empty = all tools
    tool_blacklist: tuple[str, ...] = ()
    model_preference: tuple[str, ...] = ()  # preferred model names
    description: str = ""
    verification_steps: tuple[tuple[str, str], ...] = ()  # (name, command) pairs


_HARNESS_PRESETS: dict[HarnessType, HarnessConfig] = {
    HarnessType.NATIVE: HarnessConfig(
        harness_type=HarnessType.NATIVE,
        description="Default JARVIS agent with full capabilities",
        max_iterations=15,
        max_tool_calls_per_step=6,
    ),
    HarnessType.CODING: HarnessConfig(
        harness_type=HarnessType.CODING,
        description="Optimized for code generation, refactoring, and review",
        max_iterations=20,
        max_tool_calls_per_step=8,
        tool_whitelist=(),
        tool_blacklist=(),
        model_preference=("coding",),
        system_prompt_addendum=(
            "\nYou are a coding-focused agent. Always inspect project conventions "
            "before changing code. Verify libraries exist instead of assuming them. "
            "Follow existing architecture and style. Use task tracking for complex work. "
            "Respect user confirmations for destructive operations."
        ),
    ),
    HarnessType.RESEARCH: HarnessConfig(
        harness_type=HarnessType.RESEARCH,
        description="Optimized for analysis, search, and information gathering",
        max_iterations=12,
        max_tool_calls_per_step=4,
        tool_whitelist=("web.search", "browser.open", "filesystem.read", "shell.execute", "search.code"),
        model_preference=("reasoning",),
        system_prompt_addendum=(
            "\nYou are a research-focused agent. Prioritize gathering information "
            "before making changes. Cite sources. Be thorough but concise."
        ),
    ),
    HarnessType.DEBUG: HarnessConfig(
        harness_type=HarnessType.DEBUG,
        description="Optimized for diagnosing and fixing bugs",
        max_iterations=15,
        max_tool_calls_per_step=6,
        model_preference=("reasoning", "coding"),
        system_prompt_addendum=(
            "\nYou are a debugging agent. Start by reproducing the issue. "
            "Read error messages carefully. Form hypotheses before making changes. "
            "Verify fixes with tests. Avoid unrelated changes."
        ),
    ),
    HarnessType.COMPUTER_USE: HarnessConfig(
        harness_type=HarnessType.COMPUTER_USE,
        description="For tasks requiring screen interaction, browser, or GUI",
        max_iterations=20,
        max_tool_calls_per_step=10,
        model_preference=("vision",),
    ),
    HarnessType.MINIMAL: HarnessConfig(
        harness_type=HarnessType.MINIMAL,
        description="Lightweight: direct answers, minimal tool use",
        max_iterations=3,
        max_tool_calls_per_step=2,
        enable_planning=False,
        enable_verification=False,
    ),
}


class Harness:
    """A harness wraps model execution with specific behavior policies."""

    def __init__(self, config: HarnessConfig | None = None):
        self._config = config or _HARNESS_PRESETS[HarnessType.NATIVE]

    @property
    def config(self) -> HarnessConfig:
        return self._config

    @property
    def type(self) -> HarnessType:
        return self._config.harness_type

    def build_system_prompt_addendum(self) -> str:
        return self._config.system_prompt_addendum

    def filter_tools(self, tools: list | None) -> list:
        """Filter tool list based on whitelist/blacklist.

        Matching is canonical-name aware: underscore and legacy spellings are
        normalized to dotted names before comparison, so a whitelist written
        against either convention still works (and a stale list never silently
        strips every tool). Malformed entries are skipped defensively.
        """
        if not tools:
            return list(tools) if tools is not None else []
        if not self._config.tool_whitelist and not self._config.tool_blacklist:
            return list(tools)
        whitelist = {_canonical_tool_name(n) for n in self._config.tool_whitelist}
        blacklist = {_canonical_tool_name(n) for n in self._config.tool_blacklist}
        filtered = []
        for t in tools:
            try:
                name = t.get("function", {}).get("name", "") if isinstance(t, dict) else ""
            except AttributeError:
                name = ""
            canonical = _canonical_tool_name(name)
            if blacklist and canonical in blacklist:
                continue
            if whitelist and canonical not in whitelist:
                continue
            filtered.append(t)
        return filtered


class HarnessSelector:
    """Selects the best harness for a given task or lets user choose."""

    def __init__(self) -> None:
        self._harnesses: dict[HarnessType, Harness] = {
            ht: Harness(config) for ht, config in _HARNESS_PRESETS.items()
        }
        self._active: Harness = self._harnesses[HarnessType.NATIVE]

    @property
    def active(self) -> Harness:
        return self._active

    def select(self, harness_type: HarnessType) -> Harness:
        try:
            self._active = self._harnesses[harness_type]
        except (KeyError, TypeError):
            self._active = self._harnesses[HarnessType.NATIVE]
        return self._active

    def auto_select(self, goal: str | None) -> Harness:
        """Heuristic: pick harness based on goal content."""
        if not goal:
            return self.select(HarnessType.NATIVE)
        goal_lower = goal.lower()
        if any(w in goal_lower for w in ("debug", "fix", "error", "bug", "crash")):
            return self.select(HarnessType.DEBUG)
        if any(w in goal_lower for w in ("search", "find", "research", "analyze", "compare")):
            return self.select(HarnessType.RESEARCH)
        if any(w in goal_lower for w in ("code", "implement", "refactor", "write", "add feature")):
            return self.select(HarnessType.CODING)
        if any(w in goal_lower for w in ("screen", "browser", "click", "screenshot")):
            return self.select(HarnessType.COMPUTER_USE)
        return self.select(HarnessType.NATIVE)

    def list_harnesses(self) -> list[dict[str, Any]]:
        return [
            {"type": ht.value, "description": h.config.description, "active": h is self._active}
            for ht, h in self._harnesses.items()
        ]
