#!/usr/bin/env python
"""Fix _cmd_skills three issues"""

with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Fix 1: Replace the tools_ok calculation with tags_str
content = content.replace(
    'tools_ok = sum(1 for t in s.tool_names if t in tool_names)',
    'tags_str = ", ".join(s.tags[:3]) if s.tags else ""'
)

# Fix 2: Replace the tools count in the table row
content = content.replace(
    'f"{tools_ok}/{len(s.tool_names)}"',
    tags_str if 'tags_str' in dir() else ""
)

# Actually, let me do this step by step
# Fix 1 already added tags_str, now fix the table row
content = content.replace(
    'f"{tools_ok}/{len(s.tool_names)}"',
    '"' + (", ".join(s.tags[:3]) if "s" in dir() else "") + '"'
)

# Hmm, this is getting complicated. Let me just rewrite the whole function section.
# Let me find the exact range and replace it.

# Read the file again to get fresh content
with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find and replace the entire _cmd_skills function body
# The function starts at def _cmd_skills and ends at def _cmd_plugins
old_body_start = '    for s in sorted(skill_reg.values(), key=lambda x: x.name):'
old_body_end = '    console.print(\n        Text(f"  {len(skill_reg.list_all())} skills, {len(tool_names)} tools", style="dim")\n    )\n\n\n\n\ndef _cmd_plugins'

# Actually, let me just rewrite from line 1123 to 1141
lines = content.split('\n')
# Lines 1123-1141 (1-indexed) need to be replaced
# 1123:     for s in sorted(skill_reg.values(), key=lambda x: x.name):
# 1124:         tools_ok = sum(1 for t in s.tool_names if t in tool_names)
# 1125:         risk_raw = getattr(s, 'risk', '') or ''
# 1126:         risk_str = (
# 1127:             "high" if "high" in str(risk_raw)
# 1128:             else "medium" if "medium" in str(risk_raw)
# 1129:             else "low"
# 1129:         )
# 1130:         table.add_row(
# 1131:             s.name,
# 1132:             f"{tools_ok}/{len(s.tool_names)}",
# 1133:             risk_str,
# 1134:             s.description[:50],
# 1135:         )
# 1136:     console.print(table)
# 1137:     console.print(
# 1138:         Text(f"  {len(skill_reg.list_all())} skills, {len(tool_names)} tools",
# 1139:              style="dim")
# 1140:     )

# Replace lines 1123-1140 (0-indexed: 1122-1139)
new_lines = """    for s in sorted(skill_reg.values(), key=lambda x: x.name):
        tags_str = ", ".join(s.tags[:3]) if s.tags else ""
        risk_raw = getattr(s, 'risk', '') or ''
        risk_str = (
            "high" if "high" in str(risk_raw)
            else "medium" if "medium" in str(risk_raw)
            else "low"
        )
        table.add_row(
            s.name,
            tags_str,
            risk_str,
            s.description[:50],
        )
    console.print(table)
    console.print(
        Text(f"  {len(skill_reg)} skills registered", style="dim")
    )"""

# Replace the lines
# Find the start line number
start_line = None
end_line = None
for i, line in enumerate(content.split('\n')):
    if 'for s in sorted(skill_reg.values(), key=lambda x: x.name):' in line:
        start_line = i
    if 'def _cmd_plugins' in line and start_line:
        end_line = i
        break

if start_line is not None and end_line is not None:
    # Replace lines from start_line to end_line
    new_content = '\n'.join(content.split('\n')[:start_line]) + '\n' + new_lines + '\n' + '\n'.join(content.split('\n')[end_line:])
    with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'w', encoding='utf-8', errors='replace') as f:
        f.write(new_content)
    print('Replaced _cmd_skills function body')
else:
    print(f'start_line={start_line}, end_line={end_line}')