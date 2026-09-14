"""Skill tools — the agent-facing surface of the skill registry.

``skills.load``  — progressive disclosure: pull a named skill's full
                   instructions into the conversation on demand.
``skills.list``  — advertise what's available (name + one-line description).

The system prompt already advertises every skill in one line each
(see core/agent/context.py:_skills_block); these tools are the "load" half of
the advertise-then-load contract, so heavy instruction bodies never sit in
context unless a task actually needs them.
"""

from __future__ import annotations

import logging

from tools.schema import ToolResult, truncate

logger = logging.getLogger("jarvis.tools.skills")

_MAX_INSTRUCTION_CHARS = 12_000


async def skills_list(params: dict) -> ToolResult:
    """List every registered skill: name, description, tags, risk."""
    from skills.registry import build_default_skill_registry

    skills = build_default_skill_registry()
    if not skills:
        return ToolResult(success=True, output="No skills registered.")

    lines: list[str] = []
    for name, skill in sorted(skills.items()):
        tags = ",".join(getattr(skill, "tags", []) or [])
        risk = getattr(skill, "risk", "medium")
        has_docs = "docs" if getattr(skill, "instructions_path", "") else "no-docs"
        lines.append(f"{name} [{risk}, {has_docs}" + (f", tags: {tags}]" if tags else "]"))
        if skill.description:
            lines.append(f"  {skill.description}")
    return ToolResult(
        success=True,
        output="\n".join(lines),
        metadata={"count": len(skills)},
    )


async def skills_load(params: dict) -> ToolResult:
    """Load one skill's full instructions by name."""
    from skills.registry import get_skill

    name = str(params.get("name") or "").strip()
    if not name:
        return ToolResult(success=False, error="Parameter 'name' is required.")

    skill = get_skill(name)
    if skill is None:
        from skills.registry import list_skills
        available = ", ".join(list_skills())
        return ToolResult(
            success=False,
            error=f"Unknown skill '{name}'. Available: {available}",
        )

    body = skill.load_instructions()
    if not body:
        return ToolResult(
            success=True,
            output=(
                f"Skill '{name}' has no separate instruction file. "
                f"Guidance: {skill.description}"
            ),
            metadata={"name": name, "loaded": False},
        )

    return ToolResult(
        success=True,
        output=truncate(
            f"# Skill: {name}\n\n{body}", _MAX_INSTRUCTION_CHARS
        ),
        metadata={"name": name, "loaded": True, "chars": len(body)},
    )


__all__ = ["skills_list", "skills_load"]
