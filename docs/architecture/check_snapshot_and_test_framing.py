#!/usr/bin/env python3
"""regression: only canonical runtime references, not one-off comments, are valid."""
from __future__ import annotations

from runtime.kernel import JarvisRuntime

READONLY_SNAPSHOT_HEADING = "# READ-ONLY SNAPSHOT — NOT A LIVE AUDIT"
EXPECTED_CONFIG = {
    "branch": "dynamic-island",
    "commit": "0ad5497",
    "remote_commit": "0ad5497",
    "credential_helper": "store,cache",
}

KNOWN_VALID_RUNTIME_REFERENCE_COUNT = 3

def check_readonly_snapshot_framing(
    path: str = "docs/architecture/FULL-REPOSITORY-COUCIL-AUDIT.md",
) -> tuple[bool, str]:
    """Confirm the read-only snapshot prefaces the document and is not silently
    treated as current repository status by assertions on this file."""
    try:
        data = open(path, encoding="utf-8", errors="replace").read()
    except OSError as e:
        return False, f"cannot read {path}: {e}"

    heading_present = READONLY_SNAPSHOT_HEADING in data
    if not heading_present:
        return False, "READ-ONLY SNAPSHOT heading missing from the audit document"

    opening_note_present = "preserved for traceability" in data
    if not opening_note_present:
        return False, "READ-ONLY SNAPSHOT opening traceability note missing"

    return True, "read-only snapshot framing present and kept verbatim"

def check_frozen_stale_assertion_removed(path: str = "tests/desktop/test_backend_smoke.py") -> tuple[bool, str]:
    """The previously accepted stale form used only an agent loop guard and did
    not name the canonical runtime harness path."""
    try:
        data = open(path, encoding="utf-8", errors="replace").read()
    except OSError as e:
        return False, f"cannot read {path}: {e}"

    stale = "runtime.agent_loop.harness is not None"
    if stale in data:
        return False, f"legacy stale form still present: {stale!r}"

    canonical = "runtime.harness_selector.active is not None"
    if canonical not in data:
        return False, "canonical runtime assertion missing after correction"

    return True, "legacy stale assertion removed; canonical runtime assertion present"

if __name__ == "__main__":
    def _run() -> int:
        failures: list[str] = []

        ok, msg = check_readonly_snapshot_framing()
        if not ok:
            failures.append(msg)

        ok, msg = check_frozen_stale_assertion_removed()
        if not ok:
            failures.append(msg)

        if failures:
            for f in failures:
                print(f"FAIL: {f}", file=__import__("sys").stderr)
            return 1
        print("OK: doc snapshot framed as read-only; stale test assertion removed; canonical runtime reference present")
        return 0

    raise SystemExit(_run())
