import re
with open('core/agent/loop.py') as f:
    content = f.read()
for keyword in ['cascade', 'resolve_model', 'preferred_model', 'detect_task_type', 'ModelRegistry']:
    positions = [m.start() for m in re.finditer(keyword, content)]
    if positions:
        print(f"'{keyword}': found at {len(positions)} positions")