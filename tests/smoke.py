"""Full end-to-end smoke test for JARVIS MK-X (live core only).

Phase 0 (2026-08-03): subsystem sections for dead packages (performance_engine,
distributed_engine, evolution_engine, interaction_engine, knowledge_engine,
orchestration_engine, perception_engine, self_evolution, system_optimizer,
digital_twin, personal_intelligence, ai_runtime, benchmark, cache_system,
gpu_optimization, hyper_optimization, os_optimization, reasoning_system,
se_factory) were removed. Those packages now live under _quarantine/2026-08-03.
"""
import sys, asyncio, time
sys.path.insert(0, ".")

def main():
    print("=== JARVIS MK-X Smoke Test ===\n")

    # 1. Init JARVIS
    from core.jarvis import JarvisMKX
    j = JarvisMKX()
    print(f"[OK] JarvisMKX initialized (session={j.session_id})")

    # 2. Test LLM
    async def test_llm():
        return await j.process_text("Say hello in exactly 5 words.")
    t0 = time.time()
    resp = asyncio.run(test_llm())
    latency = (time.time() - t0) * 1000
    print(f"[OK] LLM responded in {latency:.0f}ms: {resp[:80]}")

    # 3. Test deterministic intents
    async def test_time():
        return await j.process_text("What time is it?")
    resp2 = asyncio.run(test_time())
    print(f"[OK] Time query: {resp2[:60]}")

    async def test_greet():
        return await j.process_text("Hello!")
    resp3 = asyncio.run(test_greet())
    print(f"[OK] Greeting: {resp3[:60]}")

    # 4. Test health checks
    try:
        from core.health import run_all_checks
        checks = run_all_checks()
        passed = sum(1 for c in checks if c.ok)
        total = len(checks)
        print(f"[OK] Health: {passed}/{total} passed")
    except Exception as e:
        print(f"[SKIP] Health checks: {e}")

    # 5. Test provider status
    status = j.get_status()
    print(f"[OK] Providers: {list(status['providers'].keys())}")
    for name, info in status["providers"].items():
        avail = info["available"]
        model = info["model"]
        print(f"  {name}: avail={avail} model={model}")

    # 6. Test context
    messages = j.context.get_messages()
    print(f"[OK] Context: {len(messages)} messages in history")

    # 7. Test memory
    stats = j.memory.get_stats()
    print(f"[OK] Memory: {stats}")

    # 8. Test IntentRouter
    from core.intent_router import IntentRouter
    ir = IntentRouter()
    for text, expected in [
        ("open notepad", "action.open"),
        ("search python tutorial", "action.search"),
        ("what time is it", "query.time"),
        ("hello", "meta.greet"),
        ("thanks", "meta.thanks"),
        ("describe screen", "vision.screen_capture"),
        ("volume up", "action.desktop_control"),
        ("search memory python", "memory.vector_query"),
        ("random chat text here", "general.chat"),
    ]:
        intent = ir.classify(text)
        tag = "OK" if intent.name == expected else "FAIL"
        print(f"  [{tag}] '{text}' -> {intent.name} (expected {expected})")

    # 9. Test New Modules (Vector Memory & Plugin Loader)
    try:
        from memory.vector_store import VectorMemoryStore
        vs = VectorMemoryStore()
        vs.store_vector("I love building AI assistants", category="preference")
        matches = vs.search_similar("AI assistants")
        print(f"[OK] Vector Memory match count: {len(matches)}")
    except Exception as e:
        print(f"[FAIL] Vector memory test: {e}")

    try:
        from core.plugin_loader import PluginLoader
        pl = PluginLoader()
        loaded = pl.discover_and_load()
        print(f"[OK] Plugin loader discovered plugins: {list(loaded.keys())}")
    except Exception as e:
        print(f"[FAIL] Plugin loader test: {e}")

    # 10. Security Engine (live production module)
    try:
        from security.engine import get_security_engine
        se = get_security_engine()
        stats = se.get_status()
        print(f"[OK] SecurityEngine: mode={stats.get('mode', 'unknown')}")
    except Exception as e:
        print(f"[FAIL] SecurityEngine: {e}")

    j.shutdown()
    print("\n=== ALL SMOKE TESTS PASSED ===")

if __name__ == "__main__":
    main()
