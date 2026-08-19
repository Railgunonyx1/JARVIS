# JARVIS MK-X — Master Roadmap

> Master backlog organized by priority. Research repos are idea sources, not dependencies.
> Every research entry goes through: read -> inspect -> compare -> Adopt/Adapt/Reject -> implement.

## Research Pipeline

Research runs in parallel with implementation but cannot destabilize active sprints.
Research produces proposals, not uncontrolled changes.

```
GitHub repo
     ↓
Read architecture / README / docs
     ↓
Inspect source + tests
     ↓
Identify genuinely superior implementations
     ↓
Compare against JARVIS
     ↓
Classify: Adopt | Adapt | Research further | Reject
     ↓
Update MK-X architecture (if Adopt/Adapt)
     ↓
Create implementation task
```

**Current research backlog (execute in order):**

1. OpenWork — coding-agent workflow, autonomous execution, tool architecture
2. Nanocoder — coding agent, CLI architecture, agent loop, tool execution
3. Rowboat — agent architecture, memory, multi-agent workflows
4. OpenObserve — observability, logs, metrics, traces, event pipelines
5. MindWalk — agent reasoning, memory, context, workflow architecture
6. RowboatLab — agent experimentation, orchestration
7. TUIOS — terminal-native OS concepts, process architecture
8. Terminal UI Operating System — window management, TUI interaction
9. Switchyaro — agent automation, orchestration, workflow patterns
10. Kronos — agent architecture, reasoning, automation
11. Council of High Intelligence — multi-agent councils, deliberation
12. Build AI Agents for Free — low-cost models, local inference

---

## P0 — Critical / Current Kernel

### Kernel & Agent Runtime

- [ ] Reconcile local Sprint 20 with GitHub
- [ ] Verify actual 317/317 test state
- [ ] Audit AgentLoop
- [ ] Finalize state machine
- [ ] Add explicit recovery state
- [ ] Harden cancellation/timeouts
- [ ] Handle context overflow
- [ ] Harden HarnessSelector
- [ ] Harden ModelGateway
- [ ] Make ToolExecutionService the only tool execution boundary
- [ ] Harden VerificationEngine
- [ ] Complete kernel end-to-end tests
- [ ] Protocol conformance testing

### Security

- [ ] Permission engine audit
- [ ] Tool risk classification
- [ ] Shell sandboxing
- [ ] Filesystem sandboxing
- [ ] Generated-code security gate
- [ ] Secret redaction
- [ ] Event persistence redaction
- [ ] Memory redaction
- [ ] Credential isolation
- [ ] Security regression suite
- [ ] Audit all MCP/ACP/Codex execution paths

### Tool System

- [ ] Standardize shell.execute
- [ ] Remove stale shell.cmd references
- [ ] Normalize tool naming
- [ ] Tool capability metadata
- [ ] Tool risk metadata
- [ ] Tool permission metadata
- [ ] Tool timeout metadata
- [ ] Tool side-effect metadata

---

## P1 — Agent Intelligence

### Harness System

- [ ] Native harness
- [ ] Coding harness
- [ ] Research harness
- [ ] Debug harness
- [ ] Computer-use harness
- [ ] Minimal/fast harness
- [ ] Planning harness
- [ ] General-purpose harness
- [ ] Harness-specific tool policies
- [ ] Harness-specific verification policies
- [ ] Harness-specific model requirements
- [ ] Harness evaluation framework

### Planning

- [ ] Goal decomposition
- [ ] Task planning
- [ ] Dynamic replanning
- [ ] Failure recovery
- [ ] Iteration budgets
- [ ] Tool budgets
- [ ] Parallel task execution
- [ ] Subtask delegation
- [ ] Plan verification

### Verification

- [ ] Test verification
- [ ] Ruff verification
- [ ] Type checking
- [ ] Build verification
- [ ] Git diff verification
- [ ] Security verification
- [ ] Automatic repair loop
- [ ] Independent review harness

### Model Gateway

- [ ] Capability-based model routing
- [ ] Provider health tracking
- [ ] Health cooldown
- [ ] Session affinity
- [ ] Model combinations
- [ ] Cost-aware routing
- [ ] Latency-aware routing
- [ ] Context-size routing
- [ ] Vision capability routing
- [ ] Tool-use capability routing
- [ ] Coding capability routing
- [ ] Automatic fallback
- [ ] Local-model routing
- [ ] Hardware-aware model selection

### Providers

- [ ] Gemini
- [ ] Groq
- [ ] OpenRouter
- [ ] OpenCode Zen
- [ ] Mistral
- [ ] NVIDIA NIM
- [ ] OmniRoute
- [ ] Ollama
- [ ] Provider capability normalization

### Memory V2/V3

- [ ] AuthorityMemory
- [ ] Authority levels
- [ ] Rule > decision > procedure > gotcha > session hierarchy
- [ ] Supersession chains
- [ ] Provenance
- [ ] Confidence
- [ ] Memory validation
- [ ] Memory lifecycle (candidate > validated > active > superseded > archived)
- [ ] HOT/WARM/COLD tiers
- [ ] sqlite-vec
- [ ] Semantic retrieval
- [ ] Relevance scoring
- [ ] Authority scoring
- [ ] Recency scoring
- [ ] Project/task matching
- [ ] Memory deduplication
- [ ] Memory pruning
- [ ] Memory compaction
- [ ] Memory evaluation
- [ ] HandoffPacket
- [ ] HandoffBuilder
- [ ] Session recovery

### Event Architecture

- [ ] Canonical BusEvent
- [ ] Event schema versioning
- [ ] Session IDs
- [ ] Trace IDs
- [ ] Event persistence
- [ ] Event replay
- [ ] Session reconstruction
- [ ] Crash recovery
- [ ] Event redaction
- [ ] Event-based observability
- [ ] Task lifecycle events
- [ ] Tool lifecycle events
- [ ] Model events
- [ ] Verification events
- [ ] Memory events

### Protocols & Interoperability

**MCP:**
- [ ] MCP client
- [ ] MCP server
- [ ] External MCP tools
- [ ] Unified ToolExecutionService
- [ ] MCP security tests

**ACP:**
- [ ] ACP adapter
- [ ] ACP client integration
- [ ] ACP conformance tests

**Codex:**
- [ ] Codex Exec adapter
- [ ] Native execution protocol
- [ ] Codex compatibility tests

**Open Interpreter compatibility:**
- [ ] AGENTS.md
- [ ] .agents/skills
- [ ] Shared tool standards
- [ ] Harness interoperability
- [ ] Portable project conventions

### Terminal

**Core TUI:**
- [ ] Claude-Code-style terminal experience
- [ ] Rich renderer
- [ ] Streaming responses
- [ ] Tool progress
- [ ] Task progress
- [ ] Verification status
- [ ] Model indicator
- [ ] Harness indicator
- [ ] Token usage
- [ ] Context usage
- [ ] Latency display
- [ ] Error display
- [ ] Dynamic terminal resizing
- [ ] ANSI correctness
- [ ] Windows console compatibility

**Commands:**
- [ ] /harness
- [ ] /model
- [ ] /session
- [ ] /memory
- [ ] /tools
- [ ] /permissions
- [ ] /status
- [ ] /tasks
- [ ] /config
- [ ] /help

### Task & Process System

- [ ] Production TaskQueue
- [ ] Bounded concurrency
- [ ] Semaphore-based workers
- [ ] Pending task dispatch
- [ ] Cancellation
- [ ] Graceful shutdown
- [ ] Background tasks
- [ ] Foreground tasks
- [ ] Task priorities
- [ ] Task persistence
- [ ] Task recovery
- [ ] Process supervision

### Coding Agent

- [ ] Repository discovery
- [ ] Project detection
- [ ] AGENTS.md discovery
- [ ] .agents/skills discovery
- [ ] Codebase indexing
- [ ] Relevant-file retrieval
- [ ] Context compression
- [ ] Code editing
- [ ] Patch generation
- [ ] Test execution
- [ ] Lint execution
- [ ] Type checking
- [ ] Build checking
- [ ] Diff review
- [ ] Security review
- [ ] Automatic repair
- [ ] Git integration

### Git Intelligence

- [ ] git.status
- [ ] git.diff
- [ ] git.log
- [ ] git.branch
- [ ] git.checkout
- [ ] git.commit
- [ ] git.revert
- [ ] Commit verification
- [ ] Diff review
- [ ] Safe destructive-operation confirmation

### Research Agent

- [ ] Research harness
- [ ] Web search
- [ ] Web extraction
- [ ] Source ranking
- [ ] Evidence collection
- [ ] Claim tracking
- [ ] Citation tracking
- [ ] Source deduplication
- [ ] Research memory
- [ ] Research synthesis
- [ ] Multi-source verification

### Computer Use / Vision

- [ ] Screen capture
- [ ] Screen analysis
- [ ] OCR
- [ ] UI element detection
- [ ] Vision model capability
- [ ] GUI action proposals
- [ ] Permission gating
- [ ] GUI executor
- [ ] Observation loop
- [ ] Visual verification
- [ ] Browser automation
- [ ] Desktop automation

### Windows Reliability

- [ ] InputReader TTY/non-TTY handling
- [ ] Console spawning fixes
- [ ] pythonw.exe where appropriate
- [ ] Subprocess lifecycle
- [ ] Ctrl-C handling
- [ ] EOF handling
- [ ] Terminal resize
- [ ] ANSI/Unicode handling
- [ ] Background process management
- [ ] Daemon lifecycle
- [ ] Shutdown tests
- [ ] Windows regression suite

### Configuration

- [ ] Central configuration loader
- [ ] jarvis.toml
- [ ] models.toml
- [ ] harnesses.toml
- [ ] tools.toml
- [ ] policies.toml
- [ ] Configuration validation
- [ ] Environment overrides
- [ ] Provider configuration cleanup

---

## P2 — Observability & Evaluation

- [ ] Full tracing
- [ ] Task trajectories
- [ ] Token accounting
- [ ] Cost accounting
- [ ] Provider latency
- [ ] Tool latency
- [ ] Verification metrics
- [ ] Harness success rates
- [ ] Model success rates
- [ ] Memory retrieval precision
- [ ] Memory retrieval recall
- [ ] Failure classification
- [ ] Regression benchmarks
- [ ] Agent evaluation suite

---

## P2 — Performance

- [ ] Cold-start benchmark
- [ ] Warm-start benchmark
- [ ] TTFT benchmark
- [ ] Tool latency benchmark
- [ ] Memory retrieval benchmark
- [ ] Context construction benchmark
- [ ] Event-bus benchmark
- [ ] Terminal rendering benchmark
- [ ] Provider benchmark
- [ ] Memory usage tracking
- [ ] CPU usage tracking
- [ ] Concurrency benchmark
- [ ] Hardware-aware optimization

---

## P2 — Codebase Cleanup

**Do not run a blanket ruff --fix until the architecture is frozen.**

- [ ] Ruff modernization (by subsystem: core/ > providers/ > memory/ > runtime/ > tools/ > tests/ > cli/ > workflows/ > legacy/)
- [ ] Import cleanup
- [ ] Type modernization
- [ ] Whitespace cleanup
- [ ] Workflow refactoring
- [ ] Remove unused variables
- [ ] Remove dead code
- [ ] Remove duplicate utilities
- [ ] Clean root artifacts
- [ ] Improve .gitignore
- [ ] Remove obsolete test dumps
- [ ] Consolidate configuration

---

## P2 — Dependency & Supply Chain

- [ ] pip-audit
- [ ] Review LiteLLM vulnerabilities
- [ ] Review aiohttp vulnerabilities
- [ ] Review cryptography vulnerabilities
- [ ] Update vulnerable dependencies
- [ ] Verify compatibility
- [ ] Lock production dependencies
- [ ] Separate development dependencies
- [ ] Dependency regression tests

---

## P2 — Voice

- [ ] Groq Whisper
- [ ] faster-whisper
- [ ] Non-blocking local STT
- [ ] Piper TTS
- [ ] Edge-TTS fallback
- [ ] Voice barge-in
- [ ] Speech cancellation
- [ ] Voice event integration
- [ ] TTS secret/output redaction
- [ ] Voice > IntentRouter > AgentKernel

---

## P3 — Multimodal

- [ ] Text input
- [ ] Voice input
- [ ] Image input
- [ ] Screenshot input
- [ ] File input
- [ ] Vision reasoning
- [ ] Multimodal memory
- [ ] Multimodal tool execution

All must converge on the same AgentKernel.

---

## P3 — Web / Tauri Client

- [ ] WebSocket gateway
- [ ] React 19
- [ ] Vite
- [ ] Tailwind v4
- [ ] Zustand
- [ ] Tauri
- [ ] Live event rendering
- [ ] Terminal/client synchronization
- [ ] Session management
- [ ] Model/harness controls
- [ ] Tool visualization

The GUI is a client of JARVIS, not a second agent implementation.

---

## P3 — Plugin Ecosystem

- [ ] Plugin manifest
- [ ] Plugin discovery
- [ ] Plugin lifecycle
- [ ] Plugin tools
- [ ] Plugin skills
- [ ] Plugin commands
- [ ] Plugin permissions
- [ ] Plugin events
- [ ] Plugin isolation
- [ ] Plugin compatibility tests

---

## P3 — Advanced Multi-Agent System

- [ ] Subagent manager
- [ ] Specialized subagents
- [ ] Research agent
- [ ] Coding agent
- [ ] Testing agent
- [ ] Review agent
- [ ] Planner agent
- [ ] Agent handoffs
- [ ] Agent budgets
- [ ] Agent isolation
- [ ] Multi-agent evaluation
- [ ] Council/deliberation architecture

The Council of High Intelligence research should inform this phase.

---

## Repo Status

- **Sprint 0 (done):** Observability core
- **Sprint 1 (done):** Agent Runtime Baseline
- **Phase 1 (done):** Controlled demolition (legacy quarantined)
- **Sprints 2-15 (done):** Agent kernel, memory, tools, providers, event bus, terminal, persistence
- **Sprint 16 (done):** Model Gateway (capability routing, health, affinity, combos)
- **Sprint 17 (done):** Harness abstraction (6 types, auto_select, tool filtering)
- **Sprint 18 (done):** Authority Memory (supersession, provenance, HandoffPacket)
- **Sprint 19 (done):** Protocol adapters (MCP, ACP, Codex)
- **Sprint 20 (in progress):** Kernel integration (wiring Harness + Gateway + ToolService + Verification)
- **Current:** Phase A — kernel wiring. 317/317 tests green.
