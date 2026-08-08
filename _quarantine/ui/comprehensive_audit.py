"""COMPREHENSIVE JARVIS MK-X AUDIT — tests all 15+ phases + prior audit findings."""
import sys, os, time, json, asyncio, inspect, textwrap, pathlib
from pathlib import Path
sys.path.insert(0, str(Path(r'C:\Users\aayan\Desktop\JARVIS')))
TMP = Path(r'C:\Users\aayan\AppData\Local\Temp\opencode')

R = {"pass": 0, "fail": 0, "skip": 0}

def safe(label, fn):
    try:
        fn()
        R["pass"] += 1
        print(f"  [OK  ] {label}")
    except Exception as e:
        R["fail"] += 1
        msg = str(e).replace('\n',' | ')[:120]
        print(f"  [FAIL] {label}  {msg}")

def section(title):
    print(f"\n─── {title} ───")

# ═══════════════════════════════════════════════════
section("GROUP 1: CORE MODULE IMPORTS (Ph1-3)")
for m in ["core.lazy_imports","core.container","core.state_machine",
          "core.service_registry","core.metrics","core.event_store",
          "core.config_service","core.task_manager","core.cache",
          "core.capability_registry","core.model_manager","core.resource_manager",
          "core.security","core.plugin_loader","core.workflow",
          "core.voice_service","core.memory_v2","core.telemetry",
          "core.supervisor","core.durable_task","core.plugin_market"]:
    safe(f"Import {m}", lambda mm=m: __import__(mm))

section("GROUP 2: SYSTEM + API MODULE IMPORTS")
safe("Import systems.event_bus", lambda: __import__("systems.event_bus"))
for m in ["api.v1.models","api.v1.memory","api.v1.events",
          "api.v1.capabilities","api.v1.security","api.v1.factory",
          "api.ws_server"]:
    safe(f"Import {m}", lambda mm=m: __import__(mm))

# ═══════════════════════════════════════════════════
section("GROUP 3: LAZY IMPORTS")
from core.lazy_imports import LazyModule
lazy = LazyModule("os.path")
safe("LazyModule not loaded init", lambda: check("", not lazy.is_loaded))
lazy.load()
safe("LazyModule loads on demand", lambda: check("", lazy.is_loaded and hasattr(lazy, "join")))

section("GROUP 4: DI CONTAINER")
from core.container import ServiceContainer, ServiceLifetime
c = ServiceContainer()
safe("Container create", lambda: check("", isinstance(c, ServiceContainer)))
class _S: pass
c.register(_S, _S, lifetime=ServiceLifetime.SINGLETON)
sv = c.resolve(_S)
safe("Container register+resolve singleton", lambda: check("", sv is not None))
safe("Container singleton reuse", lambda: check("", c.resolve(_S) is sv))

section("GROUP 5: STATE MACHINE + SERVICE REGISTRY")
from core.state_machine import KernelState, ServiceState
safe("KernelState 3+ members", lambda: check("", len(KernelState.__members__) >= 3))
safe("ServiceState valid transition",
     lambda: check("", ServiceState.CREATED.can_transition_to(ServiceState.INITIALIZING)))
safe("ServiceState invalid transition blocked",
     lambda: check("", not ServiceState.STOPPED.can_transition_to(ServiceState.RUNNING)))
from core.service_registry import ServiceRegistry
sr = ServiceRegistry()
sr.register("core.test", {"n":"test"})
safe("ServiceRegistry resolve", lambda: check("", sr.resolve("core.test")["n"]=="test"))

section("GROUP 6: METRICS / EVENT / CONFIG / TASK")
from core.metrics import MetricsCollector
safe("MetricsCollector", lambda: MetricsCollector().record("t",1))
from core.event_store import EventStore
es = EventStore()
es.store("t.e", {"k":"v"})
safe("EventStore store+count", lambda: check("", es.count()==1))
from core.config_service import ConfigService
cfg = ConfigService()
cfg.set("k","v")
safe("ConfigService get/set", lambda: check("", cfg.get("k")=="v"))
safe("ConfigService default", lambda: check("", cfg.get("x","d")=="d"))
from core.task_manager import TaskManager
tm = TaskManager()
task = tm.create("test")
tm.update(task.id, "running")
safe("TaskManager lifecycle", lambda: check("", str(tm.get(task.id).status).find("RUN")>=0))

section("GROUP 7: EVENTBUS v2")
from systems.event_bus import EventBus
eb = EventBus()
recv = []
eb.subscribe("t.*", lambda e: recv.append(e))
eb.publish("t.h", {"m":"hi"})
safe("EventBus pub/sub", lambda: check("", len(recv)>=1 and "hi" in str(recv)))

section("GROUP 8: CACHE + ACTION REGISTRY")
from core.cache import Cache
ca = Cache()
ca.set("k","v")
safe("Cache set+get", lambda: check("", ca.get("k")=="v"))
ca.invalidate("k")
safe("Cache invalidate", lambda: check("", ca.get("k") is None))
from core.action_registry import ActionRegistry
ar = ActionRegistry()
ar.register("ta", lambda p: "ok")
safe("ActionRegistry execute", lambda: check("", ar.execute("ta",{})=="ok"))

section("GROUP 9: CAPABILITY TREE")
from core.capability_registry import CapabilityTree, Capability, CapabilityRisk, CapabilityCategory
ct = CapabilityTree.build_branch([
    Capability(name="search.web", category=CapabilityCategory.SYSTEM,
               risk=CapabilityRisk.LOW, tags=["search","web"], cost=0.01),
    Capability(name="file.read", category=CapabilityCategory.SYSTEM,
               risk=CapabilityRisk.MEDIUM, tags=["file"], permissions=["fs.read"]),
])
safe("CapabilityTree build", lambda: check("", False))
# We check it's not None - build_branch likely modifies tree but might return None
from core.capability_registry import CapabilityTree as CT2
import inspect
sig = inspect.signature(CapabilityTree.build_branch)
print(f"  build_branch signature: {sig}")
safe("CapabilityTree search by tag", lambda: check("", len(ct.search(tags=["web"]))>=1))
safe("CapabilityTree resolve", lambda: check("", ct.resolve("search.web") is not None))
safe("CapabilityTree subtree", lambda: check("", bool(ct.subtree("search"))))

section("GROUP 10: MODEL MANAGER")
from core.model_manager import ModelManager
mm = ModelManager()
cat, conf = mm.classify("write a poem")
safe("ModelManager classify", lambda: check("", cat is not None and conf > 0))
safe("ModelManager cost filter", lambda: check("", isinstance(mm.filter_by_cost(0.02), list)))

section("GROUP 11: RESOURCE MANAGER")
from core.resource_manager import ResourceManager
rm = ResourceManager()
safe("ResourceManager get_status", lambda: check("", isinstance(rm.get_status(), dict)))
safe("ResourceManager pressure", lambda: check("", rm.pressure() in ("none","mild","high","critical")))
safe("ResourceManager throttle", lambda: check("", isinstance(rm.should_throttle(), bool)))

section("GROUP 12: SECURITY")
from core.security import SecurityManager
sm = SecurityManager()
ctx = sm.create_context("test_user", ["user"])
safe("SecurityContext auth_level", lambda: check("", ctx.authorization_level == "standard"))
safe("Security allow allowed path",
     lambda: check("", sm.check_file_access(str(Path.home()/"t.txt"),"read")[0]))
safe("Security block dangerous path",
     lambda: check("", not sm.check_file_access(r"C:\Windows\system32\config","read")[0]))
safe("Security has format_confirmation_prompt",
     lambda: check("", callable(sm.format_confirmation_prompt)))

section("GROUP 13: PLUGIN SYSTEM")
from core.plugin_loader import PluginSandbox, PluginManager
safe("PluginSandbox blocks os", lambda: check("", not PluginSandbox().is_safe("os")))
safe("PluginSandbox blocks subprocess", lambda: check("", not PluginSandbox().is_safe("subprocess")))
safe("PluginSandbox allows math", lambda: check("", PluginSandbox().is_safe("math")))

section("GROUP 14: WORKFLOW ENGINE")
from core.workflow import WorkflowEngine
wfe = WorkflowEngine(checkpoint_dir=TMP/"wf_aud")
wf = wfe.create_workflow("test_wf", [
    {"tool":"search","params":{"q":"hello"}},
    {"tool":"read","params":{"url":"x"},"depends_on":["step_0"]},
])
safe("WorkflowEngine create_workflow", lambda: check("", wf is not None))
async def _test_wf():
    wf.steps[0].id = "step_0"
    wf.steps[1].id = "step_1"
    wf.steps[1].depends_on = ["step_0"]
    result = await wfe.execute(wf.id)
    safe("WorkflowEngine execute", lambda: check("", result.get("status")=="completed"))

    # Resume with fresh engine
    wfe2 = WorkflowEngine(checkpoint_dir=TMP/"wf_aud")
    resumed = wfe2.resume(wf.id)
    safe("WorkflowEngine resume", lambda: check("", resumed is not None))
    safe("WorkflowEngine cancel", lambda: check("", wfe2.cancel(wf.id)))
asyncio.run(_test_wf())

section("GROUP 15: VOICE SERVICE")
from core.voice_service import VoiceService
vs = VoiceService()
safe("VoiceService init", lambda: check("", vs is not None))
safe("VoiceService status has keys",
     lambda: check("", all(k in vs.get_status() for k in ("listening","speaking","vad"))))

section("GROUP 16: MEMORY V2")
from core.memory_v2 import (MemoryExtractor, ImportanceScorer,
    KnowledgeGraph, MemoryHierarchy, KnowledgeTriple)
ext = MemoryExtractor()
facts = ext.extract("My name is Alice and I love programming in Python.")
safe("MemoryExtract identity+preference",
     lambda: check("", len(facts)>=2 and any(f.category=="identity" for f in facts)))
scorer = ImportanceScorer()
s1 = scorer.score("I really love this!")
safe("ImportanceScorer", lambda: check("", s1 > 0))
kg = KnowledgeGraph(path=TMP/"kg_aud.json")
kg.add_triple(KnowledgeTriple(subject="Alice", relation="likes", obj="Python"))
safe("KnowledgeGraph add+search", lambda: check("", len(kg.search("Alice"))==1))
safe("KnowledgeGraph get_related", lambda: check("", "Alice" in kg.get_related("Alice")))
mh = MemoryHierarchy(kg=kg, extractor=ext, archive_path=TMP/"arch_aud.json")
proc = mh.process("I love machine learning. My brother is a doctor.")
safe("MemoryHierarchy process", lambda: check("", len(proc)>=1))
ctx = mh.get_context("machine learning")
safe("MemoryHierarchy context retrieval", lambda: check("", len(ctx)>10))
kg.clear()

section("GROUP 17: TELEMETRY V2")
from core.telemetry import TraceProvider, LLMObservability, LatencyTracker, Stages
tp = TraceProvider()
root = tp.start_trace("audit")
with tp.span("child", parent=root):
    pass
tp.end_span(root)
safe("TraceProvider span hierarchy",
     lambda: check("", len(tp.get_trace(root.trace_id))==2))
safe("TraceProvider export", lambda: check("", len(tp.export_json())>=2))
llo = LLMObservability()
llo.record(model="gpt-4o", prompt="t", completion="ok",
           prompt_tokens=10, completion_tokens=5, latency_ms=100)
stats = llo.get_stats()
safe("LLMObservability stats", lambda: check("", stats["total_calls"]==1 and stats["total_tokens"]==15))
safe("LLMObservability cost>0", lambda: check("", stats["total_cost"]>0))
safe("LLMObservability recent_calls", lambda: check("", len(llo.recent_calls(5))>=1))
lt = LatencyTracker()
lt.start_request()
lt.mark(Stages.LLM_FIRST_TOKEN)
lt.mark(Stages.LLM_COMPLETE)
lt.end_request()
safe("LatencyTracker stages", lambda: check("", len(lt.get_summary().get("stages",[]))>=1))

section("GROUP 18: SUPERVISOR (OTP-style)")
from core.supervisor import Supervisor, ServiceSpec
sup = Supervisor()
async def _dummy():
    while True: await asyncio.sleep(10)
sup.add(ServiceSpec(name="svc1", start=_dummy))
safe("Supervisor add", lambda: check("", "svc1" in sup.get_status()))

section("GROUP 19: DURABLE TASKS")
from core.durable_task import DurableExecutor
async def _test_dur():
    de = DurableExecutor(db_path=TMP/"dur_aud.db")
    tid = await de.submit("test", lambda: asyncio.sleep(0.01))
    await de.wait(tid, timeout=5)
    s = de.get_status(tid)
    safe("DurableTask submit+wait", lambda: check("", s and s.get("status")=="completed"))
    de.close()
asyncio.run(_test_dur())

section("GROUP 20: PLUGIN MARKETPLACE")
from core.plugin_market import PluginMarketplace, PluginMarketEntry
mp = PluginMarketplace(plugin_dir=TMP/"mp_aud")
mp.register(PluginMarketEntry(id="p1",name="P1",version="1.0",author="t",
                              description="test",source="local"))
safe("PluginMarket register", lambda: check("", mp.get_stats()["total"]==1))
safe("PluginMarket search", lambda: check("", len(mp.search("P1"))==1))

section("GROUP 21: WS SERVER")
from api.ws_server import WSServer
ws = WSServer()
safe("WSServer init port", lambda: check("", ws.port==8765))

# ═══════════════════════════════════════════════════
section("GROUP 22: PRIOR AUDIT FINDINGS REMEDIATION")

# CRITICAL-1: _safe_path fix
import actions.file_manager as fm
_safe = getattr(fm, "_safe_path", None)
if _safe:
    try:
        _safe(r"C:\Windows\evil.exe", check_allowed=True)
        safe("CRITICAL-1: _safe_path no-op", False)  # should never reach
    except PermissionError:
        safe("CRITICAL-1 FIXED: _safe_path raises PermissionError", True)
    except Exception as e:
        safe(f"CRITICAL-1: Unexpected error: {e}", False)
else:
    safe("CRITICAL-1: _safe_path not found", False)

# Check other findings via source code analysis
def _check_src(path, pattern, label, invert=False):
    p = Path(path)
    if p.exists():
        src = p.read_text(encoding="utf-8")
        found = pattern in src if not invert else pattern not in src
        safe(label, lambda: check("", found))
    else:
        safe(label, False)

_check_src(r'C:\Users\aayan\Desktop\JARVIS\web\server.py', '"/api/auth/token',
           "CRITICAL-2: Auth endpoint exposed", invert=False)
_check_src(r'C:\Users\aayan\Desktop\JARVIS\web\server.py', '0.0.0.0',
           "HIGH-1: Flask host binding", invert=True)
_check_src(r'C:\Users\aayan\Desktop\JARVIS\pipeline\stt.py', 'asyncio.to_thread',
           "CRITICAL-3: STT non-blocking")
_check_src(r'C:\Users\aayan\Desktop\JARVIS\pipeline\tts.py', 'Semaphore',
           "HIGH-4: TTS Semaphore")
_check_src(r'C:\Users\aayan\Desktop\JARVIS\pipeline\tts.py', 'lru_cache',
           "HIGH-7: TTS cache")
_check_src(r'C:\Users\aayan\Desktop\JARVIS\core\jarvis.py', '_handle_action',
           "MED-2: _handle_action removed", invert=True)

section("GROUP 23: EXISTING SYSTEMS")
from memory.store import MemoryStore
ms = MemoryStore(data_dir=TMP/"ms_aud")
ms.store("k1","v1")
safe("MemoryStore store+recall", lambda: check("", ms.recall("k1")=="v1"))
ms.close()
from memory.memory_manager import load_memory, remember, forget
mem = load_memory()
safe("MemoryManager load", lambda: check("", isinstance(mem, dict)))
safe("MemoryManager remember", lambda: check("", "Remembered" in remember("tk","tv")))
safe("MemoryManager forget", lambda: check("", "Forgotten" in forget("tk")))

section("GROUP 24: API v1 ENDPOINTS")
from api.v1.models import MemoryItem, EventRecord, CapabilityInfo
mi = MemoryItem(key="k", value="v", tags=["t"])
safe("API MemoryItem model", lambda: check("", mi.key=="k" and mi.value=="v"))
from api.v1.memory import MemoryAPI
mapi = MemoryAPI(ms)
safe("API MemoryAPI store+recall",
     lambda: check("", mapi.store(MemoryItem(key="ak1",value="av1",tags=["t"]))
                    and mapi.recall("ak1")=="av1"))

# ═══════════════════════════════════════════════════
section("GROUP 25: DEAD PACKAGES")
dead_list = [
    "hyper_optimization","ai_runtime","performance_engine","os_optimization",
    "gpu_optimization","system_optimizer","cache_system","orchestration_engine",
    "inference_engine","reasoning_system","knowledge_engine","interaction_engine",
    "personal_intelligence","digital_twin","evolution_engine","self_evolution",
    "reliability_engine","distributed_engine","workflows","agents","external",
    "se_factory","perception_engine","voice_engine","mcp_jarvis","systems",
]
base = Path(r'C:\Users\aayan\Desktop\JARVIS')
found = [d for d in dead_list if (base/d).is_dir()]
if found:
    safe(f"DEAD PACKAGES FOUND: {len(found)}", lambda: check("", False))
    for d in found: print(f"    {d}/")
else:
    safe("All dead packages removed", lambda: check("", True))

# ═══════════════════════════════════════════════════
section("═══ FINAL REPORT ═══")
t = R["pass"] + R["fail"]
print(f"  PASS: {R['pass']}/{t} ({R['pass']/t*100:.1f}%)" if t else "  (no checks)")
print(f"  FAIL: {R['fail']}/{t} ({R['fail']/t*100:.1f}%)" if t else "")
print()
print("  CHECKLIST:")
for s, g in [("CORE IMPORTS", "groups 1-2"),
             ("LAZY / DI / STATE / REGISTRY", "groups 3-5"),
             ("METRICS / EVENT / CONFIG / TASK", "group 6"),
             ("EVENTBUS / CACHE / ACTIONS", "groups 7-8"),
             ("CAPABILITY TREE / MODEL MANAGER", "groups 9-10"),
             ("RESOURCE / SECURITY / PLUGIN", "groups 11-13"),
             ("WORKFLOW / VOICE / MEMORY", "groups 14-16"),
             ("TELEMETRY / SUPERVISOR / DURABLE", "groups 17-19"),
             ("PLUGIN MARKET / WS / EXISTING", "groups 20-23"),
             ("DEAD PACKAGES / AUDIT FINDINGS", "groups 24-25")]:
    print(f"    {s:<35} {g}")
