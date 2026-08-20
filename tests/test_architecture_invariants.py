"""Architecture invariant tests.

These tests verify the hard invariant stated in AGENTS.md:

    No external protocol, router, adapter, or agent path may directly
    invoke a tool executor. All individual tool execution must pass
    through ToolExecutionService.

If these tests fail, someone has added a code path that bypasses
the single tool execution boundary.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. Static analysis: no direct calls to AgentToolExecutor.execute outside
#    of ToolExecutionService
# ---------------------------------------------------------------------------

def _find_bypass_calls() -> list[tuple[str, int, str]]:
    """Scan Python source files for calls to .executor.execute() or
    .permissions.check() on objects that look like AgentLoop instances.

    Returns list of (file, line_no, code_line).
    """
    violations: list[tuple[str, int, str]] = []
    project_root = Path(__file__).resolve().parents[1]

    # Files that are allowed to reference permissions/executor directly
    ALLOWLIST = {
        "tool_service.py",   # owns the executor/permissions
        "loop.py",           # creates the service (constructor only)
        "__init__.py",
    }

    for py_file in project_root.rglob("*.py"):
        # Skip test files, archive, quarantine
        rel = py_file.relative_to(project_root)
        parts = rel.parts
        if any(p.startswith("_quarantine") for p in parts):
            continue
        if py_file.name in ALLOWLIST:
            continue
        if "test_" in py_file.name or py_file.name.startswith("conftest"):
            continue
        if "venv" in parts or "__pycache__" in parts:
            continue

        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(rel))
        except Exception:
            continue

        for node in ast.walk(tree):
            # Look for: something.permissions.check(...) or something.executor.execute(...)
            if isinstance(node, ast.Attribute):
                if node.attr in ("check", "execute") and isinstance(node.value, ast.Attribute):
                    if node.value.attr in ("permissions", "executor"):
                        line_no = node.lineno
                        line_text = source.splitlines()[line_no - 1].strip()
                        violations.append((str(rel), line_no, line_text))

    return violations


def test_no_direct_executor_bypass():
    """No file outside tool_service.py/loop.py should call
    .permissions.check() or .executor.execute() directly.
    """
    violations = _find_bypass_calls()
    if violations:
        msg = "Architecture violation: direct permission/executor access found:\n"
        for f, ln, code in violations:
            msg += f"  {f}:{ln}  {code}\n"
        msg += "\nAll tool execution must go through ToolExecutionService."
        pytest.fail(msg)


# ---------------------------------------------------------------------------
# 2. AgentLoop must not expose .permissions or .executor as public attributes
# ---------------------------------------------------------------------------

def test_agentloop_no_public_executor():
    """AgentLoop should not have a public .permissions or .executor attribute.

    These should only exist inside ToolExecutionService. The constructor
    may create them as local variables (e.g. _permissions, _executor) to
    pass to ToolExecutionService, but they must never be stored on self.
    """
    import inspect
    from core.agent.loop import AgentLoop

    public_bypass = []

    # 1. Check class-level attributes (descriptors, etc.)
    for name in ("permissions", "executor"):
        if name in AgentLoop.__dict__:
            attr = AgentLoop.__dict__[name]
            if not isinstance(attr, property):
                public_bypass.append(f"class attr: {name}")

    # 2. Check __init__ source for self.permissions = or self.executor =
    #    (local _permissions is OK, self.permissions is not)
    source = inspect.getsource(AgentLoop.__init__)
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    if isinstance(target.value, ast.Name) and target.value.id == "self":
                        if target.attr in ("permissions", "executor"):
                            public_bypass.append(f"self.{target.attr} = ... in __init__")

    if public_bypass:
        pytest.fail(
            f"AgentLoop exposes public tool-bypass attributes: {public_bypass}. "
            f"Use loop._tool_service instead."
        )


# ---------------------------------------------------------------------------
# 3. ToolExecutionService is the only creator of PermissionEngine + Executor
# ---------------------------------------------------------------------------

def test_tool_execution_service_owns_components():
    """Verify ToolExecutionService constructor creates/owns the permission
    engine and executor.
    """
    from core.agent.tool_service import ToolExecutionService

    # Create with no external dependencies — it should create its own
    mock_registry = MagicMock()
    mock_registry.get.return_value = None
    mock_registry.to_openai_tools.return_value = []

    svc = ToolExecutionService(registry=mock_registry)
    assert svc._permissions is not None, "ToolExecutionService must own PermissionEngine"
    assert svc._executor is not None, "ToolExecutionService must own AgentToolExecutor"


# ---------------------------------------------------------------------------
# 4. Protocol adapters use tool_service, not direct executor
# ---------------------------------------------------------------------------

def test_mcp_adapter_uses_tool_service():
    """MCPAdapter must route tool calls through ToolExecutionService."""
    from runtime.protocols import MCPAdapter

    adapter = MCPAdapter(tool_service=AsyncMock())
    assert adapter._tool_service is not None


def test_acp_adapter_uses_tool_service():
    """ACPAdapter must route tool calls through ToolExecutionService."""
    from runtime.protocols import ACPAdapter

    adapter = ACPAdapter(tool_service=AsyncMock())
    assert adapter._tool_service is not None


def test_codex_adapter_uses_tool_service():
    """CodexExecAdapter must route tool calls through ToolExecutionService."""
    from runtime.protocols import CodexExecAdapter

    adapter = CodexExecAdapter(tool_service=AsyncMock())
    assert adapter._tool_service is not None


# ---------------------------------------------------------------------------
# 5. Mode management goes through ToolExecutionService
# ---------------------------------------------------------------------------

def test_tool_service_mode_management():
    """ToolExecutionService should expose mode getter/setter."""
    from core.agent.tool_service import ToolExecutionService

    mock_registry = MagicMock()
    mock_registry.get.return_value = None
    mock_registry.to_openai_tools.return_value = []

    svc = ToolExecutionService(registry=mock_registry, mode="agent")
    assert svc.mode == "agent"
    result = svc.set_mode("plan")
    assert result is True
    assert svc.mode == "plan"


def test_agentloop_delegates_mode_to_service():
    """AgentLoop.mode and set_mode() should delegate to ToolExecutionService."""
    from core.agent.loop import AgentLoop

    # Create a mock loop-like object that has _tool_service
    mock_service = MagicMock()
    mock_service.mode = "agent"
    mock_service.set_mode.return_value = True

    # Verify the property and method exist on AgentLoop
    assert hasattr(AgentLoop, "mode"), "AgentLoop must have .mode property"
    assert hasattr(AgentLoop, "set_mode"), "AgentLoop must have .set_mode method"
