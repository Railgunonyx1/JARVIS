#!/usr/bin/env python3
import json
from pathlib import Path

_here = Path(__file__).resolve().parent
_audits = _here.parent / "audits"

# Read bandit after
with open(_audits / "bandit_after.json") as f:
    d = json.load(f)
t = d["metrics"]["_totals"]
print(
    f"BANDIT AFTER: "
    f"HIGH={t['SEVERITY.HIGH']} "
    f"MEDIUM={t['SEVERITY.MEDIUM']} "
    f"LOW={t['SEVERITY.LOW']} "
    f"loc={t['loc']}"
)

# Read bandit before (in audits folder)
with open(_audits / "bandit_before.json") as f:
    d2 = json.load(f)
t2 = d2["metrics"]["_totals"]
print(
    f"BANDIT BEFORE: "
    f"HIGH={t2['SEVERITY.HIGH']} "
    f"MEDIUM={t2['SEVERITY.MEDIUM']} "
    f"LOW={t2['SEVERITY.LOW']} "
    f"loc={t2['loc']}"
)

# Read current bandit
try:
    current = _audits / "bandit_current.json"
    with open(current) as f:
        d3 = json.load(f)
    t3 = d3["metrics"]["_totals"]
    print(
        f"BANDIT CURRENT: "
        f"HIGH={t3['SEVERITY.HIGH']} "
        f"MEDIUM={t3['SEVERITY.MEDIUM']} "
        f"LOW={t3['SEVERITY.LOW']} "
        f"loc={t3['loc']}"
    )
except OSError:
    print("No current bandit.json found")

# Read audit results
try:
    results = Path("audit_results.json")
    with open(results) as f:
        ar = json.load(f)
    print("\nPYTEST:", ar["pytest"]["status"], "(", ar["pytest"].get("passed", "?"), "passed)")
    print("RUFF errors:", ar["ruff"]["error_count"])
    print("PIP CHECK:", ar["pip_check"]["status"])
except OSError:
    print("\nNo audit_results.json found")
