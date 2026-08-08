## Objective
- JARVIS MK-X migration from monolith god object to service-oriented AI operating system is **100% complete across all 15 phases**.

## What Was Built

### Phase 0 — Benchmark framework
- `benchmark/startup_benchmark.py`, `telemetry_benchmark.py`, `memory_benchmark.py`, `voice_benchmark.py`
- Baseline: 13.37s cold start / 294MB idle / 700ms avg TTFT

### Phase 1 — Startup Surgery (13.37s → 5.85s, 56%)
- `core/lazy_imports.py` — Lazy Import Firewall
- Voice lazy loading, TTS precache deferred, concurrent provider warmup

### Phase 2 — DI + Registry + State Machine + Metrics + EventBus v2 + Services
- **DI Container**: `core/container.py` — Singleton/Request/Transient, topological startup
- **Service Registry**: `core/service_registry.py` — domain.service pattern
- **State Machine**: `core/state_machine.py` — KernelState + ServiceState with transition validation
- **Metrics**: `core/metrics.py` — ring buffer → async SQLite flush
- **Event Store**: `core/event_store.py` — Event Sourcing Lite (5000 max)
- **Config Service**: `core/config_service.py` — profiles, runtime overrides, change listeners
- **Task Manager**: `core/task_manager.py` — task lifecycle
- **EventBus v2**: `systems/event_bus.py` — priority queues, middleware pipeline, channels, trace_id

### Phase 3 — Clean Kernel + ActionRegistry
- `core/action_registry.py` — replaced 30+ if/elif chain
- 21 handler classes in `core/action_handlers.py`
- `core/action_init.py` — register_all_actions() factory
- Removed ~20 dead None attributes, construction 4.5s → 1.18s

### Phase 3.5 — Cache Layer
- `core/cache.py` — tiered LRU + TTL (memory → SQLite → provider), get_or_compute, invalidate pattern

### Phase 4 — Versioned APIs (`api/v1/`)
- `api/v1/models.py` — MemoryItem, EventRecord, CapabilityInfo, PermissionRequest
- `api/v1/memory.py` — MemoryAPI (store/recall/search/delete)
- `api/v1/events.py` — EventAPI (publish/subscribe/unsubscribe)
- `api/v1/capabilities.py` — CapabilityAPI (query/search/list_all)
- `api/v1/security.py` — SecurityAPI (request_permission, audit log)
- `api/v1/factory.py` — wire_apis(container)

### Phase 5 — Capability Registry v2
- `core/capability_registry.py` — CapabilityTree with tree structure, atomic merge, search by tags/risk/permissions/cost/latency
- 69 capabilities across 12 categories

### Phase 6 — ModelManager
- `core/model_manager.py` — Tiered routing (TINY→VISION), query classification, cost/latency/capability filtering, auto failover with cooldown, health tracking

### Phase 7 — ResourceManager
- `core/resource_manager.py` — CPU, RAM, Disk, GPU (pynvml), Battery, Network, ThreadPool, pressure detection (NONE/MILD/HIGH/CRITICAL), quotas, should_throttle/degrade_tts/skip_animations

### Phase 8 — Security Fortress
- `core/security.py` — wraps security/engine.py, SecurityContext, FileAccessPolicy, risk prompts, plugin permission checking
- **CRITICAL FIX**: `actions/file_manager.py::_safe_path()` — no-op → raises PermissionError

### Phase 9 — Plugin System
- `core/plugin_loader.py` — PluginManager with manifests (YAML/JSON), PluginSandbox (blocked imports/ file open), lifecycle hooks, capability registration via merge_capabilities, @jarvis_plugin decorator

### Phase 10 — WorkflowEngine + Scheduler
- `core/workflow.py` — DAG scheduler, topological sort, parallel execution, resource-aware throttling, exponential backoff retry, checkpoint/resume via JSON, crash recovery

### Phase 11 — Voice Service
- `core/voice_service.py` — Service wrapper around VAD/wake word/STT/TTS, stream helpers, DI integration

### Phase 12 — Memory v2
- `core/memory_v2.py` — MemoryExtractor (fact/preference/identity/project extraction), ImportanceScorer (novelty/repetition/emotional), MemoryHierarchy (session→long-term→archive tiers), KnowledgeGraph (lightweight GraphRAG with entity-relation triples, BFS traversal)

### Phase 13 — Telemetry v2
- `core/telemetry.py` — Extended: TraceProvider (OpenTelemetry-style spans with parent-child, trace_id, export), LLMObservability (Langfuse-style per-call tracking: model, tokens, latency, cost, model breakdown)

### Phase 14 — Frontend (React/Vite + Tauri + WebSocket)
- `frontend/` — Vite+React scaffold, JARVIS HUD with arc reactor animation, event log, top/bottom bars, WebSocket hook
- `frontend/src-tauri/` — Tauri v2 config (Rust needed for `cargo tauri dev`)
- `api/ws_server.py` — Async WS server broadcasting heartbeat (status, memory, CPU, uptime) + event queue
- Frontend build: 193KB JS + 5KB CSS

### Phase 15 — Production
- `core/supervisor.py` — Erlang OTP-style service supervision: auto-restart on crash, exponential backoff, health checks, restart policies (permanent/temporary/never), EventBus integration
- `core/durable_task.py` — Durable async task executor: SQLite-backed persistence, retry with backoff, timeout, crash recovery (recover_pending), survive restarts
- `core/plugin_market.py` — Plugin marketplace: registry (local/url/github), discovery, search, install/uninstall, stats

## Key Research Influences
- **LangGraph** → WorkflowEngine DAG scheduling + checkpoints
- **Home Assistant** → EventBus + ServiceRegistry
- **Mem0/Letta** → Memory v2 extraction + hierarchy
- **GraphRAG** → KnowledgeGraph triples + BFS traversal
- **LiteLLM/RouteLLM** → ModelManager tiered routing
- **Temporal** → DurableTask executor with persistence
- **OpenTelemetry** → TraceProvider spans + trace_id
- **Langfuse** → LLMObservability cost/token tracking
- **Erlang OTP** → Supervisor with restart policies
- **OpenInterpreter** → SecurityManager + sandbox
- **Pipecat** → VoiceService streaming pipeline
- **Tauri** → Frontend architecture (Rust pending)

## Next Steps (Future Work)
1. **Install Rust** → Run `rustup-init` then `cd frontend && npm run tauri dev` for native desktop app
2. **Streaming architecture** — Full duplex audio/LLM/Tool streaming with WebRTC
3. **Context Engine** — LLMLingua-style compression, semantic caching (GPTCache), optimal prompt building
4. **Durable Agent Runtime** — LangGraph-style agent loops with Temporal-grade durability
5. **Observability** — OpenTelemetry export to Grafana/Prometheus/Langfuse
6. **Multi-device** — NATS messaging layer for distributed JARVIS
7. **Plugin Marketplace** — Remote index server, version resolver, dependency management
8. **Structured Outputs** — Instructor/Outlines integration for tool calling
9. **Service Mesh** — Kubernetes-style service discovery and load balancing
10. **TTS/STT optimization** — Whisper.cpp, Kokoro TTS, streaming Silero VAD

## Relevant Files (Complete)
- `core/container.py`, `core/state_machine.py`, `core/service_registry.py`, `core/metrics.py`, `core/event_store.py`, `core/config_service.py`, `core/task_manager.py`
- `core/cache.py`, `core/action_registry.py`, `core/action_handlers.py`, `core/action_init.py`
- `core/capability_registry.py`, `core/model_manager.py`, `core/resource_manager.py`
- `core/security.py`, `core/plugin_loader.py`, `core/workflow.py`
- `core/voice_service.py`, `core/memory_v2.py`, `core/telemetry.py`
- `core/supervisor.py`, `core/durable_task.py`, `core/plugin_market.py`
- `core/jarvis.py` (compatibility shim), `core/lazy_imports.py`
- `systems/event_bus.py`
- `api/v1/models.py`, `api/v1/memory.py`, `api/v1/events.py`, `api/v1/capabilities.py`, `api/v1/security.py`, `api/v1/factory.py`
- `api/ws_server.py`
- `frontend/` (Vite + React + Tauri), `frontend/src-tauri/` (Rust config)
- `security/engine.py` (legacy, wrapped by core/security.py)
- `actions/file_manager.py` (PermissionError fix)
- `memory/store.py`, `memory/memory_manager.py`, `memory/memory_optimizer.py`
- `pipeline/vad.py`, `pipeline/wake_word.py`, `pipeline/stt.py`, `pipeline/tts.py`
