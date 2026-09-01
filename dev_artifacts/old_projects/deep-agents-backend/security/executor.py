"""Secure Executor — the single authoritative boundary for OS command execution.

Every agent-controlled OS command must pass through here. Two execution forms:

- STRUCTURED: an executable plus an explicit argument list, run with
  ``subprocess(..., shell=False)``. This is always preferred.
- GOVERNED SHELL: a script string run through an approved shell host
  (PowerShell or cmd) passed as ``-Command``/``/c`` argv. The script is
  validated against shell operators and dangerous command patterns first.

CommandPolicy decides which form applies (or rejects the request outright);
SecureExecutor runs the process with a sanitized environment, a constrained
working directory, a hard timeout with process-tree termination, and bounded
output capture.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import signal
import subprocess  # nosec B404 -- subprocess is required for the executor; see module docstring
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("jarvis.security.executor")

MAX_OUTPUT_BYTES = 1024 * 1024  # 1 MB
DEFAULT_TIMEOUT = 60

# Credential-like env var names removed before any process is spawned.
_SECRET_PATTERNS = (
    "api_key", "apikey", "token", "secret", "password", "credential",
    "authorization", "groq", "gemini", "openrouter", "opencode", "openai",
)

# Shell metacharacters / operator sequences that indicate chaining, command
# substitution, or redirection. Never allowed in a governed-shell script.
_SHELL_OPERATORS = (
    "&&", "&", "||", ";", "|", "`", "$(", "${", "\n", "\r", "\x00",
    ">", ">>", "<", "2>&1", ">&", "^",
)

# Executables that are never allowed, by basename (case-insensitive).
_BLOCKED_EXECUTABLES = (
    "shutdown", "reboot", "restart", "bcdedit", "diskpart", "format",
    "rd", "rmdir", "deltree", "reg.exe", "taskkill",
)

# Dangerous command fragments checked in governed-shell scripts.
_DANGEROUS_PATTERNS = (
    r"\bformat\b", r"\brd\b", r"\brmdir\b", r"\bdeltree\b",
    r"\bdel\s+/[sqf]", r"\brm\s+-[rf]", r"\bshutdown\b", r"\breboot\b",
    r"\bbcdedit\b", r"\bdiskpart\b", r"\breg\s+(add|delete)\b",
    r"\bInvoke-Expression\b", r"\bIEX\b", r"\bRemove-Item\b",
    r"\b(New-Object|\[System\.Diagnostics\.Process\])\b",
)


class ExecMode(Enum):
    """How a request is allowed to run."""
    BLOCKED = "blocked"
    STRUCTURED = "structured"
    POWERSHELL = "powershell"
    CMD = "cmd"


def sanitize_environment(env: dict[str, str] | None = None) -> dict[str, str]:
    """Environment copy with credential-like variables removed."""
    base = dict(os.environ)
    for key in list(base):
        lower = key.lower()
        if any(pattern in lower for pattern in _SECRET_PATTERNS):
            base.pop(key, None)
    if env:
        base.update({k: v for k, v in env.items()
                     if not any(p in k.lower() for p in _SECRET_PATTERNS)})
    return base


def _resolve_executable(name: str) -> str | None:
    """Resolve an executable name/path to an absolute path, if possible."""
    name = name.strip().strip('"')
    if not name:
        return None
    if os.path.isabs(name):
        return name if os.path.isfile(name) else None
    found = shutil.which(name)
    return found


@dataclass
class ExecRequest:
    """A command execution request (raw string or structured exe+args)."""
    command: str = ""
    executable: str = ""
    args: list[str] = field(default_factory=list)
    shell: str = ""  # "powershell" | "cmd" | "" (auto)
    cwd: str | None = None
    env: dict[str, str] | None = None
    timeout: int = DEFAULT_TIMEOUT
    max_output_bytes: int = MAX_OUTPUT_BYTES


@dataclass
class ExecResult:
    """Outcome of a secure execution."""
    success: bool = True
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0
    timed_out: bool = False
    blocked: bool = False
    reason: str = ""
    mode: str = ExecMode.STRUCTURED.value

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": round(self.duration_ms, 1),
            "timed_out": self.timed_out,
            "blocked": self.blocked,
            "block_reason": self.reason,
            "mode": self.mode,
        }


def _blocked(reason: str) -> ExecResult:
    return ExecResult(success=False, blocked=True, reason=reason,
                      mode=ExecMode.BLOCKED.value)


class CommandPolicy:
    """Decides whether and how a command may run.

    Checks, in order: executable allow/deny, dangerous patterns, shell
    operators, argument validity, and the working-directory constraint.
    """

    def __init__(
        self,
        blocked_executables: tuple | None = None,
        dangerous_patterns: tuple | None = None,
        shell_operators: tuple | None = None,
        default_shell: str = "powershell",
        allowed_cwds: list[str] | None = None,
        blocked_cwds: list[str] | None = None,
    ) -> None:
        self._blocked_executables = tuple(blocked_executables or _BLOCKED_EXECUTABLES)
        self._dangerous_patterns = tuple(dangerous_patterns or _DANGEROUS_PATTERNS)
        self._shell_operators = tuple(shell_operators or _SHELL_OPERATORS)
        self.default_shell = default_shell if default_shell in ("powershell", "cmd") else "powershell"
        self.allowed_cwds = [os.path.expanduser(d) for d in (allowed_cwds or [
            "~", "~/Desktop", "~/Documents", "~/Downloads", "~/Pictures",
            "~/Music", "~/Videos",
        ])]
        self.blocked_cwds = [os.path.expanduser(d) for d in (blocked_cwds or [
            "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
            "C:\\System32", "C:\\ProgramData", os.path.join(os.path.expanduser("~"), ".ssh"),
        ])]

    # ── classification ─────────────────────────────────────────────────────

    def classify(self, req: ExecRequest) -> ExecMode:
        """Determine the execution mode for a request, or BLOCKED."""
        if req.executable:
            return self._classify_structured(req.executable, req.args)

        command = (req.command or "").strip()
        if not command:
            return ExecMode.BLOCKED

        parts = shlex.split(command, posix=not _is_windows())
        if not parts:
            return ExecMode.BLOCKED

        # Structured when the first token resolves to a real executable.
        exe_path = _resolve_executable(parts[0])
        if exe_path:
            return self._classify_structured(exe_path, parts[1:])

        return self._classify_shell_script(command, req.shell)

    def _classify_structured(self, executable: str, args: list[str]) -> ExecMode:
        exe_base = os.path.basename(executable).lower()
        for blocked in self._blocked_executables:
            if blocked.lower() == exe_base:
                return ExecMode.BLOCKED

        for arg in args:
            if "\x00" in arg:
                return ExecMode.BLOCKED

        return ExecMode.STRUCTURED

    def _classify_shell_script(self, command: str, shell: str) -> ExecMode:
        for op in self._shell_operators:
            if op in command:
                return ExecMode.BLOCKED

        lower = command.lower()
        for pattern in self._dangerous_patterns:
            if re.search(pattern, lower):
                return ExecMode.BLOCKED

        chosen = shell or self.default_shell
        if chosen == "cmd":
            return ExecMode.CMD
        return ExecMode.POWERSHELL

    def _has_operator(self, text: str) -> bool:
        return any(op in text for op in self._shell_operators)

    # ── working directory constraint ───────────────────────────────────────

    def check_cwd(self, cwd: str) -> tuple[bool, str]:
        """Ensure a working directory is inside an allowed area."""
        try:
            resolved = os.path.realpath(cwd)
        except OSError as e:
            return False, f"Invalid working directory: {e}"

        for blocked in self.blocked_cwds:
            if _is_within(resolved, blocked):
                return False, f"Working directory is in a blocked area: {blocked}"

        for allowed in self.allowed_cwds:
            if _is_within(resolved, allowed):
                return True, ""

        # Fall back to project root when the caller did not pin a cwd.
        if os.path.realpath(resolved) == os.path.realpath(_default_project_root()):
            return True, ""
        return False, f"Working directory outside allowed areas: {cwd}"

    def effective_cwd(self, req: ExecRequest) -> str:
        """Resolve the working directory, defaulting to the project root."""
        if req.cwd:
            return os.path.realpath(str(req.cwd))
        return _default_project_root()

    def validate_cwd(self, cwd: str) -> tuple[bool, str]:
        return self.check_cwd(cwd)


def _is_windows() -> bool:
    return os.name == "nt"


def _is_within(path: str, base: str) -> bool:
    """True if ``path`` is inside ``base`` (or equals it)."""
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        return False
    return rel == "." or not (rel.startswith("..") or os.path.isabs(rel))


def _default_project_root() -> str:
    try:
        from core.project import ProjectContext
        return str(ProjectContext.discover().root_path)
    except Exception:
        return os.getcwd()


def _shell_host(shell: ExecMode) -> str:
    """Absolute path to the approved shell host executable."""
    if shell == ExecMode.POWERSHELL:
        for candidate in (
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            "/usr/bin/pwsh",
        ):
            if os.path.isfile(candidate):
                return candidate
        found = shutil.which("powershell") or shutil.which("pwsh")
        return found or "powershell"
    for candidate in (r"C:\Windows\System32\cmd.exe", "/bin/sh"):
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which("cmd")
    return found or "cmd"


class SecureExecutor:
    """Runs approved commands with shell=False and hard resource bounds."""

    def __init__(self, policy: CommandPolicy | None = None) -> None:
        self.policy = policy or CommandPolicy()
        self._active: dict[int, tuple[subprocess.Popen, int]] = {}  # pid -> (proc, pgid)
        self._lock = threading.Lock()

    def execute(self, req: ExecRequest) -> ExecResult:
        """Run a request through the policy boundary."""
        mode = self.policy.classify(req)
        if mode == ExecMode.BLOCKED:
            reason = self._explain_block(req)
            logger.warning("Executor blocked request: %s", reason)
            return _blocked(reason)

        ok, reason = self.policy.check_cwd(self.policy.effective_cwd(req))
        if not ok:
            return _blocked(reason)

        if mode == ExecMode.STRUCTURED:
            argv = [req.executable, *req.args]
            return self._run(argv, req, mode)
        return self._run_shell(req, mode)

    def _explain_block(self, req: ExecRequest) -> str:
        """Return a specific human-readable reason why the request was blocked."""
        command = (req.command or "").strip()
        exe = req.executable or ""
        # Check blocked executable
        if exe:
            exe_base = os.path.basename(exe).lower()
            for blocked in self.policy._blocked_executables:
                if blocked.lower() == exe_base:
                    return f"Blocked executable: {exe_base}"
        # Check shell operators
        for op in self.policy._shell_operators:
            if op in command:
                return f"Blocked: contains shell operator '{op}'"
        # Check dangerous patterns
        lower = command.lower()
        for pattern in self.policy._dangerous_patterns:
            if re.search(pattern, lower):
                return f"Blocked: matches dangerous pattern '{pattern}'"
        # Check blocked executables in command
        parts = command.split()
        if parts:
            for blocked in self.policy._blocked_executables:
                if blocked.lower() == parts[0].lower():
                    return f"Blocked executable: {blocked}"
        return "Command failed policy checks"

    def _run_shell(self, req: ExecRequest, mode: ExecMode) -> ExecResult:
        host = _shell_host(mode)
        if mode == ExecMode.POWERSHELL:
            argv = [host, "-NoProfile", "-NonInteractive", "-Command", req.command]
        else:
            argv = [host, "/d", "/c", req.command]
        return self._run(argv, req, mode)

    def _run(self, argv: list[str], req: ExecRequest, mode: ExecMode) -> ExecResult:
        start = time.time()
        cwd = self.policy.effective_cwd(req)
        if not os.path.isdir(cwd):
            logger.warning("Executor refused invalid working directory %r", cwd)
            return ExecResult(success=False, exit_code=-1,
                              stderr=f"Working directory is not a directory: {cwd}",
                              mode=mode.value)
        env = sanitize_environment(req.env)
        creationflags = subprocess.CREATE_NO_WINDOW if _is_windows() else 0
        if _is_windows():
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP

        try:
            # Structured argv (executable + args) with shell=False; the command
            # was already classified by CommandPolicy above.
            proc = subprocess.Popen(  # nosec B603
                argv,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=env,
                creationflags=creationflags,
                start_new_session=not _is_windows(),
            )
        except (OSError, ValueError) as e:
            logger.error("Executor failed to start (mode=%s, cwd=%r, argv=%r): %s",
                         mode.value, cwd, argv, e)
            return ExecResult(success=False, exit_code=-1,
                              stderr=str(e), mode=mode.value)

        with self._lock:
            # Store the actual process group ID for reliable tree kill on Linux.
            pgid = proc.pid  # default: same as PID (session leader)
            if not _is_windows():
                try:
                    pgid = os.getpgid(proc.pid)
                except (OSError, ProcessLookupError):
                    pgid = proc.pid
            self._active[proc.pid] = (proc, pgid)

        cap = req.max_output_bytes
        out_sink: list[bytes] = []
        err_sink: list[bytes] = []
        sink_lock = threading.Lock()
        out_thread = threading.Thread(target=self._drain,
                                      args=(proc.stdout, out_sink, cap, sink_lock),
                                      daemon=True)
        err_thread = threading.Thread(target=self._drain,
                                      args=(proc.stderr, err_sink, cap, sink_lock),
                                      daemon=True)
        out_thread.start()
        err_thread.start()

        timed_out = False
        try:
            proc.wait(timeout=req.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._terminate_tree(proc)

        out_thread.join(timeout=5)
        err_thread.join(timeout=5)
        duration_ms = (time.time() - start) * 1000

        with self._lock:
            self._active.pop(proc.pid, None)

        stdout = b"".join(out_sink).decode("utf-8", errors="replace")
        stderr = b"".join(err_sink).decode("utf-8", errors="replace")
        return ExecResult(
            success=proc.returncode == 0 and not timed_out,
            stdout=stdout,
            stderr=stderr,
            exit_code=-1 if timed_out else proc.returncode,
            duration_ms=duration_ms,
            timed_out=timed_out,
            mode=mode.value,
        )

    @staticmethod
    def _drain(stream, sink: list[bytes], cap: int, lock: threading.Lock) -> None:
        """Read a stream into a bounded sink, discarding anything past cap."""
        chunks: list[bytes] = []
        total = 0
        try:
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                if total < cap:
                    room = cap - total
                    chunks.append(chunk[:room])
                    total += room
        except Exception:
            pass  # nosec B110 -- reader threads stop on stream teardown
        finally:
            with lock:
                sink[:] = chunks

    def _terminate_tree(self, proc: subprocess.Popen, pgid: int | None = None) -> None:
        """Kill the process and its whole tree.

        Args:
            proc: The process to kill.
            pgid: The process group ID (Linux only). If None, looks it up.
        """
        if _is_windows():
            try:
                subprocess.run(  # nosec B603 B607 -- fixed Windows taskkill utility
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True, timeout=10, check=False,
                )
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass  # nosec B110 -- best-effort kill fallback
        else:
            try:
                _pgid = pgid
                if _pgid is None:
                    _pgid = os.getpgid(proc.pid)
                os.killpg(_pgid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                try:
                    proc.kill()
                except Exception:
                    pass  # nosec B110 -- best-effort kill fallback
        try:
            proc.wait(timeout=10)
        except Exception:
            pass  # nosec B110 -- process already gone or unkillable

    def kill_all(self) -> int:
        """Terminate every active process tree. Returns the count killed."""
        killed = 0
        with self._lock:
            entries = list(self._active.values())
            self._active.clear()
        for proc, pgid in entries:
            self._terminate_tree(proc, pgid=pgid)
            killed += 1
        return killed

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active_processes": len(self._active),
                "default_shell": self.policy.default_shell,
                "blocked_executables": list(self.policy._blocked_executables),
            }


_executor: SecureExecutor | None = None
_executor_lock = threading.Lock()


def get_secure_executor() -> SecureExecutor:
    """Process-wide singleton SecureExecutor."""
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = SecureExecutor()
    return _executor
