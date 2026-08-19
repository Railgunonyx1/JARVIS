#!/usrusr/bin/env python3
"""Run new JARVIS audit and report results."""
import json
import os


def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

print("=" * 60)
print("JARVIS MK-X - NEW SYSTEM AUDIT")
print("=" * 60)

# 1. Bandit security audit
print("\n--- Bandit Security Audit ---")
before = load_json('audits/bandit_before.json')
after = load_json('audits/bandit_after.json')

if before and after:
    bt = before['metrics']['_totals']
    at = after['metrics']['_totals']
    print(f"Before: HIGH={bt['SEVERITY.HIGH']} MEDIUM={bt['SEVERITY.MEDIUM']} LOW={bt['SEVERITY.LOW']}")
    print(f"After:  HIGH={at['SEVERITY.HIGH']} MEDIUM={at['SEVERITY.MEDIUM']} LOW={at['SEVERITY.LOW']}")
    print(f"Delta:  HIGH {at['SEVERITY.HIGH']-bt['SEVERITY.HIGH']} MEDIUM {at['SEVERITY.MEDIUM']-bt['SEVERITY.MEDIUM']} LOW {at['SEVERITY.LOW']-bt['SEVERITY.LOW']}")
else:
    print("bandit_before.json or bandit_after.json not found")

# 2. Pytest results
print("\n--- Test Suite ---")
results_file = load_json('audit_results.json')
if results_file and 'pytest' in results_file:
    r = results_file['pytest']
    if isinstance(r.get('passed'), int):
        print(f"Tests passed: {r['passed']}")
    else:
        print(f"Status: {r.get('status', 'unknown')}")
else:
    # Check pytest output
    if os.path.exists('audits/pytest_output.txt'):
        print("audits/pytest_output.txt found (see file for details)")
    else:
        print("No pytest results available")

# 3. Ruff lint
print("\n--- Ruff Lint ---")
if os.path.exists('audits/ruff_output.txt'):
    print("audits/ruff_output.txt found (see file for details)")
else:
    print("No ruff results available")

# 4. Pip check
print("\n--- Dependency Check ---")
# pip check status
print("pip check: Running...")
import subprocess

proc = subprocess.run(['python', '-m', 'pip', 'check'], capture_output=True, text=True, cwd='C:\\Users\\aayan\\Desktop\\JARVIS')
output = proc.stdout + proc.stderr
if 'No broken requirements' in output:
    print("No broken requirements - OK")
else:
    print("Issues found - see output above")

# 5. Mypy
print("\n--- Type Checking ---")
if os.path.exists('audits/mypy_report.txt'):
    print("audits/mypy_report.txt found")
else:
    print("No mypy report available")

# 6. Summary
print("\n" + "=" * 60)
print("AUDIT COMPLETE")
print("=" * 60)
