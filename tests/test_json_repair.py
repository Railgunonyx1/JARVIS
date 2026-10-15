"""Tests for tolerant JSON repair of LLM tool-call arguments.

Covers providers/json_repair.py (ported from goose#8272 / partial-json
research) and the MALFORMED_TOOL enforcement in tool_service. The old
behavior at every provider parse site was json.loads fail -> {} -> the
tool EXECUTES with empty arguments; these tests pin the new contract:
ambiguous repairs succeed, truncation fails explicitly, and a
JSON_ERROR_KEY-marked call is never executed.
"""

from __future__ import annotations

import pytest

from providers.json_repair import (
    JSON_ERROR_KEY,
    arguments_with_error_marker,
    repair_json_args,
)


class TestRepairSuccesses:
    """Ambiguous-but-unambiguous repairs the ladder must handle."""

    @pytest.mark.parametrize("raw,expected", [
        ("{}", {}),
        ('{"a": 1}', {"a": 1}),
        ("", {}),  # empty args are legitimately {}
        ("```json\n{\"a\": 1}\n```", {"a": 1}),  # markdown fence
        ('{"a": 1} Let me check the file.', {"a": 1}),  # trailing reasoning
        ('Here is the call: {"a": 1}', {"a": 1}),  # leading reasoning
        # Literal newlines/tabs inside strings (LLMs emit these)
        ('{"p": "/f", "c": "l1\nl2\tt"}', {"p": "/f", "c": "l1\nl2\tt"}),
        # Curly apostrophes INSIDE values are preserved (fidelity)
        ('{"q": "it\u2019s"}', {"q": "it\u2019s"}),
        # Curly double quotes as DELIMITERS are fixed, values untouched
        ('{\u201cq\u201d: "it\u2019s"}', {"q": "it\u2019s"}),
        ('{"s": "a \u201cb\u201d c"}', {"s": "a \u201cb\u201d c"}),
        # Non-dict top level gets wrapped
        ("[1, 2]", {"value": [1, 2]}),
        ("42", {"value": 42}),
    ])
    def test_repair_success(self, raw, expected):
        args, err = repair_json_args(raw)
        assert err == ""
        assert args == expected

    def test_non_dict_wraps_value(self):
        args, ok = arguments_with_error_marker("[1, 2]")
        assert ok and args == {"value": [1, 2]}


class TestRepairFailures:
    """Cases that must fail explicitly, never silently become {}."""

    @pytest.mark.parametrize("raw", [
        '{"path": "/f", "content": "unterminated',  # truncated mid-string
        '{"a": [1, 2, {"b": "x"',  # truncated mid-structure
        "not json at all",
        '{"a": }',  # broken syntax, unrepairable
    ])
    def test_repair_fails_with_marker(self, raw):
        args, ok = arguments_with_error_marker(raw)
        assert not ok
        assert JSON_ERROR_KEY in args
        assert args[JSON_ERROR_KEY]  # non-empty error description

    def test_truncation_error_is_descriptive(self):
        _, err = repair_json_args('{"path": "/f", "content": "unterminated')
        assert "truncated" in err.lower()

    def test_no_none_input_crash(self):
        args, err = repair_json_args(None)
        assert not err or args == {}


class TestToolServiceEnforcement:
    """A JSON_ERROR_KEY-marked call must be rejected, never executed."""

    @pytest.mark.asyncio
    async def test_marked_call_rejected_as_malformed(self):
        import asyncio

        from core.agent.permissions import PermissionEngine
        from core.agent.state import FailureClass
        from core.agent.tool_service import ToolExecutionService
        from providers.types import ToolCall
        from tools.registry import ToolRegistry
        from tools.schema import Tool, ToolResult

        executed = []

        def probe(args):
            executed.append(dict(args))
            return ToolResult(success=True, output="ok")

        class _L:
            def record(self, *a, **k):
                pass

            def record_tool(self, *a, **k):
                pass

        tool = Tool(
            name="filesystem.write", description="write",
            parameters={"type": "object", "properties": {
                "path": {"type": "string"}, "content": {"type": "string"},
            }, "required": ["path", "content"]},
            permission="filesystem.write", risk="low", handler=probe,
        )
        reg = ToolRegistry()
        reg.register(tool)
        svc = ToolExecutionService(
            registry=reg,
            permissions=PermissionEngine(_L(), mode="agent"),
            decision_logger=_L(), mode="agent",
        )

        bad = ToolCall(
            name="filesystem.write", id="c1",
            arguments={JSON_ERROR_KEY: "arguments truncated (stream cut or token cap)"},
        )
        result = await svc.execute_tool(bad)
        assert result.failure_class == FailureClass.MALFORMED_TOOL
        assert executed == []  # never executed

        good = ToolCall(
            name="filesystem.write", id="c2",
            arguments={"path": "/tmp/x", "content": "hello\nworld"},
        )
        result = await svc.execute_tool(good)
        assert result.error == ""
        assert executed == [{"path": "/tmp/x", "content": "hello\nworld"}]


class TestParseSitesUseRepair:
    """Provider parse sites must route through the repair module."""

    def test_json_args_uses_repair(self):
        from providers.types import json_args

        # Fenced + curly-quote input that strict json.loads would reject.
        args = json_args('```json\n{\u201cq\u201d: "v"}\n```')
        assert args == {"q": "v"}

    def test_json_args_failure_carries_marker(self):
        from providers.types import json_args

        args = json_args('{"path": "/f", "content": "unterminated')
        assert JSON_ERROR_KEY in args
