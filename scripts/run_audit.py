#!/usr/bin/env python3
"""Run focused JARVIS audit."""
from __future__ import annotations

from pathlib import Path

import json
import re
import subprocess
import sys

results = {}

venv = r"C:\Users\aayan\Desktop\JARVIS\.venv"
exclude = "venv,_quarantine,research_files"

repo_root = Path(__file__).resolve().parents[1]

# 1. pytest - fast
print("Running pytest...")
proc = subprocess.run(
    [sys.executable, "-m", "pytest", "--tb=short", "-q"],
    cwd=repo_root,
    capture_output=True, timeout=60,
)
try:
    output = proc.stdout.decode('utf-8', errors='replace')
except Exception:
    output = proc.stdout.decode('cp1252', errors='replace')
results["pytest"] = {
    "output": output
}
m = re.search(r'(\d+)\s+passed', output.lower())
if m:
    results["pytest"]["passed"] = int(m.group(1))
    results["pytest"]["status"] = "GREEN"
else:
    results["pytest"]["status"] = "CHECK_OUTPUT"

# 2. ruff check - fast
print("Running ruff check...")
proc = subprocess.run(
    [sys.executable, "-m", "ruff", "check", "--select=E,F,W,UP"],
    cwd=repo_root,
    capture_output=True, timeout=60,
)
try:
    output = proc.stdout.decode('utf-8', errors='replace')
except Exception:
    output = proc.stdout.decode('cp1252', errors='replace')
results["ruff"] = {
    "output": output
}
error_count = sum(
    1 for line in output.splitlines()
    if 'error:' in line.lower() or line.strip().startswith('JARVIS')
)
results["ruff"]["error_count"] = error_count

# 3. bandit - focused on active tree only
print("Running bandit (active tree)...")
proc = subprocess.run(
    [sys.executable, "-m", "bandit", "-r", ".", "--exclude", venv, "--quiet", "-f", "json"],
    cwd=repo_root,
    capture_output=True, timeout=60,
)
try:
    bandit_data = json.loads(proc.stdout)
    totals = bandit_data.get("metrics", {}).get("_totals", {})
    results["bandit"] = {
        "HIGH": totals.get("SEVERITY.HIGH", 0),
        "MEDIUM": totals.get("SEVERITY.MEDIUM", 0),
        "LOW": totals.get("SEVERITY.LOW", 0),
        "loc": totals.get("loc", 0),
    }
except Exception as e:
    results["bandit"] = {"error": str(e)}

# 4. pip check
print("Running pip check...")
proc = subprocess.run(
    [sys.executable, "-m", "pip", "check"],
    cwd=repo_root,
    capture_output=True, timeout=60,
)
try:
    output = proc.stdout.decode('utf-8', errors='replace') + proc.stderr.decode('utf-8', errors='replace')
except Exception:
    output = proc.stdout.decode('cp1252', errors='replace') + proc.stderr.decode('cp1252', errors='replace')
results["pip_check"] = {
    "status": "OK" if "No broken requirements" in output else "ISSUES",
    "output": output,
}

# 5. mypy - focused
print("Running mypy...")
proc = subprocess.run(
    [sys.executable, "-m", "mypy", "."],
    cwd=repo_root,
    capture_output=True, timeout=60,
)
try:
    output = proc.stdout.decode('utf-8', errors='replace') + proc.stderr.decode('utf-8', errors='replace')
except Exception:
    output = proc.stdout.decode('cp1252', errors='replace') + proc.stderr.decode('cp1252', errors='replace')
results["mypy"] = {
    "output": output
}

# Write results
try:
    audit_results_path = repo_root / "audit_results.json"
    with audit_results_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
except Exception as e:
    print("Could not write audit results:", e)
