"""Smoke test: every registered tool must resolve to a valid callable handler.

`build_default_registry()` stores handler *objects*, so a handler that
references an unbound name does not fail at build time -- it fails later,
when the agent invokes that tool. That is why the doc.search / agenda.view /
web.archive dispatchers in `tools/__init__.py` need their target functions
bound at module scope.

This test suite verifies tool registration, handler reachability, and
module-level bindings.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import tools as tools_pkg

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def registry():
    return tools_pkg.build_default_registry()


def test_registry_is_populated(registry):
    assert len(registry._tools) > 0, "default registry registered no tools"


def test_every_tool_has_callable_handler(registry):
    """Verify that all registered tools have an actual callable handler."""
    broken: list[str] = []
    for name, spec in registry._tools.items():
        handler = getattr(spec, "handler", None)
        if handler is None or not callable(handler):
            broken.append(f"{name}: handler is not callable ({handler!r})")
    assert not broken, "Tools with invalid handlers:\n  " + "\n  ".join(broken)


def test_handler_dispatchers_are_reachable(registry):
    """The dispatchers in tools/__init__.py must be registered and callable."""
    for tool_name, handler_name in (
        ("doc.search", "doc_retrieval_handler"),
        ("agenda.view", "agenda_view_handler"),
        ("web.archive", "web_archive_handler"),
        ("topic.watch", "topic_watch_handler"),
    ):
        spec = registry._tools.get(tool_name)
        assert spec is not None, f"{tool_name} not registered"
        handler = getattr(spec, "handler", None)
        assert getattr(handler, "__name__", None) == handler_name, (
            f"{tool_name} handler is {handler!r}, expected {handler_name}"
        )


def test_module_dispatchers_are_bound():
    """Verify that module-level dispatcher targets in tools package are bound."""
    for fn_name in (
        "agenda_add", "agenda_list", "agenda_remove",
        "doc_search", "doc_stats",
        "web_archive_list", "web_archive_read",
    ):
        target = getattr(tools_pkg, fn_name, None)
        assert callable(target), f"{fn_name} must be imported and callable in tools package"


def test_submodule_attributes_survive():
    """`tools.agenda_view` / `tools.web_archive` must stay MODULES.

    Both modules export a function that shares its own module's name. Binding
    that function as a bare package attribute silently replaces the submodule
    the rest of the codebase does `from tools import agenda_view as ag`, which
    breaks every caller of `ag.agenda_view(...)` with
    "'function' object has no attribute ...". The dispatchers therefore reach
    these two through the module object instead of a bare name.
    """
    import types

    for mod_name in ("agenda_view", "web_archive", "doc_retrieval"):
        attr = getattr(tools_pkg, mod_name)
        assert isinstance(attr, types.ModuleType), (
            f"tools.{mod_name} must stay a module, got {type(attr).__name__}"
        )
        assert attr.__name__.endswith(mod_name)


_DISPATCH_CASES = [
    # (handler attr, action, dotted target the action must reach)
    ("doc_retrieval_handler", "stats", "doc_stats"),
    ("doc_retrieval_handler", "search", "doc_search"),
    ("doc_retrieval_handler", "", "doc_search"),
    ("agenda_view_handler", "add", "agenda_add"),
    ("agenda_view_handler", "remove", "agenda_remove"),
    ("agenda_view_handler", "list", "agenda_list"),
    ("agenda_view_handler", "view", "_agenda_view_mod.agenda_view"),
    ("web_archive_handler", "list", "web_archive_list"),
    ("web_archive_handler", "read", "web_archive_read"),
    ("web_archive_handler", "archive", "_web_archive_mod.web_archive"),
]


@pytest.mark.parametrize("handler_name,action,target_name", _DISPATCH_CASES)
def test_dispatcher_invocation_reaches_target(monkeypatch, handler_name, action, target_name):
    """Every action branch must resolve its target and return a ToolResult.

    This is the test that catches the F821 class of bug: the dispatchers
    reference names (doc_search, agenda_add, _web_archive_mod.web_archive, ...)
    that must resolve at *call* time. Stubbing the target keeps the test
    hermetic -- no calendar, archive, or index side effects.
    """
    reached: list[str] = []

    def _stub(args: dict):
        reached.append(args.get("action", ""))
        return tools_pkg.tool_result(True, target_name)

    owner, _, attr = target_name.rpartition(".")
    if owner:
        monkeypatch.setattr(getattr(tools_pkg, owner), attr, _stub)
    else:
        monkeypatch.setattr(tools_pkg, target_name, _stub, raising=False)
    handler = getattr(tools_pkg, handler_name)

    result = handler({"action": action})

    assert reached, f"{handler_name}({action!r}) never called {target_name}"
    assert getattr(result, "success", None) is True, f"{handler_name}({action!r}) -> {result!r}"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
def test_no_undefined_names_in_repo():
    """Static F821 gate over the whole repo.

    Runtime smoke tests cannot catch an unbound name that only fires on an
    error path -- `build_default_registry()` stores handler *objects*, so a
    dispatcher referencing an unbound global builds fine and only explodes
    when the agent invokes it. Ruff resolves names statically, which is what
    catches the whole class at once.
    """
    proc = subprocess.run(
        ["ruff", "check", "--select", "F821", "--no-cache",
         "--output-format", "concise", "."],
        cwd=_REPO_ROOT, capture_output=True, text=True, timeout=180,
    )
    offenders = [ln for ln in proc.stdout.splitlines() if "F821" in ln]
    assert not offenders, "undefined names (F821):\n  " + "\n  ".join(offenders)
