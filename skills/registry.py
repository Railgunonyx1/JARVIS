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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.utils import get_project_root

logger = logging.getLogger("jarvis.skills")

_MANIFESTS_DIR = get_project_root() / "skills" / "manifests"
_SKILLS_DIR = get_project_root() / ".agents" / "skills"

_CORE_KEYS = ("name", "description", "tools", "tags", "version")


def _parse_verification(raw: Any) -> list[tuple[str, str]]:
    """Normalize a manifest ``verification`` block into (name, command) tuples.

    Accepts a list of command strings, ``{"name", "command"}`` objects, or
    ``[name, command]`` pairs. Steps without a command are skipped.
    """
    steps: list[tuple[str, str]] = []
    if not raw:
        return steps
    if isinstance(raw, (str, dict)):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return steps
    for item in raw:
        if isinstance(item, str):
            cmd = item.strip()
            if cmd:
                steps.append((cmd.split()[0], cmd))
        elif isinstance(item, dict):
            cmd = str(item.get("command") or "").strip()
            if cmd:
                steps.append((str(item.get("name") or cmd.split()[0]), cmd))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            name, cmd = str(item[0]).strip(), str(item[1]).strip()
            if cmd:
                steps.append((name or cmd.split()[0], cmd))
    return steps


_FM = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", re.DOTALL)


def parse_skill_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ``SKILL.md`` YAML frontmatter from its markdown body.

    Tolerant: missing/bad frontmatter yields ``({}, text)``. Uses PyYAML when
    available and falls back to a minimal ``key: value`` line parser.
    """
    m = _FM.match(text)
    if not m:
        return {}, text
    raw, body = m.group(1), text[m.end():]
    meta: dict[str, Any] = {}
    try:
        import yaml  # optional; the repo already depends on it
        data = yaml.safe_load(raw)
        if isinstance(data, dict):
            meta = {str(k): v for k, v in data.items() if v is not None}
    except Exception:
        for line in raw.splitlines():
            if ":" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
    return meta, body


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
    verification: list[tuple[str, str]] = field(default_factory=list)
    metadata: SkillMetadata = field(default_factory=SkillMetadata)


@dataclass
class Skill:
    """One discovered skill (metadata + contract)."""

    name: str
    description: str
    instructions_path: str = ""
    instructions_text: str = ""
    contracts: dict[str, SkillContract] = field(default_factory=lambda: {})
    enabled: bool = True

    def load_instructions(self) -> str:
        """Load this skill's full instructions (progressive disclosure).

        Returns the markdown body, or "" when the skill ships none.
        """
        if self.instructions_text:
            return self.instructions_text
        if not self.instructions_path:
            return ""
        path = get_project_root() / self.instructions_path
        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Cannot load instructions for %s: %s", self.name, e)
            return ""

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

    def verification_steps(self) -> list[tuple[str, str]]:
        """Declared post-execution verification checklists as (name, command)."""
        seen: list[tuple[str, str]] = []
        for contract in self.contracts.values():
            for step in contract.verification:
                if step not in seen:
                    seen.append(step)
        return seen


def _norm(name: str) -> str:
    """Folder/skill name -> manifest key (same convention as the importer)."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def _coerce_list(value: Any) -> list[str]:
    """Normalize a frontmatter value into a list[str] (lists, CSV, ``[a,b]``)."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [part.strip() for part in text.split(",") if part.strip()]


class SkillRegistry:
    """Discovers and loads skill manifests from ``skills/manifests``."""

    def __init__(self, manifests_dir: str | Path | None = None,
                 skills_dir: str | Path | None = None) -> None:
        self.manifests_dir: Path = (
            Path(manifests_dir)
            if manifests_dir is not None
            else _MANIFESTS_DIR
        )
        if skills_dir is None:
            # Explicit manifests_dir => isolated registry (tests); only the
            # default registry also discovers native SKILL.md skills.
            skills_dir = _SKILLS_DIR if manifests_dir is None else ""
        self.skills_dir: Path | None = Path(skills_dir) if skills_dir else None
        self.skills: dict[str, Skill] = {}

    def discover_and_load(self) -> dict[str, Skill]:
        """Load JSON manifests, then any native ``*/SKILL.md`` skills.

        Manifests win on name collisions (``SKILL.md`` files are skipped when
        a manifest already registered that name), preserving import order.
        """
        if self.manifests_dir.is_dir():
            for path in sorted(self.manifests_dir.glob("*.json")):
                data = self._read_manifest(path)
                if data is None:
                    continue
                self._current_manifest = path.name
                self._register(data)
            self._current_manifest = None
        self._load_skill_md_files()
        return self.skills

    def _load_skill_md_files(self) -> None:
        """Register skills authored as ``<dir>/SKILL.md`` with YAML frontmatter."""
        if self.skills_dir is None or not self.skills_dir.is_dir():
            return
        for path in sorted(self.skills_dir.glob("*/SKILL.md")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                logger.warning("Skipping unreadable skill file %s: %s", path, e)
                continue
            meta, body = parse_skill_frontmatter(text)
            name = _norm(str(meta.get("name") or path.parent.name))
            if not name:
                continue
            if name in self.skills:
                logger.debug(
                    "SKILL.md %s duplicates skill %r; keeping existing", path, name
                )
                continue
            self._current_manifest = str(path)
            self._register_skill_md(name, meta, body)
            self._current_manifest = None

    def _register_skill_md(self, name: str, meta: dict[str, Any], body: str) -> None:
        description = str(meta.get("description") or "").strip()
        if not description:
            for line in body.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    description = stripped
                    break
        metadata = SkillMetadata(
            name=name,
            description=description,
            tags=_coerce_list(meta.get("tags")),
            version=str(meta.get("version", "1.0.0")),
        )
        try:
            timeout = int(meta.get("timeout", 90) or 90)
        except (TypeError, ValueError):
            timeout = 90
        contract = SkillContract(
            tools=_coerce_list(meta.get("tools")),
            risk=str(meta.get("risk", "medium")),
            timeout=timeout,
            preferred_models=_coerce_list(meta.get("preferred_models")),
            verification=_parse_verification(meta.get("verification")),
            metadata=metadata,
        )
        skill = Skill(name=name, description=description, instructions_text=body)
        skill.contracts["default"] = contract
        self.skills[name] = skill

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
            verification=_parse_verification(data.get("verification")),
            metadata=metadata,
        )

        skill = self.skills.get(name)
        if skill is not None:
            # Two manifests declaring the same skill name is a packaging
            # error (e.g. a native git_workflow.json and a pack copy
            # soc_git_workflow.json): the later file used to silently
            # replace the earlier contract. Keep the first (sorted order =
            # native packs before prefixed packs) and say so.
            logger.warning(
                "Duplicate skill name %r in %s; keeping earlier registration",
                name,
                getattr(self, "_current_manifest", "?"),
            )
            return
        skill = Skill(name=name, description=metadata.description)
        self.skills[name] = skill
        skill.contracts["default"] = contract
        if data.get("instructions"):
            skill.instructions_path = str(data["instructions"])

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


def list_all_skills() -> dict[str, Skill]:
    """Convenience: return the name -> Skill map for all loaded skills."""
    return build_default_skill_registry()


def list_skills() -> list[str]:
    """Convenience: return the sorted names of all loaded skills."""
    return sorted(build_default_skill_registry().keys())


def get_skill(name: str) -> Skill | None:
    """Convenience: fetch one skill by name, or None."""
    return build_default_skill_registry().get(name)


__all__ = [
    "SkillContract",
    "SkillMetadata",
    "SkillRegistry",
    "Skill",
    "build_default_skill_registry",
    "reset_skill_registry_cache",
    "get_skill",
    "list_all_skills",
    "list_skills",
    "parse_skill_frontmatter",
]
