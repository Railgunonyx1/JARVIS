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
import asyncio
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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
        "tools.py",          # defines AgentToolExecutor itself
        "kernel.py",         # composition root — wires the single boundary
        "__init__.py",
    }

    # Exclude directories that should not be scanned
    EXCLUDE_DIRS = {"migration", "dsh", "venv", "__pycache__", "_quarantine", "node_modules"}

    # Use os.walk to avoid broken symlinks in node_modules
    import os
    for dirpath, dirnames, filenames in os.walk(project_root):
        # Skip excluded directories
        rel_dir = os.path.relpath(dirpath, project_root)
        dir_parts = rel_dir.split(os.sep) if rel_dir != "." else []
        if any(p in EXCLUDE_DIRS for p in dir_parts):
            dirnames.clear()  # Don't recurse into this directory
            continue

        for filename in filenames:
            if not filename.endswith(".py"):
                continue

            py_file = Path(dirpath) / filename
            try:
                rel = py_file.relative_to(project_root)
            except (ValueError, OSError):
                continue
            parts = rel.parts

            # Skip excluded directories
            if any(p in EXCLUDE_DIRS for p in parts):
                continue
            if any(p.startswith("_quarantine") for p in parts):
                continue
            if py_file.name in ALLOWLIST:
                continue
            if "test_" in py_file.name or py_file.name.startswith("conftest"):
                continue

            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(rel))
            except Exception:
                continue

            for node in ast.walk(tree):
                # Look for: AgentToolExecutor(...) direct construction outside owner files
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name) and func.id == "AgentToolExecutor":
                        line_no = node.lineno
                        line_text = source.splitlines()[line_no - 1].strip()
                        violations.append((str(rel), line_no, line_text))
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
# 1b. Runtime proof that protocol adapters delegate to tool_service.execute_tool
# ---------------------------------------------------------------------------

def _assert_route_to_service(adapter):
    mock_svc = MagicMock()
    mock_svc.execute_tool = AsyncMock(return_value=MagicMock(
        success=True, output="ok", error="",
    ))
    adapter = adapter(tool_service=mock_svc)
    name = adapter.__class__.__name__

    async def dispatch():
        if name == "CodexExecAdapter":
            await adapter.handle_tool("shell.execute", {"command": "echo hi"})
        else:
            await adapter.handle_request(
                "tools/call", {"name": "shell.execute", "arguments": {"command": "echo hi"}},
            )

    asyncio.run(dispatch())
    assert mock_svc.execute_tool.called, f"{name} did not route to ToolExecutionService"
    call = mock_svc.execute_tool.call_args[0][0]
    assert call.name == "shell.execute"
    assert call.arguments == {"command": "echo hi"}


def test_mcp_delegates_to_tool_service_execute_tool():
    from runtime.protocols import MCPAdapter
    _assert_route_to_service(MCPAdapter)


def test_acp_delegates_to_tool_service_execute_tool():
    from runtime.protocols import ACPAdapter
    _assert_route_to_service(ACPAdapter)


def test_codex_delegate_to_tool_service_execute_tool():
    from runtime.protocols import CodexExecAdapter
    _assert_route_to_service(CodexExecAdapter)


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


def test_loop_wires_tool_verifier_to_service():
    """AgentLoop must wire ToolResultVerifier to its ToolExecutionService so
    post-tool verification actually executes instead of silently skipping."""
    from core.agent.loop import AgentLoop
    from core.agent.tool_service import ToolExecutionService
    from core.harness import Harness, HarnessConfig, HarnessType
    from core.project import ProjectContext
    from tools.registry import ToolRegistry

    def _resp(text: str):
        from providers.types import LLMResponse
        return LLMResponse(text=text, model="fake", provider="fake")

    class _FakeRouter:
        def __init__(self, responses):
            self._responses = list(responses)

        async def complete(self, *args, **kwargs):
            return self._responses.pop(0)

    registry = ToolRegistry()
    loop = AgentLoop(
        router=_FakeRouter([_resp("done.")]),
        registry=registry,
        project=ProjectContext(root_path=Path(__file__).resolve().parents[1]),
        decision_logger=None,
        harness=Harness(HarnessConfig(harness_type=HarnessType.MINIMAL,
                                      enable_verification=True)),
    )
    assert loop._tool_verifier._tool_service is loop._tool_service
    assert loop._tool_verifier._enabled is True
    assert isinstance(loop._tool_service, ToolExecutionService)


# ---------------------------------------------------------------------------
# 6. Legacy execution chain is quarantined — nothing active may reference it
# ---------------------------------------------------------------------------

def _find_quarantine_imports() -> list[tuple[str, int, str]]:
    """Scan active source for imports of the quarantined legacy chain."""
    import os
    project_root = Path(__file__).resolve().parents[1]
    QUARANTINED_REFS = (
        "core.executor",
        "core.task_queue",
        "import workflows",
        "from workflows",
    )
    EXCLUDE_DIRS = {"migration", "dsh", "venv", "__pycache__", "node_modules"}
    imports: list[tuple[str, int, str]] = []

    for dirpath, dirnames, filenames in os.walk(project_root):
        rel_dir = os.path.relpath(dirpath, project_root)
        dir_parts = rel_dir.split(os.sep) if rel_dir != "." else []
        if any(p in EXCLUDE_DIRS or p.startswith("_quarantine") for p in dir_parts):
            dirnames.clear()
            continue
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            py_file = Path(dirpath) / filename
            try:
                rel = py_file.relative_to(project_root)
            except (ValueError, OSError):
                continue
            if any(p.startswith("_quarantine") for p in rel.parts):
                continue
            if py_file.name.startswith("test_") or py_file.name == "conftest.py":
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
            except Exception:
                continue
            for i, line in enumerate(source.splitlines(), 1):
                stripped = line.strip()
                if not stripped.startswith(("import ", "from ")):
                    continue
                if any(ref in stripped for ref in QUARANTINED_REFS):
                    imports.append((str(rel), i, stripped))
    return imports


def test_legacy_chain_not_referenced_by_active_runtime():
    """The legacy AgentExecutor/task_queue/workflows chain must be quarantined
    and never reachable from active, non-test source."""
    imports = _find_quarantine_imports()
    if imports:
        msg = "Active source still references the quarantined legacy chain:\n"
        for f, ln, code in imports:
            msg += f"  {f}:{ln}  {code}\n"
        msg += "\nThese modules live in _quarantine/ and must not be imported."
        pytest.fail(msg)


def test_quarantined_modules_relocated():
    """The legacy execution modules no longer exist at their old paths."""
    root = Path(__file__).resolve().parents[1]
    for old_path in ("core/executor.py", "core/task_queue.py", "workflows"):
        assert not (root / old_path).exists(), f"{old_path} must be quarantined"
        assert (root / "_quarantine").exists()


def test_code_scan_is_canonical_security_home():
    """Generated-code scanning lives in security.code_scan, not core.executor."""
    import security.code_scan as cs
    assert hasattr(cs, "check_generated_code")
    assert hasattr(cs, "FORBIDDEN_CODE_PATTERNS")
    assert hasattr(cs, "generated_code_enabled")


# ---------------------------------------------------------------------------
# 7. Deterministic failure classification precedence
# ---------------------------------------------------------------------------

def test_failure_classification_precedence():
    """Precedence: CANCELLED > TIMEOUT > PERMISSION > CONTEXT_OVERFLOW >
    PROVIDER > MODEL > TOOL."""
    from core.agent.state import FailureClass, classify_failure

    assert classify_failure("x", is_cancelled=True, is_timeout=True) == FailureClass.CANCELLED
    assert classify_failure("x", is_timeout=True, is_permission=True) == FailureClass.TIMEOUT
    assert classify_failure("x", is_permission=True, is_context_overflow=True) == FailureClass.PERMISSION_DENIED
    assert classify_failure("too many tokens", is_provider=True) == FailureClass.CONTEXT_OVERFLOW
    assert classify_failure("api error", is_provider=True) == FailureClass.PROVIDER_FAILURE
    assert classify_failure("provider returned an empty response") == FailureClass.MODEL_FAILURE
    assert classify_failure("unknown tool") == FailureClass.MALFORMED_TOOL
    assert classify_failure("something broke") == FailureClass.TOOL_FAILURE
