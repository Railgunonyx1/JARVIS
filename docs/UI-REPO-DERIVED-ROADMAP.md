# JARVIS × GitHub Repo Mine — Full Sweep

Every repo from the 2026-09 list, mapped to a concrete JARVIS improvement.
Status legend: **DONE** (shipped in this pass) · **NEXT** (high-value, small) ·
**LATER** (valuable, bigger) · **REF** (design inspiration only).

## Workflow & orchestration
| Repo | Use for JARVIS | Status |
|---|---|---|
| n8n-io/n8n | Integration workflow library: node catalog informs JARVIS skill manifests (which connectors users expect) | LATER |
| activepieces/activepieces | Piece/connector UX: per-connector auth cards in JARVIS permissions | LATER |
| windmill-labs/windmill | Scripts→UI: JARVIS companion tasks could expose generated forms — matches tools page direction | NEXT |
| kestra-io/kestra | Declarative YAML task graphs → JARVIS task manifests (tasksPage already renders rows) | LATER |
| huginn/huginn | Watch-then-act agents → watch.rule/watch.run chaining page.watch → notify | DONE (watch rules) |
| automatisch/automatisch | Zapier-style trigger/action pairs for JARVIS recipes | LATER |
| PrefectHQ/prefect | Retry/observability semantics for companion tasks | NEXT (semantics only) |
| dagster-io/dagster | Asset-oriented model → JARVIS research artifacts lineage | LATER |
| apache/airflow | Scheduling vocabulary; cron fields for recurring tasks | LATER |
| temporalio/temporal | Durable execution: agent tasks must survive restarts (kernel side) | LATER |
| conductor-oss/conductor | Event-driven worker protocol → DSH task distribution | REF |
| triggerdotdev/trigger.dev | Background job UX: run history + logs view in tasksPage | NEXT |
| inngest/inngest | Durable functions triggered by events → JARVIS event bus | REF |
| xuxueli/xxl-job | Cron console patterns for recurring JARVIS jobs | REF |

## File watchers & runners
| Repo | Use for JARVIS | Status |
|---|---|---|
| casey/just | Readable task runner → JARVIS "routines" file format (justfile-like) | DONE (routine.add/list/remove/run) |
| watchexec/watchexec | File-change triggers for dev workflows in JARVIS terminal | LATER |
| eradman/entr | Minimal change-trigger → same | REF |

## Browser automation
| Repo | Use for JARVIS | Status |
|---|---|---|
| microsoft/playwright | Already the jbrowser backend | DONE (existing) |
| puppeteer/puppeteer | CDP reference for orbit/cdp.py fixes | REF |
| webdriverio/webdriverio | Wait/assertion semantics → jbrowser tool waits | DONE (browser.wait tool) |
| seleniumbase/SeleniumBase | Sane-default wrapping → jbrowser defaults | REF |
| Kaliiiiiiiiii-Vinyzu/patchright (+python) | Hardened Playwright build for stubborn sites → alternate jbrowser backend flag | LATER |
| autoscrape-Labs/pydoll | WebDriver-less CDP driving — validates orbit/cdp.py approach | REF |
| getmaxun/maxun | Record-and-replay → JARVIS "show me how" workflow recorder | LATER |
| lightpanda-io/browser | Headless-for-automation target for low-RAM mode | LATER |
| alirezamika/autoscraper | Learn-scraping-from-example → JARVIS extract tool upgrade | NEXT |
| MechanicalSoup/MechanicalSoup | Form-fill without browser → lightweight agent fallback | REF |
| dgtlmoon/changedetection.io | Page-watch with diff notifications → orbit://watch page | DONE (page.watch tool + orbit://watch UI) |

## Documents & OCR
| Repo | Use for JARVIS | Status |
|---|---|---|
| py-pdf/pypdf | Agent tool: pdf.split/merge/extract | DONE (pdf.extract_text/split/merge) |
| jsvine/pdfplumber | Table extraction tool for research agents | DONE (pdf.extract_tables) |
| ocrmypdf/OCRmyPDF + tesseract | Agent tool: searchable PDFs from scans | LATER |
| tesseract-ocr/tesseract (+js) | OCR backend for screenshot reading (vision-agent) | LATER |
| PaddlePaddle/PaddleOCR | Table-heavy document parsing | LATER |
| PDFMathTranslate | Preserve-layout translation tool | REF |
| opendataloader-pdf | Accessible PDF parsing | REF |
| paperless-ngx/paperless-ngx | Self-hosted document memory: JARVIS file > paperless export | LATER |
| python-openxml/python-docx | Agent tool: report generation (.docx) | DONE (doc.report) |
| qax-os/excelize (Go) | Excel output for agents (or use openpyxl) | REF |
| dream-num/univer | Embeddable spreadsheet component for data pages | LATER |

## Data / CLI toolbox
| Repo | Use for JARVIS | Status |
|---|---|---|
| jqlang/jq + mikefarah/yq | → JSON/YAML query in orbit://tools (dot-path shipped; jq-syntax later) | DONE (base) |
| johnkerl/miller | CSV/TSV stats tool for agents | DONE (data.stats) |
| dathere/qsv + csvkit + saulpw/visidata | CSV toolkit → agent data tools + tools page CSV viewer | DONE (data.query/convert; UI viewer LATER) |
| tobymao/sqlglot + sqlfluff | SQL transpile/lint → agent SQL helper | REF |
| dbcli/pgcli/mycli + tconbeer/harlequin | Terminal SQL UX for JARVIS console | REF |
| pola-rs/polars | Fast local DataFrames for agent analysis tools | DONE (pandas-backed data.stats/query/convert; polars swap LATER) |

## Modern CLI replacements (bundle into JARVIS terminal defaults)
| Repo | Status |
|---|---|
| BurntSushi/ripgrep, sharkdp/fd, sharkdp/bat, eza, zoxide, fzf, atuin, gum, glow, delta, hyperfine, tldr/tealdeer, jless, yazi, dua-cli, nnn, superfile, fq | Ship as the default PATH for JARVIS terminal sessions (winget list) | NEXT |

## Terminal & multiplexing
| Repo | Use for JARVIS | Status |
|---|---|---|
| tmux/zellij | Session-surviving terminal tabs → JARVIS terminal persistence | LATER |
| ohmyzsh, fish, starship, direnv, mise | Default shell ergonomics for the JARVIS terminal | REF |
| kitty, alacritty, tabby | Terminal renderer inspiration | REF |

## Desktop & media
| Repo | Use for JARVIS | Status |
|---|---|---|
| flameshot/ShareX | Annotated screenshot → JARVIS vision-agent capture flow | NEXT |
| Genymobile/scrcpy | Android control tool (device automation skill) | LATER |
| obsproject/obs-studio, mpv, mifi/lossless-cut | Recording/trimming tools for media agents | LATER |

## Files & sync
| Repo | Use for JARVIS | Status |
|---|---|---|
| rclone/rclone | One backend for 70+ storages → JARVIS backup/download targets | DONE (remote.status/transfer via secure executor; sync is dry-run+confirm gated) |
| restic/kopia/borg/duplicati | Encrypted snapshot backups of workspace | LATER |
| syncthing | P2P sync for multi-device JARVIS | LATER |
| localsend, schollz/croc | Quick transfer actions from downloads page | LATER |
| jhspetersson/fselect, wagoodman/dive | SQL-over-files, image inspection tools | REF |

## Internal tools / no-code data
| Repo | Use for JARVIS | Status |
|---|---|---|
| appsmith, ToolJet, budibase | Admin-panel patterns → JARVIS dashboards | REF |
| nocodb, baserow, teable, grist, saltcorn, nocobase, apitable | Grid-over-SQL UI for memory/tasks pages | LATER |
| hoppscotch, bruno, Kong/insomnia | API-client page (bruno's file-based collections fit JARVIS) | DONE (api.parse/api.run — native .bru parser, no npm dep; UI page LATER) |
| CorentinTh/it-tools | → orbit://tools (JSON/Base64/URL/hash/UUID/timestamps) | DONE |

## Notes & knowledge
| Repo | Use for JARVIS | Status |
|---|---|---|
| outline, docmost, AFFiNE, appflowy | Team wiki sync targets for JARVIS memory export | LATER |
| TriliumNext/Trilium, Logseq, siyuan, silverbullet, zk | Scriptable knowledge graphs → memory page integrations | LATER |
| joplin, memos, marktext | Lightweight note targets | REF |

## Monitoring & alerts
| Repo | Use for JARVIS | Status |
|---|---|---|
| Louislam/uptime-kuma | → status footer + diagnostics service health (kernel/bridge probes) | DONE (footer base) |
| healthchecks/healthchecks | Dead-man's switch: alert when scheduled tasks stop | DONE (task.ping/task.alert) |
| binwiederhier/ntfy + gotify + caronc/apprise | Push notifications for long tasks | DONE (notify.send, ntfy+Gotify; apprise later) |
| grafana, prometheus, netdata, glances | Metrics stack for the kernel | LATER |
| gethomepage/homepage | Status dashboard for JARVIS services | REF |

## Secrets & access
| Repo | Use for JARVIS | Status |
|---|---|---|
| Infisical/infisical | Secrets manager for agent credentials (API keys per task) | DONE (secret.ref/secret.status) |
| FiloSottile/age | Encrypted exports | REF |
| bitwarden/vaultwarden/keepassxc | Credential providers for the agent (read-only, approved) | LATER |
| gchq/CyberChef | Multi-step transform recipes → tools page "recipes" | NEXT (concept) |

## Thinking UI
| Repo | Use for JARVIS | Status |
|---|---|---|
| Jakubantalik/thinking-orbs | 9 verb-state orb animations → agent matrix/float/agent-bar | DONE (vanilla port, 8 states) |

## Omarchy / misc
| Repo | Use for JARVIS | Status |
|---|---|---|
| omacom/omarchy | Tiling/layout presets → tiling-ui.js layout gallery | REF |
| microsoft/markitdown | Doc→Markdown export action on pages/downloads | DONE (docs.to_markdown tool) |
| AtomicBot-ai/atomic-agent | Agent scaffolding patterns | REF |
| awesome-selfhosted, awesome-sysadmin | Ongoing index to re-mine quarterly | REF |

## Shipped in pass 2 (repo-mine sweep, this update)
7. **pdf.extract_text / pdf.extract_tables / pdf.split / pdf.merge** — pypdf + pdfplumber agent tools (pypdf, jsvine/pdfplumber)
8. **docs.to_markdown** — docx/html/pdf/ipynb/xlsx/csv/json → Markdown (microsoft/markitdown concept)
9. **page.watch** — arm/check/remove URL watches with line-level diffs, persisted under memory/ (changedetection.io)
10. **orbit://watch** — browser UI page listing armed watches (changedetection.io)
11. **notify.send** — ntfy.sh + Gotify push notifications for long tasks (binwiederhier/ntfy, gotify/server)
12. **browser.wait** — condition waits (selector/text/gone/delay) instead of blind sleeps (webdriverio semantics)

## Shipped this pass (summary)
1. **orbit://tools** — JSON format/minify/query, Base64, URL codec, SHA-256, UUID, timestamps (it-tools/CyberChef/jq concept)
2. **Thinking orbs** — canvas verb-states on the agent matrix, float, agent glyph (thinking-orbs port)
3. **Status footer** — always-on telemetry strip (uptime-kuma/glances concept)
4. **NTP v2** — live UTC clock, greeting, contextual "resume session" card
5. **Settings appearance** — accent/density/motion pickers persisted locally
6. **Sakana Fugu Ultra v2 + Max** — provider added to the model catalogue (OpenAI-compatible, key-gated)

## Shipped in pass 5 (chat continuity + UX depth)
21. **Conversation memory** — per-tab sessions + history sent to the model (the amnesia bug: every message used to arrive as a brand-new session with only the latest text)
22. **Markdown rendering** — XSS-safe bold/italic/code/lists/links in chat (was raw `**asterisks**`)
23. **Persona hardening** — system prompt forbids unsolicited numbered plans / clarify-checklists for small models
24. **/new command** — per-tab fresh conversation (clears thread + rotates session)
25. **Collapse-to-rail mode** — double-click the rail: 48px parked rail with hover flyout panel (true Opera GX FX), persisted
26. **Panel persistence** — the rail reopens the panel you last used
27. **Live watch badge** — polls the bridge every 30s, pulses when a watch fires

## Shipped in pass 4 (UI v2.1 — Opera GX sidebar + clash fixes)
16. **Rail redesign** — brand glyph, 38px pill targets, accent-notch active state (replaces the clashing paper-solid inversion from the F1 layer), watch badge
17. **New sidebar panels** — Bookmarks / History / Downloads / Watches / Flow (clock + session telemetry + autosaving note + shortcuts): the "middle of the page" moved into the rail, Opera GX-style, while the full orbit:// pages remain for power use
18. **Clash fixes** — status footer no longer slides under the sidebar (`:has()`-aware), duplicate `.sidebar::before/::after` decorations (gradient wash vs F1 crosshairs) collapsed to one quiet source of truth
19. **Watches panel + badge** — armed page watches visible in the rail with a changes badge (mirror via localStorage from orbit://watch)
20. **NTP quick tiles wired** — the six new-tab tiles had no click handlers at all (dead buttons); they now navigate (Ctrl+click opens a background tab)

## Shipped in pass 3 (repo-mine deep sweep)
13. **task.ping / task.alert** — healthchecks.io dead-man's switch: recurring tasks check in; task.alert sweeps and pushes (once per silence episode) when one goes quiet (healthchecks/healthchecks)
14. **watch.rule / watch.run** — huginn-style rules binding a watched URL to an action (notify/agent_note) on changed/unchanged/any, persisted + history-capped (huginn/huginn × dgtlmoon/changedetection.io)
15. **secret.ref / secret.status** — Infisical-style credential indirection: register env vars into a local index, resolve to masked handles; values never enter model context; unregistered names are unresolvable (Infisical/infisical)

Also fixed this pass: a **full-suite cross-contamination bug** — a jbrowser test started the sync Playwright driver on the main thread, which parks a running event loop and makes every later `asyncio.run()` in the process fail (the source of the mysterious 90+ failure runs). All 913 tests now pass together.

## Shipped in pass 6 (repo-mine: data, reports, routines)
28. **data.stats / data.query / data.convert** — pandas-backed profiling, filtering and CSV/TSV/JSON/JSONL conversion (johnkerl/miller, dathere/qsv, jqlang/jq)
29. **doc.report** — formatted Word reports with title/headings/bullets (python-openxml/python-docx)
30. **routine.add / list / remove / run** — just-style named step recipes persisted under memory/ (casey/just); routine.run validates against the live registry and returns an ordered plan executed through the normal tool path — no nested execution, no permission bypass

## Shipped in pass 7 (repo-intake applied: rclone + bruno)
31. **remote.status / remote.transfer** — rclone-backed transfers across 70+ providers via the secure executor (no shell strings); sync is destructive-gated: dry_run first, explicit confirm=true to execute (rclone/rclone)
32. **api.parse / api.run** — bruno-style file-based API collections: native .bru parser (meta/get/post/headers/query/body:json), {{var}} interpolation with UPPER_CASE env fallback (secret values never echo into output), SSRF guard on loopback/private targets, executed through the shared pooled HTTP client — no npm/@usebruno/cli dependency (usebruno/bruno)

Imported the **repo_intake_and_plan** skill (README-first repo scanning, documented-command extraction, conservative inference/eval/training classification) — used to drive this pass.

## Still NEXT (highest value remaining)
- **maxun-style recorder**: record a browser workflow into a replayable routine
- **tools-page data viewer**: grid view over data.stats output
- **API collections UI page**: orbit://apis with collection tree + per-request run buttons
- **rclone remotes UI**: downloads-page remote picker backed by remote.status

## Shipped in pass 8 (FatihMakes/Mark-LIV port: ambient initiative)
33. **topic.watch** — concept-level monitoring via news headlines, at most one check/day per topic, md5 title-hash dedup (same headline = silence, not an alert), bounded state, and the Mark-LIV values guardrail: crypto/finance topics are refused outright in any language (FatihMakes/Mark-LIV actions/background_monitor.py)
34. **proactive engine** — silence-gated, cooldown-gated check-in consults with a rotating focus (projects → wellbeing → useful-detail); `/v1/proactive` consult endpoint is event-driven (no polling loop), chat pipeline records activity per turn; the generated prompt enforces 1–2 sentences, no tools, matching the user's language, and treats silence as a valid answer (FatihMakes/Mark-LIV actions/proactive.py, ProactiveEngine 2.0)

Also fixed this pass (orbit3.css UI layer): sidebar panel now honors the real `.hidden` dock contract (JARVIS window wasn't loading when opened), NTP stats strip reflowed compact/wrapped (was half-cut), and the leftover neon flash sources (orbit-v2 cyan accent re-set, F1 dot-grid/LED pulses, polish glow) are suppressed under the calm Orbit-3 palette.

## Shipped in pass 9 (sukeesh/Jarvis port: quick-compute family)
35. **calc.safe** — exact arithmetic via a whitelisted AST validator (numbers, + - * / // % **, parens, sqrt/abs/round/min/max/floor/ceil/log/trig, pi/e/tau) — never eval(), injection-proof, instant (sukeesh/Jarvis calculate/solve plugins)
36. **convert.unit** — length/mass/temperature/data/speed/time/volume/area conversion with alias resolution and category auto-detection (km→mi, GB→MiB, C→F, lb→kg) (sukeesh/Jarvis lengthconv/massconv/tempconv family)
37. **convert.base** — integer conversion between bases 2–36; without a target base, shows binary/octal/decimal/hex side by side (sukeesh/Jarvis binary/hex plugins)
38. **gen.password** — secrets-based generator with per-set guarantees, lookalike exclusion, and an entropy estimate; never stored or logged (sukeesh/Jarvis random password plugin)

All four are permission="system.query" / risk="safe" and fully hermetic — the assistant answers these without a model round-trip or opening a tab. Also back-filled topic.watch into the tool-inventory risk sets (missed in pass 8).

Evaluated and skipped: immo2n/Friday-AI (conscious/deep memory is a greeting table + Q/A sqlite — our memory tools are strictly further along); FRIDAY-inspired multi-agent command centers (orchestration architecture, not an additive tool pass — noted as a future direction).

## Shipped in pass 10 (2026 assistant landscape: AnythingLLM retrieval + Leon-class calendar)
39. **doc.search** — private TF-IDF retrieval over the workspace's OWN documents (.md/.txt/.pdf/.csv/.json/.py and more, pypdf-backed PDF text): ranked chunks with file, score, and snippet so answers quote real text; hidden dirs and node_modules skipped; bounded corpus (400 files / 2 MB each). The zero-dependency slice of AnythingLLM's local-first RAG bet — no embeddings, no model download, and it never invents a match that isn't literal (AnythingLLM/AnythingLLM)
40. **agenda.view** — calendar awareness from iCalendar sources: auto-discovers workspace .ics files, accepts subscribed .ics URLs via the pooled HTTP client (Google/Outlook export format), real RFC 5545 line unfolding, UTC/all-day handling, and simple RRULE expansion (DAILY/WEEKLY/MONTHLY + INTERVAL/COUNT/UNTIL; complex rules degrade to the base occurrence). action=add/list/remove manages the source registry; paths are root-jailed (leon-ai/leon scheduling gap, ICS standard)

Both are risk="safe". Evaluated and noted, not ported: Vellum's process-isolated credential executor (we have secret.ref indirection; a separate executor process is an architecture change, not a tool pass), QwenPaw's Tool Guard approval cards (our permission/risk pipeline covers the same ground), Mirix-style screen-watching agents (privacy posture conflict), OVOS/Mycroft voice stack (voice path already built on Kokoro/SAPI).

Landscape source: Vellum's "8 Best Open-Source Personal AI Assistants in 2026" survey (Sep 2026) — the category's 2026 themes (proactivity, skills architectures, local-first) are all now represented in JARVIS: pass 8 proactive engine, 121-tool registry, doc.search + Jan.ai-style local-first retrieval.

## Shipped in pass 11 (web-memory trio: Miniflux + wallabag + ArchiveBox)
41. **feed.read** — RSS 2.0 / Atom 1.0 / JSON Feed ingestion with reader hygiene: tracking parameters stripped from item URLs (full Miniflux list + any utm_* variant) before they are ever reported, unseen-only filtering with a marked-check seen-file, and tolerance for real-world invalid XML (bare '&' repaired before parsing, as Miniflux does) (miniflux/v2)
42. **reading.list** — wallabag-style save-for-later: stores the article's extracted text (title/paragraph readability pass) alongside metadata under memory/reading/, so "what did that article say" survives page changes or deletion; extraction failures keep the URL saved rather than losing it; saved text is automatically visible to doc.search (wallabag/wallabag)
43. **web.archive** — content-hash-deduplicated page snapshots under memory/archive/<slug>/: a snapshot is stored only when the page actually changed (sha256 of extracted text), history capped at 12 per URL with manifest read/diff by index; snapshot filenames carry the hash so same-second snapshots cannot clobber each other; archived text is visible to doc.search (ArchiveBox/ArchiveBox — text+manifest slice, not the WARC/media engine)

All three are permission="web.search" / risk="low", network via the shared pooled HTTP client. Together with page.watch (diffing) and topic.watch (concept-level news), JARVIS now covers the full web-memory spectrum: watch, read-later, preserve.

## Shipped in pass 12 (daily-driver classics: wttr.in + notmuch + espanso)
44. **weather.get** — key-free current conditions + 1-7 day forecast via open-meteo geocoding/forecast (the chubin/wttr.in no-signup philosophy): plain-language WMO weather codes, place name or lat/lon, through the pooled HTTP client (chubin/wttr.in lineage)
45. **mail.digest** — the notmuch/neomutt headers-only school: read-only IMAP over SSL (EXAMINE — nothing marked as read), UNSEEN headers grouped by sender domain with newest subjects, RFC 2047 decoding, HEADER.FIELDS-only fetch so bodies never leave the server. Off unless JARVIS_IMAP_HOST/USER/PASSWORD (app password) are set in the environment (notmuch/notmuch, neomutt/neomutt)
46. **snippet.store** — espanso-style :trigger → text expansion. The integration point is browser.type: typed text is scanned for :trigger tokens and expanded from memory/snippets.json before entering the page; unknown tokens and prose colons are untouched. Managed via add/list/remove/expand (federico-terzi/espanso)

Also noted for a future pass: ActivityWatch (time tracking — requires a local watcher process, an architecture piece rather than a tool).

Tool count: 124 → 127. weather.get/mail.digest risk="low"/"safe" (read-only observation); snippet.store risk="low" under memory.remember (memory-bookkeeping writer, same class as topic.watch).

## Shipped in pass 13 (local RAG in chat: AnythingLLM's core bet, fully wired)

Passes 10-12 built the private corpus (notes + saved articles + archives all visible to doc.search); pass 13 closes the loop by putting it behind the browser chat itself, so knowledge-seeking turns answer from the user's own documents with zero uploads and zero network.

- **jbrowser-bridge/rag.py** — chat-turn context injection: the latest user turn is gated by a cheap knowledge cue (question word / knowledge verb / document reference + at least 2 content tokens); matching turns get the top TF-IDF passages from doc.search prepended as a LEADING system message, which composes for free with the existing engine contract (trim_messages pins the head, page context stays a trailing system message, the agent engine folds it into the goal). Hard caps: 3 sources, 700-char passages, 3200-char total context. Fail-open everywhere — any retrieval failure degrades to plain chat; JARVIS_RAG=0 disables (AnythingLLM/AnythingLLM — the local-first document RAG slice, stdlib TF-IDF edition)
- **tools/doc_retrieval.py** — two-tier index cache so per-turn retrieval never re-walks the workspace: the TF-IDF index is keyed by a per-file (path, mtime_ns, size) signature (content edits and deletions rebuild immediately), and the candidate file list is cached between 30 s walk epochs (a full rglob over this repo costs ~1.7 s even with node_modules skipped for indexing). Measured steady state: sub-millisecond retrieval, 0.01 ms for gated-out smalltalk, vs 4.6 s cold
- **Background index warm** — the first knowledge-y turn of a bridge process starts a daemon warm thread and waits at most 750 ms: small corpora (tests, small workspaces) get full context on that same turn; big corpora (this one: 3,871 chunks from 384 files) answer that one turn unburdened while the build continues, then serve sub-ms context on every later turn. Total added latency per process: a single bounded stall, and only turns that arrive while the build is in flight pay nothing extra
- **tests/test_rag_chat_pipeline.py** (20 tests) — gate precision, receipt parsing, score floor / one-passage-per-source / char budgets, cache identity semantics, warm-gate timing semantics, fail-open on retrieval errors and missing modules, trim_messages head-pinning, ModelGatewayEngine head+tail composition, and end-to-end POST /v1/chat injection including skip, disable (JARVIS_RAG=0), and failure paths
- Also fixed: tests/test_anythingLLM_doc_retrieval_agenda.py workspace-file test hardcoded September 2026 calendar dates and time-bombed the moment the real date scrolled past them — the fixture ICS is now generated relative to the current date

No new tool names; tool count stays 127. This is the first integration pass: every corpus piece shipped in passes 8-12 (reading.list, web.archive, doc.search) is now answerable directly from browser chat without invoking a tool by hand.
