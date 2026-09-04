# JARVIS Orbit — G0 Subsystem Audit & Classification

Status: implemented at the start of the G0→G13 build (baseline: 660 passed /
19 skipped + 7 jbrowser bridge = 667 / 19; single-engine `jbrowser` suite 64
passed).

This document records the KEEP / EXTEND / REFACTOR / REPLACE / DELETE / CREATE
classification of every relevant subsystem before Orbit build begins. It is
the G0 deliverable and the source of truth for "reuse before create".

---

## 1. Executive summary

JARVIS already owns the entire execution, permission, agent, memory, event,
and model-routing stack it needs. Orbit adds **one** new capability surface
— direct **CDP control of Chromium** — and reuses every governing subsystem.
The single most important finding:

- The existing `jbrowser/` Playwright backend already implements the correct
  `BrowserBackend` engine-neutral interface and holds the controller, tab
  manager, session manager, page-context builder, network policy, and risk
  table. It is kept and reused. Orbit adds a **`CDPBackend`** implementing the
  same `BrowserBackend` interface so the agent drives Chromium over **CDP**
  (the locked control surface), with no `chrome.debugger` execution path.

The architectural law holds: JARVIS remains the sole authority for
intelligence, agents, tools, permissions, DSH, cancellation, memory, telemetry,
and security. Chromium is a capability provider behind `BrowserController`.

---

## 2. Execution-gate chain (locked, unchanged)

```
USER/CLIENT -> INTENT ROUTER -> AGENT KERNEL -> HARNESS -> MODEL GATEWAY
    -> PROVIDER ROUTER -> MODEL -> TOOL EXECUTOR -> SANDBOX + PERMISSIONS
    -> OBSERVATION -> VERIFICATION -> BUS EVENT -> {TUI, Persistence, MCP, ACP}
```

Orbit browser actions flow:

```
DSH -> AgentKernel -> ToolExecutionService -> PermissionEngine
    -> browser.<verb> tool -> BrowserController -> CDPBackend -> Chromium (CDP)
```

No protocol, adapter, agent, or extension path bypasses `ToolExecutionService`. There is **no** redundant `chrome.debugger` execution path (the MV3 extension's `controller.js` CDP control is removed; the extension is a thin DSH client).

---

## 3. Classification

### KEEP (reuse as-is, no changes)

| Subsystem | File / module | Why kept |
|-----------|---------------|----------|
| Single tool boundary | `core/agent/tool_service.py` | `ToolExecutionService` is the mandated execution gate; permission + observer + timeout + redaction already implemented. |
| Permission engine | `core/agent/permissions.py` | `PermissionEngine` already bridges mode config → security engine → risk gate; high/critical gating via `_apply_risk_gate`. |
| Agent state machine | `core/agent/state.py` | Deterministic `TaskStatus` + `FailureClass` precedence + terminal states. |
| Tool registry | `tools/registry.py` | Canonical catalog; all tools register here. |
| Tool schema | `tools/schema.py` | `Tool` declarative metadata. |
| Browser risk table | `tools/classification.py` | Canonical `browser_risk_for_tool` (mutations HIGH + destructive; reads/nav LOW). Single source of truth. |
| Event bus | `runtime/event_bus.py` | Canonical `BusEvent` pub/sub. |
| Model gateway | `providers/model_gateway.py` | Capability-aware routing/health/session affinity. |
| Provider router | `providers/router.py` | Fallback chain from `config/models.toml` (default `gemini`). |
| Composition root | `runtime/kernel.py` | `build_kernel` assembles the canonical graph (config + registry + router + memory + loop). |
| Memory stack | `memory/*` | Selectively integrated in G12. |
| Capability registry | `core/capability_registry.py` | Capability metadata. |
| Network policy | `jbrowser/network.py` | `BrowserNetworkPolicy` default-deny private/loopback/link-local. |
| Tab manager | `jbrowser/tabs.py` | Stable JARVIS UUID tab ids. |
| Session manager | `jbrowser/sessions.py` | Persistent profiles + session isolation. |
| Page context | `jbrowser/page_context.py` | Bounded observation (`[elN]` handles, interactives/links/forms). |
| Browser events | `jbrowser/events.py` | `browser.*` BusEvents. |
| Optimization | `jbrowser/optimization.py` | Launch flags, tab cap. |

### EXTEND (keep, add capability for Orbit)

| Subsystem | Change |
|-----------|--------|
| `core/agent/state.py` | Add `TaskStatus.WAITING_BROWSER` + transitions so agents can pause (not fail) when the browser is down (G10). |
| `core/agent/tools.py` / executor | Ensure a general resource-lock primitive is available for tab ownership (G5). |
| `runtime/kernel.py` | Add an Orbit composition seam (`build_orbit_runtime`) that wires `CDPBackend` + browser tools + bridge backend without touching the canonical `build_kernel` graph (G3–G6). |
| `jbrowser-bridge/backend.py` `KernelBackend` | Replace the `echo` default path with a real engine call into `ModelGateway`/`AgentLoop` (G7). |
| `tools/registry.py` browser tools | Register orbit browser tools (`browser.navigate`, `browser.read`, `browser.click`, …) behind `BrowserController` (G5). |

### REFACTOR (restructure, behavior preserved)

| Subsystem | Change |
|-----------|--------|
| `jbrowser/controller.py` `BrowserController` | Add a `backend`-selection seam so it can drive `CDPBackend` (CDP) as well as `PlaywrightBackend` (Playwright retained for hermetic tests). Keep RLock serialization, session registry, event emission. |
| `jbrowser/backend/playwright.py` | Keep as the reference `BrowserBackend` implementation used by hermetic tests; it already satisfies the interface CDP must also satisfy. No ownership change. |

### REPLACE (swap implementation, keep contract)

| Subsystem | Change |
|-----------|--------|
| `extensions/jbrowser/src/controller/controller.js` | **Remove** the `chrome.debugger` CDP control path (fail-closed boundary, consent UI). The extension's service worker becomes a thin `BridgeClient` → DSH (HTTP/SSE) → `BrowserController`. The browser itself is the chromium product; JARVIS control lives in the kernel, not the extension. |
| `jbrowser-bridge` SSE stream | HTTP status + SSE chat only; all control happens through the JARVIS tool gate, not through a raw bridge control endpoint. |

### DELETE

| Subsystem | Change |
|-----------|--------|
| (none functional) | No live subsystem is deleted. Legacy chains remain quarantined under `_quarantine/`. |

### CREATE (new — the only genuinely new surface)

| Deliverable | Module | Purpose |
|-------------|--------|---------|
| CDP subsystem | `orbit/cdp/*`, `orbit/cdp/backend.py` | Direct CDP transport to unbranded Chromium: attach, `CDPBackend` implementing `BrowserBackend`, target registry (JARVIS UUID ↔ CDP target id), ordered serialization, disconnect/reconnect. The locked control surface. |
| Orbit browser runtime | `orbit/runtime.py` | Composition seam: Chromium launch via runtime resolver, `CDPBackend`, `BrowserController`, browser tools, network policy. |
| Orbit tools | `orbit/tools.py` | `browser.*` tool handlers registered in the canonical registry, all routed through `ToolExecutionService` → `BrowserController`. |
| Tab ownership | `orbit/ownership.py` | USER / AGENT / SYSTEM ownership + budgets; `TAB_NOT_OWNED` enforcement inside execution. |
| Agents (extend existing runtime) | `orbit/agents/*` | Main agent on user tabs + parallel research sub-agents on their own tabs/workspaces; per-agent budgets; real cancellation; `WAITING_BROWSER`. |
| Bridge kernel backend | `orbit/bridge.py` | Real `KernelBackend` → `ModelGateway` / `AgentLoop` for sidebar/SSE chat. |
| Chrome import wizard | `orbit/import/*` | Bookmarks/history/settings/extensions; passwords via user-mediated CSV guidance only. |
| Packaging / installer / first-run | `orbit/package/*`, launcher | Delivery layer (never drives architecture). Runtime resolver: `J_BROWSER_CHROMIUM_PATH` or packaged artifact; never the user's Chrome profile, never a hardcoded absolute path. |
| Security hardening tests | `tests/test_orbit_*.py` | Prompt-injection, CDP, network, cross-agent, private-range, crash-recovery. |
| Docs | `docs/jbrowser/orbit-*.md`, `docs/jbrowser/j-browser-architecture.md` update | Implemented behavior only; AGENTS.md architecture contract updated. |

---

## 4. Runtime decision (grounded, not hardcoded)

Dev/CI runtime = **unbranded Playwright Chromium** build present on this
machine (`%LOCALAPPDATA%\ms-playwright\chromium-1234\chrome-win64\chrome.exe`,
headed, supports `--load-extension`). It is resolved at runtime via
`J_BROWSER_CHROMIUM_PATH` or the packaged runtime resolver — never embedded
as an absolute user path in Orbit code. Branded Chrome (installed, v152) is
**never** used as the Orbit runtime and its profile is never touched.

Profile: `config/browser_profiles/orbit/` (gitignored). Product name: **JARVIS Orbit**; accent **blue**; existing icon.

---

## 5. Provider (answers 7 + 8) — grounded finding

`config/models.toml` defines a real `[router]` with `default_provider =
"gemini"` and a full fallback chain (`groq, gemini, cerebras, deepseek,
openrouter, opencode_zen, mistral, nvidia_nim, huggingface, omni_route,
ollama`). `runtime/kernel.py` already builds the canonical `ModelGateway`
from this config. Therefore the Orbit `KernelBackend` will drive **real**
model answers through JARVIS's existing router/gateway — no invented
credentials and no parallel browser-specific model config (answer 8E).
If the provider stack is not functional at the G7 gate, the build **stops**
and reports rather than selecting an incompatible/invented provider.

---

## 6. Test strategy (locked)

- Unit + integration for every new module (hermetic; no Playwright/CDP driver
  needed via mocked backend).
- Real-Chromium E2E + failure injection + security + performance at G13
  (gated behind `JARVIS_RUN_BROWSER_LIVE=1`, default suite stays hermetic).
- Baseline preserved: full default suite 660 passed / 19 skipped (+ existing
  browser bridge tests). No regression tolerated.
- Existing `chrome.debugger`-based extension control is removed (replaced by
  thin DSH client), so no `java // unix`-specific code remains.

---

## 7. Gate map (G0→G13) — unchanged from the locked spec

G0 audit ✔ → G1 foundation → G2 runtime spike → G3 vertical slice 1 →
G4 CDP+registry → G5 tools → G6 extension/bridge → G7 agents →
G8 agent slice → G9 security → G10 crash recovery → G11 import →
G12 memory → G13 E2E/perf/packaging/installer/first-run/docs/CI.

Done at the end of G0. Next: G1.
