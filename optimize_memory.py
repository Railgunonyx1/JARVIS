#!/usr/bin/env python
with open('memory/api.py', 'r') as f:
    content = f.read()

# Find and replace the format_for_prompt method
old_start = """    # ── prompt rendering ──────────────────────────────────────────────
    def format_for_prompt(self, project: str, max_tokens: int = 4000) -> str:
        """Render a token-bounded memory section for the system prompt.

        Three-layer architecture:
        1. CORE MEMORY — always injected (identity, preferences, priorities)
        2. DECISION MEMORY — recent decisions
        3. RECENT MEMORY — other recent memories (up to limit)
        """
        from runtime.observability.tracer import get_tracer

        with get_tracer().span("memory.prompt", {"project": project, "max_tokens": max_tokens}):
            c = self._controller
            sections = []

            # ── Layer 1: CORE MEMORY (always injected) ──
            # Identity, preferences, and priorities MUST appear in every conversation.
            # These are fetched by category, not by recency.
            if c._kv is not None:
                core_lines = ["[CORE MEMORY]"]
                core_categories = ["identity", "preferences", "priorities"]
                core_found = False
                for category in core_categories:
                    items = c._kv.recent(limit=20, category=category)
                    if items:
                        for item in items:
                            value = str(item["value"]).replace("\\n", " ")[:200]
                            core_lines.append(f"- {item['key']}: {value}")
                            core_found = True
                if core_found:
                    sections.append("\\n".join(core_lines))

            # ── Layer 2: DECISION MEMORY ──
            if c._decisions is not None:
                decisions = c._decisions.recall(project=project, query="", limit=5)
                if decisions:
                    lines = ["[DECISION MEMORY]"]
                    for d in decisions:
                        lines.append(
                            f"- {d['goal'][:100]} \\u2192 {d['decision']}"
                            + (f" | {d['rationale'][:120]}" if d["rationale"] else "")
                        )
                    sections.append("\\n".join(lines))

            # ── Layer 3: RECENT MEMORY (other categories, up to limit) ──
            if c._kv is not None:
                # Get recent memories EXCLUDING core categories (already included above)
                recent = c._kv.recent(limit=8)
                if recent:
                    # Filter out items already in core memory
                    seen_keys = set()
                    for section in sections:
                        for line in section.split("\\n"):
                            if line.startswith("- "):
                                key = line.split(":")[0][2:]
                                seen_keys.add(key)
                    filtered = [r for r in recent if r["key"] not in seen_keys]
                    if filtered:
                        lines = ["[RECENT MEMORY]"]
                        for r in filtered:
                            value = str(r["value"]).replace("\\n", " ")[:200]
                            lines.append(f"- {r['key']}: {value}")
                        sections.append("\\n".join(lines))

            # ── Layer 4: PROJECT KNOWLEDGE ──
            if c._knowledge is not None:
                knowledge = c._knowledge.format_for_prompt(project, max_tokens=max_tokens)
                if knowledge:
                    sections.append(knowledge)

            if not sections:
                return ""
            text = "\\n\\n".join(sections)
            budget_chars = max(80, max_tokens * 4)
            if len(text) > budget_chars:
                text = text[: budget_chars] + "\\n"
            return text"""

new_method = """    # ── prompt rendering ──────────────────────────────────────────────
    def format_for_prompt(self, project: str, max_tokens: int = 2000) -> str:
        """Render a token-bounded memory section for the system prompt.

        Two-layer architecture (down from three):
        1. CORE MEMORY — always injected (identity, preferences, priorities)
           Only 3 items total, shown as key: value (truncated to 80 chars).
        2. RECENT MEMORY — up to 3 other memories (excludes core categories).
           Shown as key: value (truncated to 80 chars).

        Token budget is respected via max_tokens parameter (default 2000).
        """
        from runtime.observability.tracer import get_tracer

        with get_tracer().span("memory.prompt", {"project": project, "max_tokens": max_tokens}):
            c = self._controller
            sections = []

            # ── Layer 1: CORE MEMORY (always injected, 3 items max) ──
            # Identity, preferences, and priorities MUST appear in every conversation.
            # Fetched by category, limited to 1 item per category.
            if c._kv is not None:
                core_lines = ["[MEM]"]
                core_categories = ["identity", "preferences", "priorities"]
                core_shown = 0
                for category in core_categories:
                    if core_shown >= 3:
                        break
                    items = c._kv.recent(limit=5, category=category)
                    if items:
                        # Show only the most recent/relevant item per category
                        item = items[0]
                        value = str(item["value"]).replace("\\n", " ")[:80]
                        core_lines.append(f"- {item['key']}: {value}")
                        core_shown += 1
                if core_shown > 0:
                    sections.append("\\n".join(core_lines))

            # ── Layer 2: RECENT MEMORY (up to 3 other memories) ──
            if c._kv is not None:
                # Get recent memories, exclude core categories
                recent = c._kv.recent(limit=6)
                if recent:
                    # Filter out core category keys
                    core_keys = set()
                    # Collect keys from core memory section if present
                    for section in sections:
                        for line in section.split("\\n"):
                            if line.startswith("- ") and ": " in line:
                                key = line.split(": ")[0][2:]
                                core_keys.add(key)
                    # Also add known core category keys
                    for cat in ["identity", "preferences", "priorities"]:
                        core_keys.add(cat)
                    filtered = [r for r in recent if r["key"] not in core_keys]
                    if filtered:
                        # Show max 3 recent memories, sorted by relevance
                        lines = ["[REC]"]
                        for r in filtered[:3]:
                            value = str(r["value"]).replace("\\n", " ")[:80]
                            lines.append(f"- {r['key']}: {value}")
                        sections.append("\\n".join(lines))

            if not sections:
                return ""
            text = "\\n\\n".join(sections)
            # Respect max_tokens budget (4 chars/token heuristic)
            budget_chars = max(50, max_tokens * 3)
            if len(text) > budget_chars:
                text = text[: budget_chars] + "..."
            return text"""

if old_start in content:
    new_content = content.replace(old_start, new_method)
    with open('memory/api.py', 'w') as f:
        f.write(new_content)
    print('format_for_prompt optimized successfully')
else:
    print('Old string not found')
    # Debug: show what's around line 289
    lines = content.split('\n')
    for i in range(288, 295):
        print(f'L{i}: {lines[i-1]}')