# JARVIS MK-X — Terminal-First Autonomous Engineering Agent

**JARVIS MK-X** is a terminal-first autonomous engineering agent. It runs entirely in your local terminal using Rich for rendering, `msvcrt` for Windows key handling, and your choice of LLM providers (Groq, Gemini, OpenRouter, Ollama).

## Quick Start

```bash
# Install dependencies
python -m pip install -r requirements.txt

# Launch the interactive terminal (default: agent mode)
python -m cli

# Or launch with a specific mode
python -m cli --mode plan
python -m cli --mode controlled
python -m cli --mode smart
python -m cli --mode agent

# One-shot goal
python -m cli "analyze this repository"

# JSON output for piping
python -m cli --json "list files"

# Show help
python -m cli --help
```

## Architecture

```
JARVIS MK-X
├── cli/                          # Rich terminal CLI
│   ├── main.py                   # Entry point & interactive loop
│   ├── renderer.py               # Rich rendering engine
│   ├── bridge.py                 # AgentBridge (event translation)
│   ├── models.py                 # View-models (AppState, Plan, Message, etc.)
│   ├── layout.py                 # Responsive terminal layout
│   ├── theme.py                  # Color vocabulary & symbols
│   ├── input.py                  # Windows msvcrt key handling + history
│   ├── daemon_ui.py              # Daemon WebSocket bridge (optional)
│   ├── ux.py                     # LiveTaskDisplay (event-driven Live region)
│   ├── commands.py               # Command registry (/help, /mode, etc.)
│   ├── cockpit.py                # Diagnostic dashboard (on demand)
│   └── details.py                # Expanded task views
│
├── core/agent/                   # Agent loop & observer pattern
│   ├── loop.py                   # AgentLoop (decision making, tool execution)
│   ├── observer.py               # TaskObserver (event stream)
│   └── event_store.py            # Persistent event store
│
├── providers/                    # LLM provider abstraction
│   ├── base.py                   # Abstract provider + health tracking
│   ├── router.py                 # Fallback chain router
│   ├── groq_provider.py          # Groq (Llama 3.1 8B, fast)
│   ├── gemini_provider.py        # Gemini Flash (complex reasoning)
│   ├── openrouter_provider.py    # OpenRouter free tier
│   └── ollama_provider.py        # Ollama (local, offline)
│
├── tools/                        # Executable tool actions
│   ├── filesystem/               # File read/write/delete
│   ├── grep/                     # Text search
│   ├── bash/                     # Command execution
│   └── package/                  # Package management
│
├── memory/                       # Categorized memory system
│   ├── store.py                  # SQLite + JSON backend
│   └── memory_manager.py         # Identity, preferences, facts
│
├── context/                      # Context management
│   └── engine.py                 # Sliding window + user profile
│
├── runtime/                      # Performance & observability
│   ├── benchmark/                # Benchmark gate & performance tracking
│   └── observability/            # Exporters & dashboards
│
├── actions/                      # Action handlers
│   ├── open_app.py               # App launcher (60+ aliases)
│   ├── web_search.py             # Multi-mode search
│   ├── system_monitor.py         # GPU/CPU monitoring
│   └── proactive.py              # Background proactive engine
│
├── tools/                        # Tool definitions & registry
│
├── config/                       # Configuration files
│   ├── jarvis.toml               # Main config
│   ├── models.toml               # Model settings (budgets, tokens)
│   ├── voice.toml                # Voice settings (legacy)
│   └── security.toml             # Security settings
│
└── benchmark/                    # Performance benchmarks & baselines

## Philosophy

**Terminal-first**: The terminal is the primary interface. No GUI, no voice, no web dashboard by default. Rich provides Markdown rendering, syntax highlighting, and live live-updates via the `Live` region driven by the agent's event stream.

**In-process architecture**: AgentLoop runs in-process with the CLI. No daemon, no WebSocket, no network hop for the local terminal. This gives lower latency, fewer failure modes, and simpler debugging.

**Provide**:
- Multiple LLM providers (Groq → Gemini → OpenRouter → Ollama → template fallback)
- Tool execution with permission prompts
- Memory system for facts & context
- Rich terminal rendering with live telemetry
- Comprehensive CLI command set

## Quick Start

```bash
# Install dependencies
python -m pip install -r requirements.txt

# Launch the interactive terminal (default: agent mode)
python -m cli

# Or launch with a specific mode
python -m cli --mode plan     # Read-only plan mode
python -m cli --mode controlled  # Confirm every consequential action
python -m cli --mode smart     # Dynamic autonomy by risk
python -m cli --mode agent     # Full autonomous execution

# One-shot goal
python -m cli "inspect the repository"

# JSON output for piping to other tools
python -m cli --json "list files"

# Show the help system
python -m cli /help
```

## Commands

| Command | Description |
|---------|-------------|
| `python -m cli` | Interactive terminal (agent mode) |
| `python -m cli --mode plan` | Read-only plan mode |
| `python -m cli --mode controlled` | Confirm every consequential action |
| `python -m cli --mode smart` | Dynamic autonomy by risk |
| `python -m cli --mode agent` | Full autonomous execution |
| `python -m cli "goal"` | One-shot goal |
| `python -m cli --json "query"` | JSON output |
| `python -m cli /help` | Show help |
| `python -m cli /mode` | Show current mode |
| `python -m cli /model` | Show last model/provider |
| `python -m cli /status` | Show daemon status / in-process status |
| `python -m cli /context` | Show context budget report |
| `python -m cli /tokens` | Show context usage |
| `python -m cli /memory search <q>` | Semantic memory retrieval |
| `python -m cli /memory add <k>=<v>` | Remember a fact |
| `python -m cli /history` | List recent tasks |
| `python -m cli /history <id>` | Replay a task timeline |
| `python -m cli /audit` | Security audit log |
| `python -m cli /audit trace <id>` | Replay an audit trace |
| `python -m cli /tree` | Show project tree |
| `python -m cli /resume` | Re-run the last goal |
| `python -m cli /cockpit` | Diagnostic dashboard (on demand) |
| `python -m cli /verbose` | Toggle backend messages |
| `python -m cli /clear` | Clear screen |
| `python -m cli /exit` | Quit |

## Architecture

```
JARVIS MK-X
├── cli/                          # Rich terminal CLI
│   ├── main.py                   # Entry point & interactive loop
│   ├── renderer.py               # Rich rendering engine
│   ├── bridge.py                 # AgentBridge (event translation)
│   ├── models.py                 # View-models (AppState, Plan, Message, etc.)
│   ├── layout.py                 # Responsive terminal layout
│   ├── theme.py                  # Color vocabulary & symbols
│   ├── input.py                  # Windows msvcrt key handling + history
│   ├── daemon_ui.py              # Daemon WebSocket bridge (optional)
│   ├── ux.py                     # LiveTaskDisplay (event-driven Live region)
│   ├── commands.py               # Command registry (/help, /mode, etc.)
│   ├── cockpit.py                # Diagnostic dashboard (on demand)
│   └── details.py                # Expanded task views
│
├── core/agent/                   # Agent loop & observer pattern
│   ├── loop.py                   # AgentLoop (decision making, tool execution)
│   ├── observer.py               # TaskObserver (event stream)
│   └── event_store.py            # Persistent event store
│
├── providers/                    # LLM provider abstraction
│   ├── base.py                   # Abstract provider + health tracking
│   ├── router.py                 # Fallback chain router
│   ├── groq_provider.py          # Groq (Llama 3.1 8B, fast)
│   ├── gemini_provider.py        # Gemini Flash (complex reasoning)
│   ├── openrouter_provider.py    # OpenRouter free tier
│   └── ollama_provider.py        # Ollama (local, offline)
│
├── tools/                        # Tool actions & registry
│   ├── filesystem/               # File read/write/delete
│   ├── grep/                     # Text search
│   ├── bash/                     # Command execution
│   └── package/                  # Package management
│
├── memory/                       # Categorized memory system
│   ├── store.py                  # SQLite + JSON backend
│   └── memory_manager.py         # Identity, preferences, facts
│
├── context/                      # Context management
│   └── engine.py                 # Sliding window + user profile
│
├── runtime/                      # Performance & observability
│   ├── benchmark/                # Benchmark gate & performance tracking
│   └── observability/            # Exporters & dashboards
│
├── actions/                      # Action handlers
│   ├── open_app.py               # App launcher (60+ aliases)
│   ├── web_search.py             # Multi-mode search
│   ├── system_monitor.py         # GPU/CPU monitoring
│   └── proactive.py              # Background proactive engine
│
├── config/                       # Configuration files
│   ├── jarvis.toml               # Main config
│   ├── models.toml               # Model settings (budgets, tokens)
│   ├── voice.toml                # Voice settings (legacy)
│   └── security.toml             # Security settings
│
└── benchmark/                    # Performance benchmarks & baselines
```

## LLM Routing

```
Groq Llama 3.1 8B (fast) → Gemini Flash (complex) → OpenRouter Free → Ollama qwen2.5:1.5b (offline) → template fallback
```

## Hardware

- Python 3.11.x
- Rich terminal rendering
- msvcrt Windows key handling (or `sys.stdin.readline()` off-Windows)
- Optional: Groq API key, Gemini API key, OpenRouter API key, Ollama local model

## Configuration

Edit `config/jarvis.toml` for settings. API keys go in environment variables or `config/.env`:

```
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
OPENROUTER_API_KEY=sk-or-...
```

## Migration History

JARVIS evolved from a cloud-first voice assistant (PyQt6 HUD, Piper TTS, Flask backend, daemon/Web UI) to a **terminal-first autonomous engineering agent**. The in-process architecture was chosen for simplicity, lower latency, and fewer failure modes. The legacy GUI/voice architecture is documented in the **Architecture History** section below.

## Architecture History (Legacy)

> This section documents the previous architecture for reference. The current terminal-first design replaced it starting in Phase 4.
>
> **OLD JARVIS**:
> - Cloud-first voice assistant with local fallback
> - PyQt6 Arc Reactor HUD UI
> - Flask-based web server
> - Daemon/WebSocket bridge (`127.0.0.1:8787`)
> - Voice pipeline (Piper TTS, Groq Whisper, openWakeWord)
> - State machine (IDLE → LISTENING → THINKING → SPEAKING)
> - `python main.py` with `--gui`, `--text`, `--voice` flags
> - `launcher.py` for venv + Ollama auto-start
>
> The migration to terminal-first began in Phase 4 and completed with the current `cli/` architecture. All core reasoning, tool execution, and memory capabilities were preserved; the rendering and interaction layers were rebuilt for the terminal.

## License

MIT License. See `LICENSE` for details.