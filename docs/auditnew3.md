# JARVIS MK-X - Comprehensive Audit

**Label: auditnew 3**
**Date:** 2026-08-11
**Scope:** active source tree (excluded `venv`, `web/node_modules` contents, `.kilo`, `.kilocode`, `temp_extract`, legacy dirs)
**Method:** ruff (lint + selected rules), bandit (SAST), pip-audit (OSV), secret regex scan, per-file test suite runs, manual code review.

## Executive summary

| Severity | Count | Headline |
|---------:|------:|----------|
| Critical | 1 | `tests/test_daemon.py` hangs - new `InputReader` ignores redirected `sys.stdin` |
| High | 2 | daemon WMI spawn opens a second console window; REPL typed text renders black |
| Medium | 3 | audit-log f-string SQL (low real risk), duplicate MCP route key, B904 raise-without-cause |
| Low | ~35 | bandit lows, 15 unused vars, test-style nits |
| Dependencies | 19 vulns | in 4 packages - all transitive/tooling; pinned runtime list is clean |

Overall the runtime is healthy: no secrets in tracked source, permissions/sandbox layers present, and ~143 tests confirmed passing across CLI, daemon-server, memory, IPC, observability and security suites. The one critical item is a **regression introduced by the P1 CLI gap-close**.

## 1. Security

### 1.1 Static analysis (bandit 1.9.4)
Scanned `core, agents, tools, memory, daemon, security, workflows, runtime, providers, inference_engine, mcp_jarvis, systems, cli, knowledge_graph, executors, interfaces, notifications, serializers, settings, voice, ui`.

- **B608 (Medium) - `security/audit.py:177-182`** - `get_stats()` builds SQL with f-strings. **Low real risk:** only a constant `"timestamp > ?"` / `"WHERE"` fragment is interpolated; the `since` value is always bound as a parameter. False positive in practice; ideally rewrite as static SQL.
- **B404 (Low) - `security/sandbox.py:18`** - `subprocess` import. Expected: the sandbox exists precisely to shell out under policy.
- **B110 (Low) - `security/sandbox.py:184`** - `except Exception: pass` during process teardown. Acceptable (best-effort kill), could log.

### 1.2 Secrets scan
Regex scan of all tracked files for API keys/tokens (OpenAI `sk-`, Google `AIza`, GitHub `ghp_`, AWS `AKIA`, `Bearer`, `api_key=`): **no matches in tracked source**. Only hits were bundled binaries under `web/node_modules`.

### 1.3 Secret handling
- `config/api_keys.json`, `.env`, `config/.env` are `.gitignore`d. Confirmed untracked.
- Permission gate (`core/security.py`, `security/executor.py`) and sandbox (`security/sandbox.py`) present; mode switching (`plan/controlled/smart/agent`) enforced in the agent loop.

### 1.4 Dependencies (pip-audit 2.10.1, OSV DB)
**19 known vulnerabilities in 4 installed packages:**

| Package | Version | Vulns | Fix |
|--------:|--------:|------:|----:|
| litellm (transitive) | 1.72.2 | 14 | >=1.84.0 |
| pip (tooling) | 24.0 | 3 | >=26.1.2 |
| aiohttp (transitive) | 3.14.2 | 1 | 3.14.3 |
| cryptography (transitive) | 49.0.0 | 1 | 50.0.0 |

The pinned **runtime** list in `requirements.txt` (groq, google-generativeai, openai, ollama, rich, typer, textual, mcp, etc.) shows no advisories. litellm is not a declared dependency - it arrives transitively; recommend pinning it (or the parent that pulls it) to a fixed version.

## 2. Correctness & regressions

### 2.1 CRITICAL - `tests/test_daemon.py` hangs
The P1 gap-close replaced `console.input()` in `cli/main.py` with `InputReader`. On Windows `InputReader.read_line()` always routes to raw `msvcrt` reads - **even when `sys.stdin` is not a console**. The daemon-REPL tests monkeypatch `sys.stdin` to a `StringIO`; `msvcrt.getwch()` ignores it and blocks forever on real keyboard input.

Affected:
- `tests/test_daemon.py::test_interactive_repl_runs_goal_and_prints_summary`
- `tests/test_daemon.py::test_interactive_repl_survives_daemon_failures`

Consequence: the full suite cannot complete, and `echo "goal" | jarvis` piping is broken on Windows. **Fix:** in `read_line()`, when `sys.stdin.isatty()` is false, fall back to plain `sys.stdin.readline()` (raise `EOFError` on EOF, matching the old `input()` semantics). This is the P0 item and unblocks the suite.

### 2.2 Duplicate dict key - `mcp_jarvis/server.py:35 & 74`
`"memory.query": "memory"` appears twice in a route map. Same value, so benign - but one entry is silently shadowed. Remove the duplicate.

### 2.3 `memory/vector_store.py` - ruff F821 (`np` undefined)
**False positive.** `from __future__ import annotations` is present (line 21) and `import numpy as np` is function-local (lines 68, 84). Annotations are lazily evaluated; runtime is safe.

### 2.4 `B904` - `core/executor.py:195,199`
`raise` inside `except` without `raise ... from err` - chains are dropped. Cosmetic but degrades debugging of tool-call failures.

## 3. Runtime / UX issues (user-reported, root-caused)

### 3.1 HIGH - Two console windows open
- `jarvis.cmd` relaunches into Windows Terminal (the "main" window).
- The daemon is then spawned by `daemon/lifecycle._spawn()` via WMI `Win32_Process.Create` (console-subsystem `python.exe`). WMI creation carries **no `CREATE_NO_WINDOW` flag**, so a second visible cmd window appears for the daemon process.
- The `subprocess.Popen` fallback paths already pass `_WIN_DETACH_FLAGS` (includes `CREATE_NO_WINDOW`) and are fine.

**Fix (recommended):** in `start_daemon()` (Windows), replace `sys.executable` with `pythonw.exe` (GUI subsystem - never allocates a console). Apply to the WMI command string (where flags cannot be passed) and keep the existing Popen flags as backstop.

### 3.2 HIGH - Typed REPL text renders black
`InputReader` writes the input line as raw bytes with no ANSI state. After Rich renders a status bar the Windows console attribute is left as the last styled token (e.g. `dim`/dark), so the next raw write appears near-black on dark terminals.

**Fix (recommended):** in `_redraw()`, emit a leading ANSI reset (`\x1b[0m`) and style the prompt with the theme brand (bold cyan) via ANSI; compute padding from plain-string widths (ANSI has zero display width). This restores the old `console.input(Text("JARVIS", style="bold cyan"))` look.

## 4. Test suite health

Per-file runs (venv Python 3.11):

| File | Result |
|------|-------:|
| test_cli_repl.py + test_ux.py | 32 passed |
| test_imports / test_startup / test_observability / test_security_fixes / test_task_observer / test_context_engine | 68 passed |
| test_daemon_ws | 11 passed |
| test_mem | 14 passed |
| test_memory_stage1 | 13 passed |
| test_pipe_ipc | 1 passed |
| test_client_reconnect | 4 passed |
| **test_daemon** | **HANGS (2.1)** |
| test_daemon_spawn / test_executor_e2e / test_executor_security / test_tui / test_world_monitor | not run (blocked by hang) |

~143 confirmed passing. `tests/test_daemon_ws.py:305` uses a blind `assert_exception` (B017) - tighten to a specific exception.

## 5. Code quality / lint (ruff)

Repo-wide: **1975 findings** (1500+ auto-fixable). Breakdown:

| Code | Count | Meaning |
|-----:|------:|---------|
| UP006 | 613 | use `X | None` / generic builtins (modernization) |
| UP045 | 466 | non-optional non-types (modernization) |
| UP035 | 232 | import from `collections.abc` |
| E501 | 196 | line too long (>120) |
| F401 | 181 | unused imports |
| I001 | 139 | import sorting |
| E701 | 22 | compound statements |
| PLW1510 | 16 | subprocess without `check=` |
| F841 | 15 | unused variables (dead code) |
| F821 | 3 | all false positives (2.3) |
| B/B-series | ~14 | see 2.4 + tests |
| misc | ~90 | W291/W292/W293/W605, F541, F601, etc. |

Top files by lint load: `core/capability_registry.py` (121), `agents/agent_ecosystem.py` (68), `core/intent_router.py` (48), `core/model_manager.py` (41), `knowledge_graph/*` (~77 combined).

Notes: `_quarantine_removed/` (32 tracked files) is legacy reference code but is scanned by lint - add to exclude. The majority of findings are UP* modernization with safe autofixes and would be a mechanical follow-up pass, not a correctness risk.

## 6. Repo hygiene

- `.gitignore` correctly covers `venv/`, `.kilo/`, `.kilocode/`, `.env`, `config/api_keys.json`, `memory/*.db`, logs, voice packs, legacy dirs (`temp_extract/`, `Jarvis-MK37-main/`, `ultron-by-sagar-builds-main/`).
- **Issue:** `web/node_modules/` is **committed** (2,558 tracked files) - bloat in history; should be removed from the index and gitignored.
- `_quarantine/` (quarantine history) and `_quarantine_removed/` (32 files) are tracked. Intentional if kept for reference, but exclude both from lint/test scans.
- No pre-commit hooks / CI gate enforcing ruff or bandit - recommended.

## 7. Recommendations (prioritized)

| Priority | Action |
|---------:|--------|
| P0 | Fix `InputReader` non-tty stdin fallback (unblocks full suite + pipe input) |
| P1 | Spawn daemon via `pythonw.exe` on Windows (single console window) |
| P1 | Add ANSI reset + themed prompt to `InputReader._redraw` (readable typed input) |
| P2 | Remove duplicate MCP route key; `raise ... from err` in `core/executor.py`; fix 15 unused vars |
| P2 | `git rm -r --cached web/node_modules` + gitignore; exclude `_quarantine*` from scans |
| P3 | Pin litellm (>=1.84.0), upgrade aiohttp/cryptography/pip; add CI lint+bandit gate |
| P3 | Mechanical UP* ruff modernization pass (safe autofixes only) |

### Parked (research only, not in this pass)
Provider/gateway research (FreeLLMAPI, OmniRoute, Free LLM Gateway, LLM-Rosetta, LLMGateway, LM-Proxy, OpenProxy, RelayFreeLLM, LiteLLM, Ollama + ContinuityBench stateful-failover) - provider layer untouched by design; a later M0 provider pass should own model selection/retries/cooldowns/circuit-breaking itself and treat gateways as replaceable inference infrastructure.
