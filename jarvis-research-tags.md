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

## Research Principle

> The GitHub list is a **research corpus feeding the architecture**, not an installation checklist. Extract patterns, algorithms, and UX ideas — don't blindly install dependencies that contradict JARVIS's terminal-native, low-RAM, daemon-first design.

---

## Saved Files

- `C:\Users\aayan\Desktop\JARVIS\jarvis-research-tags.md` — This research analysis
- Referenced in project consolidation at `C:\Users\aayan\Desktop\JARVIS/`

---