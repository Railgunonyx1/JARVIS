# JARVIS MK-X (Mark LXXXV) — AI Personal Assistant

Cloud-first voice assistant with local fallback, built for low-resource hardware.

## Quick Start

```bash
# Option 1: Use the launcher (recommended)
start.bat

# Option 2: Direct Python
python main.py              # GUI (Arc Reactor HUD)
python main.py --text       # Terminal chat
python main.py --voice      # Voice mode
python main.py --health     # Health checks
```

The launcher auto-activates the venv, installs dependencies, and starts Ollama.

## Architecture

```
JARVIS/
├── main.py                 # Entry point (GUI / text / voice / health)
├── launcher.py             # App launcher (venv, deps, Ollama auto-start)
├── start.bat               # One-click Windows launcher
├── ui.py                   # PyQt6 Arc Reactor HUD
├── voice_manager.py        # TTS output (Piper → Edge-TTS)
│
├── core/                   # Core orchestration
│   ├── config.py           # TOML config loader
│   ├── jarvis.py           # Main orchestrator
│   ├── api_keys.py         # API key management
│   ├── utils.py            # Shared utilities
│   └── prompt.txt          # System prompt
│
├── providers/              # LLM provider abstraction
│   ├── base.py             # Abstract provider + health tracking
│   ├── router.py           # Fallback chain router
│   ├── groq_provider.py    # Groq (Llama 3.1 8B)
│   ├── gemini_provider.py  # Gemini Flash
│   ├── ollama_provider.py  # Ollama (local)
│   └── openrouter_provider.py  # OpenRouter free tier
│
├── pipeline/               # Voice pipeline
│   ├── stt.py              # Speech-to-text (Groq Whisper → faster-whisper)
│   ├── tts.py              # Text-to-speech (Piper → Edge-TTS)
│   ├── vad.py              # Voice activity detection
│   └── wake_word.py        # Wake word detection (openWakeWord)
│
├── cognition/              # Intelligence layer
│   ├── intent_router.py    # Intent classification
│   ├── task_queue.py       # Task queue
│   ├── planner.py          # Task planning
│   ├── executor.py         # Task execution
│   └── error_handler.py    # Error handling
│
├── context/                # Context management
│   └── engine.py           # Sliding window + user profile
│
├── dialogue/               # Dialogue management
│   └── state_machine.py    # State machine (IDLE → LISTENING → THINKING → SPEAKING)
│
├── memory/                 # Memory system
│   ├── store.py            # SQLite + JSON backend
│   └── memory_manager.py   # Categorized memory (identity, preferences, etc.)
│
├── personality/            # Personality layer
│   ├── engine.py           # Mood tracking, time awareness
│   └── responses.py        # Deterministic response generator
│
├── diagnostics/            # Self-monitoring
│   ├── engine.py           # System metrics (CPU, GPU, RAM)
│   └── health.py           # Component health checks
│
├── actions/                # Action handlers
│   ├── open_app.py         # App launcher (60+ aliases)
│   ├── web_search.py       # Multi-mode search
│   ├── system_monitor.py   # GPU/CPU monitoring
│   └── proactive.py        # Background proactive engine
│
├── config/                 # Configuration files
│   ├── jarvis.toml         # Main config
│   ├── models.toml         # Model settings
│   ├── voice.toml          # Voice settings
│   └── security.toml       # Security settings
│
└── venv/                   # Python virtual environment
```

## LLM Routing

Groq Llama 3.1 8B (fast) → Gemini Flash (complex) → OpenRouter Free → Ollama qwen2.5:1.5b (offline) → template fallback

## Hardware

- Python 3.11.9, Ollama (local models)
- PyQt6 HUD with Arc Reactor visualization
- Piper TTS (local) + Edge-TTS (cloud fallback)
- Groq Whisper (cloud STT) + faster-whisper (local fallback)

## Configuration

Edit `config/jarvis.toml` for settings. API keys go in environment variables or `config/.env`:
```
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
OPENROUTER_API_KEY=sk-or-...
```
