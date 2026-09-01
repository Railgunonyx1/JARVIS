#!/usr/bin/env python
"""Fix syntax error in _cmd_tools function"""

with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Fix the missing closing parenthesis in _cmd_tools
# The issue: console.print(\n        Text(...)\n  is missing the closing )
old = '''console.print(
        Text(f"  {tool_reg.count()} tools registered", style="dim")


def _cmd_status(loop) -> None:'''

new = '''console.print(
        Text(f"  {tool_reg.count()} tools registered", style="dim")
    )


def _cmd_status(loop) -> None:'''

if old in content:
    content = content.replace(old, new)
    with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'w', encoding='utf-8', errors='replace') as f:
        f.write(content)
    print("Syntax fixed")
else:
    print("Pattern not found, trying alternative...")
    # Try to find and fix any unmatched console.print
    import re
    # Find all console.print( and count
    opens = content.count('console.print(')
    closes = content.count('console.print)')
    print(f"console.print(open: {opens}, close: {closes})")