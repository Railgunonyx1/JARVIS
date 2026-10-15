"""Step 5 guard: live TTFT budget for the kernel response path.

Per PERF.md, the user-facing metric is time-to-first-visible-token on
``POST /v1/chat``. The steady state after the latency fixes is 62-102ms
(first visible token, served by the fast chain head); the budget is set at
2000ms — roughly 20x headroom against noise, tight enough to catch the
known regression classes (sticky lock-in onto a slow provider, dead chain
head, cold-loop prewarm).

Skips (never fails) when the kernel service is not running or the bridge
token is missing — this is a live-system gate, not a hermetic unit test.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

import pytest

_KERNEL_URL = "http://127.0.0.1:8170"
_TOKEN_FILE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "JARVIS" / "bridge-token"
_TTFT_BUDGET_MS = 2000.0
_TURNS = 2  # best-of-2: one transient provider hiccup must not flake the gate


def _token() -> str:
    try:
        return _TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _kernel_ok() -> bool:
    tok = _token()
    if not tok:
        return False
    try:
        req = urllib.request.Request(
            f"{_KERNEL_URL}/status", headers={"Authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(req, timeout=2) as r:
            return bool(json.loads(r.read()).get("kernel") == "online")
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return False


pytestmark = pytest.mark.skipif(
    not _kernel_ok(), reason="live kernel (127.0.0.1:8170) not running")


def _ttft_once() -> tuple[float | None, str, str | None]:
    """One chat turn: returns (ttft_seconds, provider, error)."""
    tok = _token()
    prompt = f"Reply with exactly one unique word: ttft-gate-{time.time_ns()}."
    body = json.dumps({
        "session_id": "ttft-budget-gate",
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        f"{_KERNEL_URL}/v1/chat", data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {tok}"})
    t0 = time.perf_counter()
    ttft: float | None = None
    provider = "?"
    error: str | None = None
    with urllib.request.urlopen(req, timeout=60) as resp:
        for raw in resp:
            for line in raw.split(b"\n"):
                if not line.startswith(b"data:"):
                    continue
                try:
                    ev = json.loads(line[5:])
                except ValueError:
                    continue
                kind = ev.get("type")
                if kind == "delta" and ttft is None:
                    ttft = time.perf_counter() - t0
                elif kind == "error":
                    error = str(ev.get("message") or ev)[:200]
                elif kind == "meta":
                    provider = str(ev.get("provider") or "?")
    return ttft, provider, error


def test_first_token_under_budget():
    """The response path stays under the PERF.md TTFT budget.

    Best-of-2 turns: a single transient provider hiccup (e.g. one walk to a
    slow fallback) must not fail the gate, but a persistent regression
    (sticky lock-in, dead chain head) fails on every turn and cannot hide.
    """
    results = [_ttft_once() for _ in range(_TURNS)]
    errors = [e for _, _, e in results if e]
    assert not errors, f"chat turn errored: {errors[0]}"
    ttfts = [t for t, _, _ in results if t is not None]
    assert ttfts, "no turn produced a first token"
    best_ms = min(ttfts) * 1000
    detail = ", ".join(
        f"{(t or float('nan')) * 1000:.0f}ms via {p}" for t, p, _ in results)
    assert best_ms < _TTFT_BUDGET_MS, (
        f"TTFT budget exceeded: best of {_TURNS} turns was {best_ms:.0f}ms "
        f"(budget {_TTFT_BUDGET_MS:.0f}ms) — see PERF.md. Turns: {detail}")
