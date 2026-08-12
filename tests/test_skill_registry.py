"""Tests for the skill registry index and its on-disk hot reload."""

import json
import time

import pytest

from core.skill_loader import SkillLoader
from core.skill_registry import SkillRegistry


def write_manifest(path, name, version="1.0.0", description="test skill",
                   capabilities=None):
    path.write_text(
        json.dumps(
            {
                "name": name,
                "version": version,
                "description": description,
                "capabilities": capabilities or ["process.start"],
                "permissions": [],
                "supported_modes": ["smart", "agent"],
                "entry_point": "actions.test:run",
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def registry(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    write_manifest(skills_dir / "alpha.json", "Alpha")
    return SkillRegistry(loader=SkillLoader(skills_dir))


def test_build_record_floors_risk_by_capability(registry):
    record = registry.get("Alpha")
    assert record is not None
    assert record.name == "Alpha"
    assert record.version == "1.0.0"
    assert record.max_risk == "medium"
    assert record.capabilities == ["process.start"]
    assert record.supported_modes == ["smart", "agent"]


def test_search_ranks_and_filters(registry):
    assert [r.name for r in registry.search()] == ["Alpha"]
    assert [r.name for r in registry.search("alpha")] == ["Alpha"]
    assert [r.name for r in registry.search("matching nothing")] == []
    assert [r.name for r in registry.search(mode="smart")] == ["Alpha"]
    assert [r.name for r in registry.search(mode="plan")] == []
    assert [r.name for r in registry.search(max_risk="low")] == []
    assert [r.name for r in registry.search(max_risk="medium")] == ["Alpha"]


def test_record_to_dict_exposes_detail_fields(registry):
    data = registry.get("Alpha").to_dict()
    assert data["description"] == "test skill"
    assert data["entry_point"] == "actions.test:run"
    assert data["permissions"] == []


def _force_refresh(registry):
    registry._last_check_ns = 0


def test_hot_reload_picks_up_edit(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    write_manifest(skills_dir / "alpha.json", "Alpha", version="1.0.0")
    registry = SkillRegistry(loader=SkillLoader(skills_dir))
    assert registry.get("Alpha").version == "1.0.0"

    write_manifest(skills_dir / "alpha.json", "Alpha", version="2.1.0")
    _force_refresh(registry)
    assert registry.get("Alpha").version == "2.1.0"
    assert registry.count() == 1


def test_hot_reload_picks_up_add_and_delete(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    write_manifest(skills_dir / "alpha.json", "Alpha")
    registry = SkillRegistry(loader=SkillLoader(skills_dir))
    assert registry.count() == 1

    write_manifest(skills_dir / "beta.json", "Beta")
    _force_refresh(registry)
    assert registry.count() == 2
    assert [r.name for r in registry.search()] == ["Alpha", "Beta"]

    (skills_dir / "beta.json").unlink()
    _force_refresh(registry)
    assert registry.count() == 1
    assert registry.get("Beta") is None


def test_refresh_is_throttled(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    write_manifest(skills_dir / "alpha.json", "Alpha")
    registry = SkillRegistry(loader=SkillLoader(skills_dir))
    write_manifest(skills_dir / "beta.json", "Beta")
    registry._last_check_ns = time.monotonic_ns()

    registry._refresh_if_changed()
    assert registry.count() == 1

    time.sleep(2.1)
    registry._refresh_if_changed()
    assert registry.count() == 2
