#!/usr/bin/env python
import sys
with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

old = """def _cmd_skills() -> None:
    """Show all available skills and their tool coverage."""
    from rich.table import Table

    from skills import build_default_skill_registry
    from tools import build_default_registry

    skill_reg = build_default_skill_registry()
    tool_reg = build_default_registry()
    tool_names = {t.name for t in tool_reg.list()}

    table = Table(title="JARVIS Skills")
    table.add_column("Skill", style="bold")
    table.add_column("Tools", justify="right")
    table.add_column("Risk")
    table.add_column("Description", max_width=50)

    for s in sorted(skill_reg.list_all(), key=lambda x: x.name):
        tools_ok = sum(1 for t in s.tool_names if t in tool_names)
        risk_raw = getattr(s, 'risk', '') or ''
        risk_str = (
            "high" if "high" in str(risk_raw)
            else "medium" if "medium" in str(risk_raw)
            else "low"
        )
        table.add_row(
            s.name,
            f"{tools_ok}/{len(s.tool_names)}",
            risk_str,
            s.description[:50],
        )
    console.print(table)
    console.print(
        Text(f"  {len(skill_reg.list_all())} skills, {len(tool_names)} tools", style="dim")
    )"""

new_func = "def _cmd_skills() -> None:\n    from rich.table import Table\n    from skills import build_default_skill_registry\n    skill_reg = build_default_skill_registry()\n    table = Table(title=\"JARVIS Skills\")\n    table.add_column(\"Skill\", style=\"bold\")\n    table.add_column(\"Tags\")\n    table.add_column(\"Risk\")\n    table.add_column(\"Description\", max_width=50)\n    for s in sorted(skill_reg.values(), key=lambda x: x.name):\n        tags_str = \", \".join(s.tags[:3]) if s.tags else \"\"\n        risk_raw = getattr(s, 'risk', '') or ''\n        risk_str = (\n            \"high\" if \"high\" in str(risk_raw)\n            else \"medium\" if \"medium\" in str(risk_raw)\n            else \"low\"\n        )\n        table.add_row(\n            s.name,\n            tags_str,\n            risk_str,\n            s.description[:50],\n        )\n    console.print(table)\n    console.print(Text(f\"  {len(skill_reg)} skills registered\", style=\"dim\"))\n"

if old_func in content:
    content = content.replace(old_func, new_func)
    with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'w', encoding='utf-8', errors='replace') as f:
        f.write(content)
    print('Successfully rewrote _cmd_skills function')
else:
    print('Pattern not found')