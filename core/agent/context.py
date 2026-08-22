"""AgentContextBuilder — builds the system prompt and message history.

Optimized for minimal token usage:
  - INSTANT queries: ~50 tokens (identity-only prompt)
  - SIMPLE queries: ~150 tokens (brief + memory)
  - COMPLEX queries: ~500 tokens (full instructions + memory)
  - Tool descriptions passed via API, not system prompt (saves ~1900 tokens)
"""

from __future__ import annotations

from typing import Any

from tools.registry import ToolRegistry

# ── Pre-built prompt fragments (avoid per-request string building) ────────

_IDENTITY = "You are JARVIS MK-X, an autonomous engineering agent."

_BRIEF = (
    f"{_IDENTITY} Answer simple questions directly in 1-3 sentences. "
    "Do NOT call tools unless the task requires file/system operations."
)

_FULL = (
    f"{_IDENTITY} running on a Windows PC.\n"
    "\n"
    "For simple questions, greetings, opinions, math, jokes, answer directly "
    "in 1-3 sentences. Do NOT call tools for things you can answer from knowledge.\n"
    "\n"
    "For tasks requiring code changes, file operations, or system commands:\n"
    "1. UNDERSTAND: Parse the user's goal.\n"
    "2. EXPLORE: Read relevant files first.\n"
    "3. PLAN: State your approach in 1-2 sentences.\n"
    "4. EXECUTE: Make precise, minimal changes.\n"
    "5. VERIFY: Confirm the result is correct.\n"
    "\n"
    "Tool rules:\n"
    "- filesystem.read to read files (NOT cat/type)\n"
    "- filesystem.list to list dirs (NOT dir/ls)\n"
    "- search.code to search contents (NOT grep)\n"
    "- patch.replace/insert/delete for edits\n"
    "- filesystem.write ONLY for new files\n"
    "- shell.execute ONLY when no other tool works\n"
    "- Inspect before acting: read before modifying\n"
    "- On tool error, adapt and retry with corrected call\n"
    "- Never fabricate results. Report what happened.\n"
    "- Stop when goal is complete. Summarize in 2-3 sentences."
)

_SMALL_FULL = (
    f"{_IDENTITY} running on a Windows PC.\n"
    "\n"
    "Answer simple questions directly. For code/file tasks: read first, "
    "then edit minimally. Use tools to read, write, search, and run commands. "
    "Stop when done. Summarize briefly."
)

# Cache: project context string (changes rarely)
_project_cache: dict[str, str] = {}


class AgentContextBuilder:
    """Composes the system prompt with tiered token budgets."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self._memory_cache: dict[str, tuple[str, float]] = {}
        self._memory_cache_ttl = 5.0  # seconds

    def build(
        self,
        goal: str,
        project,
        mem=None,
        tools: list | None = None,
        context_level: str = "deep",
    ) -> tuple[list[dict[str, Any]], str]:
        """Return (messages, system_prompt) with token-optimized prompt.

        context_level:
          - 'instant': ~50 tokens (identity only, no memory)
          - 'session': ~150 tokens (brief + memory)
          - 'deep':    ~500 tokens (full instructions + memory)
        """
        if context_level == "instant":
            return [{"role": "user", "content": goal}], _IDENTITY
        if context_level == "session":
            prompt = _BRIEF
            if mem is not None:
                mem_text = self._cached_memory(mem, project)
                if mem_text:
                    prompt = f"{prompt}\n{mem_text}"
            return [{"role": "user", "content": goal}], prompt

        # deep context
        lines = [_FULL]
        proj_ctx = self._project_context(project)
        if proj_ctx:
            lines.append(proj_ctx)
        if mem is not None:
            mem_text = self._cached_memory(mem, project)
            if mem_text:
                lines.append(mem_text)
        return [{"role": "user", "content": goal}], "\n".join(lines)

    def _project_context(self, project) -> str:
        """Cache project context (rarely changes)."""
        if project is None:
            return ""
        key = str(getattr(project, "root_path", ""))
        if key in _project_cache:
            return _project_cache[key]

        parts = [f"Project: {project.root_path}"]
        lang = getattr(project, "language", "")
        if lang:
            parts.append(f"Language: {lang}")
        fw = getattr(project, "framework", "")
        if fw:
            parts.append(f"Framework: {fw}")
        git = getattr(project, "git_root", None)
        if git:
            parts.append(f"Git: {git}")
        result = "\n".join(parts)
        _project_cache[key] = result
        return result

    def _cached_memory(self, mem, project) -> str:
        """Cache memory format (expensive DB query)."""
        import time
        now = time.time()
        project_root = str(getattr(project, "root_path", "")) if project else ""

        cache_key = project_root
        if cache_key in self._memory_cache:
            text, ts = self._memory_cache[cache_key]
            if now - ts < self._memory_cache_ttl:
                return text

        try:
            text = mem.format_for_prompt(project_root, max_tokens=800)
        except Exception:
            text = ""
        self._memory_cache[cache_key] = (text, now)
        return text
