"""Restrictive canonical-path gate (qwen-code #6923 pattern).

The gate canonicalizes every path-ish argument of filesystem / MCP-sourced
tools (symlinks followed, dangling links resolved, ``..`` normalized) and
denies anything whose canonical destination escapes the project root. The
matching is asymmetric: only the canonical destination is used for denial and
no raw spelling ever grants access.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agent import permissions as permissions_mod  # noqa: E402
from core.agent.permissions import PermissionEngine  # noqa: E402
from core.decision_logger import DecisionLogger  # noqa: E402
from tools.schema import Tool  # noqa: E402


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    monkeypatch.setattr(permissions_mod, "_project_root", lambda: root)
    return root


def _engine() -> PermissionEngine:
    return PermissionEngine(DecisionLogger(), mode="agent")


def _tool(name: str = "filesystem.write", permission: str = "filesystem.write",
          source: str = "") -> Tool:
    return Tool(
        name=name, description="x", parameters={},
        permission=permission, handler=lambda **_: {"ok": True},
        risk="safe", is_destructive=False, source=source,
    )


def test_relative_path_inside_root_is_allowed(root: Path):
    allowed, reason = _engine()._apply_path_gate(
        _tool(), {"path": "sub/new.txt"}, "t",
    )
    assert allowed is True
    assert reason == ""


def test_absolute_path_inside_root_is_allowed(root: Path):
    allowed, _ = _engine()._apply_path_gate(
        _tool(), {"path": str(root / "sub" / "new.txt")}, "t",
    )
    assert allowed is True


def test_dotdot_escape_is_denied(root: Path):
    allowed, reason = _engine()._apply_path_gate(
        _tool(), {"path": "../escape.txt"}, "t",
    )
    assert allowed is False
    assert "outside the project root" in reason


def test_symlink_to_outside_target_is_denied(root: Path):
    link = root / "innocent.txt"
    link.symlink_to(root.parent / "outside")
    allowed, reason = _engine()._apply_path_gate(
        _tool(), {"path": "innocent.txt"}, "t",
    )
    assert allowed is False
    assert "outside the project root" in reason


def test_dangling_symlink_to_outside_is_denied(root: Path):
    link = root / "dangling.txt"
    link.symlink_to(root.parent / "outside" / "gone.txt")
    allowed, reason = _engine()._apply_path_gate(
        _tool(), {"path": "dangling.txt"}, "t",
    )
    assert allowed is False
    assert "outside the project root" in reason


def test_symlinked_parent_escape_is_denied(root: Path):
    link = root / "portal"
    link.symlink_to(root.parent / "outside")
    allowed, reason = _engine()._apply_path_gate(
        _tool(), {"path": "portal/sub/file.txt"}, "t",
    )
    assert allowed is False
    assert "outside the project root" in reason


def test_non_filesystem_native_tool_is_not_gated(root: Path):
    allowed, _ = _engine()._apply_path_gate(
        _tool("web.search", permission="web.search"), {"path": "../escape"}, "t",
    )
    assert allowed is True


def test_mcp_tool_path_argument_is_gated(root: Path):
    tool = _tool("files.read", permission="mcp.call", source="mcp:filesystem")
    allowed, reason = _engine()._apply_path_gate(tool, {"path": "/etc/passwd"}, "t")
    assert allowed is False
    assert "outside the project root" in reason


def test_mcp_tool_url_arguments_are_skipped(root: Path):
    tool = _tool("fetch", permission="mcp.call", source="mcp:web")
    allowed, _ = _engine()._apply_path_gate(
        tool, {"source": "https://example.com/x", "target": "https://example.com/y"}, "t",
    )
    assert allowed is True


def test_blank_path_arguments_are_skipped(root: Path):
    allowed, _ = _engine()._apply_path_gate(_tool(), {"path": "  "}, "t")
    assert allowed is True


def test_full_check_denies_escaping_path_even_with_consent(root: Path):
    seen: list[tuple[str, dict]] = []

    def handler(name: str, args: dict) -> str:
        seen.append((name, args))
        return "once"

    engine = PermissionEngine(DecisionLogger(), mode="agent", confirmation_handler=handler)
    allowed, reason = asyncio.run(
        engine.check(_tool(), {"path": "../escape.txt"}, "t", "s"),
    )
    assert allowed is False
    assert "outside the project root" in reason
    assert seen == []  # the consent channel is never consulted for a path escape


def test_in_root_path_passes_full_check(root: Path):
    engine = PermissionEngine(DecisionLogger(), mode="agent")
    allowed, reason = asyncio.run(
        engine.check(_tool(), {"path": "sub/ok.txt"}, "t", "s"),
    )
    assert allowed is True
    assert reason == ""


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
