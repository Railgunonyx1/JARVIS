# JARVIS MK-X — Roadmap

Terminal-first, lightweight, Claude Code–style engineering agent.

> This roadmap is the master backlog. Completed items are checked. The repo state and
> per-sprint status live at the bottom; the Phase 1 controlled demolition is what enforces
> the **terminal-first / no-voice / no-unnecessary-UI-frameworks** constraints.

## Guiding Constraints

- Terminal-first
- Very low RAM usage
- Fast first paint
- Daemon-first
- Model-agnostic, provider-agnostic
- Persistent memory
- Strong context engineering
- Autonomous but permission-aware
- Self-improving, but never blindly self-modifying
- Everything measurable, everything testable
- No unnecessary UI frameworks
- No voice subsystem unless the architecture changes explicitly

## 1. Core Runtime & Daemon

- [ ] Make the daemon the single runtime authority
- [ ] Fix daemon crash/cancellation paths
- [ ] `asyncio.shield()` in-flight runs
- [ ] Preserve running tasks after client disconnect
- [ ] Top-level daemon crash logging
- [ ] Automatic daemon resurrection
- [ ] Watchdog / health monitoring
- [ ] Stale daemon registry cleanup
- [ ] Windows `CREATE_BREAKAWAY_FROM_JOB`
- [ ] WMI fallback spawning
- [ ] 50+ connect/disconnect survivability test
- [ ] Interrupted-request survivability test
- [ ] Real-terminal detached-daemon validation

## 2. Extreme Startup & RAM Optimization

- [x] Startup profiler (`runtime/startup_profile.py`, `--profile-startup`)
- [x] `jarvis.cli.startup` trace with milestone spans (config/tools/project/router/memory)
- [ ] Target ~100 ms launch feel
- [ ] Target interactive prompt <1 s
- [ ] Target ~0.6 s fast CLI path
- [ ] Build stdlib-only `cli/fast.py`
- [ ] Lazy-load Typer/Rich
- [ ] Eliminate expensive imports from first paint
- [ ] Import-time benchmark CSV
- [ ] memray profiling
- [ ] tracemalloc snapshots
- [ ] Bytecode precompilation
- [ ] Min-of-N benchmark harness
- [ ] Windows Defender performance investigation
- [ ] Measure interpreter / daemon / IPC / provider separately
- [ ] Keep UI viable on 512 MB RAM
- [ ] Investigate Prompt Toolkit virtual-screen/diff rendering
- [ ] Dirty-cell-only terminal redraw
- [ ] Avoid Rich on first paint
- [ ] Background initialization after prompt appears

## 3. Performance Observability

- [x] `runtime/observability/` package
- [x] `tracer.py`, `metrics.py`, `spans.py`, `exporters.py`, `dashboard.py`
- [x] SQLite performance database (`~/.jarvis/perf.db`)
- [x] Trace IDs / span IDs, ns precision, thread/process IDs
- [x] Startup spans (`jarvis.cli.startup` + milestone spans)
- [x] IPC spans (`daemon/server.py`, `daemon/client.py`)
- [x] Provider spans (`router.complete` / `router.stream` / `llm.request`)
- [x] Memory spans (`memory.retrieve` / `memory.prompt`)
- [x] `jarvis perf latest|slowest|summary`
- [ ] `jarvis perf startup`
- [ ] `jarvis perf regression`
- [ ] `jarvis dashboard`
- [ ] `jarvis benchmark`
- [ ] Loop-lag monitoring
- [ ] Cache hit/miss telemetry
- [ ] Automatic regression detection
- [ ] Per-commit performance history
- [ ] Optional OpenTelemetry / JSON / OTLP exporter
- [ ] Retention/pruning policy

## 4. Provider System

- [x] Provider abstraction (`providers/base.py`, `providers/router.py`)
- [x] Streaming TTFT + tokens-per-second KPIs (`llm.ttft_ms`, `llm.tokens_generated`)
- [x] Automatic failover / fallback events
- [x] Metrics counters (`provider.ok/fail`)
- [ ] Dynamic provider routing
- [ ] Provider capability registry
- [ ] Provider health registry
- [ ] Provider metadata cache
- [ ] Fail-fast on HTTP 429
- [ ] Retry budget ≈ 1
- [ ] Stream provider output immediately
- [ ] Offline fallback
- [ ] Provider latency benchmarking
- [ ] Provider quality benchmarking
- [ ] Provider cost tracking
- [ ] Hardware-aware model selection
- [ ] Automatic model selection
- [ ] Research NVIDIA build.nvidia.com + add provider
- [ ] Research GLM, Moonshot AI, DeepSeek
- [ ] Research OpenRouter-style routing
- [ ] Research Ollama, vLLM, llama.cpp, AirLLM, LiteLLM
- [ ] Research free LLM API ecosystems
- [ ] Evaluate unified API normalization

## 5. Memory System

- [x] `MemoryWorker` determinism fix (explicit ownership: `pause`/`resume`/`start`, deterministic `drain`, `close` joins)
- [ ] Rework persistent memory architecture
- [ ] Short-term / working / long-term memory separation
- [ ] Semantic memory
- [ ] Episodic memory
- [ ] Project memory
- [ ] User preference memory
- [ ] Memory importance scoring
- [ ] Memory consolidation
- [ ] Memory decay
- [ ] Duplicate-memory detection
- [ ] Memory retrieval ranking
- [ ] Context compression
- [ ] Memory-aware context budgeting
- [ ] SQLite-based persistence
- [ ] Evaluate sqlite-vec, Mem0, Supermemory, vector databases
- [ ] Pre-computed embeddings
- [ ] Disk-backed caches
- [ ] Memory benchmark suite
- [ ] Memory correctness tests
- [ ] Memory retrieval latency tests

## 6. Self-Improvement / Self-Learning

- [ ] Clone/sandbox JARVIS runtime
- [ ] Separate stable and experimental JARVIS instances
- [ ] Experimental instance can propose improvements
- [ ] Generate changes in isolated workspace
- [ ] Run tests automatically
- [ ] Run benchmarks automatically
- [ ] Security checks before promotion
- [ ] Performance comparison against baseline
- [ ] Human approval gate
- [ ] Promote only verified changes
- [ ] Automatic rollback
- [ ] Versioned memory/schema
- [ ] Versioned agent skills
- [ ] Change provenance
- [ ] Improvement history
- [ ] Research Prime Agent, OpenHands, MetaGPT, AutoGen, autonomous coding agents

## 7. Coding-Agent Architecture

- [ ] Persistent coding context
- [ ] Repository understanding
- [ ] Incremental code indexing
- [ ] File-change awareness
- [ ] Automatic test generation
- [ ] Automatic test execution
- [ ] Automatic debugging loop
- [ ] Structured code review
- [ ] Spec-first development
- [ ] Plan → implement → test → review loop
- [ ] Minimal-change principle
- [ ] Clarification-before-action principle
- [ ] Goal-driven execution
- [ ] Agent checkpoints
- [ ] Recovery from failed actions
- [ ] Long-running task scheduler
- [ ] Background coding tasks
- [ ] Agent task queues
- [ ] Agent inbox
- [ ] Multi-agent delegation
- [ ] Agent-to-agent communication
- [ ] Agent personas/roles
- [ ] Agent permissions
- [ ] Agent skill system (creator, discovery, versioning, testing)

## 8. Browser / Computer Automation

- [ ] Browser automation layer
- [ ] Research Playwright, Browser Use, Camofox Browser
- [ ] Agent browser
- [ ] Browser task verification
- [ ] Browser permissions
- [ ] Browser session persistence
- [ ] Website context extraction
- [ ] Automatic browser recovery

## 9. MCP / Tools / Integrations

- [ ] MCP client architecture
- [ ] MCP server discovery
- [ ] Tool registry
- [ ] Tool capability metadata
- [ ] Tool permissions
- [ ] Tool sandboxing
- [ ] Tool execution audit trail
- [ ] Tool timeout/retry policy
- [ ] External API connector system
- [ ] Unified connector abstraction
- [ ] Research Open WebUI, LibreChat, Omni.bot, Goose, Agent Reach, Agent Inbox, Cloudflare Agentic Inbox, OpenWork/Open Worker

## 10. Context Engineering

- [ ] Context engineering architecture
- [ ] Context hierarchy
- [ ] Context prioritization
- [ ] Context compression
- [ ] Context caching
- [ ] Context invalidation
- [ ] Project-context files
- [ ] Repository-context indexing
- [ ] Dynamic context assembly
- [ ] Context budgets
- [ ] Context quality scoring
- [ ] Research context-engineering repos/templates, Claude context patterns, Karpathy skills, Awesome Claude Skills

## 11. Agent Workflow / Automation

- [ ] Workflow engine
- [ ] Visual/debuggable workflow representation
- [ ] Event-driven execution
- [ ] Background jobs
- [ ] Scheduled jobs
- [ ] Task dependencies
- [ ] Retry/recovery graphs
- [ ] Human approval checkpoints
- [ ] Research n8n, LangFlow, LangChain, Semantic Kernel, Supabase, Coolify, OpenShift

## 12. RAG / Search / Knowledge

- [ ] RAG subsystem
- [ ] Document ingestion pipeline
- [ ] Incremental indexing
- [ ] Semantic search
- [ ] Hybrid search
- [ ] Reranking
- [ ] Context-aware retrieval
- [ ] PDF ingestion / inspection
- [ ] Web crawling
- [ ] Research Crawl4AI, Firecrawl, RAGFlow, LlamaIndex, Transformers, Supermemory

## 13. Research / Deep Research

- [ ] Deep-research agent
- [ ] Multi-step research planning
- [ ] Parallel source gathering
- [ ] Source verification
- [ ] Evidence tracking
- [ ] Citation tracking
- [ ] Research memory
- [ ] Research cache
- [ ] Research task queue
- [ ] Background research execution
- [ ] Research Odysseus, Agent Reach, open-source research agents

## 14. Security

- [ ] Resolve all Bandit HIGH findings
- [ ] Resolve medium security findings
- [ ] Security CI
- [ ] Dependency auditing
- [ ] Secret scanning
- [ ] Tool sandboxing
- [ ] Command permission system
- [ ] Filesystem permissions
- [ ] API-key isolation
- [ ] Scoped API tokens
- [ ] Role-based permissions
- [ ] Action approval system
- [ ] Full audit log
- [ ] Research STRIX, Authentik, security-agent architectures

## 15. Code Quality / CI

- [x] Ruff (`select E/F/W/I/UP/B/PLW`, line-length 120, py311)
- [x] Import-order cleanup (stale isort entries for quarantined packages removed)
- [x] Pytest discovery + guard suite (`tests/test_imports.py`)
- [ ] Ruff format
- [ ] MyPy
- [ ] Fix duplicate modules
- [ ] Dependency audit
- [ ] Upgrade outdated dependencies carefully
- [ ] Dependency pinning
- [ ] Test coverage
- [ ] CI test / lint / type-check / security / benchmark stages
- [ ] Performance regression gates

## 16. Terminal UI

- [x] Terminal-only architecture (legacy UI/vision/web quarantined)
- [ ] Minimal first paint
- [ ] Zero heavy framework on startup
- [ ] Prompt-first rendering
- [ ] Virtual terminal buffer
- [ ] Diff-based redraw
- [ ] Keyboard shortcuts
- [ ] Performance dashboard
- [ ] Ctrl+Shift+P performance panel
- [ ] Startup / memory / cache / provider / IPC metrics
- [ ] Optional Rich dashboard
- [ ] Prompt Toolkit final UI
- [ ] Research btop / fzf interaction patterns
- [ ] Adaptive UI scaling by physical screen size
- [ ] Context-aware panel visibility (resource monitor vs next-steps box)
- [ ] ANSI-color progress bars (minimal, no extra weight)
- [ ] Collapsible per-message blocks (reasoning, tool calls, token usage)
- [ ] Persistent next-steps box updated only when the topic changes

## 17. AI / Model Infrastructure

- [ ] Ollama, vLLM, llama.cpp, AirLLM, Transformers, LlamaIndex, NanoChat
- [ ] DeepSeek, GLM, Moonshot, NVIDIA hosted models
- [ ] Local-model fallback
- [ ] Model quantization research
- [ ] KV-cache optimization
- [ ] Context-length optimization
- [ ] Memory-efficient inference
- [ ] CPU-only fallback
- [ ] Hardware-aware routing

## 18. Voice — Explicitly Excluded

- [x] Do NOT add voice pipelines
- [x] `pipeline/`, `voice_engine/` quarantined to `_quarantine_removed/` (Phase 1 demolition)
- [x] JARVIS remains terminal-first / terminal-only

## 19. Design / UI Research

- [ ] Research Gesso / gesso.build, sketch-to-UI systems, CAD/text-to-CAD systems
- [ ] Research Fooocus
- [ ] Smart defaults
- [ ] Progressive disclosure
- [ ] Preset system
- [ ] Automatic configuration
- [ ] Consistency validation
- [ ] Design-review agents

## 20. Competitive / Open-Source Research Library

Extract reusable ideas (research-and-extraction backlog, not "install everything"):

- [ ] Prime Agent, OpenHands, OpenWork/Open Worker, STRIX
- [ ] Multi-CAI / agent skill projects, Awesome LLM Apps, Agency Agents
- [ ] LibreChat, Open WebUI, Omni.bot, Goose
- [ ] Agent Reach, Agent Inbox, Cloudflare Agentic Inbox
- [ ] Camofox Browser, Browser Use, AutoGen, MetaGPT, LangChain, LangFlow, n8n
- [ ] Mem0, RAGFlow, Crawl4AI, Firecrawl, Semantic Kernel
- [ ] Supabase, Coolify
- [ ] AirLLM, vLLM, llama.cpp, Ollama, open-source LLM API collections, Awesome Free LLM APIs
- [ ] Awesome Claude Skills, Karpathy Skills, Skill Creator
- [ ] System-prompt collections, AI project templates, context-engineering resources
- [ ] Awesome coding/resources collections

## 21. Trading / Finance Ideas

- [ ] Research Fincept Terminal, Trading Agent, AutoHedge, financial-agent architectures
- [ ] Market-data pipelines
- [ ] Finance research tools
- [ ] Risk/approval checkpoints
- [ ] Keep financial execution sandboxed and non-autonomous by default

## 22. General Engineering Knowledge

- [ ] Build Your Own X, Developer Roadmap, System Design Primer, Public APIs
- [ ] Free Programming Books, The Art of Command Line, Coding Interview University
- [ ] Algorithms/data-structure references, system-design patterns
- [ ] API design patterns, distributed-systems patterns, CLI architecture patterns

## 23. Final Architecture Goal

Terminal → ultra-fast client → permanent daemon → intelligent router → model/provider layer
→ context engine → memory → tools/MCP → autonomous task engine → verification → telemetry
→ controlled self-improvement.

## Repo Status

- **Sprint 0 (done):** Observability core — `runtime/observability/` (tracer, spans, metrics,
  exporters, SQLite perf DB), instrumentation of agent loop, providers, memory, daemon, CLI.
- **Sprint 1 — Agent Runtime Baseline (done):** MemoryWorker race fixed; TTFT + tokens/sec
  KPIs; `jarvis.cli.startup` trace wired through boot; full suite green (97 tests), ruff clean.
- **Phase 1 — Controlled demolition (done):** `pipeline/`, `actions/`, `voice_engine/` moved to
  `_quarantine_removed/`; `tests/test_imports.py` guards resurrection; surviving closure verified
  free of the quarantined packages.
- **Next milestone:** JARVIS can open a repository, understand its structure, ask for a task,
  plan changes, and execute one safe filesystem operation through the terminal
  (see Sections 7, 10, 16).
- **Blocked:** git recovery points (branch/tag/manifest) require a git-equipped machine; real
  detached-daemon and live-LLM TTFT numbers require the user's terminal + API access.
