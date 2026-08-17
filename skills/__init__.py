"""Skill → Tool bridge for JARVIS MK-X.

Skills are named capabilities that map to one or more registered tools.
The skill registry provides discovery and validation; actual execution
always flows through the ToolRegistry.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.skills")


@dataclass(frozen=True)
class Skill:
    """A named capability backed by one or more tools."""
    name: str
    description: str
    tool_names: tuple[str, ...]  # references into ToolRegistry
    tags: tuple[str, ...] = ()
    version: str = "1.0.0"

    def requires_tools(self) -> list[str]:
        return list(self.tool_names)


class SkillRegistry:
    """Discovers and validates skills against the tool registry."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def register_many(self, skills: list[Skill]) -> None:
        for s in skills:
            self.register(s)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())

    def validate(self, tool_registry: Any) -> list[str]:
        """Return list of warnings for skills whose tools are not registered."""
        warnings = []
        registered = {t.name for t in tool_registry.list()}
        for skill in self._skills.values():
            for tn in skill.tool_names:
                if tn not in registered:
                    warnings.append(f"Skill '{skill.name}' requires unregistered tool '{tn}'")
        return warnings

    def load_manifests(self, directory: str | Path) -> int:
        """Load Skill objects from JSON manifest files in a directory.

        Manifest format:
            {"name": "...", "description": "...", "tools": ["tool.name", ...], "tags": [...]}
        """
        count = 0
        d = Path(directory)
        if not d.is_dir():
            return 0
        for f in sorted(d.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                skill = Skill(
                    name=data["name"],
                    description=data.get("description", ""),
                    tool_names=tuple(data.get("tools", [])),
                    tags=tuple(data.get("tags", [])),
                    version=data.get("version", "1.0.0"),
                )
                self.register(skill)
                count += 1
            except Exception as e:
                logger.warning("Failed to load skill manifest %s: %s", f.name, e)
        return count

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        return name in self._skills


def build_default_skill_registry(manifests_dir: str | Path | None = None) -> SkillRegistry:
    """Build the default skill registry.

    Ships with zero built-in skills. Skills are loaded from manifests at
    the given directory, or from the default location.
    """
    registry = SkillRegistry()
    if manifests_dir is None:
        manifests_dir = Path(__file__).parent / "manifests"
    count = registry.load_manifests(manifests_dir)
    if count:
        logger.info("Loaded %d skill manifests from %s", count, manifests_dir)
    return registry


__all__ = [
    "Skill",
    "SkillRegistry",
    "build_default_skill_registry",
]
