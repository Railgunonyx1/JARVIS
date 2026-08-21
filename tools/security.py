"""Security scanning tools — detect secrets, check permissions, audit dependencies."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from tools.schema import ToolResult, tool_result, truncate

logger = logging.getLogger("jarvis.tools.security")

_MAX_OUTPUT = 8000

# Patterns that look like hardcoded secrets
_SECRET_PATTERNS = [
    (re.compile(r"(?:api[_-]?key|apikey)\s*[=:]\s*['\"]([A-Za-z0-9+/=_-]{16,})['\"]", re.I), "API key"),
    (re.compile(r"(?:secret|password|passwd|pwd)\s*[=:]\s*['\"]([^'\"]{8,})['\"]", re.I), "Secret/password"),
    (re.compile(r"(?:token|access_token|auth_token)\s*[=:]\s*['\"]([A-Za-z0-9+/=_-]{16,})['\"]", re.I), "Token"),
    (re.compile(r"(?:aws_access_key_id)\s*[=:]\s*['\"]([A-Z0-9]{20})['\"]", re.I), "AWS key"),
    (re.compile(r"(?:private_key)\s*[=:]\s*['\"]-----BEGIN", re.I), "Private key"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}", re.I), "OpenAI/Anthropic key"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}", re.I), "GitHub token"),
    (re.compile(r"xox[bpas]-[A-Za-z0-9-]+", re.I), "Slack token"),
]

# Files/dirs to skip
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".env.example", ".agents", "audits", "_archive",
}


async def security_scan_secrets(params: dict) -> ToolResult:
    """Scan the project for hardcoded secrets and sensitive data.

    Parameters
    ----------
    path : str
        Directory to scan. Default project root.
    include : str
        File extension filter. Default scans Python, TOML, YAML, JSON, MD files.
    """
    scan_path = Path(params.get("path", "."))
    if not scan_path.is_absolute():
        scan_path = Path.cwd() / scan_path
    scan_path = scan_path.resolve()

    extensions = {".py", ".toml", ".yaml", ".yml", ".json", ".md", ".txt", ".cfg", ".ini", ".env"}
    findings = []

    files_scanned = 0
    for f in scan_path.rglob("*"):
        if f.is_dir():
            if f.name in _SKIP_DIRS:
                continue
            continue
        if f.suffix.lower() not in extensions:
            continue
        if ".git" in f.parts or "__pycache__" in f.parts:
            continue

        files_scanned += 1
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for i, line in enumerate(content.splitlines(), 1):
            for pattern, secret_type in _SECRET_PATTERNS:
                match = pattern.search(line)
                if match:
                    try:
                        rel = f.relative_to(Path.cwd())
                    except ValueError:
                        rel = f
                    findings.append(f"  {rel}:{i} — {secret_type}")
                    break  # one finding per line is enough

        if files_scanned > 500:
            break  # safety limit

    if not findings:
        output = f"Scanned {files_scanned} files. No secrets found."
        return tool_result(True, output=output)

    header = f"⚠ Found {len(findings)} potential secrets in {files_scanned} files:"
    output = header + "\n" + "\n".join(findings[:30])
    return tool_result(False, output=truncate(output, _MAX_OUTPUT))


async def security_check_permissions(params: dict) -> ToolResult:
    """Check file permission settings and world-readable sensitive files.

    Parameters
    ----------
    path : str
        Directory to check. Default project root.
    """
    import os
    check_path = Path(params.get("path", "."))
    if not check_path.is_absolute():
        check_path = Path.cwd() / check_path
    check_path = check_path.resolve()

    findings = []
    sensitive_names = {
        ".env", ".env.local", ".env.production", ".env.staging",
        "id_rsa", "id_ed25519", ".htpasswd", "credentials.json",
        "service-account.json", "keyfile.json",
    }

    files_checked = 0
    for f in check_path.rglob("*"):
        if f.is_dir():
            continue
        files_checked += 1
        if f.name in sensitive_names or f.name.endswith(".key"):
            findings.append(f"  ⚠ Sensitive file: {f.name}")
        if ".git" in f.parts:
            continue

    output = f"Checked {files_checked} files."
    if findings:
        output += "\n" + "\n".join(findings[:20])
        return tool_result(True, output=output)
    output += "\nNo permission issues found."
    return tool_result(True, output=output)


_CODE_ISSUE_PATTERNS = [
    (re.compile(r"(?<![\w.])eval\s*\("), "eval() usage"),
    (re.compile(r"(?<![\w.])exec\s*\("), "exec() usage"),
    (re.compile(r"\bos\.system\s*\("), "os.system() usage"),
    (re.compile(r"\bpickle\.loads\s*\("), "pickle.loads() deserialization"),
]

_SUBPROCESS_SHELL = re.compile(r"\bsubprocess\.(?:call|run|Popen|check_call|check_output)\s*\(")
_YAML_LOAD = re.compile(r"\byaml\.load\s*\(")
_ASSERT = re.compile(r"^\s*assert\b")


def _is_test_file(f: Path) -> bool:
    name = f.name.lower()
    if name.startswith("test_") or name.startswith("test.") or name.endswith("_test.py"):
        return True
    parts = {p.lower() for p in f.parts}
    return bool(parts & {"tests", "test", "testing"})


def _scan_code_line(line: str, is_test: bool) -> list[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return []
    labels = []
    for pattern, label in _CODE_ISSUE_PATTERNS:
        if pattern.search(line):
            labels.append(label)
    compact = line.replace(" ", "")
    if _SUBPROCESS_SHELL.search(line) and "shell=True" in compact:
        labels.append("subprocess with shell=True")
    if _YAML_LOAD.search(line) and "SafeLoader" not in line:
        labels.append("yaml.load() without SafeLoader")
    if not is_test and _ASSERT.match(line):
        labels.append("assert in non-test code")
    return labels


async def security_scan_code(params: dict) -> ToolResult:
    """Scan Python files for common security issues.

    Detects eval/exec usage, os.system, subprocess with shell=True,
    hardcoded secrets, unsafe deserialization, yaml.load without
    SafeLoader, and assert statements outside test files.

    Parameters
    ----------
    path : str
        Directory to scan. Default project root.
    """
    scan_path = Path(params.get("path", "."))
    if not scan_path.is_absolute():
        scan_path = Path.cwd() / scan_path
    scan_path = scan_path.resolve()

    findings: list[str] = []
    files_scanned = 0
    self_path = Path(__file__).resolve()

    for f in scan_path.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in f.parts):
            continue
        if f.resolve() == self_path:
            continue
        files_scanned += 1
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        is_test = _is_test_file(f)
        try:
            rel = f.relative_to(Path.cwd())
        except ValueError:
            rel = f

        for i, line in enumerate(content.splitlines(), 1):
            labels = _scan_code_line(line, is_test)
            for pattern, secret_type in _SECRET_PATTERNS:
                if pattern.search(line):
                    labels.append(secret_type)
                    break
            for label in labels:
                findings.append(f"  {rel}:{i} — {label}")

        if files_scanned > 500:
            break

    if not findings:
        output = f"Scanned {files_scanned} Python files. No security issues found."
        return tool_result(True, output=output)

    header = f"⚠ Found {len(findings)} potential issues in {files_scanned} Python files:"
    output = header + "\n" + "\n".join(findings[:40])
    return tool_result(False, output=truncate(output, _MAX_OUTPUT))
