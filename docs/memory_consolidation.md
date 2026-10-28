# Memory Subsystem Consolidation

## Canonical System
The unified memory system is in `memory/` with:
- `memory/api.py` - Unified public API via `get_mem()` / `MemoryAPI` (primary interface)
- `memory/controller.py` - Orchestrates backends
- `memory/vector_store.py` - SQLite vector index (sqlite-vec) with deterministic hash fallback (fixed to use blake2b)
- `memory/store.py` - Core storage
- `memory/tiered_store.py` - Tiered storage
- `memory/mem.py` - Memory facade

All agent memory access should go through `get_mem()` from `memory.api`.

## Legacy/Deprecated
- `core/memory_layer.py` - Legacy memory layer with no active imports found. Should be removed or archived after verification.
- `memory/long_term.json`, `memory/long_term.json.bak` - Legacy JSON storage files (backed by newer systems)

## Other Subsystems
- `memory/decision_memory.py` - Decision-specific memory, integrated via API
- `memory/project_knowledge.py` - Project knowledge, integrated via API
- `memory/user_profile.py` - User profile, integrated via API

## Actions Taken
1. ✅ Fixed deterministic hash fallback in `memory/vector_store.py` to use `hashlib.blake2b` instead of Python's randomized `hash()`
2. ✅ Added request IDs to runtime events in backend/coordinator
3. ✅ Made cancellation event-loop safe with `call_soon_threadsafe`
4. ✅ Enforced bounded queue in backend with proper task tracking

## Recommendations
1. Audit all callers of `core/memory_layer.py` and remove if unused
2. Ensure all code uses `memory.api.get_mem()` as the canonical interface
3. Add user-visible memory inspection/correction/deletion mechanisms
4. Continue benchmarking memory quality with hybrid retrieval (vectors + keywords)
5. Separate personal preferences, episodic memories, project facts, decisions, and operational task state
6. Add proper deletion propagation across all indexes and caches
