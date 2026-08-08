# JARVIS MK-X — Dependency Graph Snapshot (Before Phase 0)

Captured 2026-08-03, static + dynamic import analysis. Used to detect accidental
coupling after the quarantine.

## Production core (must be preserved)

```
main.py ──► web/server.py ──► core/jarvis.py ──► core/{intent_router, context,
                │                 │               personality, mode_manager,
                │                 │               model_manager, cache, ...}
                │                 ├─► core/action_registry ──► actions/*
                │                 ├─► core/executor (AgentExecutor) ──► actions/*
                │                 ├─► memory/*  (store, vector_store, tiered_store)
                │                 ├─► pipeline/* (stt, tts, vad, wake_word)
                │                 ├─► providers/* (base, groq, openrouter, ...)
                │                 └─► security/engine ──► security/{policies, sandbox,
                │                                        audit, redaction}
                ├─► api/ws_server.py ──► core/jarvis
                └─► vision/* (lazy, via web/server)

core/ ├── http_pool ──► external/*          [EXTERNAL tier - runtime_uncertain]
       ├── jarvis ──dyn──► knowledge_graph  [runtime_uncertain - inert LazyModule refs]
memory/__init__ ──► memory_optimizer ──► voice_engine  [runtime_uncertain - inert chain]
```

## Candidates by tier

### confirmed_orphans (19) — zero production references, dynamic scan clean

```
ai_runtime         benchmark         cache_system
gpu_optimization   hyper_optimization  os_optimization
reasoning_system   se_factory
digital_twin       distributed_engine  evolution_engine
interaction_engine knowledge_engine  orchestration_engine
perception_engine  self_evolution   system_optimizer
performance_engine personal_intelligence  workflows
```

Reference surface: `tests/smoke.py` only (legacy touch-everything script).
`workflows` also flagged by user for runtime_uncertain (see note below).

### runtime_uncertain (5) — keep until verified

```
external      user-flagged plugin-adjacent; http_pool import chain (inert)
mcp_jarvis    user-flagged plugin-adjacent
workflows     user-flagged; smoke.py ref only (moved decision: deferred)
knowledge_graph  dynamic LazyModule string refs in core/jarvis.py (never .get())
voice_engine  import chain memory/__init__ -> memory_optimizer -> voice_engine (never invoked)
inference_engine   LIVE: jarvis.py L173 eager constructor import (model_router)
reliability_engine LIVE: container.py L244-245 get_container() import
```

## Decision record

- `knowledge_graph`: `LazyModule("knowledge_graph.graph")` at jarvis.py L35/36
  never calls `.get()`, so the package is never imported at runtime. Kept in
  `runtime_uncertain` because the reference lives in a production file.
- `voice_engine`: imported via `memory/memory_optimizer.py` -> `memory/__init__.py`
  re-export. Nothing calls `get_memory_optimizer()`. Safe to defer; if moved,
  `memory/memory_optimizer.py` import must be removed first.

## Post-quarantine expected graph

```
main.py ──► web/server.py ──► core ──► {actions, memory, pipeline, providers, security}
core/jarvis ──(inert)──► knowledge_graph [kept]
memory/__init__ ──(inert)──► voice_engine [kept]
```
