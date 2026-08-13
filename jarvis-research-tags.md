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

## Research Principle

> The GitHub list is a **research corpus feeding the architecture**, not an installation checklist. Extract patterns, algorithms, and UX ideas — don't blindly install dependencies that contradict JARVIS's terminal-native, low-RAM, daemon-first design.

---

## Saved Files

- `C:\Users\aayan\Desktop\JARVIS\jarvis-research-tags.md` — This research analysis
- Referenced in project consolidation at `C:\Users\aayan\Desktop\JARVIS/`

---