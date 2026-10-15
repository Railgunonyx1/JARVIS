# Contributing to JARVIS MK-X

Thank you for your interest in contributing to **JARVIS MK-X**! We welcome contributions to the autonomous agent kernel, the J-Browser / Orbit intelligence engine, multi-provider model routing, declarative tools, and the terminal user interface.

Please review this guide before submitting issues or pull requests.

---

## 🏛️ Architectural Contract & Invariants

JARVIS MK-X operates under a strict architectural contract. All pull requests modifying agent execution or browser control must adhere to these invariants:

1. **Single Tool Boundary**:
   All tool execution — whether triggered by the core agent loop or external protocols (MCP, ACP, Codex) — MUST pass through `core.agent.tool_service.ToolExecutionService`. Never instantiate or call `AgentToolExecutor` or tool handlers directly outside the boundary.

2. **Harness ≠ Model**:
   The Harness controls *how* the agent reasons (planning, tools, verification). The Model Gateway controls *which* model runs. They compose independently.

3. **BusEvent is the Only Event Type**:
   Every meaningful action emits a structured `BusEvent` carrying `schema_version` and `session_id`.

4. **Verification is a Post-Execution Gate**:
   Verification runs after the execution phase, not after every individual tool call. On failure, the agent transitions `VERIFYING → RECOVERING → EXECUTING` with structured context.

5. **Deterministic Failure Classification**:
   Precedence: `CANCELLED > TIMEOUT > PERMISSION_DENIED > MALFORMED_TOOL > CONTEXT_OVERFLOW > PROVIDER_FAILURE > MODEL_FAILURE > TOOL_FAILURE`.

6. **One Browser Control Path**:
   All browser interactions flow through `BrowserController` → `CDPBackend` (via `orbit.*` tools) through `ToolExecutionService`. Contested tabs yield deterministic `RESOURCE_LOCKED` signals.

---

## 🚀 Development Setup

### 1. Prerequisites
- **Python 3.11+**
- Git
- Optional: [Ollama](https://ollama.com/) (for offline local LLM testing)
- Optional: Playwright (`pip install playwright && playwright install chromium`)

### 2. Clone & Environment Setup

```bash
# Clone the repository
git clone https://github.com/Railgunonyx1/JARVIS.git
cd JARVIS

# Create and activate virtual environment
python -m venv venv

# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux/macOS:
source venv/bin/activate

# Install dependencies and dev tools
pip install -r requirements.txt
pip install pytest ruff
```

### 3. Launching Locally

```bash
# Interactive agent CLI
python -m cli

# Interactive mode with specific risk profile
python -m cli --mode smart

# Fast one-shot JSON execution
python -m cli.fast "summarize pyproject.toml"

# Windows unified launcher
JARVIS.bat
```

---

## 🧪 Testing & Quality Gates

Before opening a pull request, run the test and invariant suite:

```bash
# 1. Lint and style checks (Ruff)
ruff check .

# 2. Run core unit & integration test suite
pytest tests/ -q

# 3. Verify single-boundary architectural invariants
pytest tests/test_architecture_invariants.py

# 4. Optional: Run performance gate
python -m benchmark.gate --baseline benchmark/baseline.json --ci
```

> **Note**: Default tests are fully hermetic and do not make live network or browser calls. Live browser integration tests can be enabled with `JARVIS_RUN_BROWSER_LIVE=1 pytest tests/test_jbrowser_live.py`.

---

## 📦 Pull Request Workflow

1. **Branch Naming**: Use descriptive prefixes:
   - `feat/` for new features or capabilities
   - `fix/` for bug fixes
   - `perf/` for performance or TTFT improvements
   - `docs/` for documentation updates
   - `security/` for permission, redaction, or sandbox hardening
2. **Atomic Commits**: Write clear, imperative commit messages (`feat(kernel): add verification retry context`).
3. **No Secrets**: Never commit `.env` files, API keys, credentials, or session databases.
4. **Fill the Template**: Complete the PR checklist in `.github/PULL_REQUEST_TEMPLATE.md`.

---

## 📜 Code Style

- Enforced via **Ruff** (configured in `pyproject.toml`).
- Keep lines clear and idiomatic.
- Type annotations are strongly encouraged for public interfaces.
- Preserve existing comments and docstrings.
