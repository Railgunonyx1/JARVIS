"""Shell Executor — run commands, scripts, and system operations for JARVIS MK-X.

Runs commands in a sandboxed subprocess with timeout and output capture.

Security: raw shell/powershell commands are denied-by-default. Only commands
matching a SAFE_ALLOWLIST (and not in DANGEROUS_BLOCKLIST) may run. Python and
pip execution are allowed (they run in a subprocess with cwd=HOME).
"""

import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger("jarvis.actions.shell_exec")

HOME = Path.home()
TIMEOUT = 30  # seconds

# Commands that are considered safe for JARVIS to run by default.
SAFE_ALLOWLIST = (
    "dir", "ls", "cd", "pwd", "echo", "type", "cat", "more", "findstr", "grep",
    "ipconfig", "systeminfo", "tasklist", "netstat", "ping", "tracert", "nslookup",
    "getmac", "hostname", "whoami", "ver", "vol", "path",
    "git status", "git log", "git diff", "git branch",
    "where", "tree", "chdir",
)

# Destructive / system-modifying commands — always denied (blocklist wins).
DANGEROUS_BLOCKLIST = (
    "format", "deltree", "del /s", "rmdir /s", "rd /s", "rm -rf",
    "shutdown", "reboot", "restart-computer", "stop-computer",
    "taskkill /f", "taskkill /im", "kill -9", "killall",
    "reg delete", "reg add", "regedt32",
    "diskpart", "cleanmgr",
    "net user", "net localgroup", "net share", "sc stop", "sc delete",
    "powershell remove", "powershell -command remove-item -recurse",
    "del /f", "erase", "truncate", "mkfs", "fdisk", "dd if=",
    "schtasks /delete", "bcdedit",
    "stop-service", "disable-windowsupdate", "remove-item",
    "del .", "del *", "format c:",
)

# Single-token command names that must NOT run when seen first in the command.
_BLOCKED_FIRST = {
    "format", "deltree", "diskpart", "mkfs", "fdisk", "dd",
    "shutdown", "reboot", "poweroff", "halt",
}


def _is_allowed(command: str) -> tuple:
    """Return (allowed: bool, reason: str) for a raw shell command."""
    stripped = command.strip()
    if not stripped:
        return True, ""
    lowered = stripped.lower()
    first = re.split(r"[\s|;&]|&&|\|\|", lowered)[0].strip()
    if first in _BLOCKED_FIRST:
        return False, f"command '{first}' is blocked"
    for bad in DANGEROUS_BLOCKLIST:
        if bad in lowered:
            return False, f"matches blocked pattern '{bad}'"
    for good in SAFE_ALLOWLIST:
        if lowered == good or lowered.startswith(good + " ") or lowered.startswith(good + "/"):
            return True, ""
    return False, "command not in the safe allowlist"


def shell_action(action: str, parameters: dict, **kwargs) -> str:
    """Dispatch shell operations."""
    handlers = {
        "run": _run_command,
        "powershell": _run_powershell,
        "python": _run_python,
        "pip": _run_pip,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown shell action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("Shell action '%s' failed: %s", action, e)
        return f"Shell operation failed: {e}"


def _run_command(params: dict) -> str:
    """Run a shell command (allowlisted only)."""
    cmd = params.get("command", "")
    if not cmd:
        return "No command provided"

    allowed, reason = _is_allowed(cmd)
    if not allowed:
        logger.warning("Shell command blocked: %s (%s)", cmd, reason)
        return f"Command blocked: {reason}"

    timeout = params.get("timeout", TIMEOUT)
    cwd = params.get("cwd", str(HOME))

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        output = result.stdout.strip()
        error = result.stderr.strip()

        parts = []
        if output:
            parts.append(output)
        if error:
            parts.append(f"STDERR:\n{error}")
        if result.returncode != 0:
            parts.append(f"Exit code: {result.returncode}")

        return "\n".join(parts) if parts else "Command completed (no output)"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Command failed: {e}"


def _run_powershell(params: dict) -> str:
    """Run a PowerShell command (deny-by-default; allowlist for common read-only cmdlets)."""
    cmd = params.get("command", "")
    if not cmd:
        return "No PowerShell command provided"

    lowered = cmd.strip().lower()
    safe_ps = (
        "get-", "gci", "ls", "dir", "echo", "write-output", "getdate",
        "whoami", "hostname", "get-process", "ps", "get-service",
        "get-childitem", "test-path", "get-item", "measure-command",
        "get-wmiobject", "get-ciminstance", "get-netipaddress",
        "get-eventlog", "get-content", "gc",
    )
    if not (lowered.startswith(safe_ps) or any(lowered.startswith(s) for s in safe_ps)):
        logger.warning("PowerShell command blocked: %s", cmd)
        return "PowerShell command blocked: only read-only cmdlets are allowed"

    timeout = params.get("timeout", TIMEOUT)

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout.strip()
        error = result.stderr.strip()

        parts = []
        if output:
            parts.append(output)
        if error:
            parts.append(f"STDERR:\n{error}")

        return "\n".join(parts) if parts else "PowerShell command completed (no output)"
    except subprocess.TimeoutExpired:
        return f"PowerShell command timed out after {timeout}s"
    except Exception as e:
        return f"PowerShell command failed: {e}"


def _run_python(params: dict) -> str:
    """Run a Python script or expression."""
    code = params.get("code", "")
    if not code:
        return "No Python code provided"

    timeout = params.get("timeout", TIMEOUT)

    # If it's a single line expression, wrap it
    if "\n" not in code and not code.strip().startswith(("import", "from", "def", "class", "for", "while", "if")):
        code = f"print({code})"

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            tmp = f.name

        result = subprocess.run(
            [sys.executable, tmp],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(HOME),
        )
        os.unlink(tmp)

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode == 0:
            return output if output else "Python code completed (no output)"
        return f"Python error:\n{error}" if error else "Python code failed"
    except subprocess.TimeoutExpired:
        return f"Python code timed out after {timeout}s"
    except Exception as e:
        return f"Python execution failed: {e}"


def _run_pip(params: dict) -> str:
    """Run pip install/uninstall."""
    packages = params.get("packages", "")
    action = params.get("action", "install")

    if not packages:
        return "No packages specified"

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", action, packages],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode == 0:
            return f"Pip {action} succeeded:\n{output[-500:]}" if output else f"Pip {action} succeeded"
        return f"Pip {action} failed:\n{error[-500:]}" if error else f"Pip {action} failed"
    except subprocess.TimeoutExpired:
        return "Pip command timed out"
    except Exception as e:
        return f"Pip failed: {e}"
