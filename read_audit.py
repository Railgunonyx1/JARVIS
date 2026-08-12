#!/usr/bin/env python3
import json

# Read bandit after
with open(r'C:\Users\aayan\Desktop\JARVIS\audits\bandit_after.json') as f:
    d = json.load(f)
t = d['metrics']['_totals']
print(f"BANDIT AFTER: HIGH={t['SEVERITY.HIGH']} MEDIUM={t['SEVERITY.MEDIUM']} LOW={t['SEVERITY.LOW']} loc={t['loc']}")

# Read bandit before (in audits folder)
with open(r'C:\Users\aayan\Desktop\JARVIS\audits\bandit_before.json') as f:
    d2 = json.load(f)
t2 = d2['metrics']['_totals']
print(f"BANDIT BEFORE: HIGH={t2['SEVERITY.HIGH']} MEDIUM={t2['SEVERITY.MEDIUM']} LOW={t2['SEVERITY.LOW']} loc={t2['loc']}")

# Read current bandit
try:
    with open(r'C:\Users\aayan\Desktop\JARVIS\bandit_current.json') as f:
        d3 = json.load(f)
    t3 = d3['metrics']['_totals']
    print(f"BANDIT CURRENT: HIGH={t3['SEVERITY.HIGH']} MEDIUM={t3['SEVERITY.MEDIUM']} LOW={t3['SEVERITY.LOW']} loc={t3['loc']}")
except:
    print("No current bandit.json found")

# Read audit results
try:
    with open(r'C:\Users\aayan\Desktop\JARVIS\audit_results.json') as f:
        ar = json.load(f)
    print(f"\nPYTEST: {ar['pytest']['status']} ({ar['pytest'].get('passed', '?')} passed)")
    print(f"RUFF errors: {ar['ruff']['error_count']}")
    print(f"PIP CHECK: {ar['pip_check']['status']}")
except:
    print("\nNo audit_results.json found")
