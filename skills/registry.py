"""JARVIS MK-X — Skill manifest registry.

Loads ``skills/manifests/*.json`` capability manifests into lightweight
dataclasses. Each manifest declares a named skill: a description the agent
can match against a task, the real tool names it draws on (from the live
``tools.build_default_registry`` catalog), and optional runtime contract
metadata (risk, timeout, preferred models).

Progressive disclosure: the registry only advertises lightweight metadata
(name/description/tags/risk); heavy per-skill instructions can be loaded on
demand via ``get``/``load``. This keeps the agent's context lean (see the
research notes in AGENTS.md — skills follow the same advertise-then-load
pattern as industry Agent Skills).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.utils import get_project_root

logger = logging.getLogger("jarvis.skills")

_MANIFESTS_DIR = get_project_root() / "skills" / "manifests"

_CORE_KEYS = ("name", "description", "tools", "tags", "version")


@dataclass
class SkillMetadata:
    """Parsed manifest front-matter (advertised metadata)."""

    name: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    version: str = ""


@dataclass
class SkillContract:
    """Runtime contract for a loaded skill (sandbox + routing limits)."""

    tools: list[str] = field(default_factory=list)
    risk: str = "medium"
    timeout: int = 90
    preferred_models: list[str] = field(default_factory=list)
    metadata: SkillMetadata = field(default_factory=SkillMetadata)


@dataclass
class Skill:
    """One discovered skill (metadata + contract)."""

    name: str
    description: str
    contracts: dict[str, SkillContract] = field(default_factory=lambda: {})
    enabled: bool = True

    @property
    def tags(self) -> list[str]:
        for contract in self.contracts.values():
            return contract.metadata.tags
        return []

    @property
    def risk(self) -> str:
        risks = {c.risk for c in self.contracts.values()}
        if "high" in risks:
            return "high"
        if "medium" in risks:
            return "medium"
        return "low"

    @property
    def tools(self) -> list[str]:
        seen: list[str] = []
        for contract in self.contracts.values():
            for tool in contract.tools:
                if tool not in seen:
                    seen.append(tool)
        return seen


class SkillRegistry:
    """Discovers and loads skill manifests from ``skills/manifests``."""

    def __init__(self, manifests_dir: str | Path | None = None) -> None:
        self.manifests_dir: Path = (
            Path(manifests_dir)
            if manifests_dir is not None
            else _MANIFESTS_DIR
        )
        self.skills: dict[str, Skill] = {}

    def discover_and_load(self) -> dict[str, Skill]:
        """Load every ``*.json`` manifest in ``manifests_dir``."""
        if not self.manifests_dir.is_dir():
            return {}
        for path in sorted(self.manifests_dir.glob("*.json")):
            data = self._read_manifest(path)
            if data is None:
                continue
            self._register(data)
        return self.skills

    def _read_manifest(self, path: Path) -> dict[str, Any] | None:
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Skipping malformed skill manifest %s: %s", path, e)
            return None
        if not isinstance(data, dict):
            logger.warning("Skipping non-object manifest %s", path)
            return None
        name = data.get("name") or path.stem
        if not data.get("description"):
            logger.debug("Manifest %s has no description; still registering", path)
        return data

    def _register(self, data: dict[str, Any]) -> None:
        name = str(data.get("name") or "")
        if not name:
            return

        metadata = SkillMetadata(
            name=name,
            description=str(data.get("description", "")),
            tags=[str(t) for t in data.get("tags", [])],
            version=str(data.get("version", "1.0.0")),
        )
        contract = SkillContract(
            tools=[str(t) for t in data.get("tools", []) if t],
            risk=str(data.get("risk", "medium")),
            timeout=int(data.get("timeout", 90)),
            preferred_models=[str(m) for m in data.get("preferred_models", [])],
            metadata=metadata,
        )

        skill = self.skills.get(name)
        if skill is None:
            skill = Skill(name=name, description=metadata.description)
            self.skills[name] = skill
        skill.contracts["default"] = contract

    def get_skill(self, name: str) -> Skill | None:
        return self.skills.get(name)

    def source_files(self) -> int:
        if not self.manifests_dir.is_dir():
            return 0
        return len(list(self.manifests_dir.glob("*.json")))


def build_default_skill_registry() -> dict[str, Skill]:
    """Build and load the default skill registry once."""
    _cache = getattr(build_default_skill_registry, "_cache", None)
    if _cache is None:
        reg = SkillRegistry()
        reg.discover_and_load()
        _cache = reg.skills
        build_default_skill_registry._cache = _cache
    return dict(_cache)


def reset_skill_registry_cache() -> None:
    """Clear the module-level registry cache (for tests)."""
    build_default_skill_registry._cache = None


__all__ = [
    "SkillContract",
    "SkillMetadata",
    "SkillRegistry",
    "Skill",
    "build_default_skill_registry",
    "reset_skill_registry_cache",
]
