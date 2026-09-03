"""Plugin -> tool bridge.

By default, ``@jarvis_plugin`` plugins are discovery-only callables; they are
not wired into the agent's single tool execution boundary. This module bridges
the gap by wrapping each :class:`~core.plugin_loader.PluginRegistration` as a
first-class :class:`~tools.schema.Tool`, so plugins flow through
``ToolExecutionService`` (permission gate -> classifier -> executor) exactly
like built-in tools.

Signatures: plugins are typically plain (or keyword-only) callables that take
named arguments and return ``str``. The bridge builds a JSON-schema ``parameters``
from ``inspect.signature`` and calls ``fn(**bounds)`` with the caller-supplied
``arguments`` dict, normalizing the result into a ``ToolResult``.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

from core.plugin_loader import PluginLoader, PluginRegistration
from tools.schema import Tool, ToolResult

logger = logging.getLogger("jarvis.plugin_bridge")

PLUGIN_TOOL_PERMISSION = "plugin.call"
PLUGIN_TOOL_CATEGORY = "plugin"


def _signature_parameters(fn) -> dict[str, Any]:
    """Infer a JSON-schema ``parameters`` object from ``fn``'s signature.

    Positional/keyword params become object ``properties`` (all typed as
    ``{"type": "string"}`` unless annotated); ``*args``/``**kwargs`` are
    omitted. Every concrete param is treated as required since plugin bodies
    generally rely on them.
    """
    params: dict[str, Any] = {}
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return {"type": "object", "properties": {}, "required": []}

    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname in ("self", "cls"):
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        props: dict[str, Any] = {}
        if param.annotation is not inspect.Parameter.empty:
            ann = param.annotation
            if ann is str:
                props["type"] = "string"
            elif ann in (int, float):
                props["type"] = "number"
            elif ann is bool:
                props["type"] = "boolean"
            elif ann is dict or getattr(ann, "__origin__", None) is dict:
                props["type"] = "object"
            else:
                props["type"] = "string"
        else:
            props["type"] = "string"
        if param.default is not inspect.Parameter.empty:
            props["default"] = param.default
        else:
            required.append(pname)
        params[pname] = props

    return {
        "type": "object",
        "properties": params,
        "required": required,
    }


def _make_handler(reg: PluginRegistration) -> Any:
    """Return an async ``(args: dict) -> ToolResult`` handler for a plugin fn."""

    async def handler(arguments: dict[str, Any]) -> ToolResult:
        kwargs = dict(arguments or {})
        try:
            result = reg.fn(**kwargs)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:  # noqa: BLE001 - surface to the caller as a failed tool
            return ToolResult(
                success=False,
                error=f"plugin '{reg.name}' failed: {exc}",
                metadata={"tool": reg.name},
            )
        if isinstance(result, ToolResult):
            return result
        return ToolResult(
            success=True,
            output=str(result),
            metadata={"tool": reg.name},
        )

    return handler


def plugin_to_tool(
    reg: PluginRegistration,
    permission: str = PLUGIN_TOOL_PERMISSION,
    category: str = PLUGIN_TOOL_CATEGORY,
    namespace: str = "plugin",
) -> Tool:
    """Wrap a discovered plugin as a ``Tool`` routed through the tool boundary."""
    return Tool(
        name=f"{namespace}.{reg.name}" if namespace else reg.name,
        description=reg.description or reg.meta.get("description", "") or "",
        parameters=_signature_parameters(reg.fn),
        permission=permission,
        handler=_make_handler(reg),
        category=category,
    )


def build_plugin_tools(
    loader: PluginLoader | None = None,
    namespace: str = "plugin",
) -> list[Tool]:
    """Discover all plugins and return them as classified ``Tool`` objects.

    The returned tools are ready for registration into a ``ToolRegistry`` and
    will flow through ``ToolExecutionService`` (permission + classifier +
    executor) like any built-in tool.
    """
    from tools.classification import classify_tool

    pl = loader or PluginLoader()
    registrations = pl.discover_and_load()
    tools: list[Tool] = []
    for reg in registrations.values():
        try:
            tools.append(classify_tool(plugin_to_tool(reg, namespace=namespace)))
        except Exception as exc:  # noqa: BLE001 - one bad plugin must not block the rest
            logger.error("Failed to bridge plugin %s: %s", reg.name, exc)
    return tools


__all__ = [
    "PLUGIN_TOOL_PERMISSION",
    "PLUGIN_TOOL_CATEGORY",
    "build_plugin_tools",
    "plugin_to_tool",
]
