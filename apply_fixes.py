#!/usr/bin/env python
with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Fix 1: Replace s.tool_names with tags
content = content.replace(
    'tools_ok = sum(1 for t in s.tool_names if t in tool_names)',
    'tags_str = ", ".join(s.tags[:3]) if s.tags else ""'
)

# Fix 2: Replace the tools count in table row
content = content.replace(
    'f"{tools_ok}/{len(s.tool_names)}"',
    'tags_str'
)

# Fix 3: Replace skill_reg.list_all()
content = content.replace(
    'skill_reg.list_all()',
    'skill_reg'
)

with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'w', encoding='utf-8', errors='replace') as f:
    f.write(content)

print('Applied all fixes')