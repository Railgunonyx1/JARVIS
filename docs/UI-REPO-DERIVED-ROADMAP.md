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
| casey/just | Readable task runner → JARVIS "routines" file format (justfile-like) | NEXT |
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
| python-openxml/python-docx | Agent tool: report generation (.docx) | NEXT |
| qax-os/excelize (Go) | Excel output for agents (or use openpyxl) | REF |
| dream-num/univer | Embeddable spreadsheet component for data pages | LATER |

## Data / CLI toolbox
| Repo | Use for JARVIS | Status |
|---|---|---|
| jqlang/jq + mikefarah/yq | → JSON/YAML query in orbit://tools (dot-path shipped; jq-syntax later) | DONE (base) |
| johnkerl/miller | CSV/TSV stats tool for agents | LATER |
| dathere/qsv + csvkit + saulpw/visidata | CSV toolkit → agent data tools + tools page CSV viewer | LATER |
| tobymao/sqlglot + sqlfluff | SQL transpile/lint → agent SQL helper | REF |
| dbcli/pgcli/mycli + tconbeer/harlequin | Terminal SQL UX for JARVIS console | REF |
| pola-rs/polars | Fast local DataFrames for agent analysis tools | NEXT |

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
| rclone/rclone | One backend for 70+ storages → JARVIS backup/download targets | NEXT |
| restic/kopia/borg/duplicati | Encrypted snapshot backups of workspace | LATER |
| syncthing | P2P sync for multi-device JARVIS | LATER |
| localsend, schollz/croc | Quick transfer actions from downloads page | LATER |
| jhspetersson/fselect, wagoodman/dive | SQL-over-files, image inspection tools | REF |

## Internal tools / no-code data
| Repo | Use for JARVIS | Status |
|---|---|---|
| appsmith, ToolJet, budibase | Admin-panel patterns → JARVIS dashboards | REF |
| nocodb, baserow, teable, grist, saltcorn, nocobase, apitable | Grid-over-SQL UI for memory/tasks pages | LATER |
| hoppscotch, bruno, Kong/insomnia | API-client page (bruno's file-based collections fit JARVIS) | NEXT |
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

## Still NEXT (highest value remaining)
- **rclone remotes** as download/backup targets in the downloads page
- **maxun-style recorder**: record a browser workflow into a replayable routine
- **just-style routines file**: declarative JARVIS routines (casey/just)
- **bruno-style API collections**: file-based API request runner page
- **polars-backed data tools**: fast CSV/DataFrame analysis for research agents
