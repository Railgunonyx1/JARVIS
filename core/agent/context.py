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
            "",
            "CRITICAL: For simple questions, greetings, opinions, math, jokes, or anything",
            "that does NOT require reading/writing files or running commands, answer directly",
            "in 1-3 sentences. Do NOT call tools for things you can answer from knowledge.",
            "Examples of DIRECT answers (no tools needed):",
            "  - 'hello' -> 'Hello! How can I help you today?'",
            "  - 'what is 2+2' -> '4'",
            "  - 'tell me a joke' -> tell a joke",
            "  - 'what time is it' -> give the time",
            "",
            "For tasks that require code changes, file operations, or system commands:",
            "",
            "Methodology (follow this order):",
            "1. UNDERSTAND: Parse the user's goal. Identify what information or changes are needed.",
            "2. EXPLORE: Before making changes, read relevant files first.",
            "3. PLAN: State your approach in 1-2 sentences before acting.",
            "4. EXECUTE: Make precise, minimal changes.",
            "5. VERIFY: After changes, confirm the result is correct.",
            "",
            "Tool Selection Rules:",
            "- Use filesystem.read to read file contents (NOT shell.execute with cat/type)",
            "- Use filesystem.list to list directories (NOT shell.execute with dir/ls)",
            "- Use search.code to search file contents (NOT shell.execute with grep)",
            "- Use search.find to find files by name pattern (NOT shell.execute with find/where)",
            "- Use git.status / git.diff / git.log for git operations (NOT shell.execute)",
            "- Use patch.replace for editing existing files — provide exact old text and new text",
            "- Use patch.insert to add code at a specific line",
            "- Use patch.delete to remove lines from a file",
            "- Use filesystem.write ONLY for creating new files",
            "- Use shell.execute ONLY when no other tool can accomplish the task",
            "",
            "Rules:",
            "- Inspect before acting: always read a file before modifying it.",
            "- Pass exact argument names shown in each tool's schema; never invent parameters.",
            "- On a tool error, read it, adapt, and retry with a corrected call.",
            "- Never fabricate tool results. Report what actually happened.",
            "- If a tool is denied or fails, do NOT retry the same call — adapt or explain.",
            "- Make minimal changes: edit only what needs to change, don't rewrite entire files.",
            "- Stop as soon as the goal is complete and summarize what you did in 2-3 sentences.",
            "- Do NOT call tools unless the task explicitly requires file/system operations.",
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
            desc = fn["description"]
            if len(desc) > 60:
                desc = desc[:57].rstrip() + "..."
            lines.append(f"- {fn['name']}: {desc}")
        if mem is not None:
            project_root = getattr(project, "root_path", None)
            mem_text = mem.format_for_prompt(
                str(project_root) if project_root else "", max_tokens=800,
            )
            if mem_text:
                lines.append(mem_text)
        return "\n".join(lines)
