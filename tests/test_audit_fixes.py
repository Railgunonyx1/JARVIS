"""Regression tests for the audit's remediation items.

Covers executor forbidden-code patterns: word boundaries, ALL matches
reported, benign identifiers must not false-positive.
"""

import sys
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
