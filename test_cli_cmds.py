#!/usr/bin/env python
import sys
sys.path.insert(0, r'C:\Users\aayan\Desktop\JARVIS')

from cli.main import _cmd_plugins, _cmd_tools, _cmd_skills
import types

loop = types.SimpleNamespace()

# Test _cmd_skills
try:
    _cmd_skills()
    print('OK _cmd_skills runs')
except Exception as e:
    print(f'MISSING _cmd_skills: {type(e).__name__}')

# Test _cmd_plugins
try:
    _cmd_plugins(loop)
    print('OK _cmd_plugins runs')
except Exception as e:
    print(f'MISSING _cmd_plugins: {type(e).__name__}')

# Test _cmd_tools
try:
    _cmd_tools(loop)
    print('OK _cmd_tools runs')
except Exception as e:
    print(f'MISSING _cmd_tools: {type(e).__name__}')