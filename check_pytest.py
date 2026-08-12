#!/usr/bin/env python3
import subprocess
import sys

proc = subprocess.run(
    [sys.executable, "-m", "pytest", "--tb=short", "-q"],
    cwd="C:\\Users\\aayan\\Desktop\\JARVIS",
    capture_output=True, timeout=120
)
output = proc.stdout.decode('utf-8', errors='replace') + proc.stderr.decode('utf-8', errors='replace')
print(output)
# Extract passed count
import re

m = re.search(r'(\d+)\s+passed', output.lower())
if m:
    print(f"\nPASSED: {m.group(1)}")
else:
    print("\nCould not parse passed count")
