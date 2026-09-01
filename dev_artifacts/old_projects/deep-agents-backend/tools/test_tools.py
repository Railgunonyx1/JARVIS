"""Test tools — test discovery, execution, and analysis for the agent."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from tools.schema import ToolResult, tool_result, truncate

logger = logging.getLogger("jarvis.tools.test")

_MAX_OUTPUT = 8000


def _run_test_cmd(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
    """Run a test command and return (returncode, stdout, stderr)."""
    cmd = [sys.executable, "-m"] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(Path.cwd()), check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", "python not found"
    except subprocess.TimeoutExpired:
        return -1, "", f"test command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


async def test_discover(params: dict) -> ToolResult:
    """Discover test files and test count in the project.

    Parameters
    ----------
    path : str
        Directory to search. Default current directory.
    pattern : str
        File glob pattern. Default 'test_*.py'.
    """
    search_path = Path(params.get("path", "."))
    pattern = params.get("pattern", "test_*.py")
    cwd = Path.cwd()
    if not search_path.is_absolute():
        search_path = cwd / search_path
    search_path = search_path.resolve()
    test_files = list(search_path.rglob(pattern))
    if not test_files:
        return tool_result(True, output=f"No test files found matching '{pattern}' in {search_path}")
    # Count test functions
    total_tests = 0
    file_details = []
    for f in test_files[:30]:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            count = content.count("def test_") + content.count("async def test_")
            total_tests += count
            try:
                rel = f.relative_to(cwd)
            except ValueError:
                rel = f
            file_details.append(f"  {rel} ({count} tests)")
        except Exception:
            try:
                rel = f.relative_to(cwd)
            except ValueError:
                rel = f
            file_details.append(f"  {rel} (unreadable)")
    header = f"Found {len(test_files)} test files, ~{total_tests} tests"
    output = header + "\n" + "\n".join(file_details)
    return tool_result(True, output=truncate(output, _MAX_OUTPUT))


async def test_run_target(params: dict) -> ToolResult:
    """Run specific test files or test functions.

    Parameters
    ----------
    target : str
        Test file, directory, or specific test (e.g. 'tests/test_foo.py::test_bar').
    args : str
        Additional pytest arguments (e.g. '-v --tb=short').
    timeout : int
        Timeout in seconds. Default 120.
    """
    target = params.get("target", "")
    if not target:
        return tool_result(False, error="target is required")
    extra_args = params.get("args", "-v --tb=short")
    timeout = min(int(params.get("timeout", 120)), 300)
    args_list = ["pytest", target] + extra_args.split()
    code, out, err = _run_test_cmd(args_list, timeout=timeout)
    output = out or err or "(no output)"
    return tool_result(code == 0, output=truncate(output, _MAX_OUTPUT))


async def test_failed(params: dict) -> ToolResult:
    """Show only failed tests from the last run.

    Parameters
    ----------
    target : str
        Test file or directory. Default project root.
    """
    target = params.get("target", ".")
    code, out, err = _run_test_cmd(["pytest", target, "-v", "--tb=short", "--no-header", "-q"])
    # Filter for FAILED lines
    failed_lines = []
    for line in (out + "\n" + err).splitlines():
        if "FAILED" in line or "ERROR" in line or "assert" in line.lower():
            failed_lines.append(line)
    if not failed_lines:
        if code == 0:
            return tool_result(True, output="All tests passed!")
        return tool_result(True, output="No failed tests found (check output manually).")
    output = "\n".join(failed_lines[:30])
    return tool_result(code != 0, output=truncate(output, _MAX_OUTPUT))


async def test_coverage(params: dict) -> ToolResult:
    """Run tests with coverage reporting.

    Parameters
    ----------
    target : str
        Test file or directory. Default project root.
    source : str
        Source directory to measure coverage for.
    """
    target = params.get("target", ".")
    source = params.get("source", ".")
    args = [
        "pytest", target,
        f"--cov={source}",
        "--cov-report=term-missing",
        "-q",
        "--tb=short",
    ]
    code, out, err = _run_test_cmd(args, timeout=180)
    # Extract coverage summary
    lines = (out + "\n" + err).splitlines()
    coverage_lines = [
        line for line in lines
        if "TOTAL" in line or "Name" in line
        or "coverage" in line.lower() or line.strip().endswith("%")
    ]
    if coverage_lines:
        output = "\n".join(coverage_lines[:15])
    else:
        output = out or err or "(no coverage output)"
    return tool_result(code == 0, output=truncate(output, _MAX_OUTPUT))


async def test_run(params: dict) -> ToolResult:
    target = params.get("path", ".")
    markers = params.get("markers", "")
    verbose = params.get("verbose", False)
    args = ["pytest", target, "--tb=short", "--no-header", "-q"]
    if markers:
        args.extend(["-m", markers])
    if verbose:
        args.append("-v")
    code, out, err = _run_test_cmd(args, timeout=300)
    lines = (out or err or "(no output)").splitlines()
    summary = [line for line in lines if "passed" in line or "failed" in line or "error" in line or "warning" in line]
    output = "\n".join(summary[-5:]) if summary else (out or err or "(no output)")
    return tool_result(code == 0, output=truncate(output, _MAX_OUTPUT))


async def test_benchmark(params: dict) -> ToolResult:
    target = params.get("path", ".")
    code, out, err = _run_test_cmd(
        ["pytest", target, "--benchmark-only", "-q"], timeout=120,
    )
    if code != 0 and ("unknown option" in (err or "") or "benchmark" in (err or "")):
        code, out, err = _run_test_cmd(
            ["pytest", target, "-q", "--durations=10"], timeout=120,
        )
    output = out or err or "(no benchmark output)"
    return tool_result(code == 0, output=truncate(output, _MAX_OUTPUT))
