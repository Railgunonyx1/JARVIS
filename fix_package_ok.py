#!/usr/bin/env python3
"""Fix #7: package_ok default change"""
import sys

# Read the file
with open('_archive\2026-08-15_terminal_first\ui\providers.py', 'r') as f:
    content = f.read()

# The old pattern
old = """online = bool(info.get("available")) and bool(info.get("package_ok", True))
        rows.append((name.upper(), "ONLINE" if online else "OFFLINE",
                     latency, rate, str(info.get("model", "unknown"))))"""

# The new pattern
new = """has_package = info.get("package_ok", None)  # None = unknown
        online = bool(info.get("available")) and (
            has_package is True or (has_package is None and info.get("available") is True)
        )
        rows.append((name.upper(), "ONLINE" if online else "OFFLINE",
                     latency, rate, str(info.get("model", "unknown"))))"""

if old in content:
    content = content.replace(old, new)
    print('✅ Fix #7 applied: package_ok default')
    with open('_archive\2026-08-15_terminal_first\ui\providers.py', 'w') as f:
        f.write(content)
    print('✅ File written')
else:
    print('! Fix #7 pattern not found (may already be patched)')
    print('! Old pattern:')
    print(repr(old))
    print('! New pattern:')
    print(repr(new))
"