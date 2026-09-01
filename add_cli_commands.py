#!/usr/bin/env python3
"""Add /plugins and /tools CLI commands to JARVIS main.py"""

with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

# Find the line with "    )" that closes the skills table (around line 1140)
# and the 3 blank lines before def _cmd_status (lines 1142-1144)
# Insert the new functions after line 1143 (the 3rd blank line) and before line 1145 (def _cmd_status)

# Let's find the exact insertion point
insert_after = None
for i, line in enumerate(lines):
    if 'def _cmd_status' in line and i > 1100:
        insert_after = i - 1  # Insert before this line
        break

if insert_after is None:
    print("Could not find insertion point")
    exit(1)

# The new functions to insert
new_functions = '''
def _cmd_plugins(loop) -> None:
    """Show all discovered plugins."""
    from core.plugin_loader import PluginLoader, list_plugins

    pl = PluginLoader()
    loaded = pl.discover_and_load()

    from rich.table import Table
    table = Table(title="JARVIS Plugins")
    table.add_column("Plugin", style="bold")
    table.add_column("Description")

    for name, reg in sorted(list_plugins().items()):
        table.add_row(name, reg.description or "")

    console.print(table)
    console.print(Text(f"  {len(loaded)} plugins loaded", style="dim"))


def _cmd_tools(loop) -> None:
    """Show all registered tools from the default registry."""
    from rich.table import Table

    from tools import build_default_registry

    tool_reg = build_default_registry()

    table = Table(title="JARVIS Tools")
    table.add_column("Tool", style="bold")
    table.add_column("Category")
    table.add_column("Permission")

    for tool in tool_reg.list():
        table.add_row(
            tool.name,
            tool.category.value if tool.category else "",
            ", ".join(tool.permissions) if tool.permissions else "",
        )

    console.print(table)
    console.print(
        Text(f"  {tool_reg.count()} tools registered", style="dim")


'''

# Insert after the found line
lines.insert(insert_after, new_functions)

# Write back
with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'w', encoding='utf-8', errors='replace') as f:
    f.writelines(lines)

print(f"Successfully inserted commands at line {insert_after + 1}")