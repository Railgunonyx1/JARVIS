#!/usr/bin/env python
"""Fix _cmd_skills three issues"""

with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

# Fix 1: line 1124 - s.tool_names -> tags_str
# Fix 2: line 1133 - len(s.tool_names) -> remove (we're not showing tools count)
# Fix 3: line 1139 - skill_reg.list_all() -> skill_reg

# We'll modify specific lines
for i, line in enumerate(lines):
    # Fix 1: line 1124 (0-indexed: 1123) - replace tool_names reference
    if i == 1123 and 's.tool_names' in line:
        lines[i] = lines[i].replace('tools_ok = sum(1 for t in s.tool_names if t in tool_names)', 'tags_str = ", ".join(s.tags[:3]) if s.tags else ""')
        print(f'Fixed line {i+1}: tool_names -> tags_str')
    
    # Fix 2: line 1133 (0-indexed: 1132) - remove the tools_ok/ tool_names part
    if i == 1132 and 'f"{tools_ok}/{len(s.tool_names)}"' in line:
        lines[i] = lines[i].replace('f"{tools_ok}/{len(s.tool_names)}"', tags_str if 'tags_str' in lines[1123] else "")
        print(f'Fixed line {i+1}: removed tools count')
    
    # Fix 3: line 1139 (0-indexed: 1138) - replace skill_reg.list_all()
    if i == 1138 and 'skill_reg.list_all()' in line:
        lines[i] = lines[i].replace('skill_reg.list_all()', 'skill_reg')
        print(f'Fixed line {i+1}: list_all() -> skill_reg')

with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'w', encoding='utf-8', errors='replace') as f:
    f.writelines(lines)

print('Applied all _cmd_skills fixes')