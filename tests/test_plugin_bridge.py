"""Tests for the plugin -> tool bridge (tools/plugin_bridge.py).

Verifies that ``@jarvis_plugin`` callables can be wrapped as first-class
``Tool`` objects and executed through ``ToolExecutionService`` (the single tool
boundary), exactly like built-in tools.
"""

from __future__ import annotations

import asyncio

from core.agent.tool_service import ToolExecutionService
from core.plugin_loader import PluginLoader, PluginRegistration
from providers.types import ToolCall
from tools.plugin_bridge import build_plugin_tools, plugin_to_tool
from tools.registry import ToolRegistry


def _reg(fn, name="demo_report", description="Build a report"):
    return PluginRegistration(name=name, fn=fn, description=description)


def _demo_report(metric: str, limit: int = 5) -> str:
    return f"report for {metric} (limit {limit})"


def test_plugin_to_tool_namespaces_and_schema():
    reg = _reg(_demo_report)
    tool = plugin_to_tool(reg)
    assert tool.name == "plugin.demo_report"
    assert tool.permission == "plugin.call"
    assert tool.category == "plugin"
    props = tool.parameters["properties"]
    assert "metric" in props
    assert props["metric"]["type"] == "string"
    # limit has a default -> not required
    assert "limit" not in tool.parameters["required"]
    assert "metric" in tool.parameters["required"]


def test_plugin_tool_executes_through_service():
    reg = _reg(_demo_report)
    tool = plugin_to_tool(reg)
    registry = ToolRegistry()
    registry.register(tool)
    svc = ToolExecutionService(registry=registry)
    call = ToolCall(name="plugin.demo_report", arguments={"metric": "cpu", "limit": 3}, id="pp1")
    result = asyncio.run(svc.execute_tool(call))
    assert result.success
    assert result.output == "report for cpu (limit 3)"


def test_plugin_tool_captures_exceptions():
    def boom(flag: str) -> str:
        raise RuntimeError("plugin exploded")

    reg = _reg(boom, name="boom")
    tool = plugin_to_tool(reg)
    registry = ToolRegistry()
    registry.register(tool)
    svc = ToolExecutionService(registry=registry)
    call = ToolCall(name="plugin.boom", arguments={"flag": "x"}, id="pp2")
    result = asyncio.run(svc.execute_tool(call))
    assert not result.success
    assert "boom" in result.error


def test_build_plugin_tools_from_loader():
    loader = PluginLoader()
    tools = build_plugin_tools(loader=loader)
    assert isinstance(tools, list)
    for t in tools:
        assert t.name.startswith("plugin.")
        assert t.permission == "plugin.call"
