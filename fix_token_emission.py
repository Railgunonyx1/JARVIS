#!/usr/bin/env python
with open('core/agent/loop.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find the verification.passed block and add token emission after it
old_pattern = '''self._emit("verification.passed", {
    "steps_run": ver_report.steps_run,
}, trace_id)'''

new_pattern = '''self._emit("verification.passed", {
    "steps_run": ver_report.steps_run,
}, trace_id)

# Emit token usage report at iteration multiples of 5
if state.iteration % 5 == 0:
    self._emit("token.usage", {
        "iteration": state.iteration,
        "token_usage": self._token_usage.copy(),
        "budget_total": sum(self.context_manager.budget.to_dict().values()),
    }, trace_id)'''

if old_pattern in content:
    new_content = content.replace(old_pattern, new_pattern)
    with open('core/agent/loop.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Token emission pattern added successfully')
else:
    print('Pattern not found - showing surrounding context')
    idx = content.find('self._emit("verification.passed"')
    if idx >= 0:
        print(content[idx:idx+150])
"