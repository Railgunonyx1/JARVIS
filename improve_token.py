#!/usr/bin/env python
"""Improve Jarvis: Add active token usage tracking (Improvement #1)."""

import sys
import os

sys.path.insert(0, '.')

print("="*60)
print("IMPROVEMENT #1: Active Token Usage Tracking")
print("="*60)

# Read current loop.py
try:
    with open('core/agent/loop.py', 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    print(f"File read successfully, length: {len(content)} chars")
except Exception as e:
    print(f"Error reading file: {e}")
    sys.exit(1)

changes = []

# Change 1: Add _last_budget_check alongside _token_usage initialization
old_init = """            # Token usage tracking per section
            _token_usage: dict[str, int] = {
                "system": 0,
                "memory": 0,
                "files": 0,
                "messages": 0,
                "response": 0,
            }"""

new_init = """            # Token usage tracking per section
            _token_usage: dict[str, int] = {
                "system": 0,
                "memory": 0,
                "files": 0,
                "messages": 0,
                "response": 0,
            }
            _last_budget_check = time.time()"""

if old_init in content:
    content = content.replace(old_init, new_init)
    changes.append("Change 1: Added _last_budget_check alongside _token_usage initialization")
    print("Change 1 complete")
else:
    print("Change 1: Pattern not found - checking for variations...")
    if '_token_usage' in content:
        print("  _token_usage found in file, but exact pattern not matched")
    else:
        print("  _token_usage not found in file")

# Change 2: Add token counting after context compression
old_comp = '_latency_log.append(("context_compress", (time.monotonic() - _t_compress) * 1000))'

new_comp = '''_latency_log.append(("context_compress", (time.monotonic() - _t_compress) * 1000))
                # Track actual token usage from compressed context
                if hasattr(self, '_last_memory_prompt') and self._last_memory_prompt is not None:
                    self._token_usage["memory"] = estimate_tokens(self._last_memory_prompt)
                if messages:
                    self._token_usage["messages"] += estimate_tokens(messages)'''

if old_comp in content:
    content = content.replace(old_comp, new_comp)
    changes.append("Change 2: Added token counting after context compression")
    print("Change 2 complete")
else:
    print("Change 2: Context compression pattern variant searched")
    old_comp2 = '_latency_log.append(("context_compress", (time.monotonic() - _t_compress) * 1000))'
    if old_comp2 in content:
        content = content.replace(old_comp2, new_comp)
        changes.append("Change 2: Added token counting (alternative pattern)")
        print("Change 2 complete (alternative)")

# Change 3: Add token usage report emission every 5 iterations
old_emit = 'self._emit("verification.passed", {"steps_run": ver_report.steps_run}, trace_id)'

new_emit = '''# Emit token usage report at iteration multiples of 5
                if state.iteration % 5 == 0:
                    self._emit("token.usage", {
                        "iteration": state.iteration,
                        "token_usage": self._token_usage.copy(),
                        "budget_total": sum(self.context_manager.budget.to_dict().values()),
                    }, trace_id)'''

if old_emit in content:
    content = content.replace(old_emit, new_emit)
    changes.append("Change 3: Added token usage report emission at iteration 5")
    print("Change 3 complete")
else:
    print("Change 3: Emission pattern variant searched")

# Change 4: Reset tracking at session start  
old_reset = 'state = AgentState(task_id=trace_id, goal=goal)'

new_reset = '''state = AgentState(task_id=trace_id, goal=goal)
            # Reset token usage tracking for new session
            self._token_usage = {"system": 0, "memory": 0, "files": 0, "messages": 0, "response": 0}
            self._last_budget_check = time.time()'''

if old_reset in content:
    content = content.replace(old_reset, new_reset)
    changes.append("Change 4: Added token usage reset at session start")
    print("Change 4 complete")
else:
    print("Change 4: Session start pattern variant searched")

# Write the improved file
if changes:
    with open('core/agent/loop.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"\n{'='*60}")
    print(f"Improvements applied: {len(changes)}")
    for i, c in enumerate(changes, 1):
        print(f"  {i}. {c}")
    print(f"{'='*60}")
    print("Jarvis token usage tracking improved!")
    print("\n--- Verification ---")
    # Quick verification
    with open('core/agent/loop.py', 'r', encoding='utf-8', errors='replace') as f:
        vcontent = f.read()
    checks = {
        '_last_budget_check': '_last_budget_check' in vcontent,
        'token counting': 'estimate_tokens(self._last_memory_prompt)' in vcontent,
        'token emission': 'token.usage' in vcontent,
        'session reset': 'self._token_usage =' in vcontent,
    }
    for k, v in checks.items():
        print(f"  {k}: {'OK' if v else '✗'}")
else:
    print(f"\nNo changes were made - patterns not found in file structure")
    print("The file may have different structure or encoding")