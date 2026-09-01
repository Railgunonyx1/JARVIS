with open('core/agent/loop.py', 'r') as f:
    content = f.read()

# Add max_verification_retries to harness config processing (after line 158)
old = """self._verification_enabled = hc.enable_verification
            self._planning_enabled = hc.enable_planning"""

new = """self._verification_enabled = hc.enable_verification
            self._planning_enabled = hc.enable_planning
            self._max_verification_retries = getattr(hc, "max_verification_retries", 3)"""

if old in content:
    content = content.replace(old, new)
    with open('core/agent/loop.py', 'w') as f:
        f.write(content)
    print('Added max_verification_retries to harness config')
else:
    print('Pattern not found')
    # Show what's around line 158
    lines = content.split('\n')
    for i in range(150, 165):
        print(f'{i+1}: {lines[i]}')
PYEOF