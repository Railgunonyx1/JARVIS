"""J-Browser — skills transfer.

J-Browser carries JARVIS's full skill stack. The canonical ``skills/``
manifests are the source of truth; this module surfaces them as J-Browser
capabilities so the browser agent can advertise-then-load the same skills as
the terminal agent, plus a browser-specific skill index.

"Transfer" here is not a copy — J-Browser and the terminal share one skill
registry (one source of truth), which is exactly the convergence discipline
from Phase A. Browser automation is one skill among the inherited set.
"""

from __future__ import annotations

from dataclasses import dataclass

try:  # skills/registry is optional to keep the platform lean
    from skills.registry import SkillRegistry
    _HAS_REGISTRY = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_REGISTRY = False


@dataclass
class JbrowserCapability:
    """One skill surfaced inside the J-Browser context."""

    name: str
    description: str
    tags: list[str]
    is_browser: bool


_BROWSER_SKILL_NAMES = {
    "browser_automation", "web_research",
}


def _load_registry() -> SkillRegistry | None:
    if not _HAS_REGISTRY:
        return None
    try:
        registry = SkillRegistry()
        registry.discover_and_load()
        return registry
    except Exception:
        return None


def inherited_skills() -> list[JbrowserCapability]:
    """All JARVIS skills, surfaced intact inside J-Browser."""
    registry = _load_registry()
    if registry is None:
        return []
    out: list[JbrowserCapability] = []
    for name, skill in registry.skills.items():
        out.append(JbrowserCapability(
            name=name,
            description=getattr(skill, "description", "") or "",
            tags=list(getattr(skill, "tags", []) or []),
            is_browser=name in _BROWSER_SKILL_NAMES,
        ))
    out.sort(key=lambda c: c.name)
    return out


def browser_skills() -> list[JbrowserCapability]:
    """The subset of inherited skills relevant to browse/research tasks."""
    return [c for c in inherited_skills() if c.is_browser]


def skill_count() -> int:
    return len(inherited_skills())
