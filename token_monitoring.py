#!/usr/bin/env python
with open('core/agent/loop.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find the latency logging section and add token tracking
old_section = '''# Pipeline latency tracker
            _latency_log: list[tuple[str, float]] = []'''

new_section = '''# Pipeline latency tracker
            _latency_log: list[tuple[str, float]] = []
            # Token usage tracking per section
            _token_usage: dict[str, int] = {
                "system": 0,
                "memory": 0,
                "files": 0,
                "messages": 0,
                "response": 0,
            }'''

if old_section in content:
    new_content = content.replace(old_section, new_section)
    with open('core/agent/loop.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Token usage tracking initialized')
else:
    print('Old section not found')
    # Try to find where _latency_log is defined
    idx = content.find('_latency_log')
    if idx >= 0:
        print('Found at index', idx)
        print(content[max(0,idx-100):idx+100])