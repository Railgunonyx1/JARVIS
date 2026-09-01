#!/usr/bin/env python
"""Fix _cmd_tools category and permission handling"""

with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

old = """    for tool in tool_reg.list():
        table.add_row(
            tool.name,
            tool.category.value if tool.category else \"\",
            \", \".join(tool.permissions) if tool.permissions else \"\",
        )"""

new = """    for tool in tool_reg.list():
        table.add_row(
            tool.name,
            tool.category if tool.category else \"\",
            tool.permission if tool.permission else \"\",
        )"""

if old in content:
    content = content.replace(old, new)
    with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'w', encoding='utf-8', errors='replace') as f:
        f.write(content)
    print('Fixed _cmd_tools category/permission')
else:
    print('Pattern not found - checking current content...')
    # Show what's around line 1176-1182
    lines = content.split('\n')
    for i in range(1175, 1185):
        if i < len(lines):
            print(f'{i+1}: {lines[i][:80]}')