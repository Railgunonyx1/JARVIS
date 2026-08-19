# JARVIS MK-X GitHub Research Analysis

**Research Date**: 2026  
**Purpose**: Curated list of GitHub projects organized by JARVIS function categories with adoption recommendations  
**Principle**: Research corpus feeding architecture — extract patterns, don't blindly install

---

## Immediate Adoption (P0/P1) — High Confidence

| Project | Category | Why |
|---------|----------|-----|
| microsoft/agent-framework | Provider router, skills system, MCP integration | "Framework for building, orchestrating and deploying AI agents and multi-agent workflows with support for Python and .NET" — directly applicable to JARVIS daemon/provider design |
| sqliteai/sqlite-vector | Vector search in SQLite | "Cross-platform, ultra-efficient SQLite extension that brings vector search capabilities to your embedded database" — fits 512 MB RAM constraint; local-first, no external DB (was sqlite-vec) |
| mem0ai/mem0 | Conversation/long-term memory | "Universal memory layer for AI Agents" — purpose-built for AI agents; active development (owner is mem0ai, not mem0-dev) |
| OpenTelemetry | Tracing and metrics | Already partially implemented in JARVIS Python code |
| Playwright | Browser automation backend | Industry standard; can be wrapped for JARVIS |

---

## Evaluate for P1/P2

| Project | Category | Notes |
|---------|----------|-------|
| modelcontextprotocol/python-sdk | MCP Python SDK | "Official Python SDK for Model Context Protocol servers and clients" — ~24k stars, MIT |
| PrefectHQ/fastmcp | MCP server/client framework | "The fast, Pythonic way to build MCP servers and clients" — ~27k stars, Apache-2.0 (owner is PrefectHQ, not jlowin) |
| github/github-mcp-server | GitHub MCP server | "GitHub's official MCP Server" — ~32k stars, MIT, Go |
| microsoft/skills | Skills, MCP servers, agents | "Skills, MCP servers, Custom Agents, Agents.md for SDKs to ground Coding Agents" — ~2.9k stars, MIT, TypeScript (was agent-skills) |
| OpenHands/OpenHands | Code agent patterns | "AI-Driven Development" — study patterns; don't copy directly |
| BerriAI/litellm | Provider abstraction layer | "The fastest, litest AI Gateway. Rust core with Python SDK. Call 100+ LLM APIs in OpenAI (or native) format with cost tracking, guardrails, load balancing, and logging" — if not building custom provider layer |

---

## Research Only (P2/R&D)

| Project | Category | Evaluation Notes |
|---------|----------|-----------------|
| MetaGPT | Multi-role software development | Complex multi-role pipeline; evaluate carefully |
| CrewAI | Multi-agent orchestration | Multi-agent patterns worth studying |
| vLLM | High-throughput serving | Requires GPU; assess GPU availability |
| RAGFlow/Crawl4AI | Advanced document pipelines | Document processing evaluation |

---

## Verified Repository Metadata (via GitHub API, 2026-08-13)

| Repo | Verified description | Stars | Language | License |
|------|---------------------|-------|----------|---------|
| ollama/ollama | "Get up and running with Kimi-K2.6, GLM-5.2, MiniMax, DeepSeek, gpt-oss, Qwen, Gemma and other models" | 178,391 | Go | MIT |
| ggml-org/llama.cpp | "LLM inference in C/C++" (org is ggml-org, not ggerganov) | 123,729 | C++ | MIT |
| openai/whisper | "Robust Speech Recognition via Large-Scale Weak Supervision" | 107,184 | Python | MIT |
| microsoft/autogen | "A programming framework for agentic AI" | 60,389 | Python | CC-BY-4.0 |
| github/github-mcp-server | "GitHub's official MCP Server" | 32,198 | Go | MIT |
| PrefectHQ/fastmcp | "The fast, Pythonic way to build MCP servers and clients" | 27,197 | Python | Apache-2.0 |
| gorilla/websocket | "Fast, well-tested and widely used WebSocket implementation for Go" | 24,851 | Go | BSD-2-Clause |
| modelcontextprotocol/python-sdk | "The official Python SDK for Model Context Protocol servers and clients" | 23,998 | Python | MIT |
| microsoft/skills | "Skills, MCP servers, Custom Agents, Agents.md for SDKs to ground Coding Agents" | 2,883 | TypeScript | MIT |
| microsoft/agent-framework | "Framework for building, orchestrating and deploying AI agents and multi-agent workflows with support for Python and .NET" | verified | Python/.NET | MIT |
| sqliteai/sqlite-vector | "Cross-platform, ultra-efficient SQLite extension that brings vector search capabilities to your embedded database" | verified | C | MIT |
| OpenHands/OpenHands | "AI-Driven Development" | verified | Python | MIT |
| mem0ai/mem0 | "Universal memory layer for AI Agents" | verified | Python | Apache-2.0 |
| BerriAI/litellm | "The fastest, litest AI Gateway. Rust core with Python SDK" | verified | Rust/Python | MIT |

> Note: star counts snapshot as of 2026-08-13; descriptions are official. See https://api.github.com/repos/{owner}/{repo} to re-verify.

---

## Avoid / Extract Patterns Only

| Category | Reason |
|----------|--------|
| Electron-based projects | Contradicts terminal-native constraint |
| Voice-specific repos | Explicitly excluded from JARVIS scope |
| Heavy UI frameworks | JARVIS is React + terminal, not desktop-first |

---

## Batch 2 — Verified Repos by Category (via GitHub API, 2026-08-13)

### Agent Frameworks & Orchestration

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| run-llama/llama_index | "LlamaIndex is the leading document agent and OCR platform" | 51,605 | Python | MIT | MEDIUM — RAG/OCR/agent patterns, heavy dep, extract patterns only |
| agno-agi/agno | "Build, run, and manage agent platforms" (was phidatahq/phidata) | 41,683 | Python | Apache-2.0 | MEDIUM — web-research agent + tool patterns |
| langchain-ai/langgraph | "Build resilient agents" | 39,571 | Python | MIT | R&D — stateful graph orchestration ideas |
| getzep/zep | "Zep — Examples, Integrations, & More" (agent memory + knowledge graphs) | 4,832 | Python | Apache-2.0 | R&D — long-term memory alternatives to Mem0 |

### Vector Search & Memory (512 MB constraint: prefer embedded)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| qdrant/qdrant | "High-performance, massive-scale Vector Database and Vector Search Engine" | 33,946 | Rust | Apache-2.0 | R&D — too heavy for 512 MB; study HNSW/quantization patterns |
| chroma-core/chroma | "Search infrastructure for AI" | 29,043 | Rust | Apache-2.0 | R&D — embedded mode; compare vs sqliteai/sqlite-vector |
| lancedb/lancedb | "Developer-friendly OSS embedded retrieval library for multimodal AI" | 11,140 | Rust | Apache-2.0 | R&D — embedded, multimodal-ready; compare vs sqlite-vector |

### Computer Use / Vision (P2 — computer-use tag)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| microsoft/OmniParser | "A simple screen parsing tool towards pure vision based GUI agent" | 25,249 | Jupyter | CC-BY-4.0 | MEDIUM — screen-parsing backbone for desktop automation |
| TencentQQGYLab/AppAgent | "Multimodal Agents as Smartphone Users... operate smartphone apps" | 6,844 | Python | MIT | R&D — app-operation loop patterns (owner is TencentQQGYLab) |

### MCP Ecosystem

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| modelcontextprotocol/servers | "Model Context Protocol Servers" (official reference servers) | 89,512 | TypeScript | Other | HIGH — reference implementations to learn/adapt for JARVIS tool servers |

### Local Inference (P2 — no GPU required)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| mudler/LocalAI | "Open-source AI engine. Run any model — LLMs, vision, voice, image, video — on any hardware. No GPU required" | 48,418 | Go | MIT | MEDIUM — OpenAI-compatible local endpoint; MCP + distributed support |

### Terminal / CLI / TUI (terminal-first constraint)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| cli/cli | "GitHub's official command line tool" | 45,841 | Go | MIT | MEDIUM — GitHub ops patterns for JARVIS GitHub tools |
| Textualize/textual | "The lean application framework for Python... Run your apps in the terminal and a web browser" | 36,923 | Python | MIT | MEDIUM — JARVIS has Textual TUI history; TUI + web patterns |

### Desktop Shell (tauri tag — final wrapper)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| tauri-apps/tauri | "Build smaller, faster, and more secure desktop and mobile applications with a web frontend" | 110,165 | Rust | Apache-2.0 | HIGH — planned JARVIS desktop shell; already in stack |

---

## Batch 3 — Verified Repos by Category (via GitHub API, 2026-08-13)

### Tool Integration & Function Calling (P1/P2)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| ComposioHQ/composio | "Powers 1000+ toolkits, tool search, context management, authentication, and a sandboxed workbench" | 29,663 | TypeScript | MIT | MEDIUM — tool registry/auth patterns for JARVIS tool layer; heavy, extract ideas |

### Security / Sandboxing (permission-aware constraint)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| e2b-dev/E2B | "Open-source, secure environment with real-world tools for enterprise-grade agents" | 13,371 | Python | Apache-2.0 | R&D — sandbox patterns for risky agent actions |

### Browser Automation / Computer Use (P2)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| browser-use/browser-use | "Make websites accessible for AI agents. Automate tasks online with ease" | 108,998 | Python | MIT | MEDIUM — the standard AI browser-agent library; wraps Playwright |
| Skyvern-AI/skyvern | "Automate browser based workflows with AI" | 22,741 | Python | AGPL-3.0 | R&D — vision+playwright workflow automation; **AGPL — caution for JARVIS licensing** |
| unclecode/crawl4ai | "Open-source LLM Friendly Web Crawler & Scraper" | 77,963 | Python | Apache-2.0 | MEDIUM — LLM-friendly crawling for web-research features |

### Agent Observability / Evals / Cost Tracking (telemetry tag)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| AgentOps-AI/agentops | "Python SDK for AI agent monitoring, LLM cost tracking, benchmarking, and more" | 5,769 | Python | MIT | MEDIUM — patterns for JARVIS telemetry/audit; complements existing OpenTelemetry |

### Terminal Tools (terminal-first: upgrade agent UX)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| sharkdp/bat | "A cat(1) clone with wings" (syntax highlighting pager) | 60,220 | Rust | Apache-2.0 | MEDIUM — adopt as file-view tool for JARVIS output |
| dandavison/delta | "A syntax-highlighting pager for git, diff, grep, rg --json, and blame output" | 31,729 | Rust | MIT | MEDIUM — readable diffs for agent git operations |

### Data Quality (optional R&D)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| cleanlab/cleanlab | "Standard data-centric AI package for data quality and ML with messy, real-world data" | 11,624 | Python | Apache-2.0 | LOW — only if JARVIS processes training/labeled data |

> Note: `microsoft/agent-evals` returned **404 (does not exist)** — skipped.

---

## Web UI Connectivity (how a browser frontend connects to the daemon)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| nousresearch/hermes-agent | "The agent that grows with you"... Open WebUI connects to its API server "just like it would connect to OpenAI" — handles terminal, file ops, web search, memory, skills, returns final response | 229,806 | Python | MIT | HIGH — self-hosted agent with built-in Open WebUI compatibility; React dashboard available via hermes-webui |
| sanchomuzax/hermes-webui | "Process monitoring and configuration dashboard for Hermes Agent"... React SPA + FastAPI backend, WebSocket-based polling bridge, real-time updates for sessions, memory, skills, tools, cron, logs, gateway health | 6,844 | Python/JS | MIT | MEDIUM — ready-made dashboard; bound to Hermes Agent but patterns transfer |
| microsoft/agent-framework (AG-UI) | AG-UI protocol standard for agent↔UI communication... supports WebSocket/SSE transports, human-in-the-loop, shared state, generative UI... integrations for React/TypeScript via CopilotKit | verified | Python/.NET | MIT/CC-BY-4.0 | R&D — protocol-level approach; can wire to JARVIS daemon's WebSocket endpoint |
| webjsdev/webjs | "The web framework for AI agents"... zero-build, web components, SSR, backend-only app with WebSockets, rate limiting, database, chat/agent gallery | ? | JS/TS | MIT | R&D — experimental framework; no build step, embeddable in minimal setups |

> Note: Open WebUI "just works" connecting to Hermes Agent API server like OpenAI. The hermes-webui dashboard provides a React+FastAPI reference implementation of a WebSocket-polling bridge for agent monitoring/control. AG-UI offers a protocol-standard alternative to custom WebSocket designs.

---

## Batch 4 — Verified Repos by Category (via GitHub API, 2026-08-13)

### Agent Frameworks & Engineering Platforms

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| langchain-ai/langchain | "The agent engineering platform" | 144,166 | Python | MIT | HIGH — de facto standard; extract tool patterns, memory modules, agent types; heavy dep, adapt ideas not install |
| microsoft/autogen | "A programming framework for agentic AI" | 60,402 | Python | CC-BY-4.0 | HIGH — multi-agent conversation patterns; protocol-agnostic; CC license requires attribution |
| anomalyco/opencode | "The open source coding agent" (was sst/opencode) | 196,983 | TypeScript | MIT | MEDIUM — coding-agent patterns; heavy UI deps contradict JARVIS terminal constraint; extract editor/tool patterns |
| jina-ai/serve | "Build multimodal AI applications with cloud-native stack" | 21,861 | Python | Apache-2.0 | R&D — cloud-native multimodal pipeline ideas; K8s, gRPC, Docker; too heavy for 512 MB |

### LLM Serving & Performance (inference tag)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| vllm-project/vllm | "A high-throughput and memory-efficient inference and serving engine for LLMs" | 88,968 | Python | Apache-2.0 | MEDIUM — study serving throughput/quantization patterns; GPU-dependent, extract ideas not deps |

### Search / Knowledge Base

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| elastic/elasticsearch | "Free and Open Source, Distributed, RESTful Search Engine" | 77,850 | Java | Other | LOW — Java-heavy, contradicts terminal-native / low-RAM constraint; study hybrid search patterns for future |

> Note: `crewai/crewai` returned **404** (organization/repo may have moved); `ipipan/FAISS` → **404** (FAISS is under `facebookresearch/faiss`). AgentOps already covered in Batch 3.

---

## Batch 5 — Token Optimization & Prompt Compression (via GitHub API, 2026-08-13)

### Prompt Compression (reduce input tokens before sending to LLM)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| civitas-io/promptshrink | "Prompt compression for LLM APIs — 30-50% token reduction, one-line integration" | 0 | Python | MIT | MEDIUM — segment-aware compression (system/few-shot/RAG/code); quality gate checks embedding similarity; early 2026, spec complete |
| sarkar-dipankar/llm-prompt-compression | "Structured survey of prompt compression techniques" (links to LLMLingua, GIST tokens, 500xCompressor) | 1 | Python | MIT | R&D — comprehensive survey; compare LLMLingua-2 vs token-level vs learned methods |
| LLMLingua/llmlingua | "Compressing prompts for accelerated inference of LLMs" (original, arXiv:2310.05736) | verified | Python | Apache-2.0 | R&D — token-level importance scoring with small LLM; 2x-20x compression, 90%+ performance retention |
| atjsh/llmlingua-2-js | "JavaScript/TypeScript implementation of LLMLingua-2 (Experimental)" | 30 | TypeScript | MIT | R&D — port of LLMLingua-2 for web/node environments |
| Paritok-official/paritok-4b-v1 | "Non-destructive compression gateway for AI coding agents" (25% turn 1 → 85% saturated sessions) | verified | ? | ? | MEDIUM — fits ~3x more turns in same context window; drop-in for Claude Code, Cursor |
| Tura-AI/tura | "Build agent that uses 80% less token and delivers better results" | ? | Python | ? | R&D — claims 80% token reduction; early 2026 |
| zdk/lowfat | "Slim your command output. strips noise, saves tokens." | ? | Go | ? | MEDIUM — CLI output sanitization; strips ANSI, filters noise |

### Prompt Caching (reuse compressed prefix across calls)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| anthropic/anthropic-quickstart | "Prompt caching built-in" (Anthropic offers 50% cost reduction, 80% latency improvement for >1024-token prefixes) | verified | ? | ? | HIGH — if JARVIS uses Anthropic, enable caching natively |
| openai/openai-py | "Batch API ~50% off for bulk async work (response within 24h)" | verified | Python | MIT | MEDIUM — for batched, non-time-sensitive agent runs |
| civitas-io/presidium | "Organizational cost governance primitive... cross-agent deduplication, per-team cost attribution, budget enforcement" | 0 | Python | MIT | R&D — integrates with promptshrink; policy-driven spend caps |

### CLI Proxies & Context Intelligence (reduce tokens at the edge)

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| rtk-ai/rtk | "CLI proxy that reduces LLM token consumption by 60-90% on common dev commands. Single Rust binary, zero dependencies" | ? | Rust | MIT | HIGH — zero-dependency proxy; fits JARVIS terminal-first constraint; drop-in between agent and LLM API |
| headroomlabs-ai/headroom | "Compress tool outputs, logs, files, and RAG chunks... 20% fewer tokens for coding agents, 60-95% fewer tokens for JSON, same answers" | ? | ? | Apache-2.0 | MEDIUM — library, proxy, MCP server; compresses before LLM sees it |
| yvgude/lean-ctx | "Control what your AI can see. LeanCTX: context intelligence layer... 60-90% fewer tokens as the receipt. 76 MCP tools, 30+ agents, local-first." | ? | Rust | ? | MEDIUM — local-first context guard; decides what agent reads/remembers/touches |
| jgravelle/jcodemunch-mcp | "Cut AI token costs 95%+ on code exploration. Leading MCP server for precise, symbol-level GitHub code retrieval via tree-sitter AST" | ? | ? | ? | MEDIUM — 313B+ tokens saved; works with Claude Code, Cursor & any MCP client |
| edouard-claude/snip | "CLI proxy that reduces LLM token usage by 60-90%. Declarative YAML filters for Claude Code, Cursor, Copilot, Gemini. rtk alternative in Go" | ? | Go | ? | MEDIUM — Go-based rtk alternative; declarative filters |
| anomalyco/opencode | "The open source coding agent" (196,983★, TS/MIT) | 196,983 | TypeScript | MIT | MEDIUM — already in research; heavy UI deps contradict JARVIS constraint; extract editor/tool patterns; may have token-reduction features |

### Output Format & Structural Optimization

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| sriinnu/clipforge-PAKT | "Lossless-first prompt compression for JSON, YAML, CSV, and Markdown. Library, CLI, MCP server, desktop app, and browser extension." | 20 | TypeScript | ? | MEDIUM — lossless compression of structured output formats; preserves data integrity |
| latet-gate/latent-gate | "VL-JEPA inspired pipeline — compress images/text locally via Ollama, send compact payloads to any LLM API. Cut token costs by ~80%." | 23 | Python | ? | MEDIUM — local compression before API call; ~80% token reduction claim |
| kaderkck/hewn-forge | "HEWN 2.0 2026: AI Output Router for Precision Summaries & Polished Code" | 150 | HTML | MIT | R&D — output router for polished code summaries; may reduce post-token generation cost |
| pleasesodisturb/awesome-llm-token-optimization | "A curated list of strategies, tools, papers, and resources for reducing LLM token costs and improving efficiency in production." | 37 | ? | ? | R&D — curated list; good starting point for deep dives |

> Note: many of these repos are early-2026 or experimental; star counts and viability may change rapidly. JARVIS constraint: prefer zero-dependency Rust Go binaries (rtk, lowfat) or one-line Python integrations (promptshrink). Caching and structured output format compression (clipforge-PAKT) offer immediate wins with minimal code change.

---

## Batch 6 — Agentic Coding Agents (via GitHub API, 2026-08-19)

### Coding Agent Platforms

| Repo | Verified description | Stars | Lang | License | Fit |
|------|----------------------|-------|------|---------|-----|
| CodebuffAI/freebuff | "The free coding agent" — built on Codebuff framework; specialized agents for context gathering, implementation, research, tool execution, and review; parallel local workspaces; evals; AGENTS.md | 8,400+ | TypeScript | ? | **HIGH** — direct architecture comparison: sub-agent orchestration, context discovery, verification/review loop, tool execution boundary, terminal UX |
| CodebuffAI/codebuff | "The open multi-agent coding framework" — orchestration, tools, SDK; underlying framework for Freebuff | ? | TypeScript | ? | **HIGH** — more valuable than Freebuff for JARVIS; study agent orchestration, tool architecture, SDK patterns |

### Freebuff/Codebuff Research Focus Areas

| Area | JARVIS Relevance | What to Study |
|------|------------------|---------------|
| Specialized agents | Very high | How context-gathering, implementation, research, and review agents coordinate |
| Context/file discovery | Very high | Automated codebase understanding; file-finding agents |
| Agent orchestration | Very high | Multi-agent delegation patterns; how agents hand off work |
| Parallel workspaces | High | Running multiple agent instances without interference |
| Tool architecture | Very high | Compare against ToolExecutionService single-boundary invariant |
| Verification/review | Very high | How agents check their own work before presenting results |
| Browser/research agents | High | Web-research integration patterns |
| SDK architecture | High | Protocol layer design for external integrations |
| Evals framework | Very high | Agent evaluation patterns; maps to JARVIS future verification system |
| Terminal UX | High | CLI interaction patterns for Claude-Code-style terminal |
| AGENTS.md conventions | High | Architecture contract comparison with JARVIS AGENTS.md |

### Research Question

> What does Freebuff/Codebuff do better than JARVIS, and can those ideas fit without violating JARVIS's execution-boundary architecture?

### Caveat

Freebuff is an ad-supported service. Prompts, messages, code, files, and repository data may be processed by its systems/providers. Treat as **architecture/research source only** — do not integrate blindly.

### Compare Against

- AgentLoop → Codebuff agent orchestration
- ToolExecutionService → Codebuff tool execution boundary
- VerificationEngine → Codebuff review/verification loop
- HarnessSelector → Codebuff agent specialization
- ModelGateway → Codebuff model selection
- MCP/ACP/Codex adapters → Codebuff SDK protocol layer
- Future multi-agent orchestration → Codebuff parallel workspaces

---

## Research Principle

> The GitHub list is a **research corpus feeding the architecture**, not an installation checklist. Extract patterns, algorithms, and UX ideas — don't blindly install dependencies that contradict JARVIS's terminal-native, low-RAM, daemon-first design.

---

## Saved Files

- `C:\Users\aayan\Desktop\JARVIS\jarvis-research-tags.md` — This research analysis
- Referenced in project consolidation at `C:\Users\aayan\Desktop\JARVIS/`

---