#!/usr/bin/env python
with open('core/agent/loop.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Replace the tool call truncation to use adaptive