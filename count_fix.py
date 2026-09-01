#!/usr/bin/env python
"""Fix tool count in _cmd_tools"""

with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

old = 'Text(f"  {tool_reg.count()} tools registered", style="dim")'
new = 'Text(f"  {len(tool_reg)} tools registered", style="dim")'

if old in content:
    content = content.replace(old, new)
    with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'w', encoding='utf-8', errors='replace') as f:
        f.write(content)
    print('Fixed count issue')
else:
    print('Pattern not found')