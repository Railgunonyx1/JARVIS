"""Secret scan for JARVIS — API keys, tokens, and private keys in tracked files.

Used by CI (security job) and runnable locally for a one-off git-history sweep:

    python scripts/scan_secrets.py                    # working tree only
    python scripts/scan_secrets.py --history           # last 100 commits too

Exit 1 when a potential secret is found. Heuristic by design: patterns are
conservative so this never blocks on false positives like documentation
examples (``sk-example...``); real leaks should be confirmed manually.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Conservative patterns — require real-looking key material.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("openai_sk", re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b")),
    ("groq", re.compile(r"\bgsk_[A-Za-z0-9_-]{24,}\b")),
    ("huggingface", re.compile(r"\bhf_[A-Za-z0-9_-]{24,}\b")),
    ("aws", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{30,}\b")),
    ("stripe", re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("generic_key", re.compile(
        r"(?:api[_-]?key|apikey|secret|token)\s*[=:]\s*['\"][A-Za-z0-9_/+\-=]{24,}['\"]",
        re.IGNORECASE,
    )),
]

# Files that are allowed to hold secrets by design (never scanned).
IGNORE_PATHS = {
    "config/api_keys.json",
    "config/.env",
    ".env",
    "venv/",
    ".venv/",
}


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=str(ROOT), check=True,
    )
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def _scan_lines(lines: list[str], path: str, max_chars: int = 400) -> list[str]:
    hits = []
    for lineno, line in enumerate(lines, start=1):
        if len(line) > 4096:  # minified/binary-ish lines are noise
            continue
        for name, pattern in PATTERNS:
            match = pattern.search(line)
            if match:
                snippet = line.strip()[:max_chars]
                hits.append(f"  {path}:{lineno}  [{name}]  {snippet}")
                break
    return hits


def scan_tree() -> list[str]:
    hits = []
    for rel in _tracked_files():
        if any(rel.startswith(ig) or rel.endswith(ig) for ig in IGNORE_PATHS):
            continue
        full = ROOT / rel
        if not full.is_file():
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        hits.extend(_scan_lines(text.splitlines(), rel))
    return hits


def scan_history(depth: int = 100) -> list[str]:
    """Scan the last `depth` commits' diffs for secrets (one-off local sweep)."""
    commits = subprocess.run(
        ["git", "rev-list", "--max-count", str(depth), "HEAD"],
        capture_output=True, text=True, cwd=str(ROOT), check=True,
    ).stdout.split()
    hits = []
    for sha in commits:
        out = subprocess.run(
            ["git", "show", sha], capture_output=True, text=True, cwd=str(ROOT),
        ).stdout
        for hit in _scan_lines(out.splitlines(), f"history:{sha[:7]}", max_chars=200):
            hits.append(hit)
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan for secrets in the JARVIS repo.")
    parser.add_argument("--history", action="store_true", help="Also scan the last 100 commits.")
    args = parser.parse_args(argv)

    hits = scan_tree()
    if args.history:
        print("scanning git history (last 100 commits)…")
        hits.extend(scan_history())

    if not hits:
        print("SECRET SCAN: clean — no secret patterns found.")
        return 0
    print(f"SECRET SCAN: {len(hits)} potential secret(s) found:")
    print("\n".join(hits))
    return 1


if __name__ == "__main__":
    sys.exit(main())
