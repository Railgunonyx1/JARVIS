#!/usr/bin/env python
"""Quick fix for _cmd_tools syntax error"""

with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

# Find line 1184-1186 (0-indexed: 1183-1185) and fix the missing closing paren
# Lines 1183-1186 (1-indexed) are:
# 1183:     console.print(table)
# 1184:     console.print(
# 1185:         Text(f"  {tool_reg.count()} tools registered", style="dim")
# 1186: 
# Need to add closing ) after line 1185

for i, line in enumerate(lines):
    if 'Text(f"  {tool_reg.count()} tools registered"' in line:
        # This is line 1185 (0-indexed), add ) after it
        # But first check the context
        if i + 1 < len(lines) and ')' not in lines[i+1]:
            # Add ) to this line
            lines[i] = line.rstrip() + ")\n"
            print(f"Fixed line {i+1}: added closing paren")
            break

with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'w', encoding='utf-8', errors='replace') as f:
    f.writelines(lines)

print("Done fixing")