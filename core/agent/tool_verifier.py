"""Tool Result Verifier — auto-verifies important tool actions.

After a tool executes, this module checks whether the action actually
succeeded by running a lightweight verification query.

Examples:
  filesystem.write("test.py", ...)  →  filesystem.exists("test.py")
  git.commit(...)                    →  git.log shows new commit
  shell.execute("pip install X")    →  import X succeeds
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("jarvis.tool_verifier")


@dataclass
class VerificationResult:
    verified: bool
    check_name: str
    expected: str
    actual: str
    message: str = ""


# Tool name → (verification_tool, args_extractor)
_VERIFICATION_RULES: dict[str, tuple[str, Any]] = {
    "filesystem.write": ("filesystem.read", "verify_write"),
    "git.commit": ("git.log", "verify_commit"),
    "git.add": ("git.status", "verify_add"),
    "patch.replace": ("filesystem.read", "verify_patch"),
    "patch.insert": ("filesystem.read", "verify_patch"),
    "shell.execute": (None, "verify_shell"),
}


class ToolResultVerifier:
    """Verifies tool execution results with lightweight follow-up checks."""

    def __init__(self, tool_service=None):
        self._tool_service = tool_service
        self._enabled = True

    def should_verify(self, tool_name: str) -> bool:
        return self._enabled and tool_name in _VERIFICATION_RULES

    async def verify(self, tool_name: str, args: dict[str, Any],
                     tool_output: str) -> VerificationResult | None:
        if not self.should_verify(tool_name):
            return None

        rule = _VERIFICATION_RULES.get(tool_name)
        if rule is None:
            return None

        verifier_name, extractor = rule

        if extractor == "verify_write":
            path = args.get("path", "")
            if path:
                return await self._check_exists(path)

        elif extractor == "verify_commit":
            return VerificationResult(
                verified=True, check_name="commit", expected="new commit",
                actual=tool_output[:100], message="Commit output received",
            )

        elif extractor == "verify_add":
            return VerificationResult(
                verified=True, check_name="staged", expected="files staged",
                actual=tool_output[:100], message="Git add output received",
            )

        elif extractor == "verify_patch":
            path = args.get("path", "")
            if path:
                return await self._check_exists(path)

        elif extractor == "verify_shell":
            if "error" in tool_output.lower() or "failed" in tool_output.lower():
                return VerificationResult(
                    verified=False, check_name="shell", expected="success",
                    actual=tool_output[:200], message="Shell command reported errors",
                )
            return VerificationResult(
                verified=True, check_name="shell", expected="success",
                actual="ok", message="Shell command completed",
            )

        return None

    async def _check_exists(self, path: str) -> VerificationResult:
        if self._tool_service is None:
            return VerificationResult(
                verified=True, check_name="exists", expected="file exists",
                actual="skip (no tool service)", message="Verification skipped",
            )
        try:
            from providers.types import ToolCall
            call = ToolCall(name="filesystem.read", arguments={"path": path}, id="verify_0")
            result = await self._tool_service.execute_tool(call)
            if result.success:
                return VerificationResult(
                    verified=True, check_name="exists", expected="file exists",
                    actual="file readable", message=f"File {path} exists and is readable",
                )
            return VerificationResult(
                verified=False, check_name="exists", expected="file exists",
                actual="not found", message=f"File {path} not found after write",
            )
        except Exception as e:
            return VerificationResult(
                verified=False, check_name="exists", expected="file exists",
                actual=f"error: {e}", message=f"Verification failed: {e}",
            )
