"""Tests for skill-declared verification checklists.

Skills can advertise a post-execution checklist in their manifest
(``verification``). When a skill is activated via ``skills.load`` the agent
loop folds that checklist into the same verification gate used by the harness
(no parallel path). Covers manifest parsing, the skills.load metadata bridge,
AgentState activation tracking, and the loop merge helper.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skills.registry import (  # noqa: E402
    SkillRegistry,
    _parse_verification,
)


def _write(dir_path: Path, filename: str, payload: dict) -> None:
    (dir_path / filename).write_text(json.dumps(payload), encoding="utf-8")


def test_parse_verification_variants():
    assert _parse_verification(["pytest -q"]) == [("pytest", "pytest -q")]
    assert _parse_verification([{"name": "lint", "command": "ruff check ."}]) == [
        ("lint", "ruff check .")
    ]
    assert _parse_verification([["types", "mypy ."]]) == [("types", "mypy .")]
    assert _parse_verification([{"name": "no-command"}]) == []
    assert _parse_verification(None) == []
    assert _parse_verification({"command": "echo hi"}) == [("echo", "echo hi")]


def test_registry_parses_verification(tmp_path):
    _write(tmp_path, "a.json", {
        "name": "alpha",
        "description": "a",
        "verification": [
            {"name": "unit", "command": "pytest -q"},
            "ruff check .",
        ],
    })
    reg = SkillRegistry(manifests_dir=tmp_path)
    skills = reg.discover_and_load()
    assert skills["alpha"].verification_steps() == [
        ("unit", "pytest -q"),
        ("ruff", "ruff check ."),
    ]


def test_registry_no_verification_is_empty(tmp_path):
    _write(tmp_path, "b.json", {"name": "beta", "description": "b"})
    reg = SkillRegistry(manifests_dir=tmp_path)
    skills = reg.discover_and_load()
    assert skills["beta"].verification_steps() == []


def test_skills_load_exposes_verification_metadata(tmp_path):
    _write(tmp_path, "c.json", {
        "name": "gamma",
        "description": "g",
        "verification": [{"name": "check", "command": "true"}],
    })
    reg = SkillRegistry(manifests_dir=tmp_path)
    reg.discover_and_load()

    import tools.skills_tools as skills_tools
    from skills import registry as reg_mod

    orig_cache = getattr(reg_mod.build_default_skill_registry, "_cache", None)
    reg_mod.build_default_skill_registry._cache = reg.skills
    try:
        result = asyncio.run(skills_tools.skills_load({"name": "gamma"}))
    finally:
        reg_mod.build_default_skill_registry._cache = orig_cache

    assert result.success
    assert result.metadata["skill"] == "gamma"
    assert result.metadata["verification_steps"] == [["check", "true"]]


def test_agent_state_tracks_active_skills():
    from core.agent.state import AgentState

    state = AgentState(task_id="t", goal="g")
    state.record_tool("skills.load", "1", True, 1.0, metadata={"skill": "webapp_testing"})
    state.record_tool("skills.load", "2", True, 1.0, metadata={"skill": "webapp_testing"})
    state.record_tool("skills.load", "3", True, 1.0, metadata={"skill": "other"})
    state.record_tool("shell.execute", "4", True, 1.0, metadata={})

    assert state.active_skills == ["webapp_testing", "other"]
    assert state.to_dict()["active_skills"] == ["webapp_testing", "other"]


def test_loop_merges_active_skill_steps():
    from core.agent.loop import AgentLoop
    from core.agent.verification import VerificationEngine, VerificationStep

    class _State:
        active_skills = ["webapp_testing"]

    engine = VerificationEngine()
    engine.add_step(VerificationStep(name="python-import", command="x"))
    AgentLoop._add_skill_verification(None, _State(), engine, VerificationStep)

    assert [s.name for s in engine._steps] == ["python-import"]


def test_loop_merge_adds_unknown_skill_step():
    from core.agent.loop import AgentLoop
    from core.agent.verification import VerificationEngine, VerificationStep

    class _State:
        active_skills = ["webapp_testing"]

    engine = VerificationEngine()
    AgentLoop._add_skill_verification(None, _State(), engine, VerificationStep)

    names = [s.name for s in engine._steps]
    assert "python-import" in names


def test_loop_merge_ignores_unknown_and_none():
    from core.agent.loop import AgentLoop
    from core.agent.verification import VerificationEngine, VerificationStep

    class _State:
        active_skills = ["does_not_exist"]

    engine = VerificationEngine()
    AgentLoop._add_skill_verification(None, _State(), engine, VerificationStep)
    assert engine._steps == []

    AgentLoop._add_skill_verification(None, None, engine, VerificationStep)
    assert engine._steps == []


def test_parse_skill_frontmatter():
    from skills.registry import parse_skill_frontmatter

    meta, body = parse_skill_frontmatter(
        "---\nname: my-skill\ntags: [a, b]\n---\n\n# Body\n"
    )
    assert meta["name"] == "my-skill"
    assert meta["tags"] == ["a", "b"]
    assert body.strip() == "# Body"

    meta, body = parse_skill_frontmatter("no frontmatter here")
    assert meta == {}
    assert body == "no frontmatter here"


def test_registry_discovers_skill_md(tmp_path):
    skills_root = tmp_path / "skills"
    d = skills_root / "my-awesome-skill"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: my-awesome-skill\n"
        "description: does awesome things\n"
        "tags: [x, y]\n"
        "tools: [shell.execute]\n"
        "verification:\n  - name: check\n    command: \"true\"\n"
        "---\n\n# Steps\nDo the thing.\n",
        encoding="utf-8",
    )

    reg = SkillRegistry(manifests_dir=tmp_path / "none", skills_dir=skills_root)
    skills = reg.discover_and_load()

    skill = skills["my_awesome_skill"]
    assert skill.description == "does awesome things"
    assert skill.tags == ["x", "y"]
    assert skill.tools == ["shell.execute"]
    assert skill.verification_steps() == [("check", "true")]
    assert "# Steps" in skill.load_instructions()
    assert "---" not in skill.load_instructions().splitlines()[0]


def test_manifest_wins_over_skill_md(tmp_path):
    manifests = tmp_path / "m"
    manifests.mkdir()
    (manifests / "a.json").write_text(
        json.dumps({"name": "code_review", "description": "from manifest"}),
        encoding="utf-8",
    )
    skills_root = tmp_path / "s"
    d = skills_root / "code-review"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: code-review\ndescription: from skill md\n---\nBody\n",
        encoding="utf-8",
    )

    reg = SkillRegistry(manifests_dir=manifests, skills_dir=skills_root)
    skills = reg.discover_and_load()

    assert skills["code_review"].description == "from manifest"


def test_skills_dir_empty_disables_discovery(tmp_path):
    reg = SkillRegistry(manifests_dir=tmp_path, skills_dir="")
    assert reg.skills_dir is None
    assert reg.discover_and_load() == {}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
