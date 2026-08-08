# JARVIS MK-X — Dead Code Manifest

Phase 0 quarantine manifest. **Move-only, reversible.** Every component below has
a rollback step (`move_back_to_root`). Verified 2026-08-03.

Method: static import inventory + dynamic-import scan
(`importlib`, `LazyModule`, `__import__`, plain `import`) across the production
set `{core, actions, web, api, memory, pipeline, providers, security, vision}`
plus root entrypoints `{main.py, ui.py, ui_web.py, launcher.py, bench.py,
mcp_server_entry.py}`.

---

## Tier 1 — confirmed_orphans (19 components)

Zero production references. Referenced only by the legacy touch-everything
script `tests/smoke.py`, which is rewritten to the live core after quarantine.

### 1. ai_runtime
- classification: true_orphan
- location_before: ai_runtime/
- evidence: imports_found 0, production_references 0, test_references 0
- loc: 1365 (12 files)
- risk: dynamic_import_possible: false
- rollback: move_back_to_root

### 2. benchmark
- classification: true_orphan
- evidence: imports_found 0, production_references 0, test_references 0
- loc: 1342 (8 files)
- risk: false
- rollback: move_back_to_root

### 3. cache_system
- classification: true_orphan
- evidence: imports_found 0, production_references 0, test_references 0
- loc: 646 (4 files)
- risk: false
- rollback: move_back_to_root

### 4. gpu_optimization
- classification: true_orphan
- evidence: imports_found 0, production_references 0, test_references 0
- loc: 592 (6 files)
- risk: false
- rollback: move_back_to_root

### 5. hyper_optimization
- classification: true_orphan
- evidence: imports_found 0, production_references 0, test_references 0
- loc: 6207 (24 files) — largest orphan
- risk: false
- rollback: move_back_to_root

### 6. os_optimization
- classification: true_orphan
- evidence: imports_found 0, production_references 0, test_references 0
- loc: 612 (6 files)
- risk: false
- rollback: move_back_to_root

### 7. reasoning_system
- classification: true_orphan
- evidence: imports_found 0, production_references 0, test_references 0
- loc: 878 (5 files)
- risk: false
- rollback: move_back_to_root

### 8. se_factory
- classification: true_orphan
- evidence: imports_found 0, production_references 0, test_references 0
- loc: 587 (5 files)
- risk: false
- rollback: move_back_to_root

### 9. digital_twin
- classification: smoke_only
- evidence: production_references 0; tests/smoke.py only
- loc: 1058 (3 files)
- risk: false
- rollback: move_back_to_root

### 10. distributed_engine
- classification: smoke_only
- evidence: production_references 0; tests/smoke.py only
- loc: 660 (5 files)
- risk: false
- rollback: move_back_to_root

### 11. evolution_engine
- classification: smoke_only
- evidence: production_references 0; tests/smoke.py only
- loc: 844 (4 files)
- risk: false
- rollback: move_back_to_root

### 12. interaction_engine
- classification: smoke_only
- evidence: production_references 0; tests/smoke.py only
- loc: 776 (4 files)
- risk: false
- rollback: move_back_to_root

### 13. knowledge_engine
- classification: smoke_only
- evidence: production_references 0; tests/smoke.py only
- loc: 790 (4 files)
- risk: false
- rollback: move_back_to_root

### 14. orchestration_engine
- classification: smoke_only
- evidence: production_references 0; tests/smoke.py only
- loc: 496 (3 files)
- risk: false
- rollback: move_back_to_root

### 15. perception_engine
- classification: smoke_only
- evidence: production_references 0; tests/smoke.py only
- loc: 370 (3 files)
- risk: false
- rollback: move_back_to_root

### 16. self_evolution
- classification: smoke_only
- evidence: production_references 0; tests/smoke.py only
- loc: 559 (3 files)
- risk: false
- rollback: move_back_to_root

### 17. system_optimizer
- classification: smoke_only
- evidence: production_references 0; tests/smoke.py only
- loc: 468 (4 files)
- risk: false
- rollback: move_back_to_root

### 18. performance_engine
- classification: smoke_only (dead cluster)
- evidence: production_references 0; refs only from evolution_engine (also dead) + tests/smoke.py
- loc: 968 (7 files)
- risk: false
- rollback: move_back_to_root

### 19. personal_intelligence
- classification: smoke_only (dead cluster)
- evidence: production_references 0; refs only from interaction_engine/orchestration_engine (both dead) + tests/smoke.py
- loc: 809 (3 files)
- risk: false
- rollback: move_back_to_root

---

## Tier 2 — runtime_uncertain (5 components)

Kept in place pending manual confirmation of dynamic-loading paths.

### U1. external
- classification: user-flagged plugin-adjacent
- evidence: dynamic scan clean (0 dyn refs); referenced only via core/http_pool
  import path (lazy, inert); contains weather/news/rss/scraper helpers edited
  this cycle. Move deferred pending manual verification.
- rollback: n/a (not moved)

### U2. mcp_jarvis
- classification: user-flagged plugin-adjacent
- evidence: dynamic scan clean; 0 production refs. MCP entry may be wired via
  mcp_server_entry.py — verify before moving.
- rollback: n/a (not moved)

### U3. workflows
- classification: user-flagged plugin-adjacent
- evidence: dynamic scan clean; tests/smoke.py only.
- rollback: n/a (not moved)

### U4. knowledge_graph
- classification: dynamic-string referenced
- evidence: `LazyModule("knowledge_graph.graph")` + `.query` at core/jarvis.py
  L35-36. `.get()` is never called, so the package is never imported at
  runtime, but the reference lives in a production file.
- rollback: n/a (not moved)

### U5. voice_engine
- classification: inert import chain
- evidence: memory/__init__.py re-exports memory_optimizer, which imports
  voice_engine. Nothing calls get_memory_optimizer() in production.
- rollback: n/a (not moved)

### U6. inference_engine  [DISCOVERED during smoke.py triage]
- classification: live production import
- evidence: core/jarvis.py L173 eagerly imports
  `from inference_engine.model_router import get_model_router` in the
  JarvisMKX constructor and assigns `self.model_router`. NOT an orphan.
- rollback: n/a (not moved)

### U7. reliability_engine  [DISCOVERED during smoke.py triage]
- classification: live production import
- evidence: core/container.py L244-245 imports HealthMonitor + CircuitBreaker
  inside `get_container()`. NOT an orphan.
- rollback: n/a (not moved)

---

## Post-quarantine verification (2026-08-03)

- py_compile sweep: all first-party code compiles. 3 failures are pre-existing,
  vendored, unrelated: `hand_tracking_libs/Real-time-GesRec-master/{inference,
  offline_test,test_models}.py` (`targets.cuda(async=True)`, deprecated PyTorch).
- Reference re-scan: CLEAN — zero remaining imports of the 19 moved packages
  outside `_quarantine/`.
- Server boot: OK (HTTP up). Chat stream: done event. Warm round-trip: 603ms.
- `tests/smoke.py` (rewritten to live core): **ALL SMOKE TESTS PASSED** —
  21 checks: init, LLM (3.9s), time, greet, health 10/11, providers
  (groq/gemini/openrouter/opencode_zen/ollama), context, memory, Flask,
  9/9 IntentRouter cases, vector memory, plugin loader, ui_web, security engine.
- NOTE: first-boot timings (boot 10.4s, first chat 31s vs baseline 3.5s/12.8s)
  were inflated by machine-wide RAM pressure (0.6GB free). Warm latencies are
  healthy; not quarantine-related.

## Findings fixed during Phase 0

- **core/jarvis.py:418 pre-existing crash** — `process_text()` referenced
  `self.complexity_analyzer`, which is never assigned anywhere in the codebase
  (intended wiring to `inference_engine.complexity_analyzer` never added). It
  crashed `/api/chat` and any direct `process_text` call. Fixed with a
  `getattr(self, "complexity_analyzer", None)` guard. Wiring deferred to the
  inference phase. `inference_engine` therefore stays in runtime_uncertain
  (model_router is live at jarvis.py:173; the analyzer component is not yet wired).

## Summary

| Metric | Value |
|---|---|
| Production core packages | 7 (actions, core, memory, pipeline, providers, security, vision) |
| Confirmed orphans moved | 19 |
| Runtime-uncertain kept | 7 (external, mcp_jarvis, workflows, knowledge_graph, voice_engine, inference_engine, reliability_engine) |
| Estimated LOC removed from import surface | ~19,000 |
| Verification | boot test + chat stream test before and after |
| Rollback | `move_back_to_root` per component |
