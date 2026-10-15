"""Regression tests for skills.registry duplicate-name handling.

Two manifests declaring the same skill name used to silently overwrite the
earlier contract (the soc pack's copy of git_workflow replaced the native
one). The registry now keeps the FIRST registration in sorted order and
logs a warning instead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skills.registry import SkillRegistry


def _write_manifest(dir_path: Path, filename: str, name: str, tools: list[str]) -> None:
    (dir_path / filename).write_text(
        json.dumps({"name": name, "description": f"{name} skill", "tools": tools,
                    "risk": "low", "version": "1.0.0"}),
        encoding="utf-8",
    )


def test_duplicate_name_keeps_first_registration(tmp_path, caplog):
    # Sorted order: aaa_native.json loads BEFORE zzz_pack.json. The pack's
    # copy must NOT replace the native contract.
    _write_manifest(tmp_path, "aaa_native.json", "git_workflow", ["git.status"])
    _write_manifest(tmp_path, "zzz_pack.json", "git_workflow",
                    ["git.rebase", "git.cherry_pick"])

    reg = SkillRegistry(manifests_dir=tmp_path)
    skills = reg.discover_and_load()

    assert skills["git_workflow"].tools == ["git.status"]
    assert any("Duplicate skill name" in r.message for r in caplog.records)


def test_unique_names_all_register(tmp_path):
    _write_manifest(tmp_path, "a.json", "skill_one", [])
    _write_manifest(tmp_path, "b.json", "skill_two", ["shell.execute"])

    reg = SkillRegistry(manifests_dir=tmp_path)
    skills = reg.discover_and_load()

    assert set(skills) == {"skill_one", "skill_two"}


def test_imported_agent_skills_are_valid():
    """The real manifests dir: every import is discoverable and loads."""
    from skills.registry import build_default_skill_registry

    skills = build_default_skill_registry()
    assert len(skills) >= 95  # 77 native + 22-23 agent imports + soc pack

    # Imports from ~/.agents/skills advertise under their bare names.
    for expected in ("brainstorming", "minimalist_ui", "systematic_debugging",
                     "optimize", "verification_before_completion"):
        assert expected in skills, f"missing imported skill {expected}"

    # Every declared instruction path resolves and is non-empty.
    for name, skill in skills.items():
        if skill.instructions_path:
            assert skill.load_instructions(), f"empty instructions for {name}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
