#!/usr/bin/env python
import sys
sys.path.insert(0, r'C:\Users\aayan\Desktop\JARVIS')

with open(r'C:\Users\aayan\Desktop\JARVIS\cli\main.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Check for the new commands
for cmd in ['plugins', 'tools', 'skills']:
    pattern = f'elif line == "/{cmd}"'
    if pattern in content:
        print(f'OK /{cmd} command found in CLI')
    else:
        print(f'MISSING /{cmd} command')

# Also check the functions exist
for func in ['_cmd_plugins', '_cmd_tools']:
    if f'def {func}' in content:
        print(f'OK {func} function found')
    else:
        print(f'MISSING {func} function')