"""Regression tests for the audit's remediation items.

Covers the two fixes that were genuinely outstanding:

- executor forbidden-code patterns use word boundaries and report ALL
  matches (previously only the first); benign identifiers like
  ``postsystem`` / ``evaluate`` / ``exclusive`` must not false-positive.
- telemetry ``mark_error`` records the real elapsed time since the stage
  started (the old code used ``time.perf_counter() * 1000``, which is a
  wall-clock value, not a duration), and ``track()`` records a failed
  stage exactly once with the error flag set.

Fixes 1/3/4/6 from the audit were already implemented in the current
codebase (sqlite-vec KNN store, config-driven planner models, 5-min
health cache, 30s API-key cache TTL) and are not re-tested here.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── executor: forbidden-code patterns ────────────────────────────────────────

def test_forbidden_os_system_matches_direct_usage():
    from core.executor import _check_generated_code
    with pytest.raises(RuntimeError) as exc:
        _check_generated_code("import os\nos.system('rm -rf /')")
    assert "os" in str(exc.value) and "system" in str(exc.value)


def test_forbidden_eval_matches_direct_usage():
    from core.executor import _check_generated_code
    with pytest.raises(RuntimeError) as exc:
        _check_generated_code("eval('__import__(\"os\")')")
    assert "eval" in str(exc.value)


def test_forbidden_pattern_does_not_match_postsystem():
    from core.executor import _FORBIDDEN_CODE_PATTERNS
    lowered = "x = postsystem_variable".lower()
    matched = [p.pattern for p in _FORBIDDEN_CODE_PATTERNS if p.search(lowered)]
    assert matched == []


def test_forbidden_eval_does_not_match_evaluate():
    from core.executor import _FORBIDDEN_CODE_PATTERNS
    lowered = "result = evaluate(input)".lower()
    matched = [p.pattern for p in _FORBIDDEN_CODE_PATTERNS if p.search(lowered)]
    assert matched == []


def test_forbidden_exec_does_not_match_exclusive():
    from core.executor import _FORBIDDEN_CODE_PATTERNS
    lowered = "flag = exclusive".lower()
    matched = [p.pattern for p in _FORBIDDEN_CODE_PATTERNS if p.search(lowered)]
    assert matched == []


def test_forbidden_socket_connect_matches():
    from core.executor import _check_generated_code
    with pytest.raises(RuntimeError):
        _check_generated_code("import socket\nsocket.connect(('host', 443))")


def test_forbidden_bare_socket_call_matches():
    from core.executor import _check_generated_code
    with pytest.raises(RuntimeError):
        _check_generated_code("s = socket('AF_INET', 1)")


def test_forbidden_socket_does_not_match_postsocket():
    from core.executor import _FORBIDDEN_CODE_PATTERNS
    lowered = "name = postsocket_handler".lower()
    matched = [p.pattern for p in _FORBIDDEN_CODE_PATTERNS if p.search(lowered)]
    assert matched == []


def test_forbidden_reports_all_matches_not_just_first():
    from core.executor import _check_generated_code
    code = "import os\neval(x)\nsubprocess.run('ls')"
    with pytest.raises(RuntimeError) as exc:
        _check_generated_code(code)
    msg = str(exc.value)
    assert "eval" in msg
    assert "subprocess" in msg
    assert "os.system" not in msg  # present in code but not in the reject list


def test_forbidden_allows_benign_code():
    from core.executor import _check_generated_code
    _check_generated_code(
        "def add(a, b):\n    return a + b\n\nprint(add(1, 2))"
    )


# ── telemetry: mark_error / track ────────────────────────────────────────────

def test_mark_error_records_real_elapsed_not_perf_counter():
    from core.telemetry import LatencyTracker
    t = LatencyTracker()
    t.start_request()
    t.mark("start_llm")
    time.sleep(0.01)
    t.mark_error("llm")
    stage = t.get_summary()["stages"]["llm"]
    assert stage["errors"] == 1
    # Real elapsed (~10ms), not time.perf_counter()*1000 which is millions.
    assert 1.0 <= stage["last_ms"] < 1000


def test_track_records_failure_once_with_error_flag():
    from core.telemetry import LatencyTracker
    t = LatencyTracker()
    with pytest.raises(ValueError):
        with t.track("stt"):
            raise ValueError("boom")
    stage = t.get_summary()["stages"]["stt"]
    assert stage["count"] == 1
    assert stage["errors"] == 1


def test_track_records_success_once_without_error():
    from core.telemetry import LatencyTracker
    t = LatencyTracker()
    with t.track("stt"):
        pass
    stage = t.get_summary()["stages"]["stt"]
    assert stage["count"] == 1
    assert stage["errors"] == 0


def test_mark_error_without_tracked_start_falls_back_to_floor():
    from core.telemetry import LatencyTracker
    t = LatencyTracker()
    t.mark_error("never_started")
    stage = t.get_summary()["stages"]["never_started"]
    assert stage["errors"] == 1
    assert stage["last_ms"] >= 1.0
