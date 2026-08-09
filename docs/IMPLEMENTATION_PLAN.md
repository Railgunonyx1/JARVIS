# JARVIS — Implementation & Research Plan

Companion to [`ROADMAP.md`](ROADMAP.md). Converts the research backlog into an actionable
plan. Checked items reflect what already exists in the repo; everything else is backlog.

> **Master rule for every external repo/resource:** (1) identify the exact repo,
> (2) read README/architecture/examples/deps, (3) run it separately where practical,
> (4) extract architecture, algorithms, UX, memory/context, agent loops, performance,
> testing, security, (5) benchmark anything performance-related, (6) decide
> **Adopt / Adapt / Research only / Reject**, (7) implement only the useful parts,
> (8) add a JARVIS-specific test, (9) benchmark before/after, (10) document why it exists.
>
> Repositories are **idea sources**, not dependencies to install blindly.

## 1. JARVIS Core Architecture

Goal: daemon = permanent runtime, CLI = very thin client.

- [ ] Make `jarvis` CLI a lightweight client
- [ ] Make daemon the only long-lived runtime
- [ ] Create a stable IPC protocol
- [ ] Add request IDs
- [ ] Add trace IDs
- [ ] Add daemon health endpoint
- [ ] Add daemon auto-restart
- [ ] Add stale-process detection
- [ ] Add crash recovery
- [ ] Add graceful shutdown
- [ ] Add cancellation-safe execution
- [ ] Add client-disconnect protection
- [ ] Add Windows process-detachment handling
- [ ] Benchmark every IPC operation
- [ ] Eliminate local-runtime fallback unless daemon recovery genuinely fails

**Success criterion:** launch → connect → send request, NOT launch → import Python →
initialize JARVIS → initialize providers → initialize memory → finally show prompt.

## 2. Extreme Startup Optimization

Target: **perceived launch ~100–600 ms on Windows.**

- [x] Startup profiler + `--profile-startup` (`runtime/startup_profile.py`)
- [x] `jarvis.cli.startup` trace with milestone spans
- [ ] Startup benchmark harness
- [ ] Measure interpreter floor / import time / CLI init / daemon connect / first prompt / first request / first token
- [ ] Import-time CSV; identify top 20 expensive imports
- [ ] Lazy-load expensive packages
- [ ] Remove Rich / Typer from critical startup path
- [ ] Build `cli/fast.py`
- [ ] Precompile bytecode
- [ ] Investigate Windows Defender overhead
- [ ] Benchmark filesystem access / socket-IPC / process creation
- [ ] Keep expensive initialization asynchronous/background
- [ ] Never initialize embeddings/models before the prompt is usable

Tools to investigate: Memray, py-spy, tracemalloc, `-X importtime`, Ruff, Python profilers.

## 3. 512 MB UI Architecture

Build the UI independently from the model.

- [x] Terminal-only (legacy UI/vision/web quarantined)
- [ ] No Electron / no browser runtime / no heavy frontend
- [ ] Avoid persistent Rich application state
- [ ] Investigate Prompt Toolkit
- [ ] Virtual terminal buffer
- [ ] Dirty-region detection
- [ ] ANSI-only updates
- [ ] Incremental redraw
- [ ] Lazy dashboard loading
- [ ] Memory / CPU / startup benchmark

Borrow from Fooocus: smart defaults, progressive disclosure, presets, automatic configuration.

## 4. Daemon Survivability

Based on the actual WinError 64 issue.

- [x] IPC spans + timing (`daemon/server.py`, `daemon/client.py`)
- [ ] `asyncio.shield()` in-flight requests
- [ ] Keep references to protected tasks
- [ ] Don't cancel active LLM calls merely because a client disconnects
- [ ] Top-level `BaseException` logging / crash traceback / `~/.jarvis/daemon.log`
- [ ] Automatic daemon resurrection
- [ ] Watchdog
- [ ] Stale registry cleanup
- [ ] 50+ connection/disconnection test
- [ ] Interrupted-request test
- [ ] Long-running daemon test
- [ ] Real Windows terminal validation

## 5. Provider Router

JARVIS should not care which provider answers.

- [x] Provider interface (`providers/base.py`)
- [x] Router with fallback (`providers/router.py`)
- [x] Streaming TTFT + tokens/sec KPIs (`llm.ttft_ms`, `llm.tokens_generated`)
- [x] Metrics counters (`provider.ok/fail`)
- [ ] Capability registry
- [ ] Health registry
- [ ] Latency history / cost history
- [ ] Context-window / tool-calling / vision / reasoning / streaming metadata
- [ ] Provider selection algorithm
- [ ] 429 fail-fast
- [ ] One retry maximum
- [ ] Immediate fallback / provider cooldown / automatic recovery
- [ ] Local-model fallback
- [ ] Offline response fallback
- [ ] Provider benchmarking

## 6–14. Provider Research & Adapters

- [ ] **NVIDIA build.nvidia.com** — verify API + terms; adapter; normalized streaming;
      capability metadata; health; latency; compare vs existing; routing-table entry; no
      NVIDIA-specific behavior in core.
- [ ] **Awesome Free LLM APIs** — provider discovery DB (model, context length, limits,
      modalities, tools, streaming, availability); auto health-checking; failover; capability
      registry; metadata caching; rate-limit awareness; free-tier monitoring; periodic benchmarks.
- [ ] **LiteLLM** — isolated benchmark vs native abstraction (import/RAM overhead, routing,
      fallback, streaming, normalization). **Decision gate: performance > convenience.**
- [ ] **Ollama** — local backend; discovery; health; capability registry; local fallback;
      benchmark cold/warm/RAM/context; model-selection rules.
- [ ] **vLLM** — evaluate high-throughput backend (latency/memory/batching) only where
      hardware justifies it; keep optional.
- [ ] **llama.cpp** — CPU/local inference; quantized models; RAM; startup; tokens/sec;
      low-resource local fallback.
- [ ] **AirLLM** — memory-saving inference; benchmark large-model execution; CPU/RAM overhead;
      compare vs quantization; adopt only if it helps the actual hardware target.
- [ ] **Transformers** — study loading architecture; keep imports lazy; never mandatory;
      separate inference process from UI process; quantization/backends.
- [ ] **GLM / Moonshot AI / DeepSeek** (each) — adapter; capability metadata; long-context,
      reasoning, tool-calling, coding, TTFT, cost/availability benchmarks; feed router.

## 15. Memory Architecture

One of the most important areas.

```
Current conversation → Working memory → Context processor → Memory retrieval → Long-term memory → Consolidation
```

- [x] Deterministic `MemoryWorker` (explicit ownership: pause/resume/start, safe drain/close)
- [ ] Working / episodic / semantic / project / user-preference memory
- [ ] Importance / confidence / timestamps / provenance
- [ ] Memory decay / consolidation
- [ ] Duplicate & contradiction detection
- [ ] Retrieval ranking
- [ ] Context compression / memory budget

## 16–22. Memory & Retrieval Research

- [ ] **Mem0** — isolated benchmark (retrieval quality, RAM, latency, persistence); extract
      architecture; integrate or reproduce only useful mechanisms.
- [ ] **Supermemory** — long-term architecture, context retrieval, compression, relevance
      ranking; compare; benchmark.
- [ ] **sqlite-vec** — vector storage vs current backend; RAM/disk/latency; millions of
      vectors; cold start; prefer if it keeps the stack local and lightweight.
- [ ] **LlamaIndex** — study ingestion/retrieval/indexing/document loaders; benchmark dep
      overhead; borrow architecture; avoid making it mandatory.
- [ ] **RAGFlow** — study document pipelines, parsing, retrieval, chunking, metadata.
- [ ] **Crawl4AI** — web extraction backend; clean-page → markdown → structured extraction;
      crawl caching; incremental crawling; robots/permissions; source provenance.
- [ ] **Firecrawl** — compare vs Crawl4AI; don't duplicate both unless benchmarks justify.

## 23–25. Browser Automation

- [ ] **Browser Use** — goal-based navigation; page understanding; action execution;
      verification; failure recovery; permissions; session isolation; Playwright backend.
- [ ] **Playwright** — automation backend; persistent sessions; lifecycle management;
      screenshot/state capture; action verification; timeouts; recovery; permission
      boundaries; completely optional subsystem.
- [ ] **Camofox Browser** — study browser-agent architecture, anti-fragile interaction,
      context extraction; compare; integrate only unique useful patterns.

## 26. MCP

- [ ] MCP client; server discovery; tool registry
- [ ] Tool schemas; permission system; sandbox; timeout; audit logs; versioning; health checks

## 27–36. Agent & Integration Research

- [ ] **Open WebUI** — study provider abstraction, model management, tool integration,
      conversation management; extract backend concepts; don't copy the web UI.
- [ ] **LibreChat** — multi-provider architecture, agent/tool integrations, conversation
      config, plugin architecture.
- [ ] **Goose** — extensible agent, tool system, provider abstraction, config, permission
      model; adapt to terminal JARVIS.
- [ ] **OpenHands** — coding-agent loop (planning, editing, terminal execution, testing,
      error feedback, iteration), workspace isolation, human approval; extract architecture.
- [ ] **Prime Agent** — self-improvement loop, coding workflow, autonomous planning,
      test/verification loop; compare against experimental clone; safe improvement sandbox.
- [ ] **MetaGPT** — role-specialized agents (architect → dev → tester → reviewer);
      structured communication; adapt only if it improves coding.
- [ ] **AutoGen** — multi-agent orchestration, communication, termination, delegation;
      benchmark vs simpler orchestration.
- [ ] **Agency Agents** — personas/reusable roles; skill/persona registry; role-specific
      system instructions; personalities subordinate to task requirements.
- [ ] **Agent Inbox / Cloudflare Agentic Inbox** — task queue, inbox, priority, task state,
      assignment, background execution, retry, human escalation, history.
- [ ] **Agent Reach** — external-service connectors, connector registry, permissions, audit logs.

## 37. Skill Systems

Sources: Karpathy Skills, Awesome Claude Skills, Skill Creator, agent/multi-agent skill repos.

- [ ] Skill schema; metadata; discovery; installation; versioning
- [ ] Skill permissions; testing; benchmarking; dependencies; deprecation
- [ ] Skill creator agent; automatic skill improvement

## 38. Context Engineering

Sources: Context Mode, Context Engineering Intro/Template, Claude context concepts, Karpathy Skills.

- [ ] Context hierarchy; priority; budget; compression; caching; invalidation
- [ ] Project / repository / tool / memory / task context
- [ ] Automatic context assembly

## 39–45. Workflow & Backend Research

- [ ] **n8n** — event-driven workflows, node architecture, persistence, retries, scheduling,
      execution history; lightweight subset if useful.
- [ ] **LangChain** — tool/model abstraction, retrieval, memory interfaces, agent execution;
      benchmark dep overhead; don't import the framework for abstractions we can write.
- [ ] **LangFlow** — workflow representation, components, debugging, execution graphs;
      consider a lightweight internal graph representation.
- [ ] **Semantic Kernel** — plugins, planners, memory, orchestration, typed tool interfaces;
      compare vs native.
- [ ] **Supabase** — database/service architecture, auth, realtime, persistence; not mandatory
      for local-first.
- [ ] **Coolify** — self-hosting, deployment abstraction, service lifecycle, env config;
      potential future deployment manager.
- [ ] **OpenShift** — container orchestration, service deployment, secrets, health checks;
      future deployment research only.

## 46–47. Security

- [ ] **STRIX** — autonomous security testing, coordination, attack/verification loops;
      adapt defensive validation patterns; never unrestricted security autonomy.
- [ ] **Authentik** — identity architecture, RBAC, scoped permissions, API tokens, sessions,
      auth boundaries; optional for future multi-user.

## 48–50. UX & Telemetry Research

- [ ] **Open Worker / OpenWork** — permission model, connectors, agent execution, task
      lifecycle, workspace architecture; extract backend; skip web/desktop UI.
- [ ] **Fooocus** — smart defaults, presets, progressive disclosure, automatic configuration.
- [ ] **Plausible CE** — privacy-first local telemetry, lightweight analytics, dashboard
      architecture; no unnecessary external telemetry.

## 51–52. LLM App Catalogs

- [ ] **Open-source LLM Apps (Shubham Saboo)** — catalogue; extract RAG/agent/MCP/tool-use
      patterns; voice ideas research-only; benchmark only terminal-relevant ideas.
- [ ] **Awesome Free LLM APIs** — periodic discovery, availability validation, capability
      metadata refresh, dead-API detection, limit-change detection, provider score.

## 53–55. Finance & Research Agents

- [ ] **Fincept Terminal** — terminal information density, modular data providers, plugins,
      market-data pipelines, keyboard nav; borrow UX; isolate financial execution.
- [ ] **Trading Agent / AutoHedge** — decision architecture, data pipelines, risk checks,
      approval checkpoints; **no autonomous real-money actions; sandbox simulations only.**
- [ ] **Odysseus** — local-first architecture, persistent memory, agents, documents, deep
      research, MCP/tool ecosystem, hardware-aware routing; adapt backend; don't recreate the
      workspace UI.

## 56–60. Verify-Repo & Optional Capabilities

- [ ] **Project Handwrite / Citro Labs / related** — verify exact repo; read architecture;
      identify unique idea; benchmark; extract; reject if redundant.
- [ ] **CAD / text-to-CAD** — structured-output generation, CAD reasoning, validation,
      iterative generation; optional future capability; no heavy CAD deps in core.
- [ ] **PDF tools** — extraction, layout-aware parsing, tables, OCR fallback, page-level
      retrieval, citation provenance; research PDF Inspector / Stirling PDF; keep off startup path.
- [ ] **ComfyUI** — node-based workflows, modular components, serialization; apply the concept
      to JARVIS's internal task graph.
- [ ] **NanoChat / AI learning projects** — minimal LLM implementations as learning reference,
      not runtime deps.

## 61–69. Knowledge & Learning Corpus

- [ ] **Build Your Own X** — tiny prototypes (DBs, shells, networking, interpreters, search,
      schedulers, distributed systems) to understand architecture before implementing.
- [ ] **System Design Primer** — IPC, caching, queues, databases, distributed execution,
      fault tolerance, observability, load management, consistency, scalability.
- [ ] **Developer Roadmap** — curriculum: Python internals, async, networking, databases,
      OS/processes, distributed systems, security, testing, profiling, AI systems, agents.
- [ ] **Art of the Command Line** — CLI conventions, Unix composability, stdin/stdout, pipes,
      exit codes, signals, shell integration, scripting interface.
- [ ] **Public APIs** — API discovery registry, metadata, auth patterns, rate limits, health,
      tool generation from schemas.
- [ ] **Free Programming Books / Coding Interview University / Algorithms** — local searchable
      knowledge base; index concepts; semantic retrieval; source provenance; study agent.
- [ ] **You Don't Know JS / JS Algorithms / 30 Seconds of Code** — coding knowledge corpus;
      index examples; preserve attribution; no blind copying.
- [ ] **AI / AI Agents for Beginners / 100 Days of ML** — learning corpus; index; explanation
      tools; educational reference only.
- [ ] **System Prompts** — prompt subsystem: templates, versioning, A/B testing, metadata,
      performance tracking, model/task-specific prompts, regression tests, rollback.

## 70–72. Verify-Repo Items (uncertain names)

- [ ] **Gesso / gesso.build** — verify project; sketch/design → UI generation; design
      interpretation; structured UI representation; consistency validation.
- [ ] **Goose** — see §29.
- [ ] For every partially spoken / unverified name, **verify repo, author, state, purpose,
      extract only verified ideas**: CoreBunch/Static, OpenGen, Project Handwrite, Citro Labs,
      Ego Light, PDF Inspector, J-code, Colibri, Graphify, ABC Bench, "Unilia", "Mono",
      "Dot Netify", "Pony Tail Codex", "G-stack", "Caveman", "Last 30 Days", "Fine Skills",
      "Cloud Heard", and other unresolved names.

## 73. Performance Dashboard

- [x] SQLite metrics database (`~/.jarvis/perf.db`)
- [x] Recent traces / slowest traces (`jarvis perf latest|slowest|summary`)
- [x] Startup, provider, IPC, memory spans
- [ ] Startup / memory / cache / provider / IPC / pipeline panels
- [ ] Regression comparison
- [ ] Hotkey; lazy-load; keep completely outside critical startup path

## 74. SQLite Observability Core

```
runtime/observability/ → tracer.py, metrics.py, spans.py, exporters.py, db.py, schema.sql, dashboard.py, regression.py
```

- [x] Trace model / span model (ns precision, thread/process IDs, errors)
- [x] SQLite exporter (WAL, `synchronous=NORMAL`, `idx_traces_duration`)
- [x] Counters / per-trace metrics
- [x] CLI performance commands
- [x] Integration tests (`tests/test_observability.py`)
- [ ] `db.py` / `schema.sql` as named modules (currently inside `exporters.py`)
- [ ] DB migration / trace retention / pruning
- [ ] Read-only performance queries
- [ ] `regression.py`

## 75. Self-Improving JARVIS

```
Stable → Experimental → Analyze repo → Propose improvement → Implement in sandbox → Run tests
→ Run benchmarks → Security validation → Compare baseline → worse: discard / better: human approval → promote
```

- [ ] Git worktree isolation; experimental branch
- [ ] Automated implementation, tests, benchmarks
- [ ] Security & dependency checks
- [ ] Human approval; automatic rollback; improvement history
- [ ] Never allow unrestricted self-modification

## 76. JARVIS Research Intelligence

**The single highest-leverage piece** — turns "find cool repos" into a systematic subsystem.

```
Repository → Architecture extraction → Feature extraction → Benchmark → Similarity check
→ JARVIS relevance score → Adopt/Adapt/Research/Reject → Roadmap
```

Registry per repo: URL, author, license, stars/activity, architecture notes, feature matrix,
dependency footprint, RAM footprint, performance measurements, security assessment, relevance
score, implementation status, duplicate detection.

## 77. Final Architecture

Tiny CLI client → IPC → daemon (scheduler, task manager, router, permissions) → context
engine + memory engine → agent/planner → tools / code / research → provider router →
NVIDIA / cloud / local (Ollama, llama.cpp) → verification → observability → self-improvement
→ experimental JARVIS → approval → stable JARVIS.

## Execution Order

Do not implement in discovery order. Tiers:

- **Tier 1 Foundation:** daemon survivability, fast CLI, 512-MB UI, IPC, provider router,
  observability/SQLite, benchmark framework
- **Tier 2 Intelligence:** context engine, memory engine, MCP/tools, coding agent, task
  scheduler, agent inbox, browser automation
- **Tier 3 Knowledge:** RAG, PDF, web research, crawl/firecrawl, repository indexing,
  Research Observatory
- **Tier 4 Autonomy:** skills, multi-agent orchestration, background tasks, verification
  loops, self-improvement sandbox
- **Tier 5 Optimization:** provider/memory/context/startup/RAM benchmarking, regression engine
- **Tier 6 Optional:** finance, CAD, image generation, deployment, multi-user auth — only if
  they survive the benchmark/relevance filter

Key principle: the GitHub list is a **research corpus feeding the architecture**, not a
100-project installation checklist. Keep JARVIS **fast, tiny, terminal-native, persistent,
intelligent, and measurable.**
