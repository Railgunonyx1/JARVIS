# REPO_REVIEW

## Purpose

Extract actionable ideas from open-source repos and map them to JARVIS modules.

- Review mode: **curate → deep-review → record → implement.**
- Findings are ideas/patterns only. **No protected code is copied.** License rules are in the [Rules](#rules) section.
- Each idea carries `module`, `effort` (S/M/L), `risk` (low/med/high). `risk` is JARVIS-adoption risk, not upstream quality.

Module legend: `core/agent/*` loop+tool boundary, `core/harness/*`, `providers/model_gateway.py`,
`runtime/event_bus.py`, `runtime/protocols/`, `memory/*`, `tools/*`, `skills/*`, `cli/*`, `jbrowser/*`,
`orbit/*`, `jbrowser-bridge/`, `extensions/jbrowser`, `security/*`, `voice/`, `benchmark/`.

---

## Priority roadmap (highest leverage first)

| # | Action | Module | Effort | Risk | Status |
|---|--------|--------|--------|------|--------|
| 1 | A11y-tree-first SoM observation + **change-diff snapshots** (only new/removed `[elN]`) | `jbrowser/page_context.py`, `orbit/cdp.py` | S | low | pending |
| 2 | `include_snapshot` flag on every `orbit.*` tool + covering-element pre-click failure + dialog policy | `orbit/tools.py`, `orbit/controller.py` | M | low | pending |
| 3 | Browser-tool doctrine: reference-over-value, semantic summaries, self-healing errors, pagination, slim tool profiles | `tools/classification.py`, `runtime/protocols/` | S | low | pending |
| 4 | SKILL.md frontmatter + progressive-disclosure loading (name+desc in prompt, body on demand) | `skills/registry.py` | S | low | **Done** — native `*/SKILL.md` YAML frontmatter discovery + on-demand body (`parse_skill_frontmatter`) |
| 5 | Skill verification checklists wired into the post-execution gate | `core/agent/verification.py` | M | low | **Done** — manifest `verification` → `AgentState.active_skills` → `AgentLoop._add_skill_verification` |
| 6 | Post-compaction / CONTEXT_OVERFLOW skill re-bootstrap | `core/agent/state.py` | S | low | pending |
| 7 | Reversible tool-output compression (raw kept for the gate) | `core/agent/tool_service.py` | M | med | pending |
| 8 | Provider fallback chain + local-server capability probe + `<provider>/<model>` slugs | `providers/model_gateway.py` | M | med | Partial — capability registry + fallback chain (`providers/capabilities.py`, `router.select_chain`); local-server probe + slugs pending |
| 9 | Multiline input + reverse history search + queue-behind-running-turn | `cli/input.py` | M | low | pending |
| 10 | Theme tokens as data with an ASCII fallback theme | `cli/theme.py` | S | low | pending |
| 11 | Multi-signal (vector + BM25 + entity) fused retrieval + SQLite FTS5 | `memory/store.py`, `tools/doc_retrieval.py` | M | low | pending |
| 12 | Secret placeholders resolved only at the tool boundary, scrubbed from observations | `memory/keyspace.py`, `core/agent/tool_service.py` | M | low | Partial — `security/credentials.py` scanner wired into redaction |
| 13 | MCP single authenticated entry point mirroring the single tool boundary | `runtime/protocols/` | L | med | pending |
| 14 | UI-visible agent state machine (Thinking/Speaking/Standby) as BusEvents | `core/agent/state.py` | S | low | pending |
| 15 | Wake-word voice state machine over one OpenAI-compatible STT/TTS base URL | `voice/` | M | med | pending |
| 16 | Optimization-evidence receipts (hotspot → measured delta → verification gate) | `core/agent/verification.py`, `benchmark/` | M | med | **Done** — `benchmark/receipts.py` + `verify_optimization_evidence` |
| 17 | MCP read-only auto-approval trust enforcement + permission path canonicalization (symlink/`..`) | `runtime/protocols/`, `core/agent/permissions.py` | M | low | **Done** — canonical-path gate + two-key MCP trust (`bd2d310`) |
| 18 | Credential-pool failover + provider auto-detection | `providers/model_gateway.py` | M | med | **Done** — `providers/credential_pool.py` (hermes FailoverReason + strategies) |
| 19 | Retry-safe settlement + post-compaction record-conflict detection | `memory/*`, `core/agent/tool_service.py` | M | med | pending |
| 20 | Subagent registry resurrection prevention + heartbeat under commitment queues | `core/agent/state.py`, `runtime/event_bus.py` | S | low | **Done** — `core/agent/subagent_registry.py` + `heartbeat.py` |
| 21 | Token-budgeted code retrieval tool (tree-sitter, counted budgets) via MCP | `core/harness/*` | M | low | pending |
| 22 | Timeout envelope: phase leases + BACKEND/WALL attribution + cancellation propagation (jacobian) | `core/agent/tool_service.py`, `core/agent/tools.py` | S | low | **Done** (`bd2d310`) |

---

## A. Browser & CDP (Orbit, J-Browser)

### moli (lexmount/moli, Apache-2.0)
- **Ultra-lightweight headless browser** (102 MiB peak vs 348 MiB Chromium, 15% CPU time) → `jbrowser/backend/`, `orbit/cdp.py` · M/low if adopted as optional fast fetch sidecar.
- **Native CDP + WebDriver Classic + WebDriver BiDi** from one binary; no separate Chrome/Playwright install → `jbrowser/backend/base.py` unified engine abstraction · M/low.
- **On-demand layout/rendering** (skip GPU/compositor) — not a full GUI browser, but sufficient for DOM extraction & screenshots → `jbrowser/optimization.py` flags · S/low.
- **Software screenshots + native CDP/CLI PDF with embedded fonts** → `jbrowser/tools.py` `screenshot`/`pdf` · S/low.
- **Lexbench-Headless success 81.9%** (vs Chrome 99.85%) — trade pixel fidelity for resource savings; use only for `orbit.read`/`extract` paths, not `orbit.navigate` heavy interactions.
- **Avoid:** no WebGL/Canvas parity, no GPU compositor — not a drop-in Orbit replacement.

### nanobrowser (Apache-2.0)
- **Multi-agent planner/validator architecture** (Planner + Navigator + Validator) → `core/agent/loop.py`, `core/harness/` · M/low.
- **Side-panel UX with step confirmation** before destructive actions → `extensions/jbrowser`, `orbit/tools.py` `permission` metadata · M/low.
- **chrome.debugger API + Puppeteer frame tracking** (not CDP) — works inside existing Chrome/Edge, no extra binary → `jbrowser/backend/playwright.py` alt path · S/low.
- **Flexible LLM backends** (cloud + local Ollama/LM Studio via OpenAI-compat) → `providers/model_gateway.py` · S/low.
- **Avoid:** `chrome.debugger` (forbidden invariant 7); Firefox/Safari/other Chromium untested; ToS risk if used for automation on protected sites.

### rote (kedarvartak/rote, MIT)
- **Memory manager for browser agents** — treats context window as a managed resource (budget, eviction policy, layout contract, trust gate) → `memory/`, `core/agent/tool_service.py` · M/low.
- **Four efficiency planes:** Perception (distill CDP → stable IDs + diffs), Decision (context layout + cheaper model routing + skip model via memory/replay), Action (typed actions + settledness + self-healing + per-step assertions + speculative pre-exec), Learning (record runs → playbooks/site memory/transition models → replay/hints/resolution/prediction) → `core/agent/loop.py`, `orbit/tools.py`, `jbrowser/page_context.py` · M/low.
- **Observation eviction** — keep what you *did*, not what you *saw*; missing earlier-page facts fail as `recall_unavailable`; fabricated comparisons fail verification (T18) → `memory/extractor.py`, `core/agent/verification.py` · M/low.
- **Diff observations** — median diff 24 chars, 99.6% reduction vs grounded base (T10) → `jbrowser/page_context.py` `page.diff_snapshot()` · S/low.
- **Cache layout / immutable-prefix routing** — SHA-256 `prompt_cache_key` for planner prefix; cuts WP-N25 mean cost 20.5%, clears Browser Use by 16.0% at 95% CI (T11) → `providers/model_gateway.py` · S/low.
- **Verified replay executor + deterministic drift gate** — 100% recovery on selector-drifted replays (72/72), 0 silent failures, failed-closed on ambiguous control (T23) → `orbit/runtime.py`, `orbit/controller.py` · M/low.
- **Exact oracle reproducibility** — 83.6% logical token reduction at 18/18 success (T25) → benchmark gates · S/low.
- **Avoid:** history compaction not yet built (curve remains quadratic); early build — only tiers 0-1 working.

### openbrowse (openbrowse-ai/openbrowse, MIT)
- **Model-agnostic Chrome extension** — 130+ providers via live `models.dev` catalog (OpenAI, Anthropic, Google, xAI, Mistral, OpenRouter, Groq, Together, WebLLM/Ollama, Chrome Gemini Nano) → `providers/model_gateway.py` · S/low.
- **Agent side panel + OPFS per-conversation workspace** (files, JS/Python execution) → `extensions/jbrowser`, `orbit/runtime.py` · S/low.
- **MCP integration** (Notion, Slack, Linear, Vercel, Stripe, Supabase, etc.) → `runtime/protocols/` · S/low.
- **Pyodide offscreen AI inference** (WebLLM, cloud APIs, local) → `voice/`, `orbit/runtime.py` · M/low.
- **WXT + React + Vercel AI SDK** — modern extension stack → `extensions/jbrowser` migration reference · S/low.
- **Vendored `models.dev` snapshot + refresh logic** → `providers/model_registry.py` · S/low.
- **Command palette (Alt+K)** overlay injection → `extensions/jbrowser` · S/low.

### WebFurl (WeaveMindAI/Webfurl, AGPL-3.0 → ideas only)
- **Recursive compressible semantic tree** — 200k HTML → 20-50 tokens at top level; unfold on demand (query-driven, embedding similarity) → `jbrowser/page_context.py`, `memory/` · M/low.
- **Cross-user content-hash cache** (MongoDB) — static layout chunks cached once; only dynamic subtrees recompressed → `memory/store.py`, `tools/doc_retrieval.py` · M/low.
- **DOM-linked actions** — pre-computed CSS selectors for every interactive element; works against live CDP → `orbit/cdp.py`, `jbrowser/page_context.py` · S/low.
- **Budget-based unfolding** (`WEBFURL_TOKEN_BUDGET`, `WEBFURL_MAX_BUDGET`) — agent spends context only on relevant branches → `core/agent/tool_service.py` budget · S/low.
- **Pipeline:** HTML chunking → parallel LLM compression → structural parent summaries → interactive element extraction with stable CSS selectors → `tools/doc_retrieval.py`, `jbrowser/page_context.py` · M/low.
- **Avoid:** AGPL core; MongoDB dependency; cross-user cache = data governance risk.

### browser-memory (MIT)
- **Reusable memory of web actions** — learn task once, replay deterministically → `orbit/memory.py`, `orbit/runtime.py` · M/low.
- **MCP server** exposes tools → `runtime/protocols/` · S/low.
- **Optional hosted registry** (configurable) → `runtime/protocols/` · S/low.

### memorall (zrg-team/memorall, MIT)
- **Local-first knowledge graph + hybrid search** (PGlite + vectors + Drizzle) — topics, conversations, sources, nodes/edges → `memory/graph.py`, `memory/store.py` · M/low.
- **Flow Engine** (graph runtime, step/tool registry, flow builder catalog, middleware, streaming activity) → `core/agent/loop.py`, `core/harness/` · M/low.
- **Multi-target** (MV3 extension, static web, Tauri desktop) — shared React workspace, PGlite DB, Flow Engine, sandbox container → `cli/`, `extensions/jbrowser` · L/low.
- **Agent tools:** browser (extension tabs / bundled Chromium), filesystem, sandbox runtime (Node/pnpm/Vite) → `jbrowser/`, `cli/` · M/low.
- **Local-first architecture** — Wllama/WebLLM/Transformers first-class; PGlite entire store in-browser; background jobs offscreen; Supabase optional → `memory/`, `voice/` · M/low.
- **RuntimeProcessor** abstraction (MV3 offscreen / web worker / Tauri+Node sidecar) → `core/agent/tool_service.py` sandbox · M/low.
- **Agent-harness package** (reusable execution contracts + environment adapters) → `core/agent/`, `runtime/protocols/` · M/low.

### Clearcote (clearcotelabs/clearcote-browser, BSD-3)
- **Open-source stealth Chromium** — 32 engine-level C++ patches (Blink/V8/BoringSSL) for coherent fingerprint spoofing down to TLS JA3/JA4/HTTP-2 → `orbit/cdp.py`, `jbrowser/backend/playwright.py` · M/low.
- **Drop-in Playwright/Puppeteer** — swap executable, keep code; auto-downloads + SHA-256 verifies binary per OS → `jbrowser/backend/playwright.py` · S/low.
- **No JS injection** — getters are native C++ (`toString` → `[native code]`) across main frame, iframes, workers; no self-revealing shims → `orbit/cdp.py` fingerprint section · S/low.
- **JA3/JA4/HTTP-2 coherence** — TLS handshake matches Chrome version; no spoofed-JS-over-real-TLS seam → `orbit/cdp.py` · S/low.
- **Reproducible builds** — GPG-signed, SHA-256 checksummed, verifiable from source; `docs/VERIFY.md`, `docs/STEALTH-COHERENCE.md` regression gate → CI/reproducibility · S/low.
- **One `--fingerprint` seed** → stable identity across canvas, WebGL, audio, fonts, locale, hardware, TLS; `fingerprintNoise: false` disables noise while keeping identity → `orbit/cdp.py` · S/low.
- **`geoip=True` auto-matches** timezone/locale/Accept-Language/WebRTC egress to proxy exit → `orbit/controller.py` · S/low.
- **Free forever, BSD-3** — no paid tiers; npm/PyPI/NuGet packages auto-download binary → `jbrowser/backend/playwright.py` · S/low.

### CloakBrowser (CloakHQ/CloakBrowser, MIT code / Pro gated)
- **87 source-level C++ patches** (Chromium 154) — canvas, WebGL, audio, fonts, GPU, screen, WebRTC, network timing, automation signals, CDP input behavior → `orbit/cdp.py` · M/low.
- **`humanize=True` behavioral layer** — Bézier mouse curves with overshoot+correction, per-char typing with typos+self-correction, accelerate/cruise/decelerate scroll, idle micro-movements, `careful` preset → `orbit/controller.py` · M/med.
- **Passes 30+ detection sites** — reCAPTCHA v3 0.9 (human), Cloudflare Turnstile PASS, FingerprintJS PASS, BrowserScan NORMAL, `bot.incolumitas.com` 1 fail (WEBDRIVER spec only) → `jbrowser/optimization.py` stealth config · M/low.
- **Per-session fingerprint seed** persisted in profile, deterministic on revisit → `jbrowser/sessions.py` · S/med.
- **Actionability gating** — wait visible + enabled + stable before acting → `orbit/controller.py` · S/low.
- **Proxy integration** — residential proxy + `geoip=True` + `headless=False` + `humanize=True` recommended → `orbit/controller.py` · S/low.
- **Avoid:** Pro binary distribution (license keys, opaque builds); **CAPTCHA/anti-bot evasion framing** conflicts with default-deny network policy and consent invariant 9. Adopt behavioral consistency only.

### antibrow (antibrow/antibrow, MIT)
- **Kernel-level antidetect** — coherent real-device profiles (30+ categories, 500+ params from one real machine) → `orbit/cdp.py` · M/low.
- **Coherent profiles** — canvas, WebGL, WebGPU, audio, fonts, WebRTC, protocol layer all agree (sampled from one real machine) → `orbit/cdp.py` · S/low.
- **Timezone/locale follow proxy** — geo resolved from exit IP, written into fingerprint before launch → `orbit/controller.py` · S/low.
- **Proxy auth in engine** — `http/https/socks5` inline on `--proxy-server`; engine answers challenge, no helper extension → `orbit/controller.py` · S/low.
- **Encrypted relay transport** (`relay://...?key=`) — AES-256-GCM sealed WebSocket frames, HKDF-SHA256 keys, no CONNECT/SOCKS handshake → `orbit/controller.py`, `jbrowser/network.py` · M/low.
- **Passkeys captured & replayed** per profile virtual authenticator → `jbrowser/sessions.py` · M/low.
- **MCP server mode** — AI agent drives profile directly → `runtime/protocols/` · S/low.
- **Standard Playwright API** — no proprietary API; `fanout` runs same command on N profiles → `jbrowser/backend/playwright.py` · S/low.
- **Linux x64/arm64, macOS universal, Windows x64** — relay server MIT-licensed, self-hostable (Cloudflare Worker/Node) → CI/CD · S/low.

### ProxyShard/ShardBrowser (MIT)
- **Free open-source anti-detect launcher** — patched Chromium 152 with engine-level spoofing (WebGL/WebGPU/Client Hints/fonts/TLS) → `orbit/cdp.py` · M/low.
- **220+ device profiles** (Mac M1-M5, Windows NVIDIA/Intel/AMD, Linux, Android) — each with complete device identity (GPU, screen, fonts, audio, TLS ClientHello, UA-CH, WebRTC, geolocation, cookies) → `jbrowser/sessions.py` · S/low.
- **QUIC/HTTP-3 over SOCKS5 UDP relay** — end-to-end through proxy UDP relay, origin resolved by proxy → `jbrowser/network.py` · M/low.
- **TLS ClientHello** — Chrome 152 cipher suites + extension shuffling; JA4/Akamai/Peetprint match Chrome version → `orbit/cdp.py` · S/low.
- **Local HTTP API + MCP server** — Bearer JWT auth; `127.0.0.1:40325`; `Motion` CDP domain for pointer/keystrokes via browser input path → `runtime/protocols/`, `orbit/cdp.py` · M/low.
- **Automation projects** — visual steps, recording, fleet runs, WASM modules, failure routing, recording → `orbit/runtime.py` · M/low.
- **Python/Node/Rust SDKs** — same pre-launch pipeline (UDP probe, conditional QUIC, auto timezone/locale/geo, screen strategy, host-aware hardware randomization) → `cli/`, `orbit/controller.py` · S/low.

### agentic-stealth-browser (shanewas/agentic-stealth-browser, MIT)
- **Human-mimicking stealth** — passes Cloudflare, LinkedIn, Amazon, bot.sannysoft.com, pixelscan.net, CreepJS in headless → `orbit/controller.py` · M/low.
- **Region-spoofed TLS profile** (JA3/JA4-ish) — process-level, not uTLS; attach mode degrades → `orbit/cdp.py` · M/low.
- **Behavioral synthesis** — Bézier mouse curves with overshoot, variable typing speed, fatigue simulation, distraction → `orbit/controller.py` · M/low.
- **Auto-recovery chain** — block detection → proxy/session rotation → retry → `orbit/controller.py` · M/low.
- **14-day account warming** — graduated ramp-up per account → `orbit/runtime.py` · M/low.
- **Workflow orchestrator** — queue, schedule, domain concurrency, retries, persistence → `orbit/runtime.py` · M/low.
- **Security governance** — input validation, session isolation, policy engine, fail-closed MCP approval gate, per-user dashboard RBAC → `core/agent/permissions.py`, `runtime/protocols/` · M/med.
- **Auditability** — tamper-evident HMAC audit chain, success-path records, log rotation/retention, recursive + token redaction → `runtime/event_bus.py` · M/low.
- **Operator Dashboard** — live DevTools, CAPTCHA intervention, workflow recording → `extensions/jbrowser` · M/low.
- **Attach mode** — CDP attach to existing browser, stealth degradation matrix documented → `orbit/cdp.py` · S/low.
- **Fail-closed MCP approval gate** (default) — `STEALTH_APPROVAL_MODE=permissive` to restore auto-approve → `runtime/protocols/` · M/med.

### mochi (0xchasercat/mochi, MIT)
- **Relational fingerprint matrix (48-rule DAG)** — every surface derives from single `(profile, seed)` pair; deterministic, no cross-axis randomization (Mac UA never with Linux WebGL) → `orbit/cdp.py` · M/low.
- **Zero-jitter spoofing** — single ~50KB inject payload at top-of-frame, JIT-friendly Proxy traps, no async round-trips → `orbit/cdp.py` · S/low.
- **Behavioral synthesis** — `humanClick`/`humanType`/`humanScroll` via Bezier+Fitts+lognormal-digraph models, parameterized per profile (`hand`, `tremor`, `wpm`, `scrollStyle`) → `orbit/controller.py` · M/low.
- **JA4/JA3/H2-coherent `session.fetch`** — routes through Chromium via CDP (`Network.loadNetworkResource` for GET, `page.evaluate("fetch")` for non-GET); real Chrome JA4 by construction; cookies inherit from page origin → `orbit/cdp.py`, `jbrowser/network.py` · M/low.
- **Probe-Manifest harness** — `bun run harness:smoke` captures live session manifest, diffs against per-profile baselines; Zero-Diff CI gate → CI/benchmark · S/low.
- **Turnstile auto-click** (`@mochi.js/challenges`) — opt-in visible-checkbox auto-click; escalations fire `onEscalation` → `orbit/controller.py` · S/low.
- **Bun-only runtime** — single-runtime stack (no `pip` + `npm`), stock Chromium-for-Testing binary → CI/CD · S/low.
- **Avoid:** Bun-only limits deployment flexibility; no Python SDK.

### rebrowser/rebrowser-bot-detector (MIT)
- **Modern bot detection test suite** — covers `Runtime.enable` leak, `sourceUrl` leak, `mainWorldExecution`, `navigator.webdriver`, `bypassCsp`, viewport defaults, `window.dummyFn`, user-agent, `pwInitScripts`, `exposeFunctionLeak` → `orbit/cdp.py`, `jbrowser/backend/playwright.py` · S/low.
- **Fixes via `rebrowser-patches`** — disable `Runtime.enable`, custom source URLs, isolated contexts, `--disable-blink-features=AutomationControlled`, viewport `null`, avoid CSP bypass → `jbrowser/backend/playwright.py` · S/low.
- **Use as regression gate** in CI to verify stealth configuration → CI/benchmark · S/low.

### ShardX Launcher (ProxyShard/ShardBrowser, MIT)
- **Chromium fork + agent platform** (C++ patches + TypeScript/Rust agent) — two products: neo (agent-driven) + BrowserOS (user-facing with AI tab) → `orbit/` + `extensions/jbrowser` concept · L/med.
- **MCP endpoint (`claw-server`)** + dashboard extension (`claw-app`) for live session watch/replay → `jbrowser-bridge/server.py`, `extensions/jbrowser` · M/low.
- **One-click login import from Chrome** (persistent profile) → `jbrowser/sessions.py`, `config/browser_profiles/` · S/low.
- **Agent runs in parallel tabs, live replay like video** → `orbit/runtime.py`, `jbrowser/tabs.py` · M/low.
- **Patches applied to Chromium source** (fingerprint, security, performance) — capture relevant patches only, avoid AGPL fork maintenance.
- **Avoid:** AGPL code reuse; CAPTCHA/anti-bot evasion framing; full Chromium fork build chain (Python/gn/ninja) — extract patches/ideas, not the build.

### openbrowser-ai (billy-enrizky/openbrowser-ai, MIT)
- **CodeAgent architecture:** LLM writes Python in persistent namespace executed over CDP → `orbit/runtime.py`, `orbit/tools.py` `orbit.eval` · M/low.
- **15 LLM providers + MCP server** (single `execute_code` tool) → `providers/model_gateway.py`, `runtime/protocols/` · S/low.
- **3.2× fewer tokens than Playwright MCP, 6× fewer than Chrome DevTools MCP** (response size 7.8k vs 1.1M chars) → `orbit/tools.py` token-optimized returns · S/low.
- **CLI daemon** (`-c` flag) with saved login state, auto-shutdown → `cli/`, `orbit/controller.py` · S/low.
- **Auto-detects local Chromium (Chrome/Edge/Brave/Chromium) + uvx install fallback** → `orbit/cdp.py` `_find_chromium()` · S/low.
- **Saved logins KMS-encrypted** (cloud) / local encrypted → `security/`, `jbrowser/sessions.py` · M/low.
- **FastAPI + Next.js cloud platform** with VNC streaming, scheduled workflows — pattern for future hosted Orbit.

### browser-control (keon/browser-control, MIT)
- **Tiny Rust CDP CLI** (single static binary, no SDK/runtime) — shell-native subcommands (`snapshot`, `click`, `eval`, `cdp`) → `cli/`, `orbit/tools.py` · S/low.
- **Provider-agnostic cloud** (Browser Use, Steel, Hyperbrowser, Browserbase, custom CDP URL) → `jbrowser-bridge/server.py`, `runtime/protocols/` · S/low.
- **Raw CDP escape hatch** (`eval`, `cdp` subcommands) — never hit a wall; agent writes arbitrary JS when helpers insufficient → `orbit/tools.py` `orbit.eval` / `orbit.cdp` · S/low.
- **Reproducible pinned toolchain** (`rust-toolchain.toml` + `Cargo.lock`) → CI reproducibility · S/low.
- **Stable element refs via `snapshot`** (numbered `[elN]` style) — aligns with JARVIS page-context handles → `jbrowser/page_context.py`, `orbit/cdp.py` · S/low.
- **Avoid:** no built-in permission model (inverse of invariant 1) — would need wrapper through `ToolExecutionService`.

### browser-use (MIT)
- **Structured action batching** (`max_actions_per_step`) → one model turn fills a whole form, fewer round-trips. `core/agent/loop.py`, `orbit/tools.py` · M/med.
- **`ActionResult` separates `long_term_memory` / `error` / `extracted_content`** → durable facts vs per-step observation in tool results. `core/agent/tool_service.py` · S/low.
- **`allowed_domains` / `prohibited_domains` with O(1) set matching, TLD wildcards rejected** → complements private-IP deny. `jbrowser/network.py` · S/low.
- **Dedicated `page_extraction_llm`** (cheaper model for page text vs reasoning). `providers/model_gateway.py` · M/low.
- **`max_failures` + `final_response_after_failure`** → one last model call with intermediate state instead of dying. `core/agent/loop.py` · S/low.
- *Avoid:* `disable_security`, default telemetry, parameter-name-coupled tool injection.

### vercel-labs/agent-browser (Apache-2.0)
- **Snapshot diffs as the primary observation** (`--if-changed`). Agent sees only what changed. → `jbrowser/page_context.py` `page.diff_snapshot()` · M/low.
- **Stable never-reused tab ids + human labels** + CDP targetId accepted everywhere; positional indices rejected. → `orbit/registry.py` · S/low.
- **Covering-element pre-click check** → structured failure naming the `elN` to dismiss first. → `orbit/controller.py` · M/low.
- **Semantic finders alongside refs** (`find role/button --name`, label, placeholder, testid). → `orbit/tools.py`, `tools/classification.py` · S/low.
- **Dialog policy:** auto-accept `alert`/`beforeunload`, require explicit handling of `confirm`/`prompt`, pending-dialog warning threaded into every response. → `orbit/cdp.py` · S/low.
- **Domain allowlist as an MCP tool field** so the approval prompt is meaningful. → `extensions/jbrowser`, `jbrowser-bridge/server.py` · M/low.
- *Avoid:* never surface page-provided tool metadata as trusted — keep it behind the permission gate.

### ChromeDevTools/chrome-devtools-mcp (Apache-2.0)
- **A11y-tree snapshot is the default observation; screenshot is secondary** — explicitly "prefer snapshot over screenshot". → `jbrowser/page_context.py` · S/low.
- **`include_snapshot` on every mutating tool** → fresh post-action observation in the same call, no extra round-trip. → `orbit/tools.py` · S/low.
- **Adopt as browser-tool doctrine:** token-optimized semantic summaries ("LCP was 3.2s", not 50k JSON lines); **reference-over-value** (path/URI, never inline bytes); self-healing errors with context + suggested fix; small composable blocks; progressive complexity (simple defaults, hidden advanced). → `tools/classification.py`, `orbit/tools.py` · S/low.
- **Paginated large responses** (`pageIdx`/`pageSize`) with "more pages available". → `orbit/tools.py` · S/low.
- **Named isolated contexts** (`isolatedContext`) within a session. → `orbit/controller.py`, `jbrowser/backend/playwright.py` · S/low.
- **Category-gated tool surfaces / `--slim` mode** for large catalogs. → `orbit/tools.py`, `runtime/protocols/` · M/low.
- *Avoid:* default-on telemetry; keep arbitrary JS eval HIGH/critical gated.

### Skyvern (AGPL-3.0 → ideas only)
- **Selector-first with NL/LLM fallback on failure**, aligned to `retry_semantics`. → `orbit/tools.py`, `tools/classification.py` · M/low.
- **Four orthogonal page commands** — `act` / `extract` / `validate` / `prompt` (validate returns bool for cheap state assertions). → `orbit/tools.py` · M/low.
- **Caller-supplied extraction schema** constrains output shape. → `orbit/tools.py`, `core/agent/verification.py` · S/low.
- **Workflow chaining** (deterministic task→extract→loop→task plans, replayable without re-reasoning). → `skills/`, `core/agent/loop.py` · L/med.
- *Avoid:* AGPL code reuse; cloud browser tunneling (externalizes a live browser with cookies over a public URL — conflicts with the loopback-only bridge); default telemetry.

### lightpanda-io/browser (AGPL-3.0 → ideas only)
- **Native Markdown + semantic AX-tree dumps** (no post-hoc HTML→MD; AX tree carries role/name/isInteractive/xpath). → `orbit/cdp.py` via `Accessibility.getFullAXTree` · M/low.
- **Record-once / replay-token-free scripts** (deterministic macro replay, no model calls). → `skills/`, `orbit/runtime.py` · L/med.
- **`$LP_*`-style secret placeholders** resolved in-process and scrubbed back into recordings — credentials never in prompts. → `memory/keyspace.py`, `core/agent/tool_service.py` · M/low. Synergizes with the existing `orbit.import_passwords` no-secret contract.
- **MCP `Mcp-Session-Id` → one browsing session per client** (`session_new/list/close`). → `jbrowser-bridge/server.py`, `runtime/protocols/` · M/low.
- **Extraction miss semantics:** some fields missing → `null` quietly; **all** fields missing → explicit "your selectors are wrong". → `orbit/tools.py`, `core/agent/verification.py` · S/low.
- *Avoid:* AGPL code; it has no graphical rendering — at most a fast fetch/extract sidecar, not an Orbit replacement.

### CloakHQ/CloakBrowser (code MIT, Pro license-gated)
- **`humanize=True` behavioral layer:** Bézier mouse curves with overshoot, per-char typing with typos + self-correction, accelerate→cruise→decelerate scroll, idle micro-movements; `careful` preset. → `orbit/controller.py` · M/med.
- **Per-session fingerprint seed persisted in profile**, deterministic on revisit. → `jbrowser/sessions.py` · S/med.
- **Actionability gating:** wait visible + enabled + stable before acting. → `orbit/controller.py` · S/low.
- *Avoid:* Pro binary distribution (license keys, opaque Chromium downloads); **any CAPTCHA/anti-bot-evasion framing** — conflicts with default-deny network policy and consent model. Adopt behavioral consistency only, never detection-evasion patches.

### terx (ixchio/terx, MIT)
- **Local policy-enforced replay** — records semantic workflow after success, replays via CDP without LLM call → `orbit/runtime.py`, `orbit/memory.py` · M/low.
- **Three actions only** (`navigate`, `click`, `type`) with exact accessible role/label → `orbit/tools.py` · S/low.
- **Scope + precondition + postcondition** contracts (URL/title/text/selector) with fingerprint; versioned workflows → `orbit/memory.py` · M/low.
- **Destructive side-effect gating** — consume-once approval verifier required for `side_effect="destructive"`; standalone server fails closed → `core/agent/permissions.py` · M/med.
- **Dependency-free adapter** — reuses existing CDP bridge, no Playwright/Selenium runtime → `orbit/cdp.py` · S/low.
- **MCP server** with `flow.replay` tool, named discoverable tools with scope digest → `runtime/protocols/` · S/low.
- **Avoid:** not a general automation framework; only 3 semantic actions; Browser Use adapter experimental.

### flowreplay (kuilenren/flowreplay, Apache-2.0)
- **Record → portable `SKILL.md`** — human demo in real browser compiles to Markdown with machine-readable block → `skills/`, `core/harness/` · M/low.
- **Locator ladder** (CSS → ARIA role → text → XPath → coordinate) with self-healing write-back; winning locator promoted → `orbit/tools.py`, `orbit/controller.py` · M/low.
- **Deterministic replay engine** — slim Playwright executor, `{{variable}}` substitution, `flowreplay replay` · M/low.
- **Lossless SKILL.md round-trip** (`flow_to_skill_md` / `parse_skill_md`) + `distill_flow` (LLM-optional) → `skills/manifests.py` · S/low.
- **Static robustness grading** (no execution) — demotes framework-volatile CSS below semantic locators → `tools/classification.py` · S/low.
- **M0/M1 complete** (format spec, recorder, SKILL.md round-trip, replay engine, self-heal, variables); M2/M3 in progress → `skills/registry.py` · S/low.
- **Boks/Claw platform import** lossless → `extensions/jbrowser` · S/low.

### browser-trace (Wadehl/browser-trace, MIT)
- **Trace (JSONL) → Replay Spec (YAML) → deterministic replay** with network assertions → `orbit/runtime.py`, `orbit/controller.py` · M/low.
- **Locator fallback chain** (selector → role+text → rect) with assertions on network requests (`wait_for_request`) → `orbit/controller.py` · S/low.
- **CLI + MCP server + Skill** — same code path (MCP forwards to CLI) → `runtime/protocols/`, `orbit/tools.py` · S/low.
- **Trust boundary** — CLI sole entry owning browser (random port, temp profile); agents/scripts only act through commands → `orbit/controller.py` · S/low.
- **Timing comparison** (`.compare.json` with recorded vs replay ms) → `benchmark/` · S/low.

### scout (pcamarajr/scout, MIT)
- **Self-healing QA** — one-sentence scenario → AI agent verifies in real browser → deterministic Playwright script → `orbit/runtime.py`, `orbit/controller.py` · M/low.
- **Stable selector ladder** (data-testid → id → role+name → text → positional CSS) with record-time fragility warnings + deterministic fallback retries → `orbit/tools.py` · S/low.
- **Self-heal loop** — UI change → AI re-verifies & re-records → diff review → `orbit/runtime.py`, `core/agent/verification.py` · M/low.
- **MCP server** (`scout mcp`) + agent onboarding skills (`.claude/skills/scout/`, `.cursor/rules/`) → `runtime/protocols/`, `skills/` · S/low.
- **Pure replay CI** (`scout go --no-heal`) — zero LLM, seconds, ~zero cost → `benchmark/` · S/low.

### agentbrowser (AshtonVaughan/agentbrowser, MIT)
- **Visible-cursor real Chromium** — SVG cursor sprite via context init, Bezier trajectories with jitter/ease/overshoot, click ripple, 14-point trail → `orbit/controller.py` · M/low.
- **Goal-based API** — `findAndClick({goal})` DOM → text → role → vision-LLM, every step verified; `executor.executeAction` action-memory hot path → `orbit/tools.py`, `orbit/controller.py` · M/low.
- **Action verifier** — snapshots ElementBoxes pre-action, diffs post-settle, declares verified on URL/element/text change → `orbit/controller.py`, `core/agent/verification.py` · M/low.
- **Stale-element recovery** — selector failure → fallback to `getByText(originalText)` → `orbit/controller.py` · S/low.
- **Modal interrupter** — detects high-z dialogs at viewport center, classifies (cookie/consent/subscribe = blocker, login = user-relevant), auto-dismisses blockers → `orbit/controller.py` · S/low.
- **Selector library learns from verified outcomes only** — per-domain cache, cross-domain transfer via `recallByGoal` (hypothesis transfer) → `orbit/memory.py` · M/low.
- **Recorder + replay** — JSONL traces to `~/.agentbrowser/traces/`, `ReplayEngine` with configurable speed, `compactTrace` collapses trajectories, per-step screenshot + element capture (plan audit) → `orbit/runtime.py`, `benchmark/` · M/low.
- **Per-context fingerprint shield** — 5 GPU profiles, `hardwareConcurrency`, `deviceMemory`, AudioContext noise, Canvas jitter, `navigator.plugins`, deterministic seed per session → `orbit/cdp.py` · M/low.
- **CAPTCHA pipeline** — 2Captcha API, detect → solve → inject → `orbit/controller.py` · M/med.
- **HTTP API** (13 integration tests) + WebSocket events + JSONL traces at `~/.agentbrowser/traces/` → `runtime/protocols/` · M/low.
- **119/119 tests passing**, clean TypeScript build, verified bot detection bypass (Cloudflare, OneTrust, Cookiebot, Reddit, StackOverflow) · CI · S/low.

### lumen (omxyz/lumen, MIT)
- **Vision-only perception loop** — screenshot → model → action(s) → screenshot; no DOM scraping/selectors → `orbit/runtime.py`, `orbit/tools.py` · M/low.
- **History compression** — tier-1 screenshot drop + tier-2 LLM summarization at 80% context utilization → `core/agent/tool_service.py` · S/low.
- **Persistent memory** — `writeState` structured JSON survives compaction → `memory/` · S/low.
- **Streaming + session resumption** — `agent.stream()` typed `StreamEvent`, serialize/restore with `Agent.resume()` → `orbit/runtime.py` · S/low.
- **Safety** — `SessionPolicy` (domain allow/block), `PreActionHook` (imperative deny), `Verifier` (completion gate) → `core/agent/permissions.py`, `core/agent/verification.py` · S/low.
- **Repeat detection** — 3-layer (exact action repeats, category dominance, URL stall) with escalating nudges → `core/agent/loop.py` · S/low.
- **Action caching** — on-disk cache for replaying known-good actions → `orbit/memory.py` · S/low.
- **Child delegation** — model hands off sub-tasks via `delegate` → `core/agent/loop.py` · M/low.
- **Inspired by** Surfer 2 (StateStore+Verifier+plannerModel), Magnitude (ActionCache+screenshot compression), ColorBrowserAgent (SiteKB), Agent Workflow Memory (WorkflowMemory) → `memory/`, `core/harness/` · S/low.

### st4ck-lite (edo-ceder/st4ck-lite, Apache-2.0)
- **Record → deterministic markdown test** — `st4ck browse --record` writes `.md` file, replay with zero LLM (`st4ck run`) · `skills/`, `orbit/runtime.py` · M/low.
- **One primitive per call** — stable IPC vocabulary (`navigate`, `click`, `fill`, `press`, `select`, `check_box`, `hover`, `upload`, `wait_until`, `evaluate` + `click_by_text`/`type_by_text`/`hover_by_text`, conditional `branch`, observation `snapshot`/`url`, control `continue`/`abort`) over line-delimited JSON → `orbit/tools.py`, `orbit/controller.py` · S/low.
- **Conditional dispatch flags** (`dispatch_chain`, `dispatch_events`, `atomic`) for no-code runtimes (Bubble, Retool, Webflow, n8n, Wix, Glide, FlutterFlow) → `orbit/controller.py` · S/low.
- **PRD authoring skills** — three independent reviewer agents (PO/QA/Dev) → `skills/`, `core/harness/` · M/low.
- **Standalone CLI** (`npx st4ck@latest ...`) + `.claude-plugin/` marketplace manifest → `cli/`, `extensions/jbrowser` · S/low.
- **Apache-2.0**, public alpha, stable md format/CLI surface · CI · S/low.

### cairn (team-poem/cairn, MIT)
- **Discover once, replay forever** — AI discovers flow once, freezes to `skill.json`; deterministic replay with zero LLM calls → `orbit/runtime.py`, `orbit/memory.py` · M/low.
- **Self-heal on drift** — broken step → LLM maps original intent to new page, repairs single step, re-freezes → `orbit/runtime.py`, `core/agent/verification.py` · M/low.
- **Policy gate** — `ActionPolicy` deterministic gate vets every proposed action before execution (block destructive, cap wandering, stop on goal) → `core/agent/permissions.py` · S/low.
- **Perceive hook** — `PerceptionAdapter` corrects state of widgets outside a11y tree (custom checkbox in styled class) → `jbrowser/page_context.py` · S/low.
- **Trace stream** — full lifecycle as flat ordered versioned event stream (watch live or store for viewer) → `runtime/event_bus.py` · S/low.
- **Model-agnostic** — Anthropic, OpenAI, Gemini, key-less Claude Code/Codex CLI → `providers/model_gateway.py` · S/low.
- **Portable engine** — core (`cairn-engine`) with pluggable `Driver` (Playwright), `Critic`, `Reporter`, `ContextProvider`, `LlmClient` → `orbit/controller.py`, `runtime/protocols/` · M/low.
- **Browser/extension build** — `cairn-engine/browser` for non-Node environments → `extensions/jbrowser` · S/low.

### flowproof (automators-com/flowproof, Apache-2.0)
- **Record once, replay forever** — agent runs once, records trace; deterministic replay with zero LLM calls → `orbit/runtime.py`, `orbit/memory.py` · M/low.
- **Strict tool-call assertions** — `assert_tool_call` / `assert_no_tool_call` / `assert_no_egress` (Linux seccomp containment) → `core/agent/tool_service.py`, `security/` · M/med.
- **Multi-adapter** — Web (CDP), Windows desktop (UIA), SAP GUI, Vision (OCR), API, Agent boundary (OpenAI/Anthropic proxy) → `jbrowser/`, `orbit/controller.py` · M/low.
- **Healing with reviewable diff** — broken step → proposes trace diff with before/after frames, applied only with explicit `--apply` → `orbit/runtime.py`, `core/agent/verification.py` · M/low.
- **Suite support** — shared browser + isolated contexts per flow, `suite.yaml` manifest, seed/cleanup hooks, data minted by external CLI → `orbit/runtime.py` · M/low.
- **Reports** — JUnit XML, HTML report, screenshot checkpoints, optional GIF/video, `--highlight-cursor` → `benchmark/` · S/low.
- **MCP server** (`flowproof[mcp]`) — `record`, `run`, `get_trace`, `heal` over MCP → `runtime/protocols/` · S/low.
- **Security controls** — Linux egress containment (seccomp filter, declare `allow_egress`, certify `assert_no_egress`) → `security/`, `jbrowser/network.py` · M/med.
- **Rust/Python/Node unified** — single wheel via PyO3/maturin, same version across crates/python/npm → CI/CD · S/low.
- **Agent boundary testing** — record agent trajectory once against real model, replay with zero model calls, assert tool calls (OpenAI/Anthropic dialect) → `core/agent/tool_service.py` · M/low.

### FSQ (microsoft/FSQ, MIT)
- **Evidence-first AI UI automation** — Goal → Evidence → Candidate YAML → Strict Replay → Runs report → Portable HTML → `orbit/runtime.py`, `orbit/controller.py` · M/low.
- **Strict replay provider-free** — reviewed `.fsq.yaml` Case replays without LLM; CI/coding agents verify without Provider → `orbit/runtime.py`, `benchmark/` · M/low.
- **Cross-platform Cases** — Web (Playwright), Android (uiautomator2), Windows (pywinauto), macOS (Appium) share same Case/evidence/Run format → `jbrowser/`, `orbit/controller.py` · M/low.
- **Separate exploration from regression** — AI explores goal; reviewed YAML replays authored actions deterministically → `core/agent/loop.py`, `core/agent/verification.py` · M/low.
- **Evidence bundle** — screenshots, normalized UI snapshots, ordered events, metadata, reports kept per Run → `orbit/runtime.py`, `benchmark/` · S/low.
- **Local Control Plane** — workspace, evidence, Provider config local by default; `~/.fsq` auth → `cli/`, `security/` · S/low.
- **Provider support** — OpenAI, Azure OpenAI, DeepSeek, Google Gemini, GitHub Copilot; one active at a time → `providers/model_gateway.py` · S/low.
- **Suggest mode** — `--suggest` analyzes persisted Case/evidence for improvements without modifying source → `core/agent/verification.py` · S/low.
- **Local web UI** — compiled frontend on `127.0.0.1:8879`, no Node at runtime → `extensions/jbrowser` · S/low.
- **Avoid:** alpha v0.1.0, APIs may evolve; platform prerequisites not installed by `init` (browsers, ADB, Appium).

### Bug0 AI (bug0inc/passmark, Other)
- **AI regression testing** — natural-language steps via Playwright, intelligent Redis caching, auto-healing, multi-model assertion consensus (Claude + Gemini + arbiter) → `core/agent/tool_service.py`, `providers/model_gateway.py` · M/med.
- **Cache-first execution** — Redis keyed by `userFlow + step.description`; cache hit executes directly without AI; bypass on retries → `memory/store.py`, `core/agent/tool_service.py` · M/low.
- **Multi-model consensus** — primary (Claude) + secondary (Gemini) + arbiter on disagreement; consensus-based validation → `providers/model_gateway.py`, `core/agent/verification.py` · M/med.
- **Video assertions** — `video: true` records step via `page.screencast`, uploads `.webm` to Gemini Files API, evaluates against full video (toasts/banners) → `orbit/tools.py`, `orbit/controller.py` · M/low.
- **Smart waits** — AI-evaluated wait conditions with exponential backoff, no rigid selectors/time waits → `orbit/controller.py` · S/low.
- **Caching limits** — only single-step actions cached; multi-step varies too widely → `memory/store.py` · S/low.
- **Avoid:** non-standard license (Other); Redis dependency for full features; caching limited to single-step.

### autoheal-qa (RitualDev-Lab/autoheal-qa, MIT)
- **100% free local self-healing** — Playwright interceptor captures failures; Tier 1 deterministic heuristics (≥85% confidence) + Tier 2 local Ollama (`qwen2.5-coder`, `llama3.2`) for complex rewrites → `orbit/controller.py`, `orbit/tools.py` · M/low.
- **Surgical AST patcher** — updates `.spec.ts` in place, preserving indentation, chaining, formatting; `autoheal rollback` reverts `.autoheal-backup` snapshots → `orbit/tools.py`, `orbit/controller.py` · M/low.
- **Verification loop** — auto-re-runs failed test before committing patch; fails → auto-rolls back & tries next candidate → `core/agent/verification.py` · M/low.
- **Tiered reasoning** — Heuristics first ($0, <1ms), then local Ollama (`qwen2.5-coder`/`llama3.2`), graceful fallback → `core/agent/verification.py` · S/low.
- **Interactive dark-mode report** — `autoheal report` generates `autoheal-report.html` with side-by-side locator comparison, confidence breakdown (role match, string distance, action compatibility), AXTree inspector → `benchmark/`, `cli/` · S/low.
- **Playwright native** — drop-in interceptor in `playwright.config.ts`; zero wrapper/vendor lock-in → `jbrowser/backend/playwright.py` · S/low.
- **CLI commands** — `autoheal test`, `autoheal test --heal`, `autoheal heal [--yes/--no-verify]`, `autoheal report`, `autoheal rollback` → `cli/` · S/low.
- **Zero cloud** — local Ollama, no API keys, no telemetry; DOM never leaves device → `security/`, `core/agent/permissions.py` · S/low.
- **MIT license**, PRs welcome, Playwright 1.50+, Ollama local.

### healix (kunaal-ai/healix, MIT)
- **Privacy-first local self-healing** — AI runs via Ollama, zero data leaves device; HIPAA/SOC2/PCI-DSS/air-gap ready → `security/`, `core/agent/permissions.py` · S/low.
- **Agentic heal loop** — Observe (DOM) → Reason (AI) → Act (corrected action) → Verify → Learn (cache successful fixes) → `orbit/controller.py`, `orbit/tools.py` · M/low.
- **Smart APIs** — `smart_click(page, selector, text)` heals in one line; `healed_locator(page, selector)` returns Playwright `Locator` for `expect()`; `Healix.patch(page)` zero-refactor Page Objects → `orbit/tools.py`, `orbit/controller.py` · S/low.
- **Confidence scoring** — logs every decision with confidence/reasoning; returns scoped selector when count>1 → `core/agent/verification.py` · S/low.
- **Persistent learning** — `~/.healix/cache.json` persists fixes; instant replay on cache hit; separate cache per engine (Chromium/Firefox/WebKit) → `memory/store.py`, `orbit/memory.py` · S/low.
- **Performance metrics** — Prometheus `healix_heal_duration_seconds` (p95), `healix_heal_cache_total` (hit/miss) exposed; scoped follow-up call reduces second Ollama round-trip → `benchmark/`, `core/agent/verification.py` · S/low.
- **Zero-refactor integration** — `Healix.patch(page)` wraps existing Page Objects; `smart_locator` for assertions → `orbit/tools.py` · S/low.
- **Unit + integration tests** (18 unit, live browser healing demo) · CI · S/low.
- **Avoid:** Python only; Ollama required for healing; no OpenAI/Anthropic yet (planned).

### BrowserOS neo (browseros-ai/BrowserOS, AGPL-3.0 → ideas only)

---

## B. Agent loop, harness, verification, skills

### obra/superpowers (MIT)
- **SessionStart bootstrap skill** injected at session start **and after compaction** → guarantees skill discovery in long sessions. → `skills/registry.py`, `core/harness/` · S/low.
- **Mandatory-workflow skills as gates:** skills declare trigger conditions, checked before any task. → `core/harness/` consults `skills/catalog` before EXECUTING · M/med (over-trigger risk).
- **Subagent-driven development** + two-stage review (spec compliance, then quality). → `core/agent/loop.py`, verification stage · L/med.
- **Post-compaction re-bootstrap** (documented upstream failure mode). → `core/agent/state.py` CONTEXT_OVERFLOW handler · S/low.
- *Avoid:* telemetry pinging the vendor site on skill load.

### addyosmani/agent-skills (MIT)
- **SKILL.md contract:** YAML frontmatter (`name` + `description` with "Use when…" triggers, ≤1024 chars), sections Overview / When to Use / Process / Rationalizations / Red Flags / Verification. → `skills/manifests.py` schema + validator · S/low.
- **Anti-rationalization table** (excuse → rebuttal) + **evidence-required Verification checklist** per skill. → pairs with `core/agent/verification.py` · M/low.
- **Progressive disclosure:** name+description only in the prompt; SKILL.md <500 lines; refs one level deep; **scripts over inline code** (executed code costs only output tokens). → `skills/registry.py` · M/low.
- **Shared `references/` at pack root** for single-source checklists. → `skills/` layout · S/low.
- *Avoid:* model-specific workaround steps ("write the procedure, not the workaround").

### earendil-works/pi (MIT)
- **Agent Skills spec conformance** — advertise name+description at startup, load SKILL.md on demand, `/skill:name args` force-load, `disable-model-invocation`, recursive `.agents/skills/` discovery. → `skills/registry.py`, `cli/` · M/low.
- **Versioned skill packages** (install via git/npm). → `skills/catalog` manifest gains `version`/`source` · M/med.
- **Startup diagnostics:** malformed SKILL.md warns (not fatal), name collisions keep first + warn, `/reload` live edits. → registry load-time validation · S/low.
- **Supply-chain hardening:** pinned exact deps, `--ignore-scripts`, lockfile as ground truth, lifecycle-script allowlist. → CI/deps policy · M/low.
- *Avoid:* Pi has **no** permission system — the inverse of invariant #1.

### OpenHands (MIT)
- **Repo-boundary discipline** enforced by architecture tests (already mirrored by FREEZE). → `tests/` no-bypass test · S/low.
- **Per-conversation execution isolation** (own container per conversation; workspace survives container replacement). → `ToolExecutionService` sandbox · L/med.
- **Automation server separated from agent server** (decides *what* runs vs *how*). → trigger layer above AgentLoop · L/med.
- **Loopback-only binds + session-key injection only when not exposed.** → `runtime/` bridge/CLI auth · S/low.
- *Avoid:* "runs without sandbox = full filesystem" default path.

### x1xhlol/system-prompts-and-models-of-ai-tools (GPL-3.0 → patterns only)
- **Mine tool-result formatting, planning prompts, "when to ask vs act" rules** → feed `core/harness/` templates · S/low.
- **Tool schema conventions** (narrow args, descriptive errors, hints fields) → review `tools/` catalog · S/low.
- *Avoid (hard):* GPL-3.0 **and** leaked/proprietary prompt text — never paste into JARVIS prompts.

### DietrichGebert/ponytail (MIT)
- **The ladder** as an ordered checklist skill: does it need to exist → already in codebase → stdlib → native platform → installed dep → one line → minimal + one test. → `skills/` consumed by `core/harness/` · S/low.
- **Non-negotiable carve-outs:** never cut validation/error-handling/security/accessibility to save tokens. → `core/harness/`, `security/code_scan.py` · S/low.
- **`shortcut:` comment ledger + `/debt` harvest** (structured deferred-debt markers). → skill + BusEvent on deferral · M/low.
- **Review reads code beyond the diff** (blast radius); findings shaped as: what it does / what goes wrong / fix / consequence if skipped. → `core/agent/verification.py` failure context · M/low.
- *Avoid:* benchmark marketing numbers as gospel; safety-weakening intensity modes.

### JuliusBrussee/caveman (Apache-2.0)
- **Terse-output rules:** answer-first, one idea/sentence, preserve negations/numbers/payload verbatim, full sentences reserved for security/irreversible/confused cases. → `core/harness/` response directive · S/low.
- **Input compressors** for CSV/logs/YAML/test-output/JSON before the model reads (originals kept on disk). → `core/agent/tool_service.py` + a `retrieve original` tool · M/med (must not compress before `verification.py` reads evidence).
- **Reusable code blocks** (scripts the agent already wrote, re-offered instead of retyped). → `skills/` + harness suggests on repeat patterns · M/low.
- **Per-turn effort/model routing** (cheap ask → small model; resume-after-tool → low reasoning). → `providers/model_gateway.py` · M/med.
- *Avoid:* rewriting the **user's** prompt (hurts quality); telemetry; silent vendor-cloud routing.

### headroomlabs-ai/headroom (Apache-2.0)
- **Content-typed compression router** (JSON→variance-based pruning keeping outliers/first/last; code→AST-aware; prose→model) applied only to *new* bytes; **frozen prompt prefix kept byte-identical to protect KV cache.** → `providers/model_gateway.py`, `core/agent/tool_service.py` · L/med.
- **Reversible compression (CCR)** with a `retrieve` tool for full text. → tool-service + new low-risk tool · M/low.
- **CacheAligner:** flag volatile content that busts provider prefix cache; never rewrite it. → ModelGateway prompt-cache budgeting · S/low.
- **Terse note appended to the end of the system prompt** (cache-safe); dial reasoning down only on tool-result resume turns. → `providers/model_gateway.py` · S/low.
- **Failure mining → corrections in a local gitignored rules file.** → mine into `memory/authority.py` or skill amendments (human-confirmed) · M/med.
- *Avoid:* shipping an ML dependency into core; compressing **verification evidence** would break invariant #4.

---

## C. Memory & RAG

### mem0 (OSS core)
- **Single-pass ADD-only extraction** (never UPDATE/DELETE at write time; conflicts resolved at retrieval). → `memory/extractor.py`, `memory/consolidation.py` · M/med.
- **Multi-signal fusion:** vector + BM25 + entity match in parallel, fused with RRF. → `memory/store.py`, `tools/doc_retrieval.py` · M/low.
- **Entity linking** with query-entity boost. → `memory/graph.py`, `memory/keyspace.py` · M/low.
- **Temporal ranking:** event time first-class; "current state" vs "past event" queries rank differently. → `memory/store.py`, `memory/authority.py` · S–M/low.
- **Agent-confirmed outcomes stored equal-weight with user statements.** → `memory/authority.py`, `orbit/memory.py` · S/low.
- *Avoid:* hosted-cloud path; hardcoded embedding/LLM defaults (JARVIS already has ModelGateway).

### thedotmack/claude-mem
- **3-layer progressive-disclosure search:** `search` (compact index) → `timeline` (chronological neighborhood) → `get_observations` (full text only for chosen IDs) ≈ 10× token savings. → `orbit/memory.py`, `tools/doc_retrieval.py` · M/low.
- **SQLite FTS5 keyword index alongside vectors** — hybrid search with zero extra services. → `memory/store.py` · S/low.
- **Lifecycle-hook capture** (PostToolUse/Stop/SessionEnd: capture now, compress later). → `memory/extractor.py`, `core/agent/loop.py` · M/med (noise/PII).
- **`<private>` exclusion tags** keep sensitive spans out of storage. → `memory/authority.py`, `security/` · S/low.
- **Session-start injection with count limits + source toggle.** → `orbit/memory.py` · S/low.
- *Avoid:* hosted sync (data-exfil risk), PostHog telemetry, Bun/worker runtime (stay Python).

### infiniflow/ragflow
- **Template-based explainable chunking** (paper/legal/table/QA), strategy + template id stored in chunk metadata for reproducibility. → `tools/doc_retrieval.py`, `tools/doc_export.py` · M/low.
- **Knowledge compilation** post-ingest (wiki outline, entity graph, timeline, PageIndex tree) stored beside raw chunks. → `memory/graph.py` · L/med.
- **Agentic retrieval with depth modes** (Low/Med/High/Ultra): decompose → multi-round retrieve → verify evidence. → `tools/doc_retrieval.py`, `core/agent/verification.py` · M/low.
- **Grounded citations:** every answer span links a chunk id + human-auditable preview. → `tools/doc_export.py` · S/low.
- **Multiple recall + fused reranking.** → `tools/doc_retrieval.py` · M/low.
- *Avoid:* dependency zoo (ES/MySQL/MinIO/NATS) — violates sqlite-first posture; take interfaces, not infra.

### unclecode/crawl4ai (Apache-2.0)
- **Fit-markdown pipeline:** emit `raw_markdown` + filtered `fit_markdown`, let the agent pick. → `external/web_scraper.py` · M/low.
- **Adaptive crawling:** stop the deep crawl once accumulated pages pass a sufficiency check against the query. → `external/web_scraper.py`, `jbrowser/skills.py` · M/low.
- **Crash-recoverable crawls** (persist frontier + visited set). → `external/web_scraper.py`, `memory/store.py` · S–M/low.
- **Citation-aware markdown** — links become a numbered reference list, preserving provenance into RAG. → `tools/doc_export.py` · S/low.
- **Cosine-similarity chunk ranking** before LLM consumption. → `tools/doc_retrieval.py` · M/low.
- *Avoid:* stealth/undetected-browser adapter and bot-wall bypass (ToS + conflicts with `BrowserNetworkPolicy` and sensitive-site gates).

### firecrawl (AGPL-3.0 → ideas/API-shape only)
- **Map endpoint pattern:** instant full-URL discovery (sitemap + link graph), relevance-ranked before crawling. → `external/web_scraper.py`, `orbit/` · M/low.
- **Effort-tiered retrieval** (low/med/high = reasoning budget on the same model). → `tools/doc_retrieval.py`, `providers/model_gateway.py` · S/low.
- **Interact-then-extract:** scrape once, keep a page state id, follow up with prompt-driven interaction. → `jbrowser`/`orbit` controller · M/low.
- **In-pipeline media parsing** (PDF/DOCX → markdown during scrape). → `tools/doc_retrieval.py`, `tools/doc_export.py` · M/low.
- **Schema-scraped structured output** (Pydantic schema → typed JSON). → `tools/doc_retrieval.py` · S/low.
- *Avoid:* **AGPL core — never copy server code.** Hosted proxy-rotation/bot-wall = ToS risk.

### bytedance/deer-flow
- **Manual context compaction tool + session-goal object** re-checked each turn. → `core/agent/loop.py`, `core/agent/state.py` · M/med.
- **Current-task scratchpad keyspace** scoped to the active task, auto-pruned at task end (sibling to `user.*`/`agent.*`). → `memory/keyspace.py`, `orbit/memory.py` · S/low.
- **Prompt overlays:** config-level prepend/append on extraction prompts without source edits. → `memory/extractor.py` + config · S/low.
- **Request admission / RPM pacing** with a shared per-process budget across agent threads (handles 429/529 re-entry). → `providers/model_gateway.py`, `core/agent/tool_service.py` · M/low.
- **Structured provider-error taxonomy** distinguishing "provider failed" from "empty results". → failure classes · S/low.
- **Scheduled tasks with cron dry-run preview** (show next N occurrences before enable). → `runtime/`, `orbit` tools · L/med.
- *Avoid:* IM-channel gateway + "gateway-admin = code exec" footgun; LangGraph backbone — patterns only.

---

## D. Providers / model gateway

### google-gemini/gemini-cli (Apache-2.0)
- **Headless output modes** `--output-format json` / `stream-json` (NDJSON events) — mirrors the BusEvent schema. → `cli/main.py`, `cli/renderer.py` · S/low.
- **TOML custom slash-commands** (`~/.jarvis/commands/` + project override) with `{{args}}`, `@{file}` context injection, `!{shell}` output injection — **shell args auto-escaped + confirmation before exec**. → `cli/input.py`, `cli/cockpit.py` + permission gate · M/med.
- **Approval-mode cycling** (prompt / auto-edit / read-only plan). → `cli/input.py`, `core/agent/permissions.py` · M/med. *Only add plan/auto-edit — YOLO conflicts with fail-closed consent invariant 9.*
- **Paste placeholders** `[Pasted Text: N lines]` collapsible. → `cli/input.py` · S/low.
- **Gate heavy work behind first paint; `F12` debug console instead of verbose default logs.** → `cli/boot.py`, `cli/startup_profile.py` · S/low.
- *Avoid:* Node/React (Ink) rendering stack; telemetry defaults.

### Alishahryar1/free-claude-code (AGPL → ideas only)
- **Ordered fallback-model list applied mid-turn** (retries exhausted → next model, no restart). Must map to `PROVIDER_FAILURE`, not mask it. → `providers/model_gateway.py` · M/med.
- **Per-tier model routing** (cheap/expensive slots by request class: plan vs execute). → gateway route table · M/med.
- **Reasoning-effort control per model** (`Off/Low/High/From client/Inherit`). → provider request builder · S/low.
- **Provider capability conventions:** `<provider>/<model>` slugs, auto model discovery when the list endpoint is missing, manual slug fallback, local presets (`ollama/`, `lmstudio/`, `llamacpp/`). → `providers/` catalog · S/low.
- **`doctor` self-check** (provider reachability, encoding, deps). → `cli/boot.py` · S/low.
- *Avoid:* AGPL code; `curl | sh` installers (vs `scripts/download_dependencies.py`); ToS-sidestepping provider lists.

### mudler/LocalAI (MIT)
- **On-demand backend capability model:** client probes `/v1/models` + capabilities instead of hardcoding. → ModelGateway boot probe · S/low.
- **Prompt-cache-on-by-default + ordered failover chains.** → gateway routing (aligns with invariant 2) · M/med.
- **Voice pipeline as separate local endpoints** (whisper.cpp/parakeet ASR, Piper TTS, Silero VAD) behind one OpenAI-compatible API → one base_url for STT+TTS instead of per-engine code. → `voice/` · M/low.
- **Realtime speech-to-speech with tool calling + streaming pipeline stages** (VAD → streaming STT → agent → streaming TTS). → `voice/` target architecture · L/high.
- **`benchmark` latency/throughput command.** → `benchmark/`-style provider probe · S/low.
- *Avoid:* 60+ backend images (bloat vs `download_dependencies.py`); binding `0.0.0.0` without auth — copy deny-by-default auth, not the exposure.

### lobehub/lobehub (Community License — no code reuse)
- **Model-list DSL** `+add,-hide,name=display`. → `providers/model_gateway.py` formatting · S/low.
- **White-box structured, user-editable memory** (inspectable records, not opaque blobs). → `memory/` via `cli/cockpit.py` `/memory` editor · M/low.
- **Plugin/function-calling extension registry with an isolated gateway.** → `skills/`, MCP · M/med.
- **Agent schedule/report surface** fed by BusEvents. → `cli/cockpit.py` status pane · L/med.
- *Avoid:* non-open license; third-party API-proxy key-resale risk.

---

## E. CLI / TUI

### Textualize/textual (MIT)
- **Theme tokens as data** (named themes + CSS variables) → formalize `cli/theme.py` maps into a token dict + `THEMES[name]` swap (dark/light + ASCII fallback theme) · S/low.
- **Command palette** (fuzzy `Ctrl+P`) reusing the slash-command registry. → `cli/cockpit.py` · M/low.
- **Remote dev console:** log/print out-of-band to a second terminal so debug output never corrupts the frame. → `cli/renderer.py`, `cli/boot.py` · M/low.
- **Headless "pilot" testing** (scripted run asserting rendered screen text). → new `tests/test_cli_render.py` · M/low.
- **Widget decomposition** (DataTable for tool tables, TextArea for multiline). → `cli/layout.py` · L/med.
- *Avoid:* adopting full Textual as the app shell (rewrites `cockpit.py`, alternate-screen breaks cp1252 Windows console).

### gemini-cli input model
- **Command-ID keybinding layer** (`cursor.home`, `input.submit`) in a user `keybindings.json`. → `cli/input.py`, `cli/cockpit.py` · M/low.
- **Multiline contract:** Shift/Ctrl+Enter or trailing `\`+Enter = newline; **Tab = queue prompt behind a running turn**; Esc Esc = clear-or-rewind; **Ctrl+R reverse history search**; external editor (`Ctrl+G`). → `cli/input.py` · M/low.

---

## F. Voice

### Fosowl/agenticSeek (GPL-3.0 → ideas only)
- **Wake-word state machine:** STT listens continuously, activates on `agent_name`, ends on confirmation phrases → IDLE→LISTENING→CONFIRM→DISPATCH. → `voice/` · M/med.
- **`speak` / `listen` as config flags** with per-language TTS voice list. → `voice/`, `cli/startup_profile.py` · S/low.
- **Provider triplet config** `is_local` + `provider_name` + `provider_server_address` with local presets (Ollama 11434, LM Studio 1234, llama.cpp). → `providers/` profile templates · S/low.
- **Session recovery flags** (`recover_last_session` / `save_session`). → `cli/boot.py` · S/low.
- *Avoid:* GPL-3.0 code; deprecated no-auth single-thread Flask `llm_server/`; English-only STT.

### LocalAI + agenticSeek combined
- **One OpenAI-compatible base_url for STT+TTS**, engine-agnostic. → `voice/` · M/low.

---

## G. MCP / protocols / security

### ascending-llc/jarvis-registry (Apache-2.0)
- **Single authenticated MCP entry point** (SSE + Streamable HTTP) so every client hits one gateway — mirrors the single tool boundary. → `runtime/protocols/` · L/med. **Must not add a bypass around `ToolExecutionService`.**
- **Off-the-shelf OAuth2/OIDC** (Keycloak/Cognito/Entra) instead of hand-rolled bridge auth. → `security/`, `jbrowser-bridge/server.py` · M/med.
- **Per-tool scope/role ACL engine at the gateway** + semantic search over tool/skill descriptions for runtime discovery. → `core/agent/permissions.py`, `skills/` · M/low.
- **OpenTelemetry traces + Prometheus metrics + full request audit log** on every tool call. → `runtime/event_bus.py`, `benchmark/` · M/low.
- *Avoid:* k8s/Keycloak deployment scaffolding and `workflow-worker` orchestration — overkill locally.

---

## H. Token / context economy

**Consolidated doctrine (from caveman, headroom, chrome-devtools-mcp, browser-use, ponytail, microsoft/JARVIS):**

1. **Reference over value.** File path/URI/handle for heavy assets; never inline bytes into the model.
2. **Semantic summaries.** "LCP was 3.2s" instead of raw timing JSON.
3. **Diff over full state.** Send only what changed since the last observation.
4. **Freeze the prompt prefix.** Never rewrite the system-prompt head — protect the provider KV/prefix cache (`CacheAligner` idea).
5. **Compress only new bytes**, and only what enters model context; keep the **raw result** for `verification.py`.
6. **Scripts over inline code** for skills (executed code costs only its output tokens).
7. **EasyTool-style concise tool instructions** — short usage strings in the prompt, full schema only at exec time. → `core/agent/tool_service.py`, `skills/` · S/low.
8. **Stage-exposed intermediate artifacts** on the bus, not just final output (`stage.*` BusEvents). → `runtime/event_bus.py` · S/low.

---

## I. Cross-repo: notable patterns worth a dedicated spike

| Pattern | Source | JARVIS module | Effort/Risk |
|---|---|---|---|
| Task DAG with typed placeholders + dependency resolution | microsoft/JARVIS (HuggingGPT) | `core/agent/loop.py` | M/med |
| Capability-index model routing (task type → model card) | microsoft/JARVIS, LocalAI | `providers/model_gateway.py` | M/low |
| Cost-aware escalation (local first, cloud on measured failure) | open-jarvis/OpenJarvis | `providers/model_gateway.py` | M/low |
| Three execution modes (on-demand / scheduled / continuous) | open-jarvis/OpenJarvis | `core/agent/loop.py`, `core/agent/state.py` | L/med |
| Trace-driven skill optimization + A/B `bench skills` | open-jarvis/OpenJarvis | `skills/`, `benchmark/` | M/low |
| Dual-model split (cheap intent+router, large reasoning) | isair/jarvis | `providers/model_gateway.py` | M/low |
| Redaction before model context **and** before persistence | isair/jarvis | `security/`, `memory/store.py` | M/med |
| Dual-source memory (prior knowledge + solved-task precedents) | CraftJarvis/JARVIS-1 | `memory/` retrieval | M/med |
| Protocol Bridge: validate actions against execution grants then commit | LYL1015/JarvisHub | `core/agent/tool_service.py`, `security/` | M/med |
| Trajectory recording + dedicated trace viewer | LYL1015/JarvisHub | `runtime/event_bus.py`, `benchmark/` | M/low |
| UI-visible agent state → BusEvents (Thinking/Speaking/Standby) | IRISX-AI/IRIS-AI | `core/agent/state.py` | S/low |
| API keys in OS keychain, never `.env` | IRISX-AI/IRIS-AI | `security/` | S/low |
| Region-select screenshot → OCR → clipboard (scoped vision tool) | IRISX-AI/IRIS-AI | `jbrowser/`, `tools/` | M/med |
| Rolling near-context transcript (join an ongoing conversation) | isair/jarvis | `voice/` | M/low |
| File-tool symlink-escape rejection + Low Power Mode | isair/jarvis | `core/agent/tool_service.py`, `providers/` | S/low |

---

## Rules

### License tiers (what is safe to *use* vs *only read*)

| Tier | Repos | Policy |
|---|---|---|
| **Permissive (code OK, still attribute)** | MIT / Apache-2.0 / BSD-3: browser-use, agent-browser, chrome-devtools-mcp, superpowers, agent-skills, pi, OpenHands, ponytail, LocalAI, textual, crawl4ai, microsoft/JARVIS, open-jarvis, jarvis-registry, JarvisHub, LobeHub-code (`browse`), firecrawl-SDK, rote, openbrowse, browser-control, browser-memory, memorall, nanobrowser, moli, openbrowser-ai, clearcote, antibrow, shardbrowser, agentic-stealth-browser, rebrowser-bot-detector | Ideas **and** reusable snippets allowed with attribution; no wholesale copying of their architecture tests/docs. |
| **AGPL (ideas/API-shape only, never code)** | Skyvern, lightpanda, firecrawl, free-claude-code, WebFurl, BrowserOS neo | Read for patterns. Do **not** copy source, prompts, or configs. |
| **GPL (ideas only, never code/link)** | system-prompts-of-ai-tools, agenticSeek | Patterns only. Never paste their text into JARVIS prompts (leaked/proprietary content is a separate legal risk). |
| **NC / ShareAlike / closed core (NO reuse)** | Priler/jarvis (CC BY-NC-SA), CraftJarvis/JARVIS-1 (no license = all rights reserved), IRISX-AI/IRIS-AI (non-commercial, core closed), LobeHub Community License, isair/jarvis (non-commercial), CloakBrowser Pro binaries | Ideas documented here as observations. **No code, assets, prompts, or binaries may enter JARVIS.** |

### Non-negotiable adoption constraints
1. **No bypass.** Every adopted execution path must route through `ToolExecutionService` (invariant 1).
2. **No telemetry.** Anything with default-on analytics/PostHog/OpenTelemetry-to-vendor is rejected or stripped.
3. **No evasion.** Stealth/fingerprint/CAPTCHA-bypass features are out of scope — conflict with `BrowserNetworkPolicy`, sensitive-site gates, and consent invariant 9.
4. **No compression of verification evidence.** Invariant 4 requires the gate to see raw results.
5. **Fail closed.** YOLO/auto-approve modes, `disable_security`, and "run without sandbox" defaults are rejected.
6. **No cloud-exfiltration of live browser sessions.** Loopback + bearer auth only.
7. **No secrets in prompts or recordings.** Resolve at the tool boundary; scrub from observations.

---

## Reviewed index (all batches)

| Repo | Tier | Best single takeaway |
|---|---|---|
| browser-use | MIT | Diff/action batching + domain allowlists |
| vercel-labs/agent-browser | Apache-2.0 | Snapshot-diff observation + covering-element click |
| chrome-devtools-mcp | Apache-2.0 | A11y-first snapshot, `include_snapshot`, tool doctrine |
| CloakBrowser | MIT code / Pro gated | Behavioral humanization (not evasion) |
| Skyvern | AGPL | act/extract/validate/prompt + selector→NL fallback |
| lightpanda | AGPL | Native AX-tree/markdown + secret placeholders + session-scoped MCP |
| moli | Apache-2.0 | Ultra-lightweight CDP headless (15% Chrome memory) |
| nanobrowser | Apache-2.0 | Multi-agent planner/validator + chrome.debugger layer |
| rote | MIT | Memory manager: diff obs + cache layout + verified replay |
| openbrowse | MIT | Model-agnostic extension + OPFS workspace + 130 providers |
| WebFurl | AGPL | Recursive semantic tree + cross-user cache + budget unfolding |
| browser-memory | MIT | Deterministic replay memory + MCP |
| memorall | MIT | Local-first knowledge graph + Flow Engine + multi-target |
| BrowserOS neo | AGPL | Chromium fork patches + MCP endpoint + login import |
| openbrowser-ai | MIT | CodeAgent CDP + token-efficient MCP + 15 providers |
| browser-control | MIT | Shell-native Rust CDP CLI + provider-agnostic cloud |
| superpowers | MIT | SessionStart skill bootstrap + post-compaction re-inject |
| agent-skills | MIT | SKILL.md anatomy + anti-rationalization + verification checklist |
| pi | MIT | Agent Skills spec conformance + startup diagnostics |
| OpenHands | MIT | Per-conversation sandbox isolation + loopback auth |
| system-prompts-of-ai-tools | GPL | Tool-result/planning pattern mining only |
| ponytail | MIT | The ladder + non-negotiable carve-outs |
| caveman | Apache-2.0 | Terse-output rules + reversible input compression |
| headroom | Apache-2.0 | Cache-safe content-typed compression + CCR |
| mem0 | OSS core | ADD-only extraction + multi-signal RRF retrieval |
| claude-mem | — | 3-layer progressive search + FTS5 + `<private>` tags |
| ragflow | Apache-2.0 (check) | Explainable chunking + agentic retrieval depth |
| crawl4ai | Apache-2.0 | Fit-markdown + adaptive crawl + citation-aware MD |
| firecrawl | AGPL | Map endpoint + effort-tiered retrieval (API shape) |
| deer-flow | Apache-2.0 | Request admission pacing + provider-error taxonomy |
| gemini-cli | Apache-2.0 | Multiline input + slash-commands + headless JSON |
| textual | MIT | Theme tokens as data + pilot testing |
| agenticSeek | GPL | Wake-word state machine |
| lobehub | Community | White-box editable memory + schedule/report surface |
| LocalAI | MIT | Capability probe + unified voice base_url |
| free-claude-code | AGPL | Mid-turn fallback chain + `<provider>/<model>` slugs |
| microsoft/JARVIS | MIT | Task DAG + capability-index routing |
| open-jarvis | Apache-2.0 | Cost-aware escalation + trace-driven skill optimization |
| jarvis-registry | Apache-2.0 | Single authenticated MCP gateway + per-tool ACL |
| isair/jarvis | Non-commercial | Redaction + dual-model split + symlink-safe file tool |
| Priler/jarvis | CC BY-NC-SA | Wake-word engine evaluation method only |
| CraftJarvis/JARVIS-1 | No license | Dual-source precedent memory (observation only) |
| JarvisHub | Apache-2.0 | Protocol Bridge + trajectory recording |
| IRISX-AI/IRIS-AI | Non-commercial | UI-visible state machine + OS keychain keys |
| clearcote | BSD-3 | Engine-level stealth (32 C++ patches, JA3/JA4 coherent, drop-in Playwright) |
| cloakbrowser | MIT code / Pro gated | 87 C++ patches + humanize behavior (reCAPTCHA 0.9, Turnstile PASS) |
| antibrow | MIT | Kernel-level antidetect + coherent profiles + encrypted relay + passkeys + MCP |
| shardbrowser | MIT | 220+ profiles + QUIC over SOCKS5 UDP + local API/MCP + Motion CDP domain |
| agentic-stealth-browser | MIT | Human-mimicking (Bézier, fatigue, TLS spoof) + auto-recovery + 14-day warming + fail-closed MCP |
| mochi | MIT | Relational 48-rule fingerprint DAG + JA4/JA3 coherent fetch + behavioral synthesis + Probe-Manifest CI |
| rebrowser-bot-detector | MIT | Modern bot detection test suite (Runtime.enable, sourceUrl, mainWorld, webdriver, CSP, viewport) |
| browser-memory | MIT | Deterministic replay memory + MCP |
| terx | MIT | Local policy-enforced replay (3 actions) + scope contracts + approval gate |
| flowreplay | Apache-2.0 | Record → portable SKILL.md + locator ladder self-heal + variables |
| browser-trace | MIT | Trace JSONL → Replay Spec YAML → deterministic replay + network assertions |
| scout | MIT | Self-healing QA: one-sentence → AI verify → deterministic Playwright replay |
| agentbrowser | MIT | Visible cursor real Chromium + goal API + action memory + cross-domain recall + CAPTCHA |
| lumen | MIT | Vision-only loop + tiered compression + persistent memory + action cache + delegation |
| st4ck-lite | Apache-2.0 | Record → deterministic md test + stable IPC vocab + no-code runtime flags + PRD skills |

---

# Round 2

## J. Agent harness & orchestration

### openclaw/openclaw (MIT)
- **Trusted gateway / untrusted execution split**, policy enforced by code, tools run host unless sandboxed. → `core/agent/permissions.py` + sandbox · M/low.
- **Harness and model as swappable plugins** → reinforces invariant 2 by making both registries plugin-based. `core/harness/`, `providers/model_gateway.py` · M/low.
- **Inbound-as-untrusted + pairing/approval codes** for unknown senders. `core/agent/permissions.py` · S/low.
- **Security-in-repo gates**: `security/`, semgrep, pre-commit, exposure runbook. `security/code_scan.py` · S/low.
- *Avoid:* TS/pnpm monorepo surface; telemetry defaults.

### NousResearch/hermes-agent (MIT)
- **Turn-phase decomposition**: `iteration_prep / api_call / api_error / overflow / truncation / recovery` instead of one monolith. `core/agent/loop.py`, `core/agent/state.py` · M/med.
- **`pre_tool_call` / `post_tool_call` hooks + dangerous-command approval** inside dispatch. `core/agent/tool_service.py`, `permissions.py` · S/med.
- **Bidirectional iteration budgets**: independent parent/subagent caps + `max_spawn_depth`, `leaf` vs `orchestrator` roles, blocked-tool lists. `core/harness/` · M/med.
- **Delegation context isolation**: child gets zero parent history; only final summary re-enters; parallel background handles. `core/harness/`, `runtime/event_bus.py` · M/med.
- **`execute_code` programmatic tool-calling** (RPC to tools, no reasoning) = zero-context-cost turns. `core/agent/tool_service.py` · M/med.
- **Prompt-stability invariant**: system prompt never mutates mid-turn; only ephemeral layers + cache breakpoints. `core/harness/`, `providers/model_gateway.py` · S/low.
- **Skills as self-authored procedural memory** with advisory linter + `write_approval` staging gate. `memory/authority.py`, `permissions.py` · M/low.
- *Avoid:* 25k tests/1,250 files context-hostile; `hermes_state_*.py` over-decomposition.

### Significant-Gravitas/AutoGPT (classic MIT; `autogpt_platform/` = Polyform Shield)
- **Block-level retry taxonomy** (plain / with-handler / with-feedback per node). `core/agent/tool_service.py` · M/med.
- **`agbenchmark` regression suites** — challenge files + scored runs gating changes. `core/agent/verification.py` · M/low.
- **Typed block I/O contracts** between steps. `tools/classification.py` · S/low.
- **Forge SDK**: interface + component + protocol registry for authoring agents. `runtime/protocols/`, `core/harness/` · M/low.
- *Avoid:* `autogpt_platform/` is non-compete license — no code from that subtree.

### FoundationAgents/MetaGPT (MIT)
- **SOP-as-code**: plan→execute→verify as an explicit ordered procedure. `core/harness/`, `state.py` · M/med.
- **Schema-first actions** (every Action returns pydantic; roles subscribe to typed messages). `core/harness/`, `verification.py` · M/med.
- **Shared message pool / pub-sub env** with role-level subscription. `runtime/event_bus.py` · M/low.
- **Artifact-gated handoffs** (req doc / data model / API spec must exist first). `verification.py` · M/med.
- *Avoid:* role inflation token cost; no sandbox/permission model; unbounded agent count.

### ruvnet/ruflo (MIT)
- **Meta-harness framing** — wraps external harnesses (Claude Code/Codex); strongest external validation of "harness != model". `core/harness/`, `providers/model_gateway.py` · M/low.
- **Lifecycle hook system** with auto-routing. `tool_service.py`, `core/harness/` · M/med.
- **Cost tracking / budgets / provider failover routing.** `model_gateway.py`, `event_bus.py` · M/low.
- **Provenance verify** — cryptographically prove installed bytes match a signed manifest. `security/code_scan.py`, `verification.py` · M/med.
- **MetaHarness readiness score + tool-config security scan.** `verification.py` · M/low.
- *Avoid:* unreliable marketing metrics, 314-tool/35-plugin sprawl, **explicitly unsandboxed mods**; consensus algos are L/high — skip.

### github/spec-kit (MIT)
- **Converge as append-only verification gate (best fit):** reads spec/plan/tasks as sole intent, classifies gaps `missing/partial/contradicts/unrequested` with CRITICAL→LOW severity, appends traceable tasks, never rewrites. Near 1:1 with `core/agent/verification.py` → `RECOVERING` · S/M/low.
- **Analyze = read-only cross-artifact consistency check** (task w/o requirement; plan contradicts spec). `verification.py` · S/low.
- **Clarify gate**: ≤5 targeted questions on underspecified intent before planning. Intent router / harness · S/med.
- **Constitution as immutable authority** — violations are CRITICAL findings. `memory/authority.py` · S/low.
- **Phased dependency-ordered task list** (Setup → Foundational → per-story by priority → Polish, `[P]` parallel markers) ready-made task-fan-out grammar. `core/harness/`, `state.py` · M/med.
- *Avoid:* Markdown-only, no executable enforcement — scaffolding for JARVIS's deterministic gate, not a replacement.

## K. Workflow / RAG platforms

### langgenius/dify (Dify Open Source License — Apache-based + extra conditions)
- **AOP-style execution layers** (`on_node_run_start/end`, `on_event`) for quota, step/time limits, OTel, pause-persistence without touching node code. `core/harness/`, `runtime/event_bus.py` · M/low.
- **Rich tool schema** — `llm_description` vs `human_description`, `form: llm|form`, typed params (`secret-input`, `file`, `select`), `output_schema`, manifest `permission` block (tool/model/endpoint/storage scopes). `tools/classification.py`, `skills/` · M/low.
- **Declarative node error strategies** (`fail` / `default-value` / `fail-branch`) + handled-vs-fatal event split with `error_type`/`error_message`. `verification.py`, `state.py` · S/low.
- **Pause/resume persists serialized graph state** + child-safe layer subset. `event_bus.py`, `state.py` · M/low.
- **Iteration error modes** (`terminated` / `continue-on-error` / `remove-abnormal-output`) + partial-success event. `core/agent/loop.py` · S/low.
- *Avoid:* extra license conditions (never vendor code); `pkgutil.walk_packages` self-registration is implicit/magic — unfit for a security-sensitive tool loader.

### langflow-ai/langflow (MIT)
- **Component tool metadata** (`display_name`, `description`, `priority`, `tool_mode`, per-tool `status` enabled/disabled persisted). `tools/classification.py`, `skills/` · S/low.
- **Component→Tool promotion** with `to_toolkit()` + status filter. `tools/` registry · M/low.
- **Flow-as-MCP-server / REST endpoint**. `runtime/protocols/` · M/med.
- **Single-node "Execute step"** debugging. `cli/` · S/low.
- **Load-time schema validation** (reserved-name / name-overlap). `tools/` · S/low.
- *Avoid:* backend schema coupled to React-Flow frontend; inline editable Python `code` field = code-exec risk.

### langchain-ai/langchain (MIT)
- **Middleware ordering is load-bearing** — HITL must wrap before retry/error middleware or a retried call re-asks approval. `core/agent/tool_service.py`, `permissions.py` · S/med.
- **Per-tool approval policy** — `interrupt_on={tool:{allowed_decisions}}, when=predicate`, batched vs per-call, resume validated against `response_schema`. `permissions.py` · M/low.
- **Fault policies per node** — `RetryPolicy` (backoff+jitter, `retry_on`), `TimeoutPolicy` (`run_timeout` **and** progress-based `idle_timeout` + heartbeat), atomic `error_handler`, SAGA compensation via `completed` accumulator. `core/agent/loop.py`, `verification.py` · M/low.
- **Checkpointer vs Store split** + **pending-writes recovery** (don't re-run nodes that already succeeded). `memory/`, `state.py` · M/med.
- **Tool output shaping** — `return_direct`, `content_and_artifact`, `handle_tool_error`, reserved arg names. `tools/classification.py` · S/low.
- *Avoid:* `interrupt()` re-runs the node from the top (needs idempotency); don't adopt LCEL wholesale.

### open-webui/open-webui (Open WebUI License — branding clause, relicensed)
- **Pipeline stage ordering** — `inlet` → `request` (sees injected RAG chunks) → `stream` → `outlet`; `file_handler=True` opts out of built-in RAG. `core/harness/`, `memory/` · M/med.
- **Tool approval UX** — per-chat access mode persisted per-user *and* per-chat; pending call stored **on the assistant message so it survives reload**; 120s timeout → deny; multi-call approved one at a time; denial returned to the model as an error. `permissions.py`, `cli/` · M/low.
- **Deferred tool search** — `deferral_threshold` by schema char length, `always_loaded` glob allowlist, `search_tools`/`call_tool` meta-tools. `tools/classification.py`, `core/harness/` · M/med.
- **RAG pipeline** — query rewriting, hybrid BM25+dense (`hybrid_bm25_weight`), reranking, `relevance_threshold`, full-context mode. `memory/` · M/med.
- **RBAC + per-user Valves + sub-agent delegation.** `permissions.py` · M/med.
- *Avoid:* upstream HITL had an **ownership-check hole** and **no timeout on `await`** — JARVIS must enforce session ownership and bounded waits; don't keep approval state in-memory-only.

### n8n-io/n8n (Sustainable Use License — NOT OSI)
- **Crash recovery from the event log** — `ExecutionRecoveryService` replays the message bus, marks started-but-unfinished nodes `NodeCrashedError`; each event written to a local rollover log **before** propagation. `runtime/event_bus.py`, `state.py` · L/med.
- **Execution data modes + redaction policies** (db vs blob; per-node progress save; production/manual redaction). `event_bus.py` persistence · M/med.
- **Error-workflow pattern** — structured error context (`lastNodeExecuted`, `error.context.itemIndex`), `continueOnFail`/`alwaysOutputData`, `retryOnFail`/`maxTries`. `verification.py` · S/low.
- **Tombstone reclamation** for dedup after crash. `core/locks`, `state.py` · M/med.
- **Pinned data + partial execution** (freeze a node's output, run the tail). `cli/` · S/low.
- *Avoid:* license not open source; heavy queue-per-node worker model.

### mastra-ai/mastra (Apache-2.0 core; `ee/` = Enterprise License)
- **Typed graph steps** `.then/.branch/.parallel/.foreach` with per-step `input/output/resume/suspendSchema` + retries. `core/harness/` · M/med.
- **Suspend/resume snapshots** — `suspend(payload)` / `resume(resumeData)`, `suspended` vs `waiting`, **`bail()` = human rejection completes as success**, `suspendData` carries why. `state.py`, `event_bus.py` · M/low.
- **Atomic resume claim** — `suspended→running` atomically, `WORKFLOW_RESUME_ALREADY_CLAIMED`/409 on double-click or multi-instance races; adapters self-report `supportsConcurrentUpdates()`. Parallels `core/locks` / Orbit ownership. `core/locks`, `permissions.py` · S/low.
- **Trace continuity across suspend/resume** — persist `traceId/spanId/parentSpanId` so the resumed span nests under the suspended one. `event_bus.py` · M/med.
- **Evals + live observability** — scorers, async sampling rate, datasets/experiments, CI gating, OTel; workflow-step spans capture inputs/outputs/branching. `verification.py`, `benchmark/` · L/med.
- *Avoid:* `ee/` needs a license; unfinished "evented" engine; validate trace IDs before nesting (upstream bug mixed caller `traceId` with persisted `spanId`).

## L. Skills & prompt engineering

### Leonxlnx/taste-skill (MIT)
- **Machine-checked skill exit criteria** — `lint.mjs` banned-pattern scan + `inspect.mjs` real-browser measurement → FAIL/WARN, then a screenshot critique loop capped at 3 rounds. Encode skill exit criteria as *measurable* checks. → `core/agent/verification.py` extend the gate with `checks[]` (command/metric + threshold) run post-execution; failures feed RECOVERING · S/low.
- **Drawn-variation prompt pattern** — deal 3 researched directions, agent picks the one matching the subject (fights mode-collapse). `core/harness/` · M/low.
- **"Competitor test" anti-generic rubric** — if the idea sentence still works with the nearest competitor substituted, it's category-generic. `core/harness/` · S/low.
- **Progressive disclosure by reference files** — SKILL.md is the spine, 9 `references/*.md` loaded on demand, `library/` data read only via script. `skills/registry.py`, `skills/instructions/` · M/low.
- **Structured end-of-run report contract** (decisions, checks run — *never claim unrun checks* — asset credits). `core/harness/` · S/low.
- *Avoid:* Node/Chrome hard dependency (keep JARVIS gates hermetic-first, live opt-in); opinionated house rules belong in a skill, never kernel policy.

### nextlevelbuilder/ui-ux-pro-max-skill (MIT)
- **Declarative `skill.json` manifest** — name, version, license, keywords, platforms, install command; machine-readable packaging separate from prose. `skills/manifests/` · S/low.
- **Master + page-override hierarchical persistence** — global `MASTER.md` + per-page deviations, retrieval checks override first. Maps to `skills/instructions/` + `memory/keyspace` ownership (`user.*` vs `system.*`) · M/low.
- **Catalog status lifecycle** (active / supplemental / deprecated with redirects, excluded from ranking) prevents stale-skill invocation. `skills/catalog/` · M/low.
- **Offline-first stdlib-only search scripts; agents must ask before installing anything.** → encode as classification rule: dependency-free skill scripts; agent-install = HIGH risk. `tools/classification.py`, `permissions.py` · S/low.
- **Pre-delivery checklist as skill output** (contrast 4.5:1, focus states, reduced-motion, responsive widths). `verification.py` · M/med.
- *Avoid:* freemium upsell; 20+ per-host `.claude/`/`.cursor/` dirs — keep one canonical `skills/`; don't inline catalog data into prompts.

### shanraisshan/claude-code-best-practice (MIT)
- **Rich subagent frontmatter schema** (16 fields: `tools` allowlist, `disallowedTools`, `maxTurns`, `model`, `permissionMode`, `effort`, `isolation`, `memory`, `color`). → manifest carries per-skill tool allowlist/denylist + max-turns, enforced at `ToolExecutionService` (extends invariant 1) · M/med.
- **Command → Agent → Skill orchestration chain** — thin command triggers agent that delegates to a skill. `core/harness/` · L/med.
- **Memory scoping `user` / `project` / `local`** → map onto `memory/keyspace.py` (`user.*` cross-session, `agent.<id>.*` project, `system.*` local) · S/low.
- **Hooks as scoped lifecycle events** (`PreToolUse`/`PostToolUse`/`Stop`) attachable per-agent — must run *inside* the tool service post-phase, never as a bypass. `event_bus.py`, `tool_service.py` · L/high.
- **`preload` vs `available` skills** — preload injected into the system prompt, others discovered on demand. `skills/registry.py` · S/low.
- *Avoid:* `permissionMode: bypassPermissions`/`dontAsk` defaults (violates invariant 9); `isolation: worktree` without git-safety analysis; the repo tracks fast-churning betas.

### dair-ai/Prompt-Engineering-Guide (MIT)
- **ReAct + self-consistency** in the loop template (N samples + vote as an optional verify strategy). `core/harness/` · M/low.
- **Prompt chaining with typed handoffs** — planner emits chained sub-goals with explicit I/O contracts; verification gates each stage boundary. `core/harness/` · M/low.
- **Adversarial-prompting hardening at the consent boundary** — instruction-override, role-play jailbreak, tool-exfiltration patterns into the code-scan/sensitive-input gate; untrusted web/email content is *data, never instructions*. Directly relevant now that Orbit browses the live web. `permissions.py`, `security/` · M/med.
- **Factuality / citation discipline** as research-skill exit criteria. `verification.py` · S/low.
- **Task-typed prompt collections** (classification, extraction, evaluation, summarization) with a lookup key instead of one monolithic system prompt. `core/harness/` · S/low.
- *Avoid:* technique sprawl (ToT, APE, Active-Prompt) in the default harness; model-specific advice must not leak into gateway-agnostic templates (invariant 2).

### f/prompts.chat (MIT code + CC0 data)
- **Single canonical data file** (`prompts.csv`) with website + CLI + MCP views over one source. `skills/catalog/` · M/low.
- **Dual-license split**: CC0 for prompt/instruction *content*, MIT for executable scripts; per-skill license metadata in manifests. repo policy · S/low.
- **Persona-role template grammar** — role + constraints + output-format blocks composable. `core/harness/` · S/low.
- **MCP exposure of a prompt library as read-only tool** — expose metadata only, never execution. `runtime/protocols/` · L/med.
- *Avoid:* chat-era persona corpus (jailbreak-adjacent entries) — do not bulk-import; unvetted user prompts are an injection vector.

### Shubhamsaboo/awesome-llm-apps (Apache-2.0)
- **Skills ship with a security + eval CI gate** — per-skill smoke evals (golden input → expected tool-call shape) failing PRs. `skills/`, CI · M/low.
- **Self-improving skills** — rewrite skill text against eval deltas, gated by approval + `ROLLED_BACK` if evals regress. `verification.py`, `skills/` · L/high.
- **Scope-creep detector** — compare plan scope vs actual tool-call set; excess surface flagged WARN. `verification.py` · S/low.
- **Always-on scheduled scouts** emitting proactive BusEvents into the TUI (needs budget caps per period). `event_bus.py`, `cli/cockpit.py` · L/med.
- **Hash-chained append-only audit trail** for HIGH-risk actions + optional multi-model blind review via ModelGateway. `runtime/`, `verification.py` · L/med.
- *Avoid:* single-file Streamlit style (bypasses `ToolExecutionService` by design); self-rewriting agents without eval+approval gates; domain-risk templates must stay HIGH + approval-gated.

## M. Research, vision & voice

### Panniantong/Agent-Reach (MIT)
- **Ordered fallback backend routing per channel** — candidate list probed live, first working wins, failure emits a "repair prescription" as a structured BusEvent. `tools/feeds.py`, `external/web_scraper.py` · M/low.
- **`research.doctor` health-check tool** (read-only, registered through the tool service). `tools/diagnostics.py` · S/low.
- **Capability-layer, not a wrapper-tool doctrine** — keep discovery/routing in the skill registry; never wrap reads in a proxy that bypasses classification. `jbrowser/skills.py` · S/low.
- **`zero_config` vs `login_state` tool tiers** — gated channels require explicit approval like HIGH-risk browser mutations. `jbrowser/permissions.py`, `tools/classification.py` · M/low.
- **0600 credential perms + dry-run install** (preview all writes before mutating config). `memory/keyspace.py` · S/low.
- *Avoid:* agent running `pip install`/shell CLIs (bypasses the tool boundary and code-scan); cookie auth via agent shell.

### koala73/worldmonitor (AGPL-3.0 → ideas only)
- **AI-synthesized briefs from multi-source feed convergence** (`feeds.synthesize_brief(sources[], window)` → one BusEvent). `tools/feeds.py`, `event_bus.py` · M/low.
- **Freshness-tracked source metadata** (`last_ok`, `staleness_band`, `license_posture`) so the agent can decide re-fetch vs trust. `tools/feeds.py` · S/low.
- **Derived attention index with 24h movement bands** consolidated into `memory/store.py`. `memory/consolidation.py` · M/low.
- **`llms.txt` / tool manifest generated from the classification registry** for agent discovery. `tools/` · S/low.
- **Watch-topic parameterized dashboard panel streamed from BusEvents** (Orbit as situational dashboard). `orbit/` · L/med.
- *Avoid:* AGPL code; Tauri renderer→sidecar IPC had 3 trust-boundary disclosures — keep loopback+auth discipline.

### GetStream/Vision-Agents (Apache-2.0)
- **Processor pipeline before the LLM** (OCR region highlighting / UI-element detection on screenshot output) to cut small-text hallucination. `jbrowser/page_context.py` · M/low.
- **Turn detection as its own `TurnDetector`** (VAD + end-utterance-silence threshold) separate from transcription. `voice/` · M/low.
- **Text back-channel BusEvent** — inject operator hints into a running agent loop without breaking TTS. `event_bus.py` · S/low.
- **Native provider API passthrough** for realtime/multimodal methods instead of lowest-common-denominator. `providers/model_gateway.py` · M/med.
- **Cheap deterministic pass triggers, vision LLM only on novelty** (DOM diff / `[elN]` handles first). `orbit/` tool cost · M/low.
- *Avoid:* vendor edge-network dependency; K8s/Prometheus layer at current scale.

### calesthio/OpenMontage (AGPL-3.0 → ideas only)
- **Three-layer knowledge architecture** — tools ("what exists") / skills ("how we use it") / tech packs ("how it works") with declared tool→skill dependency edges so the tool service auto-attaches relevant skill context. `jbrowser/skills.py`, `skills/` · M/low.
- **Scored provider selection across 7 dimensions** with an auditable decision log surfaced as a BusEvent. `providers/model_gateway.py` · M/med.
- **Budget as a permission dimension** — estimated cost over threshold auto-upgrades to HIGH even for otherwise-LOW tools. `core/agent/permissions.py` · M/low.
- **Output-shape validators per tool family** in the existing post-execution gate (not per-call). `core/agent/verification.py` · M/low.
- **Run-tape dashboard** — BusEvent subscriber rendering tool start/done/cost/ownership as a replayable timeline. `event_bus.py`, `orbit/` · L/low.
- **Checkpoint/resume via run-state snapshots** so a crashed session resumes mid-task. `core/agent/loop.py` · L/med.
- *Avoid:* AGPL code; "agent IS the orchestrator" contradicts the single-boundary invariant; 700+ markdown skill files would bloat a curated `skills/`.

### smithakolan/AssemblyAI-AI-Voice-Bot (MIT)
- **`end_utterance_silence_threshold` (1000ms) as explicit endpointing config.** `voice/` · S/low.
- **Partial vs final transcript discrimination** — `voice.transcript.partial` (display only) vs `voice.transcript.final` (enters agent context; prevents mid-word tool triggers). `voice/`, `event_bus.py` · S/low.
- **Half-duplex turn handling** — `listening=False` during TTS playback with a tail-guard before reopening the mic. `voice/` · S/med.
- **Append-only role-tagged transcript** persisted in the `agent.*` keyspace for post-session consolidation. `memory/keyspace.py` · S/low.
- *Avoid:* hardcoded API keys; reconnect-per-turn churn at scale; voice-initiated HIGH-risk actions must still hit `permissions.py` (invariant 9).

### jev-chat/jev-chat-jarvis (MIT)
- **"Judge before write" two-phase pipeline** — intent + risk + recommended action computed *before* any draft, then drafts checked against that judgment. `core/agent/loop.py` (maps to VERIFYING→RECOVERING) · M/low.
- **`read_only_screen_context` tool mode** — screenshots/OCR stay on-device; no tool in this mode may emit click/type/submit. `jbrowser/`, `orbit/` · M/low.
- **`approval_style: fill_only`** — agent prepares exact payload but the final click/type still needs HIGH-risk approval; makes invariant 9 a visible UX. `permissions.py`, `orbit/tools.py` · S/low.
- **`drafts[]` array** (text + score + rationale) instead of a single opaque string. `orbit/tools.py` · S/low.
- **Local OCR pre-pass before shipping screenshots to a vision LLM** — cheaper and keeps sensitive pixels out of provider calls. `jbrowser/page_context.py` · M/med.
- *Avoid:* don't port accessibility-hook into the Orbit extension (violates G6 "no `chrome.debugger`"); never automate sends inside third-party clients.

### Round 2 cross-cutting

| Idea | Modules | Effort | Risk |
|---|---|---|---|
| Converge gap taxonomy feeding the post-execution gate | `core/agent/verification.py` | S/M | low |
| Durable, owned, time-bounded tool approval state | `core/agent/permissions.py` | M | low |
| Deferred/tiered tool schemas (`search_tools` meta-tool) | `tools/classification.py`, `core/harness/` | M | med |
| Event log as the durability primitive (crash recovery + redaction) | `runtime/event_bus.py` | L | med |
| Progress-based timeout + idempotent resumable steps | `core/agent/loop.py`, `state.py` | M | low |
| Endpointing + partial/final transcript events | `voice/`, `event_bus.py` | S | low |
| Budget-as-permission-dimension | `core/agent/permissions.py` | M | low |
| Untrusted-content hardening at the consent boundary | `security/`, `permissions.py` | M | med |
| Per-skill CI evals gated on merge | `skills/`, CI | M | low |
| Measurable skill exit criteria (`checks[]`) | `core/agent/verification.py` | S | low |

---

# Round 3

## N. Ultron-named repos (curated — most of the paste was game/blockchain/ultrasound noise)

### modelscope/ultron (Apache-2.0) — *best in batch*
- **L0/L1/full memory context levels** — search returns `summary_l0` (one line) or `+overview_l1`; full text fetched by id in a second call. Direct prompt-token savings. `memory/store.py` · S/low.
- **HOT/WARM/COLD tier rebalance** — percentile split by `hit_count` + `hotness = exp(-α·days)` decay + COLD TTL → `archived` (never deleted); adoption signals weighted. `memory/consolidation.py` · M/low.
- **Skill crystallization with an upgrade gate** — memories → cosine cluster (≥0.75) → at ≥5 memories an LLM synthesizes a multi-step skill (trigger, ≥3 steps, edge cases); re-crystallize at +3 new memories; publish only if a weighted **structure score strictly improves**; a **separate verifier LLM** labels each claim `grounded/hallucinated/contradicted` (pass ≥0.8 grounded, zero contradictions). `skills/`, `core/agent/verification.py` · M/med.
- **Near-dup merge + redaction on ingest** — cosine >0.85 within type → LLM merge (fallback: keep original if LLM down); Presidio + regex redaction of API keys/tokens/PII *before* persistence. `memory/consolidation.py`, `security/code_scan.py` · M/low.
- *Avoid:* `curl | bash` blueprint import; MBTI/zodiac "soul presets"; server-side trajectory self-training loop.

### NomaDamas/Ultron (MIT) — self-building harness ecology
- **Evidence-gated promotion with no-poisoning rollback** — promote only with benchmark provenance + actor audit; canary runs isolated; one bounded change at a time. Adopt the *gate discipline* for `core/harness/` changes (ledger + one-change rule: S/low; full evolution loop: L/high).
- **Secret store precedence** (`runtime secret store > env > .env`), owner-only `secrets.json`, `set --stdin` (no echo), reads expose only `SecretRef` (fingerprint/last4). `providers/model_gateway.py`, `cli/` · S/low — high hygiene value, cheap.
- **Fail-closed live seam** — configured live path with missing creds errors; never substitutes fake/stub results. `model_gateway` fallback discipline · S/low.
- **Signed RunManifest** — actor-attributed provenance, side-effect ledger, quarantine. `runtime/event_bus.py` field + `tool_service` audit · M/med.
- *Avoid:* thumbs-up/down-driven module atrophy (harness drift).

### SAGAR-TAMANG/ultron-by-sagar-builds (MIT, 982★)
- **Nothing worth adopting.** Three.js/MediaPipe holographic orb renderer for a separate closed project; 5 commits, zero agent logic. Star count ≠ substance. Marginal: gesture *hysteresis* if `voice/` ever adds gesture control.

### maharab549/ultron-ai
- **Local-provider presets as an OpenAI-compatible triple** (`API_BASE`/`API_KEY`/`MODEL_NAME`; LM Studio `:1234/v1`, Ollama `:11434/v1`, dummy key accepted) + function-calling capability probe at connect. `providers/model_gateway.py` · S/low.
- **Mock LLM server as the default dev endpoint** for hermetic tests without keys. Gateway test seam · S/low.
- **Disposable per-task sandbox container with auto-cleanup** — verify `tool_service` sandbox truly tears down per task. · M/med.
- *Avoid:* DDD layering, Baidu-default search, multi-user auth stack.

### smallporridge/WebUltron (MIT, paper artifact)
- **Nothing directly adoptable** (training pipelines, PQ/URL docid encodings, Google Drive data).
- Two transferable ideas: **pseudo-query generation** (DocTTTTTQuery-style, 10 synthetic queries per doc) to build recall-eval pairs; **ranking-metric regression gate** (MRR/nDCG) for search-quality changes instead of eyeballing. `memory/` eval harness · S/low.
- *Avoid:* actually training a seq2seq docid indexer.

### povzayd/ultron (MIT)
- **Key-format signature table** (`ghp_`, `glpat-`, `AKIA…20ch`, `sk_live_`/`sk_test_`, Slack webhook, Twilio `AC`+32hex, JWT/Bearer, Discord webhook URL) → extend `security/code_scan.py FORBIDDEN_CODE_PATTERNS` to catch credential-shaped strings in tool outputs **before** BusEvent persistence. `security/` · S/low — top takeaway.
- **Optional read-only whoami probe** as an operator-only `security.verify_secret` tool, HIGH risk + approval-gated. · S/med.
- *Avoid:* plaintext key files as input; `mv … /usr/bin` install; validating real keys from a shared file is itself a leak vector.

## O. UI, workflow & data

### AUTOMATIC1111/stable-diffusion-webui (AGPL-3.0 → ideas only)
- **Declarative options registry** — `OptionInfo(key, default, widget, args)` chained with `.info()` / `.needs_reload_ui()` / `.link()` / `.restrict_api()`, grouped via `options_section(category)`; one table drives the settings panel, docs, and API exposure flags. `tools/classification.py`, `cli/cockpit.py` · M/low.
- **Extension `metadata.ini` with dependency graph** — `Requires`/`Before`/`After` callback ordering, duplicate canonical-name rejection, disabled-list honored at load. `jbrowser/skills.py`, `tools/` catalog · M/med.
- **`restricted_opts` denylist** — path/secret keys hidden from UI and API (`restrict_api=True`). `core/agent/permissions.py`, bridge config · S/low.
- *Avoid:* AGPL code; auto `git fetch + reset --hard` extension updates (supply chain); global mutable `shared.opts` singleton.

### Comfy-Org/ComfyUI (GPL-3.0 → ideas only)
- **Partial graph re-execution** — only nodes whose inputs changed re-run; results cached; graph executes only where all inputs are valid. `core/harness/` node/graph pipelines · L/med.
- **Declarative node spec + pre-queue validation** — `INPUT_TYPES`/`RETURN_TYPES`/`VALIDATE_INPUTS` checked *before* execution; malformed graphs rejected at queue time. `core/agent/tool_service.py`, `verification.py` · M/low.
- **Node packaging via `pyproject.toml` `[tool.comfy]`** — `PublisherId`, `requires-comfyui = ">=1.0.0"` semver, license, icon. `scripts/download_dependencies.py` + tool catalog: each plugin declares a `requires-jarvis` range · M/low.
- **Offline-by-default** — core downloads nothing unless requested; `--offline` forces local-only. `providers/model_gateway.py` · S/low.
- *Avoid:* GPL code; ComfyUI-Manager-style git auto-install of unvetted custom nodes (bypasses the code-scan gate).

### shadcn-ui/ui (MIT)
- **Semantic token pairs + derived scale** — `background/foreground`, `primary/primary-foreground` under `:root`/`.dark`; radius scale computed from a single `--radius` via `calc()`. → `cli/theme.py` + `extensions/jbrowser/src/lib/tokens.css`: paired fg/bg tokens + one base radius/spacing deriving the whole scale; dark mode = override same tokens only · M/low.
- **Registry as distribution** — `registry.json`/`registry-item.json` declares files, deps, css vars per component; CLI installs items. → jbrowser UI blocks install with declared token deps · M/low.
- **oklch perceptually-uniform palette + dedicated `ring` focus token** — equal lightness steps; every focusable uses `ring`. → `tokens.css` + `cli/renderer.py`: WCAG-stepped ramps and mandatory visible focus for TUI widgets · S/low.
- *Avoid:* Tailwind-specific plumbing; keep tokens in their own layer so regeneration never overwrites hand edits.

### thedaviddias/Front-End-Checklist (MIT)
- **Rules as structured single source** — each rule = id/category/priority (Critical→Low)/remediation/verification step; `validate:rule-structure` CI check; README + MCP generated from the same table. → `core/agent/verification.py` declarative exit criteria as rule objects · M/low.
- **Priority-ordered triage + queryable rules** (`search_rules`/`get_workflow`) — agent fetches highest-confidence checks *before* acting. `tools/` catalog, `cli/cockpit.py` · M/med.
- **Skill entry points** — one global audit skill + per-rule focused skills (a11y, security, perf). `skills/` · S/low.
- *Avoid:* importing the web-specific rule corpus wholesale; checklists that become unenforced prose.

### harry0703/MoneyPrinterTurbo (MIT)
- **Resumable staged pipeline** — `--stop-at <stage>` checkpoints; batch manifest (≤100 tasks) fully pre-validated before the first task; per-task failure doesn't block others; unified JSON summary. `core/harness/` · L/med.
- **Config layering** — `config.example.toml` auto-copied on first run; precedence `CLI args > saved UI settings > built-in defaults`. `cli/`, `providers/model_gateway.py` · S/low.
- **Pluggable stage providers chosen by config** with per-provider TOML subsections; local models cached with manual-download fallback. `scripts/download_dependencies.py` · M/med.
- *Avoid:* plaintext API keys in `config.toml`.

### supabase/supabase (Apache-2.0)
- **Local-first dev stack + migration discipline** — `supabase start`, single `config.toml`, ordered SQL migrations with recorded schema history, `seed.sql` fixtures. → `memory/store.py` + orbit persistence: versioned migration dir + idempotent seed for hermetic test DBs · M/low.
- **Modular feature-clients behind a facade** — per-provider clients isolated and testable, composed under one gateway. `providers/model_gateway.py` · M/med.
- **Fail-closed authz** — JWT + RLS default-deny. Mirror in `jbrowser-bridge` bearer auth + invariant 9 · S/low.
- *Avoid:* hosted SaaS/dashboard assumptions; don't vendor the whole docker stack — minimal local Postgres path.

### Round 3 cross-cutting

| Idea | Modules | Effort | Risk |
|---|---|---|---|
| Redaction-at-ingest + credential-signature scan before persistence | `security/code_scan.py`, `memory/consolidation.py` | S/M | low |
| L0/L1 memory summaries + HOT/WARM/COLD decay | `memory/`, `memory/consolidation.py` | S/M | low |
| Secret store + redacted `SecretRef` + fail-closed live seam | `providers/model_gateway.py`, `cli/` | S | low |
| Skill structure-score upgrade gate + verifier-model check | `skills/`, `core/agent/verification.py` | M | med |
| Local-provider presets + mock-LLM hermetic test seam | `providers/model_gateway.py` | S | low |
| Rule/exit-criteria table as single source | `core/agent/verification.py`, `tools/classification.py` | M | low |
| Semantic paired tokens + derived scales + `ring` focus | `cli/theme.py`, `extensions/jbrowser/src/lib/tokens.css` | M | low |
| Pre-execution declarative arg/graph validation | `core/agent/tool_service.py` | M | low |
| Stage checkpoints + pre-validated batch manifest | `core/harness/` | L | med |
| Versioned migrations + seeds | `memory/store.py` | M | low |

---

## P. Voice / STT / TTS / Speech-to-Speech

### speech-to-speech (huggingface/speech-to-speech, MIT)
- **Full local speech-to-speech pipeline** — Silero VAD → Parakeet TDT → Qwen3.5-4B → Qwen3-TTS; runs entirely on-device → `voice/` · M/low.
- **OpenAI Realtime protocol** (WebSocket + WebRTC) at `/v1/realtime` — drop-in for OpenAI Realtime API clients, LiveKit Agents, browser demo → `runtime/protocols/`, `voice/` · M/low.
- **Swappable backends** — VAD (Silero, FireRed), STT (Parakeet, Whisper, Faster-Whisper, Nemotron, Qwen3-ASR), LLM (mlx-lm, Transformers, responses-api, chat-completions, llama.cpp), TTS (Qwen3-TTS, Kokoro-82M, KittenTTS, Pocket TTS, ChatTTS, MMS) → `voice/`, `providers/model_gateway.py` · M/low.
- **Local + hosted LLM** — swap `--llm_backend` between local (mlx-lm/Transformers) and hosted (responses-api/chat-completions) with same STT/TTS → `providers/model_gateway.py` · S/low.
- **llama.cpp integration** — separate server for LLM, speech process connects via responses-api → `providers/model_gateway.py` · S/low.
- **Offline operation** — after first run caches all model assets; runs without internet → `voice/`, `scripts/download_dependencies.py` · S/low.
- **CLI modes** — `serve` (Realtime server), `talk` (mic client), `local` (in-process compose), `websocket` (raw PCM), `socket` (TCP) → `cli/` · S/low.
- **Web search tooling** (Keenable) — LLM gets `web_search`/`fetch_page` tools executed inside pipeline, results fed back same turn → `tools/`, `runtime/protocols/` · M/low.
- **MLX / GGML / CUDA / CPU** — platform-aware defaults (MLX on macOS, GGML on Linux) → CI/CD · S/low.

### keenable-s2s (keenableai/keenable-s2s, MIT)
- **Modular VAD→STT→LLM→TTS pipeline** — OpenAI Realtime-compatible WebSocket API, every component swappable → `voice/`, `runtime/protocols/` · M/low.
- **Same backend matrix** as speech-to-speech (Parakeet TDT STT, OpenAI-compat LLM, Qwen3-TTS) → `voice/`, `providers/model_gateway.py` · S/low.
- **Live web search** — server advertises `web_search`/`fetch_page` tools to LLM, executes inside pipeline, feeds results back same turn → `tools/`, `runtime/protocols/` · M/low.
- **Fully local via llama.cpp** — separate server for LLM, speech process connects via responses-api → `providers/model_gateway.py` · S/low.
- **CLI flags for every component** — `--stt`, `--llm_backend`, `--tts`, `--mode` (realtime/local/websocket/socket) → `cli/` · S/low.

### voice-agent-starter (sarmakska/voice-agent-starter, MIT)
- **Self-hosted full-duplex voice agent** — browser captures mic → WebSocket → VAD → STT → LLM → TTS → audio chunks back → `voice/`, `runtime/protocols/` · M/low.
- **Sub-second round-trip** target (P50 ~800ms) — mic→VAD 30ms, STT partial 250ms, LLM first token 250ms, TTS first chunk 250ms → `voice/`, `benchmark/` · S/low.
- **Barge-in** — aborts in-flight LLM + TTS streams the moment user starts speaking → `voice/` · M/low.
- **Function-call passthrough** — LLM calls server-side tools mid-turn, results fed back same turn → `tools/`, `runtime/protocols/` · M/low.
- **Pluggable adapters** — STT (Whisper.cpp/Deepgram/Whisper), LLM (Groq/SarmaLink/OpenAI), TTS (OpenTTS/Cartesia/ElevenLabs) via env vars → `providers/model_gateway.py`, `voice/` · S/low.
- **Fastify 5 + Next.js 15** — `/health` endpoint, `/voice` WebSocket, web client captures audio/render transcripts → `runtime/protocols/`, `extensions/jbrowser` · S/low.
- **Shared SSE reader** for OpenAI-compatible LLM adapters → `providers/model_gateway.py` · S/low.
- **One-file adapter pattern** — drop new adapter in `adapters/` implementing interface, register in registry → `providers/model_gateway.py` · S/low.

### open-voice-agent (dvalle08/open-voice-agent, MIT)
- **Local-first LiveKit voice pipeline** — Silero VAD + Moonshine STT → Ollama LLM → Pocket TTS → audio response → `voice/`, `runtime/protocols/` · M/low.
- **Custom LiveKit plugins** — `moonshine_stt` (streaming Moonshine), `pocket_tts` (streaming Pocket TTS 24kHz) implement LiveKit `stt.STT`/`tts.TTS` interfaces → `voice/`, `runtime/protocols/` · M/low.
- **Provider config via env** — `STT_PROVIDER` (moonshine/deepgram/nvidia), `LLM_PROVIDER` (ollama/nvidia), `TTS_PROVIDER` (pocket/deepgram/nvidia) → `providers/model_gateway.py` · S/low.
- **MCP support** — `MCP_ENABLED` + `MCP_SERVER_URL` / `MCP_EXTRA_SERVER_URLS` → `runtime/protocols/` · S/low.
- **Streamlit UI** — lightweight browser client for local/Spaces deployment → `extensions/jbrowser` · S/low.
- **Docker deploy** — one-command container build → CI/CD · S/low.

### voice-agents-from-scratch (pguso/voice-agents-from-scratch, MIT)
- **Tutorial + library** — numbered chapters (audio I/O, streaming Whisper, streaming Kokoro, agent core, full voice loop, real-time duplex, tools, personality, projects) → `voice/`, `cli/` · S/low.
- **Shared library** `src/voice_agents/` — `audio`, `stt`, `tts`, `agent`, `tools` reusable building blocks → `voice/` · S/low.
- **Streaming STT/TTS** — `faster-whisper` one-shot + streaming, Kokoro streaming with profiles → `voice/` · S/low.
- **Real-time duplex** — turn-taking, interruption, duplex patterns, latency tooling → `voice/`, `benchmark/` · M/low.
- **Tool routing** — calculator, time, weather, web search, LLM tool loops → `tools/`, `core/harness/` · S/low.
- **Personality/emotional variation** — style injection in prompts → `core/harness/` · S/low.
- **Local models** — Whisper tiny.en, Qwen 2.5 0.5B Q4 GGUF, Kokoro v1.0 (~800MB) → `scripts/download_dependencies.py` · S/low.
- **uv-based** — extras for vad/serve/deploy; `models/` gitignored → CI/CD · S/low.

### NVIDIA NeMo Voice Agent (NVIDIA-NeMo/Speech/examples/voice_agent, Apache-2.0)
- **Open-source NeMo STT/TTS + HF LLM** — FastConformer streaming ASR + EOU detection (Parakeet-realtime-eou-120m), Kokoro-82M / FastPitch-HiFiGAN / magpie_tts_multilingual_357m TTS, Nemotron-3-Nano-30B / Nemotron-Nano-9B LLM → `voice/`, `providers/model_gateway.py` · M/low.
- **vLLM / HF auto-switch** — `llm.type` config forces or auto-switches between vLLM and HuggingFace backends → `providers/model_gateway.py` · S/low.
- **Speaker diarization** — up to 4 speakers in different turns (`diar_streaming_sortformer_4spk-v2.1`) → `voice/` · S/low.
- **WebSocket server** — WebRTC transport, tool calling for LLMs (weather, speaking speed, voice/accent switching) → `runtime/protocols/`, `tools/` · S/low.
- **Tool calling** — change speed, switch male/female/British/American accents, weather API → `tools/` · S/low.
- **NIM services** — optional NVIDIA Riva ASR/TTS, NIM LLM for production deployment → `providers/model_gateway.py` · M/low.

### dograh (dograh-hq/dograh, BSD-2-Clause)
- **Open-source self-hosted Vapi/Retell alternative** — visual workflow builder, MCP native, telephony (Twilio, Vonage, Telnyx, Plivo, Asterisk ARI) → `voice/`, `runtime/protocols/` · M/low.
- **Visual workflow builder** — start nodes, agent nodes, global instructions, tools, transitions, end-call outcomes → `core/harness/`, `extensions/jbrowser` · M/low.
- **Test Agent panel** — Test Audio (browser voice), Test Chat (fast text iteration with turn replay/regeneration) → `voice/`, `cli/` · S/low.
- **Telephony integrations** — Twilio, Vonage, Telnyx, Plivo, Vobiz, Cloudonix, Asterisk ARI; human handoff with call transfer → `voice/`, `jbrowser/network.py` · M/med.
- **MCP server** — coding agents inspect agents, search docs, fetch node schemas, create workflows, save edits via natural language → `runtime/protocols/` · S/low.
- **Python/Node SDKs** — programmatic agent creation and outbound calls → `cli/`, `runtime/protocols/` · S/low.
- **BYOK** — bring your own LLM/TTS/STT/telephony; self-hosted MinIO/S3 for artifacts → `security/`, `memory/store.py` · S/low.
- **One-command Docker** — `docker-compose` + `start_docker.sh`; auto-generated keys, own LLM/TTS/STT stack → CI/CD · S/low.
- **Claude Code plugin** — agent handles install, config, troubleshooting → `extensions/jbrowser`, `cli/` · S/low.

### pipecat (pipecat-ai/pipecat, MIT)
- **Open-source voice/multimodal agent framework** — composable pipelines, multi-agent ready (handoff, parallel fan-out, sidecar workers, distributed) → `core/agent/loop.py`, `core/harness/`, `runtime/event_bus.py` · M/low.
- **Huge provider matrix** — STT (AssemblyAI, AWS, Azure, Cartesia, Deepgram, ElevenLabs, Groq, Meta, Mistral, Moonshine, NVIDIA, OpenAI, Sarvam, Soniox, Speechmatics, Together, Whisper, xAI), TTS (Async, AWS, Azure, Bland, Camb AI, Cartesia, Deepgram, ElevenLabs, Fish, Google, Groq, Hume, Inworld, Kokoro, MiniMax, Mistral, Neuphonic, NVIDIA, OpenAI, Piper, Resemble, Rime, Sarvam, Smallest, Soniox, Speechify, Speechmatics, Together, xAI, XTTS), STT→STS (AWS Nova Sonic, Azure Voice Live, Gemini Multimodal Live, Grok, OpenAI Realtime, Ultravox), Transport (Daily WebRTC, FastAPI WebSocket, LiveKit WebRTC, SmallWebRTC, Vonage, WebSocket, WhatsApp) → `voice/`, `providers/model_gateway.py`, `runtime/protocols/` · M/low.
- **CLI + AI coding assistant** — `pipecat init` scaffolds bot in <1 min,Claude Code/Codex builds it → `cli/`, `core/harness/` · S/low.
- **Multi-agent** — pipelines as agents; handoff, parallel fan-out, sidecar workers, distributed deployment → `core/agent/loop.py`, `core/harness/` · M/low.
- **Ultra-low latency** — WebRTC/WebSocket transports, real-time audio/video orchestration → `voice/`, `runtime/protocols/` · S/low.
- **Python SDKs** — `uv add "pipecat-ai[option,...]"` for selective deps → CI/CD · S/low.
- **CLI monitor/deploy** — `pipecat-ai[cli]` for production monitoring → `cli/` · S/low.

---

**License tier updates:**
| Tier | Repos |
|---|---|
| **Permissive** | + speech-to-speech, keenable-s2s, voice-agent-starter, open-voice-agent, voice-agents-from-scratch, NVIDIA-NeMo Voice Agent, dograh, pipecat, agentmaker, agentos, NeuroCore, argus, agentset, mem0, aius, MemGraphRAG |
| **AGPL** | (none new) |
| **GPL** | (none new) |
| **NC/ShareAlike/Closed** | (none new) |

All tests green, lint clean. Comprehensive voice/STT/TTS/S2S + agent frameworks + memory/RAG section added.

---

# Round 4

## Q. Agent frameworks & personas

### VoltAgent/voltagent (MIT)
- **Per-tool `needsApproval` policy fn** — dynamic, risk-conditional approval (auto-approve LOW, escalate above a threshold) layered on fail-closed consent. → `core/agent/permissions.py` · M/low.
- **Structured denial codes** (`ToolDeniedError`: TOOL_FORBIDDEN / PLAN / QUOTA + reason) feed deterministic FailureClass. → `core/agent/*` · S/low.
- **Tool tags** (`destructive`, `read-only`, `external-api`) carried on spans/events for policy + audit filters. → `tools/*` · S/low.
- **Prompt-budget discipline** — supervisor sees only each sub-agent's one-line `purpose`; full `instructions` load at delegation. → `core/harness/*` · M/low.
- **"Bail" after handoff** — skip supervisor re-processing when the sub-agent emits a final output (~79% token savings). → `core/harness/*` · M/med.
- **Abort signal inside `execute`** — cancellation checked mid-tool; escalates cleanly to CANCELLED/TIMEOUT. → `core/agent/*` · M/low.
- **Streaming tool results as preliminary BusEvents** (progress yields) before the final ToolResult. → `runtime/event_bus.py` · M/med.
- *Avoid:* client-side tools with no server `execute` (violates single tool boundary); direct MCP registration; `needsApproval` default-off (consent must stay fail-closed).

### msitarzewski/agency-agents (MIT)
- **Strict frontmatter schema** for persona/skill files (`name`, `description`, `vibe`) validated at registry load. → `skills/*` · S/low.
- **Manifest-as-source-of-truth + CI consistency check** — registry consumers must agree with the manifest or build fails. → `skills/*` · S/low.
- **Runbook rosters** — named installable teams of skills/agents (reusable task recipes). → `core/harness/*` · S/low.
- **Selective activation** (`--division`, `--agent`, `--dry-run`, `--list`) — scoped skill loading instead of context flooding. → `cli/*` · S/low.
- **Single-renderer contract** — one `format` name guarantees byte-identical output across consumers. → `runtime/protocols/` · M/low.
- **Severity-tiered review checklist** (blocker / suggestion / nit) reusable for verification + skill prompts. → `skills/*`, `core/agent/verification.py` · S/low.
- *Avoid:* prompt-declared "Memory" sections (memory must flow through `memory/*`); direct file-copy installers; mass-activating 100+ personas; personas granting permission (invariant 9).

## R. Cross-platform UI & desktop

### readest/readest (AGPL-3.0 → ideas only)
- **Host-service abstraction** — one `AppService` interface with runtime-picked impls (web/native/node); extend the `BrowserBackend` pattern to a general host-services seam (fs, dialogs, TTS). → `runtime/protocols/` · M/low.
- **Theme from 3 anchors** (`base`, `base-content`, `primary`) + generated light ramp; dark/light/auto mode. → `extensions/jbrowser/src/lib/tokens.css` · S/low.
- **Global vs per-context settings layering** with per-panel reset / reset-all. → `orbit/*`, `memory/*` · M/low.
- **Rebindable keybindings with conflict UX** (record-on-press, multi-bind, conflict names-and-asks, reset-one/all). → `cli/*` · M/low.
- **Command palette** fuzzy-finding all actions/settings. → `cli/*` · M/med.
- **Ordered user find/replace rules** (plain/regex) applied to display / TTS-only scopes. → `voice/`, `tools/*` · M/low.
- **Runtime-config injection** — server-built config JSON read at startup (no rebuild for bridge URL/token). → `extensions/jbrowser` · S/low.
- *Avoid:* AGPL code; React/Next stack; 80-component reader monolith.

### pot-app/pot-desktop (GPL-3.0 → ideas only)
- **Declarative plugin manifest** (`info.json` with typed `needs[]`) drives a generic config UI. → `tools/*`, `cli/*` · M/low.
- **Service instances** — multiple instances of one plugin/provider with unique keys (multi-account/model). → `runtime/protocols/` · M/low.
- **Parallel fan-out** — N services answer one request concurrently (fits existing `concurrency` metadata). → `core/harness/*` · M/med.
- **Loopback action API** — tiny HTTP verb surface for external callers (keep `/v1/agent`, `/v1/cdp` 501). → `runtime/protocols/` · M/med.
- **Plugin dirs as first-class backup data** — keyspace backup should include skills/tool packs. → `memory/*` · S/low.
- **Toggleable background watchers** with persisted enable state (tab/page-change → EventBus). → `core/harness/*`, `orbit/*` · S/low.
- *Avoid:* GPL-3.0 code; `eval()` plugin execution (must route through ToolExecutionService + `security/code_scan.py`); unauthenticated loopback HTTP (bridge stays fail-closed); 500ms clipboard polling (prefer event-driven).

## S. Local TTS engines (`voice/`)

### rany2/edge-tts (LGPLv3 + MIT `srt_composer.py`)
- **Typed chunk stream** (`{audio | WordBoundary | SentenceBoundary}`) — audio + timing in one async generator. → `voice/` · S/low.
- **SSML/UTF-8-safe byte-boundary splitter** for chunked synthesis of long replies. → `voice/` · S/low.
- **Boundary metadata → subtitle/progress BusEvents**. → `runtime/event_bus.py`, `cli/` · M/low.
- **`stream_sync()` bridge** — async core consumed by sync terminal code. → `voice/` · S/low.
- *Avoid:* vendoring LGPLv3; dependence on an undocumented MS endpoint — pluggable driver only.

### rhasspy/piper (MIT, archived; successor piper1-gpl is GPL-3.0)
- **Voice manifest** = one `.onnx` + sidecar `.onnx.json` (sample rate, phoneme map, default knobs, speakers). → `voice/` · S/low.
- **On-demand `download_voices` + `--data-dir`** registry with lazy fetch/cache. → `voice/` · S/low.
- **Local HTTP server** (`/synthesize`, `/voices`, `/info`) with request→CLI→config default fallback chain. → `voice/`, `runtime/protocols/` · M/med.
- **Offline engine behind the same OpenAI-compatible facade** — online fails → fallback, state machine unaffected. → `voice/`, `providers/model_gateway.py` · M/med.
- **`speaker_id` + `length_scale`** mapped onto OpenAI `voice`/`speed`. → `voice/` · S/low.
- *Avoid:* GPL-3.0 successor code; archived upstream; espeak-ng as a hard dep (optional extra).

### NVIDIA-NeMo/Speech (Apache-2.0 code; weights per-model)
- **Latency-accuracy Pareto as one knob** — selectable streaming latency modes (80ms–1s). → `voice/` · L/high.
- **Offline + streaming in one checkpoint** (Parakeet-unified) — prefer unified STT engines. → `voice/` · M/med.
- **NIM/OpenAI-compatible deploy** — just another provider behind the base URL. → `providers/model_gateway.py` · M/med.
- **Hydra/YAML declarative model configs** → declarative voice profile files. → `voice/` · S/low.
- **Operational docs packaged as an agent skill** for self-service voice diagnosis. → `skills/` · S/low.
- *Avoid:* `nemo-toolkit` as a runtime dep (CUDA/Lightning/NGC weights); training pipelines — ideas only.

### OpenBMB/VoxCPM (Apache-2.0, code + weights)
- **`generate_streaming()`** — numpy chunk generator consumed incrementally (play before synthesis ends). → `voice/` · M/low.
- **Reference contract** — `POST /v1/audio/speech` (`model`/`input`/`voice`, chunked body) validates our single base-URL schema. → `providers/model_gateway.py`, `runtime/protocols/` · M/low.
- **Capability matrix per engine** (params, VRAM, RTF, sample rate, languages) + health probe at startup. → `providers/model_gateway.py` · S/low.
- **`--timestamps` word/char alignment → timeline BusEvents** for speech-synced subtitles. → `runtime/event_bus.py`, `cli/` · M/med.
- **Voice design from a natural-language description** stored as a `user.*` voice profile. → `voice/`, `memory/` · L/med.
- *Avoid:* 2B model (~8GB VRAM) as default; LoRA/webui training stack; voice cloning only with explicit consent (fail-closed via permissions).

### Round 4 cross-cutting

| Idea | Modules | Effort | Risk |
|---|---|---|---|
| Per-tool dynamic approval policy + structured denial codes | `core/agent/permissions.py` | M | low |
| Cancellation honored inside tool execution → CANCELLED/TIMEOUT | `core/agent/*` | M | low |
| Streaming preliminary BusEvents for long tool runs | `runtime/event_bus.py` | M | med |
| Manifest-as-source-of-truth + registry CI consistency gate | `skills/*`, CI | S | low |
| Selective skill/agent activation flags (`--division/--agent/--dry-run`) | `cli/*` | S | low |
| Host-service abstraction for fs/dialog/TTS seams | `runtime/protocols/` | M | low |
| Theme from 3 anchors + generated light ramp | `extensions/jbrowser/src/lib/tokens.css` | S | low |
| Declarative provider/tool manifest driving a generic config UI | `tools/*`, `cli/*` | M | low |
| One OpenAI-compatible facade fronting local + online TTS engines | `voice/`, `providers/model_gateway.py` | M | med |
| Voice engine capability matrix + startup health probe | `providers/model_gateway.py` | S | low |

**License tier updates (Round 4):**
| Tier | Repos |
|---|---|
| **Permissive** | voltagent, agency-agents, piper (MIT, archived), NVIDIA-NeMo/Speech, VoxCPM |
| **AGPL** | readest |
| **GPL / LGPL** | pot-desktop (GPL-3.0), edge-tts (LGPLv3), piper successor (GPL-3.0) |
| **NC/ShareAlike/Closed** | (none new) |

**Round 4 index (8 repos):** voltagent, agency-agents, readest, pot-desktop, edge-tts, piper, NVIDIA-NeMo/Speech, VoxCPM.

> Housekeeping: the working tree also carried an uncommitted browser-repo block with 4 sections duplicated from Section A (`rote`, `openbrowse`, `WebFurl`, `browser-memory`) and a deleted `## B.` header; both were repaired in this batch.

---

# Round 5

## T. Voice assistants & wake-word

### wzpan/wukong-robot (MIT) — *backlog listed as `wukong-robot/wukong-robot`; org URL 404s*
- **Two-engine hotword abstraction** (`detector.py` picks porcupine vs snowboy) → `voice.WakeWordBackend` interface. → `voice/` · M/low.
- **Plugin loader** (`pkgutil.walk_packages` over plugin/contrib/custom paths; `Plugin` class, `SLUG` dedup, enable/disable config, `PRIORITY` sort). → `skills/`, tool registry · M/med.
- **Snowboy PASSIVE→ACTIVE FSM** (ring buffer, silence threshold, recording timeout, detected callback). → `voice/` · S/low.
- **Barge-in** — `interrupt()` aborts TTS when re-woken; emit a BusEvent-driven cancel. → `voice/`, `runtime/event_bus.py` · S/low.
- **Tunables** (sensitivity, silent_threshold, AEC) to cut false wake. → `voice/` · S/low.
- *Avoid:* `load_module()` executes arbitrary plugin code (needs sandbox + `security/code_scan.py`); detectors call `activeListen()/doResponse()` directly — bypasses the single tool boundary.

### kalliope-project/kalliope (GPL-3.0 → ideas only)
- **Explicit FSM states + lifecycle hooks** (`Order.py`: starting_trigger → waiting → analysing; `HookManager.on_triggered/on_start_listening`). → `voice/` · M/low.
- **Signal abstraction** — any input source (order/MQTT/GPIO/schedule) binds to skills. → `runtime/event_bus.py`, intent router · M/med.
- **Trigger pause/"deaf" mode** during TTS + `skip_trigger`/`max_retry` follow-up window (multi-turn without re-wake). → `voice/` · S/med.
- **Pluggable STT/TTS/trigger factories** selected by `settings.yml` → provider registry over one base URL. → `voice/`, `providers/` · M/low.
- **`Cortex` last-order key/value memory**. → session memory · S/low.
- *Avoid:* GPL-3.0 copyleft — clean-room reimplement; YAML-driven neuron execution bypasses the tool boundary; global singletons.

### NaomiProject/Naomi (MIT)
- **ABC plugin base classes** (STT/TTS/VAD/SpeechHandler) + `info` metadata dict + `GenericPlugin` auto-prompt for missing settings. → `voice/`, `runtime/protocols/` · M/low.
- **`VADPlugin`** voice-activity detection (timeout / minimum_capture / padding frames). → `voice/` · M/med.
- **sync/async mic abstraction** → cross-platform audio I/O. → `voice/` · M/med.
- **TTI intent templates** with `{}` keyword slots + WER fuzzy `match_phrase`. → `skills/` intent match · M/low.
- **Compiled-vocabulary caching** keyed on phrases. → `voice/` · S/low.
- *Avoid:* `main_loop()/handleForever` dispatches intents straight to handlers (no ToolExecutionService); WER fuzzy matching can mis-route — gate with `verification.py`.

### thevickypedia/Jarvis (MIT)
- **Executor registry** — keyword→executor fns + `word_match.py` trigger matching. → `tools/*`, `skills/*` · M/med.
- **Tuned SpeechRecognition params** (energy/pause/non_speaking thresholds) as mic calibration. → `voice/` · S/low.
- **Hotword (porcupine) + offline fallback** (`recognize_sphinx`). → `voice/` · M/med.
- **FastAPI + Bearer-token auth** for remote control. → `runtime/protocols/` · M/low.
- **retry/timeout + background_task + crontab** modules. → `tools/*`, scheduler · M/low.
- *Avoid:* API endpoints run system commands with a stored ROOT_PASSWORD (boundary bypass + fail-open without auth); `recognize_google` ships audio to cloud by default; broad retry-except loops hide failures.

## U. Local TTS engine candidates (`voice/`)

> Streaming-first engines behind ONE OpenAI-compatible `/v1/audio/speech` base URL. Every clone path must be **consent-gated and fail-closed** (invariant 9).

### FunAudioLLM/CosyVoice (Apache-2.0)
Bi-streaming adapter (~150ms); `zero_shot/cross_lingual/sft/instruct` modes → OpenAI `voice`+extra; 300M/0.5B size tiers routed by device; vLLM/TensorRT backend optional. → `voice/`, `providers/model_gateway.py` · M/low–med.
*Avoid:* training stacks in prod; raw reference audio in responses/logs.

### QwenLM/Qwen3-TTS (Apache-2.0)
Dual-track streaming (single-char first packet); unified `/v1/audio/speech` + speaker registry; VoiceDesign→clone stored as **hashes only** in `memory/*`; 0.6B/1.7B tiers. → `voice/`, `providers/model_gateway.py` · M/low–med.
*Avoid:* unconsented reuse of voice-design outputs; training pipelines.

### myshell-ai/MeloTTS (Apache-2.0)
Lightweight chunked-synthesis wrapper; minimal `/v1/audio/speech` shim; centralized language/speaker registry; CPU-friendly small tier. → `voice/`, `providers/model_gateway.py` · S/low.

### index-tts/index-tts (Apache-2.0)
Streaming adapter with sentence/phoneme boundary tracking; OpenAI-compatible surface; strict consent (token + reference hash + purpose, no cross-session reuse without re-consent); size tiers + latency-aware routing. → `voice/`, `security/*`, `memory/authority.py` · M/low–med.

### KittenML/KittenTTS (code Apache-2.0; **weights = Stellon Labs Community License**)
ONNX CPU tiers (15M/40M/80M, 25–80 MB); sentence-aware `generate_stream` with seam fades; 5–30s zero-shot clone behind consent; device-tier autodetect; expression markup tags. → `voice/backends`, `providers/model_gateway.py` · M/low–med.
*Avoid:* KittenTTS 2 weights without per-model license review; promising token-level latency (it is chunk-level).

### SWivid/F5-TTS (code MIT; **weights CC-BY-NC**)
`/v1/audio/speech`-shaped handler over `f5-tts_infer-cli`; prompt-based zero-shot behind consent gate; RTF-driven GPU tiers; ONNX/MLX CPU port reference; sentence-chunk streaming. → `runtime/protocols/`, `voice/` · M/low–med.
*Avoid:* CC-BY-NC weights in any shipped product; Triton/TensorRT infra (SLO reference only).

### fishaudio/fish-speech (**Fish Audio Community License** — hosted-API use needs separate license)
Adopt their consent clause (no impersonation without consent, no watermark removal, bind downstream users) as JARVIS cloning policy; first-audio SLO (~100ms) as a gateway budget; unified prosody-tag grammar; speaker-ID-in-text. → `security/consent`, `voice/` · S/low–med.
*Avoid:* exposing JARVIS as a third-party TTS API; training on outputs; S2-Pro research weights.

### RVC-Boss/GPT-SoVITS (MIT)
Existing `api.py`/`api_v2.py` normalized to one OpenAI base URL; two-tier voice registry (zero-shot 5s vs fine-tuned 1min) with per-voice consent provenance; RTF tier table (0.526 CPU vs 0.028 GPU); version-pin voices. → `runtime/protocols/`, `voice/registry` · M/med.
*Avoid:* embedding the training stack (conda/UVR5/FunASR/flash-attn/Docker) in-tree — keep fine-tuning out-of-process; unbounded cloning.

## V. Agent patterns, autonomous research & JARVIS-named repos

### microsoft/ai-agents-for-beginners (MIT — pattern docs, not code)
- **Planning as an explicit Harness phase** (plan BusEvent → execute → verify) rather than implicit in the loop. → `core/harness/*` · S/low.
- **Metacognition loop** — self-question/critique/refine observation feeding VERIFYING→RECOVERING. → `core/agent/loop.py`, `core/agent/verification.py` · M/low.
- **Trustworthy-agent checklist** (grounding audit, tool-input validation, prompt-injection defenses) as a gap checklist against `security/code_scan.py`. → `security/*` · S/low.
- **Agentic RAG** — query rewrite + self-reflective retrieval/retry before declaring empty. → `memory/*` · M/med.
- **Context assembly pipeline** (system / tool defs / working memory / retrieved) as an explicit, testable step. → `memory/keyspace.py`, `core/harness/*` · M/low.
- *Avoid:* hard coupling to Microsoft Agent Framework / Foundry — do not import.

### karpathy/autoresearch (MIT) — *highest signal*
- **`program.md` as a lightweight skill** programming the research org (not the code) → a `self_improvement` skill. → `skills/*` · S/low.
- **Keep/discard git-branch loop** — experiment on a branch, log metric to TSV, advance else `git reset`; a concrete self-improvement/eval loop. → `core/harness/*`, `memory/*` · M/med.
- **Fixed wall-clock budget per experiment** for comparable eval runs. → `core/harness/*`, `benchmark/` · S/low.
- **Single-file edit scope** — agent may modify only its own skill/prompt files, never `ToolExecutionService`/executor (safe self-modification contract). → `skills/*`, `security/*` · M/low.
- **Simplicity criterion** — "equal metric + simpler code = win" as a verification preference. → `core/agent/verification.py` · S/low.
- **Structured metric extraction** (`grep "^val_bpb:"`) instead of dumping noisy logs into context. → `core/agent/tool_service.py` · S/low.
- *Avoid:* "NEVER STOP / disable all permissions" autonomy — violates invariant 9; loops must still gate high/critical actions.

### nexu-io/open-design (Apache-2.0)
- **Skills as portable `SKILL.md` directories** with catalog discovery (validates our registry format). → `skills/*` · S/low.
- **Live-file MCP exposure, not stale exports** — MCP adapter surfaces live BusEvent/memory state, never snapshots; still routed through ToolExecutionService. → `runtime/protocols/` · M/med.
- **One adapter contract with shared streaming/cancellation** for every runtime → one provider-adapter contract in ModelGateway. → `providers/model_gateway.py` · M/low.
- **SSRF guard at the edge** — block RFC1918/link-local/CGNAT/metadata IPs, drop malformed entries; reinforces `BrowserNetworkPolicy` + bridge loopback posture. → `security/*`, `jbrowser/network.py` · S/low.
- *Avoid:* their "external CLI is the engine, no kernel shipped" model is the inverse of JARVIS; preserve NOTICE if any code copied.

### alexylem/jarvis (MIT)
- **One-shot CLI verbs** (`-x "order"` direct-execute, `-l` listen-once) → `jarvis run "intent"` non-interactive. → `cli/*` · S/low.
- **`-j` JSON output mode** — machine-readable output alongside the TUI. → `cli/*` · S/low.
- **`-b` background daemon + menu** — detached, survives terminal close (cf. Orbit launcher single-instance lock). → `cli/*`, `orbit/*` · M/med.
- **Conversation-mode toggle** (`-c`) as an explicit Harness mode affecting memory writes. → `core/harness/*`, `memory/*` · S/low.
- *Avoid:* `-p https://…` installs and runs remote plugin code — fail-open install is exactly the boundary-bypass pattern the no-bypass architecture test forbids.

### affaan-m/JARVIS (**NO LICENSE — all rights reserved; ideas only, do not copy**)
- **Graceful-degradation service registry** — `GET /api/services` reports configured capabilities; JARVIS should expose a provider capability report in `cli/status`. → `providers/model_gateway.py`, `cli/*` · S/low.
- **SSE streaming of incremental results** as observations land (BusEvent streaming, no new event type). → `runtime/event_bus.py`, `cli/*` · M/low.
- **Browser-agent fan-out swarm** — parallel tabs per research target under tab-ownership locks. → `orbit/*`, `skills/*` · L/med.
- **Staged pipeline orchestrator** (capture → research → synthesize) with per-stage fallback. → `core/harness/*` · M/low.
- *Avoid:* **everything in code** (unlicensed) and its facial-recognition / account-pool stack (ethically toxic); never let degradation touch *consent* — permissions stay fail-closed.

### Round 5 cross-cutting

| Idea | Modules | Effort | Risk |
|---|---|---|---|
| Wake-word FSM + `info`-dict plugin metadata as BusEvent fields | `voice/`, `runtime/event_bus.py` | M | low |
| One provider-ABC per capability (STT/TTS/VAD) over the base URL | `voice/`, `providers/model_gateway.py` | M | med |
| Consent-gate every voice-clone path (token + reference hash + audit) | `security/*`, `memory/authority.py` | M | low |
| Voice engine capability matrix + size/device tiers | `providers/model_gateway.py`, `voice/` | S | low |
| `program.md`-style self-improvement skill + keep/discard eval loop | `skills/*`, `core/harness/*` | M | med |
| Safe self-modification: agent edits only its own skill/prompt files | `skills/*`, `security/*` | M | low |
| Metacognition self-critique feeding the verification gate | `core/agent/verification.py` | M | low |
| SSRF/network edge-hardening audit | `security/*`, `jbrowser/network.py` | S | low |
| Provider capability report + fallback chain | `providers/model_gateway.py`, `cli/*` | M | med |
| One-shot / JSON CLI verbs | `cli/*` | S | low |

**License tiers (Round 5):**
| Tier | Repos |
|---|---|
| **Permissive** | wukong-robot, Naomi, thevickypedia/Jarvis, CosyVoice, Qwen3-TTS, MeloTTS, index-tts, KittenTTS (code), F5-TTS (code), GPT-SoVITS, ai-agents-for-beginners, autoresearch, open-design, alexylem/jarvis |
| **Copyleft** | kalliope (GPL-3.0) |
| **Weight-restricted / Non-standard** | KittenTTS 2 weights, F5-TTS weights (CC-BY-NC), fish-speech (Community License) |
| **No license (do not reuse)** | affaan-m/JARVIS |

**Round 5 index (17 repos):** wukong-robot (wzpan), kalliope, Naomi, thevickypedia/Jarvis, CosyVoice, Qwen3-TTS, MeloTTS, index-tts, KittenTTS, F5-TTS, fish-speech, GPT-SoVITS, microsoft/ai-agents-for-beginners, karpathy/autoresearch, nexu-io/open-design, alexylem/jarvis, affaan-m/JARVIS.

---

# Round 6

## W. TTS engines with distinct signal

### coqui-ai/TTS (XTTS v2) — code MPL-2.0; **weights = Coqui Public Model License (non-commercial)**
- Streaming inference (<200ms chunked) behind one `/v1/audio/speech` adapter. → `voice/`, `providers/model_gateway.py` · M/med.
- 16-language + cross-language cloning **API shape** (`speaker_wav` + `language_idx`) → reference-clip contract behind a fail-closed consent gate. → `voice/clone.py`, `security/*` · M/high.
- Consented speaker-embedding registry under ownership keys. → `memory/` · S/med.
- *Avoid:* XTTS-v2 weights (CPML poisons commercial use) — keep API patterns only; training stack.

### resemble-ai/chatterbox (MIT — code **and** all weights)
- **Size tiers as `ModelProfile`s** — Nano 110M (CPU) / Turbo 350M (GPU ~75ms) / Multilingual V3 500M; register in `ModelGateway.select()` by capability + health. → `providers/model_gateway.py` · S/low.
- **Emotion exaggeration + paralinguistic tags** (`[laugh]`, `[chuckle]`) via `extra_body` passthrough. → `voice/`, `runtime/protocols/` · S/low.
- **Built-in PerTh watermarking** → log watermark status on BusEvents for provenance/audit. → `runtime/event_bus.py` · S/low.
- 5s zero-shot cloning behind an explicit approval gate; store embedding id in `memory/`. → `voice/`, `security/*` · M/med.
- *Recommended reference local backend* (cleanest licensing of the batch).

### Zyphra/Zonos (v0.1 Apache-2.0 code+weights; ZONOS2 MIT)
- **Fine-grained conditioning dict** (speaking_rate, pitch, max_freq, emotion axes) as a structured `speech_style` object. → `runtime/protocols/`, `voice/` · M/low.
- **Speaker embedding as `.npy` artifact** (not raw audio) → smaller memory footprint. → `memory/` · S/low.
- CPU-capable mid-tier profile between Nano and full GPU. → `providers/model_gateway.py` · S/low.
- *Secondary backend* — richest conditioning; 1.6B v0.1 is heavy for CPU.

### 2noise/ChatTTS (**AGPL-3.0 + CC BY-NC weights — dual poison**)
- OpenAI-compatible `openai_api.ipynb` wire-format **reference only**; prosody/paralinguistic tag grammar; conversational turn-taking tuning. → `voice/` design notes · S/low.
- *Avoid entirely:* AGPL code + non-commercial weights — do not vendor or ship; steal design notes only.

## X. STT / VAD / voice pipelines

### moonshine-ai/moonshine (MIT — streaming/English; some legacy non-English models = Moonshine Community License)
- **TinyVadCNN + moving-average segmenter** (32ms hop) producing segment bounds without storing audio; front-align/energy-centroid to avoid clipping. → `voice/` · M/low.
- **Streaming ASR pipeline** (frontend→VAD→segment→STT) with separate sessions/state + speculative token verification. → `voice/`, `providers/model_gateway.py` · M/low.
- **OpenAI-compatible surface** with chunked `add_audio` + `update_interval` for live partials; word timestamps. → `runtime/protocols/` · M/low.
- *Avoid:* legacy Community-licensed non-English non-streaming models; shipping third-party TFLM/ONNX without checksum/scan.

### k2-fsa/OmniVoice (Apache-2.0)
- **Server concurrency model** (ThreadPoolExecutor + asyncio.Semaphore, `MAX_CONCURRENT`, request timeout) for STT/TTS gating. → `voice/`, `runtime/protocols/` · M/med.
- **Streaming TTS** (sentence-split → per-sentence PCM chunks, low TTFA). → `voice/` · M/med.
- OpenAI-compatible `/v1/audio/speech` + voices/profiles CRUD. → `providers/model_gateway.py` · S/low.
- *Avoid:* heavy FlashInfer CUDA kernels; multi-process weight duplication.

### abus-aikorea/voice-pro (GPL-3.0 → ideas only)
- VAD module + audio separation (Demucs/MDX-NET ONNX) as a pre-STT cleanup stage. → `voice/` · M/med.
- Whisper stack (openai/faster-whisper/whisper-timestamped) + ONNX/PyTorch dual runtime abstraction. → `voice/`, `providers/model_gateway.py` · M/med.
- Batch subtitle translation with sentence segmentation (spaCy/lingua) → chunking strategy. → `tools/*` · M/low.
- *Avoid:* GPL-3.0 code if distributed — architectural reference only.

### PaddlePaddle/PaddleSpeech (Apache-2.0)
- **Online streaming ASR** (DeepSpeech2/Conformer with `num_decoding_left_chunks`, stride/window) + **CTC prefix beam search** (beam alpha/beta/cutoff, optional external LM). → `voice/` · M–L/med.
- **WebSocket streaming ASR server** with chunked features + `advance_decoding` endpointing. → `runtime/protocols/` · M/med.
- Modular model-centric CLI (`paddlespeech asr --model ... --decode_method ...`). → `cli/*`, `providers/model_gateway.py` · M/med.
- *Avoid:* PaddlePaddle as a runtime dep in core; training scripts; runtime LM downloads bypassing policy.

## Y. Tool / data / media pipelines

### OpenBB-finance/OpenBB (Apache-2.0) — *backlog listed as `openbq-org/OpenBB`*
- **Entry-point plugin discovery** (`openbb_core_extension` / `_provider_extension` / `_obbject_extension` groups) → `tools/*` registrations loaded only through ToolExecutionService. → `runtime/protocols/` · M/low.
- **TET provider abstraction** (`Fetcher` = QueryParams + Data + `transform_query`/`extract_data`/`transform_data`; ProviderInterface maps model→fetchers) → data-provider abstraction in `core/harness/*`. → `core/harness/*` · M/low.
- **Skills registry** (`develop_extension`, install/list/read) as a direct model for `skills/*`. → `skills/*` · S/low.
- Unified dispatch where Python+REST+MCP share one command runner → single ToolExecutionService boundary. → `tools/*` · M/low.
- *Avoid:* mutable OBBject plugins modifying results outside controlled paths; pulling the full FastAPI/Pydantic stack wholesale.

### jianchang512/pyvideotrans (**GPL-3.0 → ideas only**)
- Deterministic staged batch pipeline (STT→translate→TTS→align→mux) — model each stage as a `tools/*` with `retry_semantics` + BusEvents. → `tools/*`, `runtime/event_bus.py` · M/low.
- Channel/provider adapters with local-only keys; stage input/output contracts validated by the verification gate. → `core/harness/*`, `runtime/protocols/` · M/low.
- *Avoid:* GPL-3.0 integration into core (keep as a separate process/service at most); heavy torch/onnx/CUDA footprint.

### DrewThomasson/ebook2audiobook (Apache-2.0)
- CHAPTER-split batch pipeline (EPUB/MOBI → per-chapter TTS → mux) with progress BusEvents. → `tools/*` · M/low.
- Pluggable TTS provider abstraction with capability flags. → `core/harness/*` · S/low.
- Per-book/chapter state in memory with artifacts as BLOBs (not secrets). → `memory/` · S/low.
- `skills/audiobook_batch` end-to-end workflow. → `skills/*` · S/low.
- *Avoid:* third-party model-license caveats (surface terms via permissions); hardcoding providers.

### krillinai/OpenCreator (Apache-2.0)
- **Skills registry + install** (`SkillsDirectoryProvider`/`SkillProvider`, vendor mapping for Claude/Cursor/Codex/OpenCode/Gemini/Goose) — near-identical to `skills/*`. → `skills/*` · S/low.
- **Tool catalog + transforms** (`PromptsAsTools`/`ResourcesAsTools`, per-session activate/deactivate) → ToolExecutionService catalog + harness activation state. → `core/harness/*` · M/low.
- Creation templates (`template.json` + assets) as reusable skills; media tools emit BusEvents with a post-execution verification gate. → `skills/*`, `tools/*` · M/low.
- *Avoid:* coupling to the Codex CLI environment; heavy media deps mandatory.

## Z. Triage — reviewed, deferred (patterns already captured in Rounds 3–6)

These map onto the voice-engine / agent pattern set already documented; adopting code is not planned, so per-repo license verification is deferred until there is an adoption intent. Listing them keeps the backlog honest rather than re-deriving the same bullets.

| Repo | Category | Triage rationale |
|---|---|---|
| debpalash/VoiceStudio | voice desktop app | Same engine + plugin patterns as `voice/` (Rounds 5–6); UI-bound. |
| CorentinJ/Real-Time-Voice-Cloning | voice cloning | Cloning already covered (consent gate); legacy toolchain. |
| myshell-ai/OpenVoice | voice cloning | Clone + tone-color conversion → same consent-gated clone contract. |
| babysor/MockingBird | voice cloning | Legacy cloning; superseded by consent-gated engines above. |
| ATH-MaaS/Pixelle-Video | media gen pipeline | Same staged-pipeline pattern as pyvideotrans/OpenCreator. |
| nari-labs/dia | TTS dialogue | Multi-speaker dialogue → covered by multi-speaker registry pattern. |
| neonbjb/tortoise-tts | TTS | Slow legacy engine; adds nothing to the engine-adapter design. |
| supertone-oss-archive/supertonic | TTS | On-device tier idea already captured (ONNX tiers). |
| SparkAudio/Spark-TTS | TTS + cloning | Same streaming + consent-gated clone contract. |
| mozilla/TTS | TTS toolkit | Legacy toolkit; engine-adapter pattern already captured. |
| kyutai-labs/pocket-tts | streaming TTS | Streaming chunk protocol already captured (edge-tts/VoxCPM). |
| jianchang512/clone-voice | cloning tool | Consent-gated clone pattern already captured. |
| fishaudio/Bert-VITS2 | TTS training | Training-centric; not adoptable in core. |
| santinic/audiblez | ebook→audio | Same batch pipeline as ebook2audiobook (now covered). |
| netease-youdao/EmotiVoice | TTS emotion | Emotion/conditioning covered by Chatterbox/Zonos. |
| Blaizzy/mlx-audio | Apple-silicon audio | Platform-specific runtime; not portable to the base-URL abstraction. |
| Plachtaa/VALL-E-X | TTS | Legacy; engine-adapter pattern already captured. |
| jaywalnut310/vits | TTS research | Research model; training-centric. |
| jianchang512/ChatTTS-ui | ChatTTS frontend | UI over AGPL/NC engine — avoid on license grounds. |
| hiyouga/LlamaFactory | LLM fine-tuning | Training infra; no product relevance to the agent runtime. |
| rasbt/LLMs-from-scratch | education | Learning material; no code to adopt. |
| microsoft/generative-ai-for-beginners | education | Course repo; pattern docs only (agents course already mined in Round 5). |
| Snailclimb/JavaGuide | education (Java) | No relevance (non-Python, no agent patterns). |
| unslothai/unsloth | LLM fine-tuning | Training/fine-tuning infra; not adopted. |
| career-ops-hq/career-ops | niche web tool | Out of product scope. |
| blogminhquy/javis-os | UI experiment | Idle; cosmetic only; no new patterns. |

### Round 6 cross-cutting

| Idea | Modules | Effort | Risk |
|---|---|---|---|
| Capability enum + `ModelProfile` size/device tiers in ModelGateway | `providers/model_gateway.py` | S | low |
| One `voice/` provider adapter normalizing all TTS/STT to `/v1/audio/speech` | `voice/`, `runtime/protocols/` | M | med |
| Consent-gated clone tool (approval → reference hash → embedding id in memory) | `voice/`, `security/*`, `memory/` | M | low |
| Emotion/prosody structured field (`speech_style` + tag grammar) | `runtime/protocols/`, `voice/` | S | low |
| TTS watermark status surfaced on BusEvents for provenance | `runtime/event_bus.py` | S | low |
| VAD segmenter (hop/energy-centroid) producing bounds without storing audio | `voice/` | M | low |
| Entry-point-style plugin discovery for tools, loaded only via ToolExecutionService | `runtime/protocols/`, `tools/*` | M | low |
| TET data-provider abstraction (`transform_query/extract/transform`) | `core/harness/*` | M | low |
| Staged media pipelines as `tools/*` with per-stage BusEvents + retry semantics | `tools/*`, `runtime/event_bus.py` | M | low |

**License tiers (Round 6):**
| Tier | Repos |
|---|---|
| **Permissive** | chatterbox, Zonos, moonshine (MIT), OmniVoice, PaddleSpeech, OpenBB, ebook2audiobook, OpenCreator |
| **Copyleft** | coqui-ai/TTS (MPL-2.0 code), voice-pro (GPL-3.0), pyvideotrans (GPL-3.0) |
| **Weight-restricted / Non-standard** | Coqui XTTS weights (CPML, non-commercial), moonshine legacy non-English (Community License) |
| **Dual poison (avoid)** | ChatTTS (AGPL-3.0 + CC BY-NC) |

---

# Round 7 — Morluto contribution graph (agent infra, evidence tooling, DSH/Cordis ecosystem)

Source: Morluto's project/contribution list (own repos + upstream contributions). Licenses verified from repo roots. The six `morluto/*` agent tools are DSH-ecosystem plugins (topics `dsh-plugin`, `cordis`) and ship as MCP servers — if adopted they enter **only** through the MCP catalog behind ToolExecutionService (single tool boundary, no side doors). Nothing is vendored; patterns + optional MCP registration only.

## AA. Code intelligence & contribution research (morluto/*)

### morluto/leantoken (MIT OR Apache-2.0, Rust; MCP server)
- **Token-budgeted code retrieval** — "find the code that matters, keep the context window lean": tree-sitter indexing + token counting as first-class outputs, not vibes. → `core/harness/*` (context assembly), `tools/*` · M/low.
- **In-tree benchmarks for retrieval quality** — eval harness for context selection, replayable. → `benchmark/` · S/low.
- **Multi-host packaging** (`.agents/`, `.codex/`, AGENTS.md) — one tool, many agent hosts → `skills/*` packaging pattern · S/low.
- *Avoid:* Rust runtime dep in core; register via MCP if adopted.

### morluto/gitcontribute (MIT, Go; MCP server)
- **Pre-patch contribution research** — repo guidance, related work, code context, and validation *before* writing a patch; a deterministic pre-execution checklist. → `core/agent/verification.py` (pre-execution evidence), `skills/*` · M/low.
- Research receipts (guidance files read, related PRs/issues, validation run) attach to the post-execution gate context. → `core/agent/loop.py` · S/low.

### morluto/smokinggun (MIT, TypeScript; emits SARIF)
- **Optimization evidence before acting** — complexity hotspots + "is this change worth making", machine-readable (SARIF). → `security/code_scan.py` (SARIF interchange), `core/agent/verification.py` · M/low.
- Deterministic hotspot ranking surfaced as a BusEvent observation. → `runtime/event_bus.py` · S/low.

### morluto/flameox (MIT, Python; MCP server; local-first)
- **Runtime evidence that traces hotspots** (app/native/GPU/inference) with performance-regression detection. → `benchmark/` (orbit timing gate), `core/agent/verification.py` · M/med.
- **Evidence receipts**: tie a proposed optimization to measured before/after deltas. → `core/agent/verification.py` · S/low.

### morluto/jacobian (MIT, Python; MCP server; SymPy/flint/CyPari/pplpy/NetworkX/Z3 — no Lean4)
- **"Compute exactly, then independently check what a result proves"** — the math-domain form of JARVIS's verification invariant (checker != producer). → `core/agent/verification.py`, `tools/*` · M/low.
- Example/counterexample search as a tool contract: structured result + proof artifact in ToolResult metadata. → `core/agent/tool_service.py` · S/low.
- *Avoid:* pulling its heavy exact-arithmetic wheels (CyPari/pplpy/flint) into core deps; register as optional MCP capability.

### morluto/rea (MIT, TypeScript; agent-skills pack)
- **Domain skill-pack packaging across hosts** (Claude Code, Codex, Cursor, OpenCode, Gemini CLI…) — mirrors and extends the `skills/*` cross-host pattern. → `skills/*` · S/low.
- Binary/app reverse engineering is a HIGH-risk capability class: sandbox + explicit approval, never default-on. → `core/agent/permissions.py`, `security/*` · S/low.

### morluto/generate-social-preview — **no license file (patterns only)**
- Skill grounded in repo-local assets/examples (never generic templates) → `skills/*` skill-authoring pattern · S/low.

### morluto/internalcot (license unverified — treat as no-reuse)
- Chain-of-thought surfacing for hosts: observation value vs model-privacy trade-off; capture as a design note only.

## AB. Harness improvement, evaluation & peer platforms

### Human-Agent-Society/reef (Apache-2.0)
- **Receipts across overlapping runs** — provenance that survives concurrent/overlapping execution → `memory/*` · M/low.
- **Constant-time commit-history bookkeeping** (cached history) → `memory/store.py` · M/low.
- **Record-conflict detection after compaction** → `memory/keyspace.py` · S/low.
- **Retry-safe settlement** — rollback/commit idempotent under retries → `core/agent/tool_service.py` (retry semantics) · M/med.

### patrick-toulme/harnessgym (Apache-2.0)
- **Harness-improvement loop**: run the agent on a hard task → generate the missing reusable tooling → qualify it → replay fresh sessions with it activated. → `core/harness/*`, `skills/*` · M/med.
- **Artifact quarantine + result-parsing validation** for benchmark correctness → `security/code_scan.py`, `benchmark/` · S/low.
- **Activation reporting** — prove generated tooling actually loaded (no silent no-op). → `core/agent/verification.py` · S/low.

### harbor-framework/harbor (Apache-2.0; Terminal-Bench lineage)
- **create-task / publish skills** for agent evaluation — task packaging + publishing as host-loadable skills → `skills/*`, `benchmark/` · S/low.

### UsefulSoftwareCo/executor (MIT)
- **One MCP catalog with per-tool policies** — reference design for a single tool catalog where auth/retry/approval live per tool — the product problem JARVIS's single boundary + declarative metadata already solves; steal the policy-table shape. → `tools/classification.py`, `core/agent/tool_service.py` · S/low.

### QwenLM/qwen-code (Apache-2.0)
- **MCP read-only auto-approval trust enforcement** — read-only tools may auto-approve, but trust must be verified, not assumed → MCP permission matrix. → `runtime/protocols/`, `core/agent/permissions.py` · M/low.
- **Restrictive permission path canonicalization** — canonicalize (symlinks, `..`) before allow/deny checks. → `core/agent/permissions.py`, `security/*` · S/low.
- Config validation for fractional session/tool-call limits; malformed tool-result display resilience. → `core/agent/tool_service.py` · S/low.

### NousResearch/hermes-agent (MIT)
- **Cron scheduler double-execution prevention** — fire-once guarantees across restart/overlap → `runtime/*` scheduler · S/low.
- **Credential-pool failover + provider auto-detection** — deterministic rotation/failover → `providers/model_gateway.py` · M/med.

### openclaw/openclaw (MIT)
- **Channel identity canonicalization** (phone/e-mail across Signal/iMessage/WhatsApp) → `runtime/protocols/` identity mapping · M/med.
- **Subagent registry resurrection prevention** — a torn-down subagent must not silently reappear → `core/agent/state.py`, `core/locks.py` · S/low.
- **Heartbeat responsiveness under large commitment queues** — queue depth must not starve liveness → `runtime/event_bus.py` · M/low.
- **Transport teardown before gateway shutdown** — drain/close channels first; no write-after-close storms. → `runtime/protocols/` · S/low.

## AC. Context, composition, orchestration

### repoprompt/repoprompt-ce (Apache-2.0)
- **Context-builder model selection** — pick the model per context-building task → `providers/model_gateway.py` `select()` by capability · S/low.
- **Bounded LRU diff caching + diff-chunk reconstruction without repeated array shifts** → `cli/*`, `memory/*` · S/low.
- Replace-all matching with reused full-file indexes (one index, many replacements). → `tools/*` · S/low.

### cordiverse/cordis (MIT) — plugin meta-framework (DSH's substrate)
- **Symbol/prototype-named event dispatch + ordered concurrent async interval reads** — event identity beyond strings; delivery ordering guarantees. → `runtime/event_bus.py` subscriber identity/ordering · M/med.
- **Spatiotemporal composability** — plugin context lifecycle (load/scope/dispose) as a first-class contract → `runtime/protocols/` plugin discovery · M/med.

### scaleapi/agentenv-framework (Apache-2.0)
- **Avoid quadratic response-history diffs**; reduce implicit scheduler graphs; batch Explorer reads; index latest-version lookups. → `core/harness/*`, `memory/store.py` · M/med.
- **Journal keys** for environment state → `memory/store.py` · S/low.

### kvcache-ai/AgentENV (MIT)
- Distributed agent-environment execution (sandboxed envs at scale) — isolation-posture reference → `security/*` sandbox · S/low.
- OverlayBD truncated-mapped-read rejection: partial reads must fail, never silently corrupt → artifact integrity checks in `memory/store.py` · S/low.

### stablyai/orca (MIT), HKUDS/Vibe-Trading (MIT), openclaw/crabbox (MIT), openclaw/gitcrawl (MIT)
- Orca: fleet-of-agents ADE (parallel-agent orchestration UX); graceful degradation when a helper app is missing (skip feature, never crash onboarding) → `cli/*`, `orbit/*` startup · S/low.
- Vibe-Trading: **CLI resume preserves typed-but-unsubmitted prompt input** (pairs with roadmap #9) → `cli/input.py` · S/low.
- Crabbox: "warm a box, sync the diff, run the suite" — remote execution pattern for agent test runs → CI/`benchmark/` · S/low.
- gitcrawl: guard local stores against stray Git-metadata misclassification → path-classification guard in `memory/store.py` · S/low.

### magpie-lang/magpie (MIT)
- **Fallible JSON parsing in every layer** (FFI/runtime/codegen/analysis/lowering) — decode errors as values, never exceptions that abort a pipeline → `runtime/protocols/`, malformed tool-result handling · M/low.

### garrytan/gstack (MIT), garrytan/gbrain (MIT)
- gstack: role tools as markdown skill bundles (CEO/Designer/EM/Release/Docs/QA — the "23" figure is stale; repo now indexes 57 skills) → `skills/*` role packs · S/low.
- gbrain: persona/identity "brain" for messaging agents; **metric sign correctness** (negative trajectory metrics must not invert the signal) → `memory/*`, `benchmark/` scoring · S/low.

## AD. Triage — reviewed, deferred (outside agent-runtime relevance)

| Repo | Category | Triage rationale |
|---|---|---|
| triton-lang/triton | GPU compiler | Kernel-level; no GPU inference stack in the agent runtime. |
| tile-ai/tilelang | GPU DSL | Same. |
| fla-org/flash-linear-attention | Attention kernels | Model layer, not agent layer. |
| THUDM/slime | RL post-training | Training-side; RL patterns already captured (Rounds 4–5). |
| NVIDIA-NeMo/labs-molt | RL framework | Training-side. |
| Tencent-Hunyuan/UniRL | RL training | Training-side. |
| lucidrains/x-JEPA | JEPA world models | Research architecture; no agent-platform adoption. |
| kvcache-ai/Mooncake | KV-cache serving | Serving infra; no local LLM serving in JARVIS. |
| modelcontextprotocol/typescript-sdk | MCP TS SDK | JARVIS consumes MCP from Python; the CJS packaging fix is not portable. |
| deepseek-ai/awesome-deepseek-agent | integration guides | Docs-only; provider integration already abstracted behind the gateway. |
| QwenLM/qwen-code-docs | docs tooling | Translation pipeline; no runtime relevance. |
| sympy/sympy | CAS | Pattern captured via the jacobian bullets above. |

### Ecosystem note — DSH / Cordis

DSH = **DeepSeek Harness** (`deepseek-ai/deepseek-harness`), an "everything is a plugin" agent harness built on **Cordis** (`cordiverse/cordis`, MIT), a TS meta-framework for spatiotemporal composability. The `dsh` / `dsh-plugin` / `cordis` topics on morluto's repos mark them as DSH-ecosystem plugins; JARVIS already speaks DSH-style commands (Phase C bridge). Any wiring of these tools must go through the MCP catalog behind ToolExecutionService — one boundary, no side doors.

### Round 7 cross-cutting

| Idea | Modules | Effort | Risk |
|---|---|---|---|
| Token-budgeted code retrieval (tree-sitter + counted budgets) | `core/harness/*` | M | low |
| Optimization-evidence receipts (hotspot → delta → gate) | `core/agent/verification.py`, `benchmark/` | M | med |
| Independent-check math tool (exact compute + proof artifact) | `tools/*`, `core/agent/verification.py` | M | low |
| MCP read-only auto-approval trust enforcement | `runtime/protocols/`, `core/agent/permissions.py` | M | low |
| Permission path canonicalization (symlink/`..` bypass) | `core/agent/permissions.py` | S | low |
| Credential-pool failover + provider auto-detection | `providers/model_gateway.py` | M | med |
| Retry-safe settlement + post-compaction conflict detection | `memory/*`, `core/agent/tool_service.py` | M | med |
| Artifact quarantine for untrusted outputs | `security/*`, `benchmark/` | S | low |
| Subagent registry resurrection prevention | `core/agent/state.py` | S | low |
| Linear response-history diffs + batched store reads | `core/harness/*`, `memory/store.py` | M | low |
| Fallible JSON decoding as values across protocol boundaries | `runtime/protocols/` | M | low |
| Heartbeat under commitment queues + teardown ordering | `runtime/event_bus.py`, `runtime/protocols/` | M | med |

**License tiers (Round 7):**
| Tier | Repos |
|---|---|
| **Permissive** | morluto/leantoken (MIT OR Apache-2.0), morluto/jacobian (MIT), morluto/flameox (MIT), morluto/gitcontribute (MIT), morluto/smokinggun (MIT), morluto/rea (MIT), reef (Apache-2.0), harnessgym (Apache-2.0), harbor (Apache-2.0), executor (MIT), qwen-code (Apache-2.0), hermes-agent (MIT), openclaw (MIT), repoprompt-ce (Apache-2.0), cordis (MIT), agentenv-framework (Apache-2.0), AgentENV (MIT), orca (MIT), Vibe-Trading (MIT), crabbox (MIT), gitcrawl (MIT), magpie (MIT), gstack (MIT), gbrain (MIT) |
| **No license (do not reuse code)** | morluto/generate-social-preview, morluto/internalcot (unverified), deepseek-ai/awesome-deepseek-agent |

### Round 7 deep dive — verified mechanics (source-cited)

Deep pass over the highest-value repos; file paths verified against repo HEAD at review time. Nothing executed or vendored.

**morluto/leantoken** (`src/parser/tree_sitter.rs`, `src/storage/schema.rs`, `src/ranking/{candidate,greedy}.rs`, `src/mcp/requests/`) — SQLite index of files/chunks/symbols/symbol_refs/imports with incremental updates; ranking is linear-weighted (exact 1.0 → symbol 0.8 → ref 0.5 → bm25 0.4 → path 0.25; focus 0.35, import 0.25, change 0.2) into a budgeted greedy selection with a deferred set and a relative confidence floor (top score × MIN_RELATIVE_CONTEXT_SCORE); two-level budgets (`token_budget` 3000 default / 32000 max, plus `max_response_tokens`); cross-call dedup via caller `known_hashes` + server `receipt_id` rebased across index generations; `expected_repository_id` staleness check; diff-scoped context (`base_revision`/`changed_paths`). Reported 20.1–37.6% input-token reduction in its own 60-run study (`docs/measurement.md`) — workload-dependent. → `core/harness/*`: two-level budgets + deferral + receipt dedup.

**morluto/jacobian** (`src/jacobian/_execution.py`, `_exact.py`, `docs/reference/testing-strategy.md`) — contextvar request envelope with `TimeoutOwner` (CALLER_DEADLINE/OPERATION_WALL/BACKEND_TIMEOUT); **phase leases** reserve delivery (`0.02 + bytes/20M`) + teardown (`0.02 + work/10M`) out of the wall deadline before the backend gets its deadline; `OperationWorkLedger` charges deterministic work units; `BackendFailureReason` (INITIALIZATION/STARTUP/ABNORMAL_EXIT/MALFORMED_RESPONSE/INVALID_OUTPUT) + stages (REQUEST_PARSING/OPERATION_EXECUTION/RESULT_PROJECTION). `_exact.py`: `ExactInteger` (32,768-digit bound, canonical decimal strings on the wire), `CanonicalRational` (reduced, positive denominator, forged-repr rejection), `sha256:[0-9a-f]{64}` digests. Doctrine: a verifier counts only if it re-checks the claimed relation **by a different route**; witness/certificate fields must be absent on non-success; timeout/cancel/UNKNOWN is never a positive conclusion; assert stable error codes, not messages. → `tool_service.py` timeout attribution + `verification.py` verifier-independence rules.

**morluto/flameox** (`src/flameox/providers/contracts.py`, `benchmark_comparison.py`, `evidence_models.py`, `docs/investigations.md`) — `ProviderAnalysis{blocks, rows_observed, complete, limitations}` + `ProviderFailure{code, retryable, details, remediation}`; canonical projection (ints > 2^53−1 → strings, NaN/±∞ → strings, bad UTF → DECODE_FAILURE). Deterministic `compare_series`: identity intersection, pooled means, ratio vs baseline, unmatched reported; "ratios do not establish causal improvement". Investigations: hypothesis → discriminating experiment → supported/refuted/**inconclusive**. → ToolResult coverage/limitations shape; RECOVERING context with remediation.

**morluto/gitcontribute** (`internal/radar/radar.go`, `internal/relatedwork/references.go`, `internal/repositorycontext/policy.go`) — fixed-weight issue ranking into `Candidate{positive_signals, risks, blockers, unknowns}`, each `{code, summary, weight, source_url}`; **eligibility (ready_to_code/needs_diagnosis/needs_coordination/blocked) is separate from score and overrides sorting**; missing evidence penalizes nothing — emits `Unknown{code, summary, remediation-command}` + 4-facet confidence; every scan cap becomes an explicit `*_capped` unknown. Typed related-work relations (`claims_to_close`, `superseded_by`, `depends_on`, `blocks`, …); repo policy probed incl. AI_POLICY.md variants; maintainer-stance classification with 90-day active window; hard brief caps (50 hints/100 events/5 terms); fetched source treated as data, never instructions. → verification failure-context shape + pre-execution evidence checklist.

**morluto/smokinggun** (`src/scanners/*`, `src/investigations/store.ts`) — "complexity" = loop-nesting findings (tree-sitter; flow-sensitive collection-kind inference: list/tuple→linear, set/dict→indexed), not cyclomatic; TS checker isolated in a 768MB-capped worker with zod-strict results and complete/partial/unavailable states. `FindingV2`: content-addressed id (sha256(path+line+rule+text), truncated), `claimClass: theoretical-estimate`, `status: unvalidated`. Investigation store = immutable state machine (scanned → context-resolved → measurement-planned → baseline-measured → candidate-compared → behavior-validated) with digest/parentDigest chaining; promotion requires both sides binding shared inputs/executable/environment/behavior. → claim tri-state (estimate vs measured) + promotion gate in verification.

**morluto/rea** (`rea doctor/setup --dry-run --json`, `.agents/skills/*`) — skill install never registers the server; doctor is strictly read-only; setup returns a plan; writes are transactional (.rea.backup + sha256 recovery copy, atomic replace, verify-after-write, symlink refusal); registrations pin exact versions; pre-flight prerequisite checks before spawning children; **leases**: one session owns a target, competing sessions receive the owner's run ID. Ghidra surface: 26 read-only ops. → plan→approve→atomic-apply pattern for setup flows; lease mechanics validate RESOURCE_LOCKED. *Do not copy the delegated-consent posture* (JARVIS owns consent, fail closed).

**morluto/generate-social-preview** (no license — patterns only) — `skills/<name>/{SKILL.md, agents/<host>.yaml, assets/, references/, scripts/}` + `.claude-plugin/plugin.json`/`.codex-plugin/plugin.json` host shims advertising capabilities; helper script refuses overwrite; reports "not generated" over fabricating success. → `skills/` packaging convention.

**qwen-code** (`packages/core/src/tools/mcp-tool.ts`, `docs/design/mcp-safe-replay.md`, PR #6923) — MCP default permission is `allow` only when `trust === true` AND `isTrustedFolder()` (two-key trust); replay gated by `canSafelyReplay()` — annotations required, `readOnlyHint` voided by `destructiveHint:true`/`idempotentHint:false`, ≤3 reconnects, a one-shot invocation guard disables replay entirely (one approval = one attempt), unknown-outcome calls fail with "verify before retry". Dead sessions detected structurally (404 / `-32001`). PR #6923: **restrictive (deny/ask) rules match raw spelling + canonical destination** (symlinks followed, dangling resolved, nearest-existing-ancestor realpath), while **allow rules stay lexical-only** — asymmetric by design. → `permissions.py` two-key trust + asymmetric canonicalization; `tool_service.py` unsafe-replay failure class.

**executor** (`packages/core/sdk/src/policies.ts`, `apps/docs/mcp-proxy.mdx`) — `ToolPolicy{owner, pattern, action ∈ approve|require_approval|block, position}`; `position` is a fractional-indexing key (lexicographic = precedence, no renumbering); each owner contributes its first match, final verdict is **most restrictive wins — never widen**; credentials live at the proxy (agents never hold upstream keys); approvals are resumable paused executions (`GET …/executions/:eid`, `POST …/resume` recording the decision). → policy vocabulary + never-widen composition; approvals as WAITING_* states.

**openclaw** (PR #105793; `src/infra/heartbeat-*.ts`, `src/gateway/server-close.ts`) — runtime reads SQLite only; `doctor --fix` retires stale `subagents/runs.json` under the maintenance lock with a **byte-bound discard receipt** (never imports; file-era in-flight runs deliberately dropped). Heartbeat: skip-don't-queue with named reasons (`HEARTBEAT_SKIP_*`, `CRON_IN_PROGRESS`, `PREEMPTED`), skipped while the main command lane is busy, retried after idle grace. Commitments in SQLite with dedupe-keyed due indexes; uncertain outcomes reported, never resent. Shutdown: drain → websocket force window → wait for admitted commits past grace; ingress ack gated on durable queue admission. Identity: normalized phone/email keys; aliases can deliver but cannot prove identity; conflicting hints fail closed. → `state.py`/`memory/*` retirement receipts; `runtime/kernel.py` teardown ordering.

**reef** (`reef/core/records_types.py`, `reef/storage/{records,sql_records,commit_log}.py`, `reef/scenario/committer.py`) — receipts: record ids quoted back by clients (`x-reef-agent-record-id`), `ConsumptionReceipt{receipt_id, consumed_ids, metadata, recorded_at}`; retry with same id + canonicalized content (ignoring `created_at`) returns the existing record, mismatch raises `RecordConflict`; consumption idempotent but rejects changed metadata. `CommitLog` caches records + `{step: record}` + a file signature `(st_dev, st_ino, st_size, st_mtime_ns)` → O(1) `stat()` validation; its own append is recognized as an append-only extension and the cache is mutated in place (no reparse). Writers serialize via `flock`. Post-compaction: evicted bodies persist `content_sha256` into the retry-hash table, so retried ids still validate (conflict detection after compaction). Settlement: identical commit at an existing step = no-op; torn tail truncated; step fencing (`expected_step+1`); `recorded_retry`/`settle_sibling_record` re-settle durable-but-unacked commits without re-appending. → `memory/store.py` hash tombstones; tool replay semantics.

**harnessgym** (`src/harnessgym/{orchestrator,qualification,registry}.py`) — generated artifacts live in `.harnessgym/` (8 kinds) inventoried by `registry.json`; qualification: clean template snapshot → attempt workspace → copy **only** the reusable bundle → activate + self-test; on failure a bounded repair prompt, then `quarantine_artifacts` stamps metadata and the artifact is hidden from prompts and never injected (files kept as evidence). `activation.json`: per-server smoke (initialize + tools/list), self_test, tool inventory, `active` bool + run-level gate; generated servers wrapped by a telemetry proxy logging every `tools/call`. Result parsing strict: whole-stdout `json.loads` returning a dict only, malformed telemetry lines dropped. → skill/MCP admission gate + activation proof in verification.

**hermes-agent** (`agent/credential_pool.py`, `agent/error_classifier.py`, `cron/jobs.py`) — pool under RLock with strategies fill_first/round_robin/least_used/random; per-entry counters, cooldowns, DEAD status, leases; `FailoverReason` classification (402/quota → rotate now; 429 → retry once then rotate; model-scoped failures → model cooldown only); `resolve_runtime_pool_key(provider, base_url)` matches by identity then endpoint; unmatched-rotation bounded to one lap with a no-recovery guard for a just-marked entry. Cron: `claim_job_for_fire` fire-claim `{at, by}` under file lock (TTL 300s); `next_run_at` advanced **before** dispatch (at-most-once) + a durable pending slot for one crash recovery; completed-occurrence dedupe; 60s clock-skew tolerance. → `model_gateway.py` failover taxonomy + rotation guards.

**repoprompt-ce** (`Sources/.../LRUCache.swift`, `GitDiffEngine.swift`, `DiffApplicator.swift`, `ApplyEditsEngine.swift`) — context-builder model fallback prefers whole-file models (simpleWhole → mediumWhole → highWhole), deliberately unlike the compose model's diff-format preference. Diff cache: dict + doubly-linked list, `setReturningEvictedEntry`, dual cap (32 entries AND 64MB), admit-by-bytes with LRU eviction loop, oversized rejected outright. Diff apply/revert: single forward pass with a `contentIndex` cursor (no insert/removeFirst shifts), symmetric revert. Replace-all: count via `ranges(of:)`, refuse repeated searches within one batch, build the dual-key line index once and reuse per occurrence. → bounded caches + O(n) diff/apply for edit tools.

**cordis** (`packages/core/src/events.ts`, `fiber.ts`, `reflect.ts`) — event keys are string|symbol (`Symbol.for('cordis.*')` internals); five dispatch modes, one per event as a documented contract: `emit` (sync, registration order), `parallel` (registration-order launch, `allSettled`, AggregateError), `serial` (sequential, stops at first non-null), `bail` (sync same), `waterfall` (middleware `next()` callable once, no-call = short-circuit). Fibers PENDING/LOADING/ACTIVE/FAILED/DISPOSED/UNLOADING; `inject` deps tracked by provider-uid epoch → auto-reload on re-registration; every registration returns a disposer via `ctx.effect()`, disposers run LIFO, dependents unload before provider disposal; `ctx.isolate()` for scoped overrides. → `event_bus.py` explicit per-event dispatch contracts; plugin teardown ordering in `runtime/kernel.py`.

**gbrain** (`docs/GBRAIN_RECOMMENDED_SCHEMA.md`, `src/core/trajectory.ts`, `docs/guides/scaling-skills.md`) — markdown+YAML pages in MECE dirs with resolver READMEs (RESOLVER.md read before page creation); each page has compiled truth + append-only dated timeline; four primitives: entity registry / immutable event ledger / fact store (contradictions are data) / relationship graph; `.raw/` sidecars replaced, not appended. Trajectory math: `delta = (new − old)/|old|` so negative metrics don't invert improvement/regression; fires at `delta ≤ −0.10`; skips `old === 0`. Three-tier skill loading (always / resolver-routed / dormant). → `memory/*` schema discipline + signed-metric regression rule.

**gstack** (`docs/skills.md`, `scripts/gen-skill-docs.ts`, `gstack/llms.txt`) — one directory per skill with `SKILL.md` (+ checklists, `specialists/*.md` incl. 8 reviewer checklists); generator renders per-host copies; auto-generated `llms.txt` index (repo now indexes 57 skills). → `skills/*` role bundles + generated per-host indexes.

**Vibe-Trading** (`agent/cli/main.py`, PR #448 by morluto) — resume prompt classifies input tri-state {resume, new, pending_input}: non-answer text becomes the first turn instead of being dropped; covered by parametrized tests. → `cli/*` resume flow · S/low.

**Round 6 index (12 deep + 26 triaged):** coqui-ai/TTS, chatterbox, Zonos, ChatTTS, moonshine, OmniVoice, voice-pro, PaddleSpeech, OpenBB, pyvideotrans, ebook2audiobook, OpenCreator — plus triage table above.
