"""Static scanning for dangerous constructs in generated/executed code.

Central home for the forbidden-code denylist and its scan helper, previously
embedded in the legacy ``core.executor`` module. Keeping it in ``security``
means the gate can be reused without dragging in the dead executor chain.
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from security.redaction import redact_sensitive

logger = logging.getLogger("jarvis.security.code_scan")

FORBIDDEN_CODE_PATTERNS = [
    # Word boundaries (\b) keep these from matching substrings like
    # "postsystem", "evaluate", or "exclusive".
    re.compile(r"\bos\.system\b", re.IGNORECASE),
    re.compile(r"\bos\.popen\b", re.IGNORECASE),
    re.compile(r"\bsubprocess\.Popen\b", re.IGNORECASE),
    re.compile(r"\bsubprocess\.run\b", re.IGNORECASE),
    re.compile(r"\beval\b", re.IGNORECASE),
    re.compile(r"\bexec\b", re.IGNORECASE),
    re.compile(r"__import__", re.IGNORECASE),
    re.compile(r"\bimportlib\b", re.IGNORECASE),
    re.compile(r"\bsocket\.", re.IGNORECASE),
    re.compile(r"\bsocket\b\s*\(", re.IGNORECASE),  # bare socket(...) calls too
    re.compile(r"\brequests\b", re.IGNORECASE),
    re.compile(r"\burllib\b", re.IGNORECASE),
    re.compile(r"\bhttp\.", re.IGNORECASE),
]


def check_generated_code(code: str) -> None:
    """Reject obviously dangerous constructs even when execution is enabled."""
    lowered = code.lower()
    matched = [p.pattern for p in FORBIDDEN_CODE_PATTERNS if p.search(lowered)]
    if matched:
        raise RuntimeError(
            f"Generated code rejected: forbidden patterns found: {matched}"
        )


def generated_code_enabled() -> bool:
    """Whether the generated_code tool is explicitly enabled for this process."""
    return os.environ.get("JARVIS_ENABLE_GENERATED_CODE", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _generated_api_key() -> str:
    env_key = os.environ.get("GEMINI_API_KEY", "")
    if env_key:
        return env_key
    base_dir = Path(__file__).resolve().parents[1]
    api_config = base_dir / "config" / "api_keys.json"
    if api_config.exists():
        try:
            with open(api_config, encoding="utf-8") as f:
                return json.load(f).get("gemini_api_key", "")
        except Exception:
            return ""
    return ""


def run_generated_code(description: str, speak: Callable | None = None) -> str:
    """LLM-generate and execute Python, gated off by default for security."""
    if not generated_code_enabled():
        raise RuntimeError(
            "The generated_code tool is disabled by default for security. "
            "Set JARVIS_ENABLE_GENERATED_CODE=1 to explicitly allow it."
        )
    import google.generativeai as genai

    if speak:
        speak(redact_sensitive("Writing custom code for this task, sir."))

    home = Path.home()
    desktop = home / "Desktop"
    downloads = home / "Downloads"
    documents = home / "Documents"

    if not desktop.exists():
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
            )
            desktop = Path(winreg.QueryValueEx(key, "Desktop")[0])
        except Exception:
            pass

    genai.configure(api_key=_generated_api_key())
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=(
            "You are an expert Python developer. "
            "Write clean, complete, working Python code. "
            "Use only the standard library. "
            "Do NOT install packages, download anything, or touch the network. "
            "Return ONLY the Python code. No explanation, no markdown, no backticks.\n\n"
            f"SYSTEM PATHS:\n"
            f"  Desktop   = r'{desktop}'\n"
            f"  Downloads = r'{downloads}'\n"
            f"  Documents = r'{documents}'\n"
            f"  Home      = r'{home}'\n"
        )
    )

    try:
        response = model.generate_content(
            f"Write Python code to accomplish this task:\n\n{description}"
        )
        code = response.text.strip()
        code = re.sub(r"```(?:python)?", "", code).strip().rstrip("`").strip()

        check_generated_code(code)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        logger.info("Running generated code: %s", tmp_path)

        exec_env = {k: v for k, v in os.environ.items()
                    if not any(s in k.upper() for s in (
                        "API_KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL",
                        "PRIVATE", "AUTH",
                    ))}

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True,
            timeout=120, cwd=str(Path.home()),
            env=exec_env,
            check=False,
        )

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode == 0 and output:
            return output
        elif result.returncode == 0:
            return "Task completed successfully."
        elif error:
            raise RuntimeError(f"Code error: {error[:400]}")
        return "Completed."
    except Exception as e:
        raise RuntimeError(f"Generated code failed: {e}") from e

