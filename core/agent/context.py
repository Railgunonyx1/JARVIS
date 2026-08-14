"""AgentContextBuilder — builds the system prompt and message history."""

from __future__ import annotations

from typing import Any

from tools.registry import ToolRegistry


class AgentContextBuilder:
    """Composes the system prompt from the tool registry + project context."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def build(self, goal: str, project, mem=None) -> tuple[list[dict[str, Any]], str]:
        """Return (messages, system_prompt) for the first loop iteration."""
        return [{"role": "user", "content": goal}], self._system_prompt(project, mem)

    def _system_prompt(self, project, mem=None) -> str:
        tools = self.registry.to_openai_tools()
        lines = [
            "You are JARVIS MK-X, an autonomous engineering agent running on a Windows PC.",
            "You accomplish the user's goal by calling tools. You may call tools repeatedly.",
            "Rules:",
            "- Inspect before acting: use filesystem.list / filesystem.read before guessing.",
            "- Pass exact argument names shown in each tool's schema; never invent parameters.",
            "- On a tool error, read it, adapt, and retry with a corrected call.",
            "- Never fabricate tool results. Report what actually happened.",
            "- If a tool is denied or fails, do NOT retry the same call — adapt or explain why the goal cannot be completed.",
            "- Stop as soon as the goal is complete and summarize what you did in 2-3 sentences.",
        ]
        if project:
            lines.append("Project context:")
            lines.append(f"- root: {project.root_path}")
            if getattr(project, "language", ""):
                lines.append(f"- language: {project.language}")
            if getattr(project, "framework", ""):
                lines.append(f"- framework: {project.framework}")
            if getattr(project, "git_root", None):
                lines.append(f"- git root: {project.git_root}")
        lines.append(f"Available tools ({len(tools)}):")
        for tool in tools:
            fn = tool["function"]
            lines.append(f"- {fn['name']}: {fn['description']}")
        if mem is not None:
            project_root = getattr(project, "root_path", None)
            mem_text = mem.format_for_prompt(
                str(project_root) if project_root else "", max_tokens=1500,
            )
            if mem_text:
                lines.append(mem_text)
        return "\n".join(lines)
