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

| # | Action | Module | Effort | Risk |
|---|--------|--------|--------|------|
| 1 | A11y-tree-first SoM observation + **change-diff snapshots** (only new/removed `[elN]`) | `jbrowser/page_context.py`, `orbit/cdp.py` | S | low |
| 2 | `include_snapshot` flag on every `orbit.*` tool + covering-element pre-click failure + dialog policy | `orbit/tools.py`, `orbit/controller.py` | M | low |
| 3 | Browser-tool doctrine: reference-over-value, semantic summaries, self-healing errors, pagination, slim tool profiles | `tools/classification.py`, `runtime/protocols/` | S | low |
| 4 | SKILL.md frontmatter + progressive-disclosure loading (name+desc in prompt, body on demand) | `skills/registry.py` | S | low |
| 5 | Skill verification checklists wired into the post-execution gate | `core/agent/verification.py` | M | low |
| 6 | Post-compaction / CONTEXT_OVERFLOW skill re-bootstrap | `core/agent/state.py` | S | low |
| 7 | Reversible tool-output compression (raw kept for the gate) | `core/agent/tool_service.py` | M | med |
| 8 | Provider fallback chain + local-server capability probe + `<provider>/<model>` slugs | `providers/model_gateway.py` | M | med |
| 9 | Multiline input + reverse history search + queue-behind-running-turn | `cli/input.py` | M | low |
| 10 | Theme tokens as data with an ASCII fallback theme | `cli/theme.py` | S | low |
| 11 | Multi-signal (vector + BM25 + entity) fused retrieval + SQLite FTS5 | `memory/store.py`, `tools/doc_retrieval.py` | M | low |
| 12 | Secret placeholders resolved only at the tool boundary, scrubbed from observations | `memory/keyspace.py`, `core/agent/tool_service.py` | M | low |
| 13 | MCP single authenticated entry point mirroring the single tool boundary | `runtime/protocols/` | L | med |
| 14 | UI-visible agent state machine (Thinking/Speaking/Standby) as BusEvents | `core/agent/state.py` | S | low |
| 15 | Wake-word voice state machine over one OpenAI-compatible STT/TTS base URL | `voice/` | M | med |

---

## A. Browser & CDP (Orbit, J-Browser)

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
| **Permissive (code OK, still attribute)** | MIT / Apache-2.0: browser-use, agent-browser, chrome-devtools-mcp, superpowers, agent-skills, pi, OpenHands, ponytail, LocalAI, textual, crawl4ai, microsoft/JARVIS, open-jarvis, jarvis-registry, JarvisHub, LobeHub-code (`browse`), firecrawl-SDK | Ideas **and** reusable snippets allowed with attribution; no wholesale copying of their architecture tests/docs. |
| **AGPL (ideas/API-shape only, never code)** | Skyvern, lightpanda, firecrawl, free-claude-code | Read for patterns. Do **not** copy source, prompts, or configs. |
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
