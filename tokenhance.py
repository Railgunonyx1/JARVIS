#!/usr/bin/env python
with open('core/agent/loop.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find and replace the token tracking initialization
old_context = """# Token usage tracking per section
            _token_usage: dict[str, int] = {
                "system": 0,
                "memory": 0,
                "files": 0,
                "messages": 0,
                "response": 0,
            }"""

new_context = """# Token usage tracking per section
            _token_usage: dict[str, int] = {
                "system": 0,
                "memory": 0,
                "files": 0,
                "messages": 0,
                "response": 0,
            }
            _last_budget: ContextBudget | None = None"""

if old_context in content:
    new_content = content.replace(old_context, new_context)
    with open('core/agent/loop.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Token tracking initialization enhanced')
else:
    print('Old init not found - showing first 100 chars around area:')
    idx = content.find('# Token usage tracking per section')
    if idx >= 0:
        print(content[idx:idx+200])
"