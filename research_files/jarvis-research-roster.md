# JARVIS MK-X — GitHub Research Roster

**Generated**: 2026-10-16 · GitHub Search API, stars-sorted, deduped · 71 targeted queries across agent / browser / memory / security / UX / platform domains.
**Purpose**: research corpus feeding JARVIS MK-X + Orbit. Companion: `jarvis-research-tags.md` (curated adoption analysis).
**Principle**: extract patterns, do not blindly install. Nothing here destabilizes an active sprint (AGENTS.md research rule).

---

## Top picks — what to borrow for JARVIS

Triaged from the full sweep below (stars as of 2026-10-16). `borrow:` = concrete
extraction target for JARVIS MK-X / Orbit. Licenses flagged where they constrain
adoption (AGPL/GPL = patterns only). Cross-refs: `jarvis-research-tags.md`.

### Harness & agent loop
- [affaan-m/ECC](https://github.com/affaan-m/ECC) ★280.7k — agent-harness optimization system (skills, instincts, memory, security). borrow: skills/instinct triggering + research-first loop, validated against `core/harness`.
- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) ★254.3k — self-growing agent. borrow: growth/write-back policies for authority memory.
- [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) ★250.8k — "everything is a plugin" harness. borrow: plugin boundary design → harness extension seams without loop edits.
- [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) ★91.0k — code-agent platform. borrow: event-stream agent architecture + eval harness ideas.
- [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) ★78.7k — nano agent harness built 0→1. borrow: minimal-loop reference for `core/agent/loop.py` clarity.
- [ruvnet/ruflo](https://github.com/ruvnet/ruflo) ★75.3k — multi-agent swarm coordination. borrow: only if multi-agent lands post-Phase A.
- [HKUDS/nanobot](https://github.com/HKUDS/nanobot) ★49.1k — ultra-light personal agent (tools/memory/MCP/WebUI). borrow: low-RAM agent packaging reference.

- [headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom) ★75.5k — Apache-2.0. compress tool outputs/logs/files before they reach the model (20–95% token cuts). borrow: observation-compression stage before ModelGateway context assembly.
- [mangiucugna/json_repair](https://github.com/mangiucugna/json_repair) ★5.1k — MIT. repair malformed LLM JSON. borrow: MALFORMED_TOOL recovery hardening in tool-argument parsing.
### Browser & web surface (Orbit)
- [browser-use/browser-use](https://github.com/browser-use/browser-use) ★118.2k — canonical AI browser agent. borrow: DOM→agent serialization + action space; compare with `jbrowser/page_context.py` `[elN]` handles.
- [microsoft/playwright](https://github.com/microsoft/playwright) ★97.8k — engine already behind the jbrowser backend.
- [puppeteer/puppeteer](https://github.com/puppeteer/puppeteer) ★95.7k — CDP idioms; cross-check `orbit/cdp.py` sync recv-while-wait.
- [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) ★97.9k — agent "eyes" for social platforms. borrow: research-feed workspace on the goodeye pattern.
- [D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling) ★88.0k — adaptive scraping (selectors survive site changes). borrow: element fingerprinting → resilient page-context handles.
- [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) ★85.6k — any page → LLM-ready markdown. borrow: extraction pipeline for `browser.read`.
- [gorhill/uBlock](https://github.com/gorhill/uBlock) ★68.6k — GPL-3.0 (patterns only). borrow: static network filter-list model for Orbit shields.
- [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl) ★192.0k — AGPL (patterns only). borrow: crawl→structured-data contract shape.
- [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) ★38.2k — canonical browser-tool MCP schema. borrow: align `orbit.*` tool names/args for MCP interop.

- [dgtlmoon/changedetection.io](https://github.com/dgtlmoon/changedetection.io) ★35.1k — Apache-2.0. website change detection + alerts. borrow: watch/diff engine for the Orbit rail watch and `orbit://worldmon`.
- [assistant-ui/assistant-ui](https://github.com/assistant-ui/assistant-ui) ★12.6k — MIT. React AI-chat component library. borrow: extension sidebar chat surface.
- [webrecorder/scoop](https://github.com/webrecorder/scoop) ★215 — MIT. high-fidelity single-page capture (CLI + library). borrow: snapshot fidelity for `browser.screenshot` / read archive tier.
### Provider gateway & model routing
- [diegosouzapw/OmniRoute](https://github.com/diegosouzapw/OmniRoute) ★77.1k — MIT gateway, 359 providers / 1200+ models, one endpoint. borrow: provider-registry + failover metadata.
- [BerriAI/litellm](https://github.com/BerriAI/litellm) ★61.4k — 100+ LLM APIs in OpenAI format (already in pipeline). borrow: provider normalization table.
- [farion1231/cc-switch](https://github.com/farion1231/cc-switch) ★145.0k — desktop cross-CLI provider/account switcher. borrow: switching UX for the Orbit settings rail.

- [router-for-me/CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) ★55.4k — MIT. wrap Codex/Claude Code/Grok/etc. as OpenAI/Gemini/Claude-compatible API. borrow: protocol-adapter layer for gateway interop.
- [musistudio/claude-code-router](https://github.com/musistudio/claude-code-router) ★37.7k — MIT. local routing control plane across models with tool orchestration. borrow: per-task model routing + fusion rules.
### Memory, knowledge & docs
- [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) ★127.0k — codebase/docs/SQL/PDF → queryable knowledge graph (skill). borrow: constellation-keyspace presentation.
- [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) ★101.1k — session capture → AI compression → persistent context. borrow: session→authority-memory compression pipeline.
- [mem0ai/mem0](https://github.com/mem0ai/mem0) ★67.3k — memory layer (already in pipeline).
- [upstash/context7](https://github.com/upstash/context7) ★63.1k — up-to-date library docs for agents (MCP). borrow: docs-grounding tool backend.

- [vectorize-io/hindsight](https://github.com/vectorize-io/hindsight) ★50.2k — MIT. agent memory that learns/consolidates. borrow: consolidation pass on top of `memory/authority.py`.
- [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph) ★74.2k — MIT. pre-indexed code knowledge graph that auto-syncs on change. borrow: entity-granular code memory for agent perception.
- [Ataraxy-Labs/sem](https://github.com/Ataraxy-Labs/sem) ★3.4k + [Ataraxy-Labs/weave](https://github.com/Ataraxy-Labs/weave) ★1.3k — Apache-2.0. entity-level diffs/blame + artifact-level git merge driver (~95% false-conflict reduction). borrow: fewer bogus merge conflicts when parallel agents edit one file.
- [Egonex-AI/Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) ★86.5k — MIT. code → interactive knowledge graph you can query. borrow: pairs with graphify for codebase-teaching surfaces.
### Skills & agent content
- [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) ★164.7k — "laziest senior dev" minimal-code skill. borrow: candidate bundled skill (matches repo ethos).
- [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) ★97.7k — art-direction taste skill with browser check. borrow: UI-quality layer for Orbit design tasks.
- [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) ★77.2k — skill catalog. borrow: format survey feeding the `skills/` registry.
- [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) ★96.4k — MCP server directory. borrow: vet/adopt 2–3 servers through ToolExecutionService.

- [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) ★49.6k — MIT. agent skills for open formats (Markdown, Bases, JSON Canvas). borrow: format-handling skills for memory/notes files.
- [VoltAgent/awesome-openclaw-skills](https://github.com/VoltAgent/awesome-openclaw-skills) ★53.2k + [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) ★51.0k — MIT. large categorized skill corpora (5,400+; 177 validated science skills). borrow: taxonomy + validation bar for the `skills/` registry.
### Sandbox, quality & observability
- [daytonaio/daytona](https://github.com/daytonaio/daytona) ★71.5k — secure infra for AI-generated code. borrow: isolation model for `run_generated_code`.
- [louislam/uptime-kuma](https://github.com/louislam/uptime-kuma) ★92.5k — self-hosted uptime monitor. borrow: DSH bridge / service liveness panel.
- [netdata/netdata](https://github.com/netdata/netdata) ★81.0k — real-time full-stack observability. borrow: per-process metrics view for `orbit://diagnostics`.
- [grafana/grafana](https://github.com/grafana/grafana) ★77.3k / [prometheus/prometheus](https://github.com/prometheus/prometheus) ★66.6k — dashboards + metrics. borrow: metric naming and P50/P95/P99 presentation (`benchmark/orbit_timing.py`).

- [Wilfred/difftastic](https://github.com/Wilfred/difftastic) ★26.0k — MIT. structural (syntax-aware) diff. borrow: meaningful change summaries in VerificationEngine output.
### Documents, media & voice
- [microsoft/markitdown](https://github.com/microsoft/markitdown) ★190.5k + [docling-project/docling](https://github.com/docling-project/docling) ★69.0k — MIT. office/PDF → markdown/JSON for agents. borrow: document-ingest pipeline behind `browser.read` / files.
- [firecrawl/pdf-inspector](https://github.com/firecrawl/pdf-inspector) ★19.7k — MIT. scanned-vs-text PDF classification + text extraction. borrow: tiered read routing (text vs OCR).
- [naptha/tesseract.js](https://github.com/naptha/tesseract.js) ★38.8k — Apache-2.0. OCR in the browser. borrow: in-extension OCR fallback for scanned/image pages.
- [rhasspy/piper](https://github.com/rhasspy/piper) ★11.3k — MIT + [remsky/Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) ★5.6k — Apache-2.0. local neural TTS. borrow: opt-in voice output, fully local (Orbit speaker mode).

### Terminal / TUI (pipeline: TUIOS / Terminal UI projects)
- [jesseduffield/lazygit](https://github.com/jesseduffield/lazygit) ★83.2k / [junegunn/fzf](https://github.com/junegunn/fzf) ★83.6k — TUI + fuzzy palette interaction patterns.
- [Eugeny/tabby](https://github.com/Eugeny/tabby) ★75.0k / [alacritty/alacritty](https://github.com/alacritty/alacritty) ★66.0k / [ghostty-org/ghostty](https://github.com/ghostty-org/ghostty) ★62.3k — terminal UX references (speed, config, GPU).
- [warpdotdev/warp](https://github.com/warpdotdev/warp) ★65.5k — AGPL (patterns only). agentic terminal UX.

### Mirror / curiosity
- [koala73/worldmonitor](https://github.com/koala73/worldmonitor) ★88.5k — real-time global intelligence dashboard; namesake twin of the existing `orbit://worldmon` workspace. compare data sources.
- [stablyai/orca](https://github.com/stablyai/orca) ★93.9k — MIT. ADE for fleets of parallel agents, desktop + mobile. namesake twin of `orbit/`; compare fleet/session UX.
- [Laplace-bit/dsh-smooth-stream](https://github.com/Laplace-bit/dsh-smooth-stream) ★82 — MIT. DSH web-UI streaming-render + scroll plugin. namesake of "DeepSeek Harness"; compare streaming/scroll handling.

---

## Roster — 2089 repos shown (from 4828 collected, 71 categories)

### Agent frameworks & orchestration (30)

- [HKUDS/nanobot](https://github.com/HKUDS/nanobot) ★49.1k — Ultra-lightweight, open-source, self-hosted personal AI agent framework in Python with WebUI, tools, memory, MCP, multi-agent workflows, aut · Python · MIT · 2026-10
- [666ghj/BettaFish](https://github.com/666ghj/BettaFish) ★42.4k — 微舆：人人可用的多Agent舆情分析助手，打破信息茧房，还原舆情原貌，预测未来走向，辅助决策！从0实现，不依赖任何框架。 · Python · GPL-2.0 · 2026-10
- [esengine/DeepSeek-Reasonix](https://github.com/esengine/DeepSeek-Reasonix) ★35.8k — A reliable coding agent for complex software engineering tasks. · Go · MIT · 2026-10
- [deepset-ai/haystack](https://github.com/deepset-ai/haystack) ★26.7k — Open-source AI orchestration framework for building context-engineered, production-ready LLM applications. Design modular pipelines and agen · Python · Apache-2.0 · 2026-10
- [NirDiamant/agents-towards-production](https://github.com/NirDiamant/agents-towards-production) ★21.7k — End-to-end, code-first tutorials for building production-grade GenAI agents. From prototype to enterprise deployment. · Jupyter Notebook · NOASSERTION · 2026-09
- [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) ★20.7k — How Python does AI. Agents, realtime voice, image generation, embeddings. Every model, every interface, typed end to end. · Python · MIT · 2026-10
- [RightNow-AI/openfang](https://github.com/RightNow-AI/openfang) ★18.2k — Open-source Agent Operating System · Rust · Apache-2.0 · 2026-07
- [eigent-ai/eigent](https://github.com/eigent-ai/eigent) ★15.6k — Eigent: The Open Source Cowork Desktop - Local and Free Alternative to Claude Cowork and Codex · TypeScript · Apache-2.0 · 2026-10
- [microsoft/agent-framework](https://github.com/microsoft/agent-framework) ★14.2k — A framework for building, orchestrating and deploying AI agents and multi-agent workflows with support for Python and .NET. · Python · MIT · 2026-10
- [aden-hive/hive](https://github.com/aden-hive/hive) ★11.1k — Multi-Agent Harness for Production AI · Python · Apache-2.0 · 2026-10
- [omnigent-ai/omnigent](https://github.com/omnigent-ai/omnigent) ★10.8k — Omnigent is an open-source AI agent framework and meta-harness: orchestrate Claude Code, Codex, Cursor, Pi, and custom agents — swap harness · Python · Apache-2.0 · 2026-10
- [strands-agents/harness-sdk](https://github.com/strands-agents/harness-sdk) ★8.8k — Build an agent harness and control it end-to-end. Open-source SDK for production AI agents in Python & TypeScript - any model, any cloud. · TypeScript · Apache-2.0 · 2026-10
- [EvoMap/evolver](https://github.com/EvoMap/evolver) ★8.7k — The GEP-powered self-evolving engine for AI agents. Auditable evolution with Genes, Capsules, and Events. | evomap.ai · JavaScript · GPL-3.0 · 2026-10
- [MiroMindAI/MiroThinker](https://github.com/MiroMindAI/MiroThinker) ★8.4k — MiroThinker is a deep research agent optimized for complex research and prediction tasks. Our latest models, MiroThinker-1.7, achieves 74.0  · Python · Apache-2.0 · 2026-07
- [Upsonic/Upsonic](https://github.com/Upsonic/Upsonic) ★8.0k — Build autonomous AI agents in Python. · Python · MIT · 2026-06
- [open-multi-agent/open-multi-agent](https://github.com/open-multi-agent/open-multi-agent) ★7.0k — Self-hosted TypeScript agent runtime with durable approvals and verifiable run records. Own it, approve it, audit it. · TypeScript · MIT · 2026-10
- [crestalnetwork/intentkit](https://github.com/crestalnetwork/intentkit) ★6.5k — IntentKit is an open-source, self-hosted cloud agent cluster that manages a collaborative team of AI agents for you. · Python · MIT · 2026-09
- [microsoft/agent-governance-toolkit](https://github.com/microsoft/agent-governance-toolkit) ★6.4k — AI Agent Governance Toolkit — Policy enforcement, zero-trust identity, execution sandboxing, and reliability engineering for autonomous AI a · Python · MIT · 2026-10
- [agentscope-ai/agentscope-java](https://github.com/agentscope-ai/agentscope-java) ★6.0k — Build distributed, production-grade, long-running agents. · Java · Apache-2.0 · 2026-10
- [rllm-org/rllm](https://github.com/rllm-org/rllm) ★5.9k — Democratizing Reinforcement Learning for LLMs · Python · Apache-2.0 · 2026-10
- [didilili/ai-agents-from-zero](https://github.com/didilili/ai-agents-from-zero) ★5.4k — 🚀 2026 最系统的 AI Agent 速成指南｜智能体实战教程 · 完整学习路径  + 实战项目 + 面试题库 · 对标大模型应用开发工程师岗位 · 覆盖LangChain / LangGraph / Coze / Dify / MCP / skills / LLM / RA · Python · MIT · 2026-10
- [iflytek/skillhub](https://github.com/iflytek/skillhub) ★5.2k — Self-hosted, open-source agent skill registry for enterprises. Publish & version skill packages, govern with RBAC and audit logs, deploy   o · Java · Apache-2.0 · 2026-10
- [ag2ai/ag2](https://github.com/ag2ai/ag2) ★5.0k — AG2 (formerly AutoGen): The Open-Source AgentOS.Join us at: https://discord.gg/sNGSwQME3x · Python · Apache-2.0 · 2026-10
- [TencentCloudADP/youtu-agent](https://github.com/TencentCloudADP/youtu-agent) ★4.6k — A simple yet powerful agent framework that delivers with open-source models · Python · NOASSERTION · 2026-03
- [kungfu-systems/kungfu](https://github.com/kungfu-systems/kungfu) ★4.5k — Your agents don’t hand off the work. Kungfu keeps the same Work moving across Codex, Claude, OpenCode, and your own execution surface. · C++ · Apache-2.0 · 2026-10
- [crmne/ruby_llm](https://github.com/crmne/ruby_llm) ★4.5k — The Ruby AI framework. · Ruby · MIT · 2026-10
- [evalstate/fast-agent](https://github.com/evalstate/fast-agent) ★3.9k — Code, Build and Evaluate agents - excellent Model and Skills/MCP/ACP/A2A Support · Python · Apache-2.0 · 2026-10
- [foryourhealth111-pixel/Vibe-Skills](https://github.com/foryourhealth111-pixel/Vibe-Skills) ★3.7k — Intelligent Skill routing and workflow orchestration for AI agents — +21.12 pp reward, −29.6% tokens on SkillsBench with DeepSeekV4Flash-VE. · Python · Apache-2.0 · 2026-10
- [MiroMindAI/MiroFlow](https://github.com/MiroMindAI/MiroFlow) ★3.1k — 🏆 Top-1 on 5+ benchmarks | Web UI | Supports MiroThinker, Claude, Kimi, OpenAI · Python · Apache-2.0 · 2026-07
- [HarnessRouter/harnessrouter](https://github.com/HarnessRouter/harnessrouter) ★3.0k — HarnessRouter Community Edition: the self-hosted, Apache-2.0 edition of the unified interface for agent harnesses. Run Codex, Claude Code, H · Python · Apache-2.0 · 2026-10

### AI agents (general) (30)

- [affaan-m/ECC](https://github.com/affaan-m/ECC) ★280.7k — The agent harness performance optimization system. Skills, instincts, memory, security, and research-first development for Claude Code, Code · JavaScript · MIT · 2026-10
- [morluto/rea](https://github.com/morluto/rea) ★280.1k — Reverse engineer anything with agents, from app behavior down to native binaries. · TypeScript · MIT · 2026-10
- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) ★254.3k — The agent that grows with you · Python · MIT · 2026-10
- [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) ★250.8k — DeepSeek Harness: Everything is a Plugin. · TypeScript · MIT · 2026-10
- [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl) ★192.0k — Supercharge your AI agents with data from the web and beyond. Building the library for superintelligence. 🔥 · TypeScript · AGPL-3.0 · 2026-10
- [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) ★164.7k — Makes your AI agent think like the laziest senior dev in the room. The best code is the code you never wrote. · JavaScript · MIT · 2026-10
- [langchain-ai/langchain](https://github.com/langchain-ai/langchain) ★147.9k — The agent engineering platform. · Python · MIT · 2026-10
- [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) ★127.0k — Turn any codebase, with its docs, SQL schemas, configs, and PDFs, into a queryable knowledge graph. A /graphify skill for Claude Code, Curso · Python · Apache-2.0 · 2026-10
- [browser-use/browser-use](https://github.com/browser-use/browser-use) ★118.2k — Open-source Python library for AI browser agents, plus Browser Use Cloud: stealth browsers and a hosted agent API. · Python · MIT · 2026-10
- [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) ★107.4k — An open-source AI agent that brings the power of Gemini directly into your terminal. · TypeScript · Apache-2.0 · 2026-10
- [paperclipai/paperclip](https://github.com/paperclipai/paperclip) ★102.9k — The open-source app everyone uses to manage agents at work · TypeScript · MIT · 2026-10
- [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) ★101.1k — Persistent Context Across Sessions for Every Agent –  Captures everything your agent does during sessions, compresses it with AI, and inject · TypeScript · Apache-2.0 · 2026-10
- [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) ★97.7k — Agent skills that give coding agents taste: art direction, reference images and a browser check instead of generic AI pages · JavaScript · MIT · 2026-10
- [stablyai/orca](https://github.com/stablyai/orca) ★93.9k — Orca is the ADE for working with a fleet of parallel agents. Run any coding agent with your own subscription. Available on desktop, mobile a · TypeScript · MIT · 2026-10
- [infiniflow/ragflow](https://github.com/infiniflow/ragflow) ★92.3k — RAGFlow is a leading open-source Retrieval-Augmented Generation (RAG) engine that fuses cutting-edge RAG with Agent capabilities to create a · Go · Apache-2.0 · 2026-10
- [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) ★85.6k — Open-source web crawler and scraper for LLMs and AI agents: any website into clean, LLM-ready Markdown. Run it yourself, or use Crawl4AI Clo · Python · Apache-2.0 · 2026-10
- [tt-a1i/archify](https://github.com/tt-a1i/archify) ★84.2k — Turn any idea, plan, or codebase into a beautiful interactive diagram. An agent skill for Claude Code, Codex, and more. · JavaScript · MIT · 2026-10
- [bytedance/deer-flow](https://github.com/bytedance/deer-flow) ★83.9k — An open-source long-horizon SuperAgent harness that researches, codes, and creates. With the help of sandboxes, memories, tools, skill, suba · Python · MIT · 2026-10
- [dair-ai/Prompt-Engineering-Guide](https://github.com/dair-ai/Prompt-Engineering-Guide) ★79.2k — 🐙 Guides, papers, lessons, notebooks and resources for prompt engineering, context engineering, RAG, and AI Agents. · MDX · MIT · 2026-03
- [microsoft/ai-agents-for-beginners](https://github.com/microsoft/ai-agents-for-beginners) ★77.3k — 18 Lessons to Get Started Building AI Agents · Jupyter Notebook · MIT · 2026-10
- [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) ★77.2k — A curated list of awesome Claude Skills, resources, and tools for customizing Claude AI workflows · Python · NOASSERTION · 2026-09
- [diegosouzapw/OmniRoute](https://github.com/diegosouzapw/OmniRoute) ★77.1k — Never stop coding. Free MIT AI gateway: one endpoint, 359 providers (150+ free), 1200+ models Kimi, Claude, GPT, Gemini, GLM, DeepSeek, Mini · TypeScript · MIT · 2026-10
- [ruvnet/ruflo](https://github.com/ruvnet/ruflo) ★75.3k — 🌊 The original agent harness. Deploy intelligent multi-player swarms, coordinate autonomous workflows, and build conversational AI systems.  · TypeScript · MIT · 2026-10
- [thedaviddias/Front-End-Checklist](https://github.com/thedaviddias/Front-End-Checklist) ★74.5k — 🗂 The essential checklist for modern web development, for humans and AI agents · MDX · MIT · 2026-10
- [daytonaio/daytona](https://github.com/daytonaio/daytona) ★71.5k — Daytona is a Secure and Elastic Infrastructure for Running AI-Generated Code · NOASSERTION · 2026-07
- [code-yeongyu/oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent) ★70.1k — OmO: Just type "mass ulw" keyword with your prompt. Now you are the master of graph engineering. · TypeScript · NOASSERTION · 2026-10
- [rohitg00/ai-engineering-from-scratch](https://github.com/rohitg00/ai-engineering-from-scratch) ★70.0k — Learn AI Engineering! Learn it. Build it. Ship it for others. · Python · MIT · 2026-10
- [asgeirtj/system_prompts_leaks](https://github.com/asgeirtj/system_prompts_leaks) ★69.7k — Documented system prompts from Anthropic - Claude Fable 5.1, Opus 5.5, Claude Design, Claude Code. OpenAI - ChatGPT GPT-6-Astra, Codex. Goog · Python · CC0-1.0 · 2026-10
- [shanraisshan/claude-code-best-practice](https://github.com/shanraisshan/claude-code-best-practice) ★67.6k — from vibe coding to agentic engineering - practice makes claude perfect · HTML · MIT · 2026-10
- [mem0ai/mem0](https://github.com/mem0ai/mem0) ★67.3k — The Memory Layer for AI Agents - Drop-in memory infrastructure for AI agents and apps. Context that persists. Built for production. · Python · Apache-2.0 · 2026-10

### Autonomous agents (30)

- [Significant-Gravitas/AutoGPT](https://github.com/Significant-Gravitas/AutoGPT) ★187.6k — AutoGPT is the vision of accessible AI for everyone, to use and to build on. Our mission is to provide the tools, so that you can focus on w · Python · NOASSERTION · 2026-10
- [e2b-dev/awesome-ai-agents](https://github.com/e2b-dev/awesome-ai-agents) ★30.5k — A list of AI autonomous agents · NOASSERTION · 2026-08
- [Fosowl/agenticSeek](https://github.com/Fosowl/agenticSeek) ★27.5k — Fully Local Manus AI. No APIs, No $200 monthly bills. Enjoy an autonomous agent that thinks, browses the web, and code for the sole cost of  · Python · GPL-3.0 · 2026-10
- [OthmanAdi/planning-with-files](https://github.com/OthmanAdi/planning-with-files) ★27.5k — Persistent file-based planning for AI coding agents and long-running tasks. Crash-proof markdown plans, session recovery after /clear and co · Python · MIT · 2026-10
- [TransformerOptimus/SuperAGI](https://github.com/TransformerOptimus/SuperAGI) ★17.7k — <⚡️> SuperAGI - A dev-first open source autonomous AI agent framework. Enabling developers to build, manage & run useful autonomous agents q · Python · MIT · 2025-01
- [cft0808/edict](https://github.com/cft0808/edict) ★17.0k — 🏛️ 三省六部制 · OpenClaw Multi-Agent Orchestration System — 9 specialized AI agents with real-time dashboard, model config, and full audit trails · Python · MIT · 2026-09
- [fathah/hermes-desktop](https://github.com/fathah/hermes-desktop) ★14.4k — Desktop Companion for Hermes Agent · TypeScript · MIT · 2026-10
- [spinabot/brigade](https://github.com/spinabot/brigade) ★11.3k — Brigade — Your personal intelligence, built enterprise-grade · TypeScript · MIT · 2026-10
- [GetBindu/Bindu](https://github.com/GetBindu/Bindu) ★10.1k — Bindu: The identity, communication, and payments layer for AI agents. · Python · NOASSERTION · 2026-09
- [HarnessMD/munder-difflin](https://github.com/HarnessMD/munder-difflin) ★8.8k — an open-source alternative to the dots, bots and muses of the world, run an office of claude code/codex like agents on your laptop, sandboxe · TypeScript · MIT · 2026-10
- [RayVentura/ShortGPT](https://github.com/RayVentura/ShortGPT) ★8.0k — 🚀🎬 ShortGPT - Experimental AI framework for youtube shorts / tiktok channel automation · Python · MIT · 2025-02
- [infobyte/faraday](https://github.com/infobyte/faraday) ★6.8k — Open-source and AI-powered cybersecurity tools for offensive security, vulnerability management, and autonomous pentesting. Built by hackers · Python · GPL-3.0 · 2026-10
- [netease-youdao/LobsterAI](https://github.com/netease-youdao/LobsterAI) ★6.1k — Open-source, desktop-grade AI agent that gets real work done — data analysis, slides, docs, video & web research. Built on OpenClaw; runs to · TypeScript · MIT · 2026-10
- [aiwaves-cn/agents](https://github.com/aiwaves-cn/agents) ★6.0k — An Open-source Framework for Data-centric, Self-evolving Autonomous Language Agents · Python · Apache-2.0 · 2024-09
- [campfirein/byterover-cli](https://github.com/campfirein/byterover-cli) ★5.0k — ByteRover CLI (brv) - The portable memory layer for  autonomous coding agents (formerly Cipher) · TypeScript · NOASSERTION · 2026-06
- [gptme/gptme](https://github.com/gptme/gptme) ★4.5k — Your agent in your terminal, equipped with local tools: writes code, uses the terminal, browses the web. Make your own persistent autonomous · Python · MIT · 2026-10
- [MaxMiksa/Autonomous-Company](https://github.com/MaxMiksa/Autonomous-Company) ★3.1k — An autonomous company working 24/7 on your own PC - Windows/Linux/macOS. · Python · MIT · 2026-10
- [samugit83/redamon](https://github.com/samugit83/redamon) ★3.1k — Open-source, self-hosted AI penetration testing framework: maps your attack surface into a graph, autonomously exploits it from a Kali sandb · Python · MIT · 2026-10
- [feder-cr/invisible_playwright_mcp](https://github.com/feder-cr/invisible_playwright_mcp) ★2.8k — Playwright MCP server undetected by anti-bots and captchas: AI agent browses the web on anti-detect stealth Firefox, Python, undetected brow · Python · MIT · 2026-10
- [wanikua/danghuangshang](https://github.com/wanikua/danghuangshang) ★2.7k — Open-source multi-agent collaboration system inspired by Chinese governance — deploy and coordinate specialized AI agents with OpenClaw. · TypeScript · MIT · 2026-05
- [webfuse-com/awesome-autoresearch](https://github.com/webfuse-com/awesome-autoresearch) ★2.6k — A curated list of autonomous improvement loops, research agents, and autoresearch-style systems inspired by Karpathy's autoresearch. · NOASSERTION · 2026-09
- [semanser/codel](https://github.com/semanser/codel) ★2.5k — ✨ Fully autonomous AI Agent that can perform complicated tasks and projects using terminal, browser, and editor. · TypeScript · AGPL-3.0 · 2024-04
- [Orkas-AI/Orkas](https://github.com/Orkas-AI/Orkas) ★2.2k — Orkas is an open-source, local-first AI desktop app: a commander LLM directs specialist sub-agents, and runs your installed coding CLIs — Cl · JavaScript · MIT · 2026-10
- [4thfever/cultivation-world-simulator](https://github.com/4thfever/cultivation-world-simulator) ★2.1k — 基于 AI Agent 工作流的修仙世界模拟器，旨在还原智能、开放的仙侠世界。| An open-source Cultivation World Simulator using Agentic Workflow to create a dynamic, emerging Xia · Python · NOASSERTION · 2026-08
- [hyperspaceai/agi](https://github.com/hyperspaceai/agi) ★2.1k — The first distributed AGI system. Thousands of autonomous AI agents collaboratively train models, share experiments via P2P gossip, and push · JavaScript · MIT · 2026-10
- [the-open-engine/zeroshot](https://github.com/the-open-engine/zeroshot) ★2.0k — Enforced QA for Claude Code, Codex and Copilot. Draw the graph: code review, your own reviewers and test agents, any model per node. Slop go · Rust · MIT · 2026-10
- [melih-unsal/DemoGPT](https://github.com/melih-unsal/DemoGPT) ★1.9k — 🤖 Create agentic apps in a second with your prompts. Everything you need to create an LLM Agent - tools, prompts, frameworks, and models - a · Python · MIT · 2026-04
- [mims-harvard/ToolUniverse](https://github.com/mims-harvard/ToolUniverse) ★1.7k — Democratizing AI scientists with ToolUniverse · Python · Apache-2.0 · 2026-10
- [kyegomez/awesome-multi-agent-papers](https://github.com/kyegomez/awesome-multi-agent-papers) ★1.7k — A compilation of the best multi-agent papers · TeX · NOASSERTION · 2026-10
- [HumanSignal/Adala](https://github.com/HumanSignal/Adala) ★1.6k — Adala: Autonomous DAta (Labeling) Agent framework · Python · Apache-2.0 · 2026-10

### Agent pattern (broad) (30)

- [Snailclimb/JavaGuide](https://github.com/Snailclimb/JavaGuide) ★159.1k — Java 面试 & 后端通用面试指南，覆盖计算机基础、数据库、分布式、高并发、系统设计与 AI 应用开发 · JavaScript · Apache-2.0 · 2026-10
- [langgenius/dify](https://github.com/langgenius/dify) ★158.6k — Build Agentic workflows, RAG pipelines, with rich AI model and tool support on one collaborative workspace. Deploy on cloud, VPC, or self-ho · Python · NOASSERTION · 2026-10
- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) ★111.4k — TradingAgents: Multi-Agents LLM Financial Trading Framework · Python · Apache-2.0 · 2026-10
- [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) ★91.0k — 🙌 OpenHands: AI-Driven Development · TypeScript · MIT · 2026-10
- [koala73/worldmonitor](https://github.com/koala73/worldmonitor) ★88.5k — Real-time global intelligence dashboard. AI-powered news aggregation, geopolitical monitoring, and infrastructure tracking in a unified situ · TypeScript · AGPL-3.0 · 2026-10
- [datawhalechina/hello-agents](https://github.com/datawhalechina/hello-agents) ★83.4k — 📚 《从零开始构建智能体》——从零开始的智能体原理与实践教程 · Python · NOASSERTION · 2026-10
- [lobehub/lobehub](https://github.com/lobehub/lobehub) ★83.3k — 🤯 LobeHub is your Chief Agent Operator, organizing your agents into 7×24 operations by hiring, scheduling, and reporting on your entire AI t · TypeScript · NOASSERTION · 2026-10
- [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) ★78.7k — Bash is all you need -  A nano claude code–like 「agent harness」, built from 0 to 1 · Python · MIT · 2026-09
- [unslothai/unsloth](https://github.com/unslothai/unsloth) ★78.1k — Local UI to run and train LLMs and diffusion models. Supports GGUF, MLX, Qwen3.8, DeepSeek-V4, MiniMax-H3, Gemma 4, FLUX and more. · Python · Apache-2.0 · 2026-10
- [hiyouga/LlamaFactory](https://github.com/hiyouga/LlamaFactory) ★75.5k — Unified Efficient Fine-Tuning of 100+ LLMs & VLMs (ACL 2024) · Python · Apache-2.0 · 2026-10
- [headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom) ★75.5k — Compress tool outputs, logs, files, and RAG chunks before they reach the LLM. 20% fewer tokens for coding agents, 60-95% fewer tokens for JS · Python · Apache-2.0 · 2026-10
- [FoundationAgents/MetaGPT](https://github.com/FoundationAgents/MetaGPT) ★70.9k — 🌟 The Multi-Agent Framework: First AI Software Company, Towards Natural Language Programming · Python · MIT · 2026-01
- [calesthio/OpenMontage](https://github.com/calesthio/OpenMontage) ★68.7k — World's first open-source, agentic video production system. 12 production pipelines, 100+ tools, 700+ agent skill and production-knowledge f · Python · AGPL-3.0 · 2026-10
- [bojieli/ai-agent-book](https://github.com/bojieli/ai-agent-book) ★54.5k — 《深入理解 AI Agent：设计原理与工程实践》（李博杰 著）开源主仓库：全书正文、编译版 PDF 与按章配套代码 · Python · Apache-2.0 · 2026-10
- [huginn/huginn](https://github.com/huginn/huginn) ★50.1k — Create agents that monitor and act on your behalf.  Your agents are standing by! · Ruby · MIT · 2026-10
- [jeecgboot/JeecgBoot](https://github.com/jeecgboot/JeecgBoot) ★48.2k — 【低代码v2.0，一句话即可生成整个系统】企业级AI低代码平台，一键生成前后端代码甚至整个系统。 AI Skills 一句话画流程、设计表单、生成报表、大屏。内置 AI应用平台涵盖：AI聊天、知识库、流程编排、MCP插件等，兼容主流大模型。引领AI低代码「Skills 生成 →  · Java · Apache-2.0 · 2026-10
- [alibaba/open-code-review](https://github.com/alibaba/open-code-review) ★47.5k — Secure, fast, efficient, battle-tested at Alibaba's scale. Hybrid architecture code review tool: deterministic pipelines + LLM Agent, precis · Go · Apache-2.0 · 2026-10
- [AstrBotDevs/AstrBot](https://github.com/AstrBotDevs/AstrBot) ★42.0k — AI Agent Assistant & development framework that integrates lots of IM platforms, LLMs, plugins and AI feature, and can be your openclaw alte · Python · AGPL-3.0 · 2026-10
- [pingcap/tidb](https://github.com/pingcap/tidb) ★40.6k — TiDB is built for agentic workloads that grow unpredictably, with ACID guarantees and native support for transactions, analytics, and vector · Go · Apache-2.0 · 2026-10
- [2noise/ChatTTS](https://github.com/2noise/ChatTTS) ★39.9k — A generative speech model for daily dialogue. · Python · AGPL-3.0 · 2026-04
- [bytedance/UI-TARS-desktop](https://github.com/bytedance/UI-TARS-desktop) ★39.3k — The Open-Source Multimodal AI Agent Stack: Connecting Cutting-Edge AI Models and Agent Infra · TypeScript · Apache-2.0 · 2026-10
- [CopilotKit/CopilotKit](https://github.com/CopilotKit/CopilotKit) ★38.1k — The Frontend Stack for Agents & Generative UI. React, Angular, Mobile, Slack, and more.  Makers of the AG-UI Protocol · TypeScript · MIT · 2026-10
- [khoj-ai/khoj](https://github.com/khoj-ai/khoj) ★37.7k — Your AI second brain. Self-hostable. Get answers from the web or your docs. Build custom agents, schedule automations, do deep research. Tur · Python · AGPL-3.0 · 2026-08
- [alibaba/arthas](https://github.com/alibaba/arthas) ★37.6k — Alibaba Java Diagnostic Tool Arthas/Alibaba Java诊断利器Arthas · Java · Apache-2.0 · 2026-10
- [1Panel-dev/1Panel](https://github.com/1Panel-dev/1Panel) ★37.2k — 🔥 1Panel is a modern, open-source Linux server management panel and a lightweight AI management platform. · Go · GPL-3.0 · 2026-10
- [continuedev/continue](https://github.com/continuedev/continue) ★36.2k — open-source coding agent · TypeScript · Apache-2.0 · 2026-10
- [datawhalechina/happy-llm](https://github.com/datawhalechina/happy-llm) ★34.4k — 📚 从零开始构建大模型 · Jupyter Notebook · NOASSERTION · 2026-08
- [Tencent/WeKnora](https://github.com/Tencent/WeKnora) ★34.3k — Open-source LLM knowledge platform: turn raw documents into a queryable RAG, an autonomous reasoning agent, and a self-maintaining Wiki. · Go · NOASSERTION · 2026-10
- [alibaba/nacos](https://github.com/alibaba/nacos) ★33.5k — an easy-to-use dynamic service discovery, configuration and service management platform for building AI cloud native applications. · Java · Apache-2.0 · 2026-10
- [agentscope-ai/agentscope](https://github.com/agentscope-ai/agentscope) ★33.4k — Build and run agents you can see, understand and trust. · Python · Apache-2.0 · 2026-10

### Code / coding agents (30)

- [openinterpreter/openinterpreter](https://github.com/openinterpreter/openinterpreter) ★68.6k — A coding agent for open models like Kimi K3 and GLM 5.3 · Rust · Apache-2.0 · 2026-10
- [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) ★55.8k — A hand-picked collection of the finest of resources for the most awesome of agents, Claude Code, the undisputed champion of coding companion · Python · NOASSERTION · 2026-10
- [codewhale-hq/Codewhale](https://github.com/codewhale-hq/Codewhale) ★41.1k — Open-source Rust agent engine and terminal client for Codewhale, with provider choice, tools, approvals and receipts. · Rust · MIT · 2026-10
- [QwenLM/qwen-code](https://github.com/QwenLM/qwen-code) ★28.5k — An open-source AI coding agent that lives in your terminal. · TypeScript · Apache-2.0 · 2026-10
- [1jehuang/jcode](https://github.com/1jehuang/jcode) ★20.9k — High performance coding agent harness written in rust · Rust · MIT · 2026-10
- [YaoApp/yao](https://github.com/YaoApp/yao) ★8.1k — ✨ All your agents and workspaces in one place, on every device you own. Track tasks on a board, accessible from desktop, mobile, browser, or · Go · NOASSERTION · 2026-10
- [algorithmicsuperintelligence/openevolve](https://github.com/algorithmicsuperintelligence/openevolve) ★7.6k — Open-source implementation of AlphaEvolve · Python · Apache-2.0 · 2026-10
- [vastsa/PI-Desktop](https://github.com/vastsa/PI-Desktop) ★6.9k — Local-first AI coding agent desktop: Electron + Rust host core + pi Agent Harness + user-installable plugins · TypeScript · LGPL-3.0 · 2026-10
- [anus-dev/ANUS](https://github.com/anus-dev/ANUS) ★6.5k — A free coding agent in your terminal. It runs on the smartest free model that is up today. · JavaScript · MIT · 2026-10
- [KunAgent/Kun](https://github.com/KunAgent/Kun) ★6.3k — Local-first AI agent workspace for coding, writing, design, research, and automation — one runtime for desktop GUI and TUI. · TypeScript · NOASSERTION · 2026-10
- [Q00/ouroboros](https://github.com/Q00/ouroboros) ★6.2k — Agent OS: the agent gets smarter on its own. We just hold the line: Interview-gated, staged evaluation, budgeted evolution loop. MCP server, · Python · MIT · 2026-10
- [google/agents-cli](https://github.com/google/agents-cli) ★6.1k — The CLI and skills that turn any coding assistant into an expert at creating, evaluating, and deploying AI agents on Google Cloud. · Python · Apache-2.0 · 2026-10
- [cloudflare/vibesdk](https://github.com/cloudflare/vibesdk) ★5.4k — An open-source vibe coding platform that helps you build your own vibe-coding platform, built entirely on Cloudflare stack · TypeScript · MIT · 2026-09
- [nexu-io/html-video](https://github.com/nexu-io/html-video) ★4.7k — Programmatic video for coding agents — HTML to video on your laptop. Turn HTML, CSS & data into real MP4s with pluggable render engines, 21  · HTML · Apache-2.0 · 2026-06
- [ccch1mneyyy/dsh-TUI](https://github.com/ccch1mneyyy/dsh-TUI) ★4.7k — DSH's officially top-recommended TUI plugin — high performance, low overhead, cute pixel whale, smooth mouse interaction. One-command instal · TypeScript · MIT · 2026-10
- [CommandCodeAI/command-code](https://github.com/CommandCodeAI/command-code) ★4.1k — Command Code AI — the best coding agent for open models. · NOASSERTION · 2026-10
- [JetBrains/go-modern-guidelines](https://github.com/JetBrains/go-modern-guidelines) ★3.9k — Help AI coding agents write modern Go · Go · Apache-2.0 · 2026-10
- [tutti-os/tutti](https://github.com/tutti-os/tutti) ★3.8k — Where people and agents build in tune. · TypeScript · Apache-2.0 · 2026-10
- [Windy3f3f3f3f/how-claude-code-works](https://github.com/Windy3f3f3f3f/how-claude-code-works) ★3.7k — Deep dive into Claude Code internals — architecture, agent loop, context engineering, and more. / 深入解析 Claude Code 源码：架构、Agent 循环、上下文工程、工具系统 · MIT · 2026-08
- [SeemSeam/claude_codex_bridge](https://github.com/SeemSeam/claude_codex_bridge) ★3.6k — Visible multi-agent CLI workspace for mixing Codex, Claude, Gemini, Kimi, Qwen, Cursor, Copilot, Pi, OpenCode, and other AI coding agents · Python · NOASSERTION · 2026-10
- [superagent-ai/grok-cli](https://github.com/superagent-ai/grok-cli) ★3.5k — An open-source coding agent for the Grok API · TypeScript · MIT · 2026-07
- [fuxicodex/Fuxi](https://github.com/fuxicodex/Fuxi) ★3.3k — FuXi is a fast, self-contained AI coding agent that lives in your terminal — edit code, run commands, and drive tools, with cost-aware routi · Python · NOASSERTION · 2026-09
- [zeronsh/zeron](https://github.com/zeronsh/zeron) ★3.2k — A native control plane for Claude Code, Codex, Cursor, Devin and other coding agents. · Rust · MIT · 2026-10
- [cocoindex-io/cocoindex-code](https://github.com/cocoindex-io/cocoindex-code) ★2.9k — A super light-weight embedded code search engine CLI (AST based) that just works -  improves speed and efficiency for coding agent  🌟 Star i · Python · Apache-2.0 · 2026-10
- [openlit/openlit](https://github.com/openlit/openlit) ★2.9k — OpenLIT is the open-source agent harness engineering platform: trace, evaluate, guard, and improve everything around the model in your AI ag · TypeScript · Apache-2.0 · 2026-10
- [teaql/teaql-agent-kit](https://github.com/teaql/teaql-agent-kit) ★2.8k — A model-driven harness for AI coding agents: semantic modeling, app generation, progressive API Assist and evidence-based verification. · Python · MIT · 2026-09
- [Windy3f3f3f3f/claude-code-from-scratch](https://github.com/Windy3f3f3f3f/claude-code-from-scratch) ★2.8k — Build your own Claude Code from scratch.  🔍 Claude Code 开源了 50 万行代码，读不动？用 ~5000 行 TypeScript / Python 从零复现核心架构，11 章分步教程带你理解 coding agent 精髓 · Python · MIT · 2026-07
- [itayinbarr/little-coder](https://github.com/itayinbarr/little-coder) ★2.7k — A harness optimized to smaller LLMs · TypeScript · Apache-2.0 · 2026-09
- [CoderLuii/HolyClaude](https://github.com/CoderLuii/HolyClaude) ★2.6k — AI coding workstation: Claude Code + web UI + 8 AI CLIs + headless browser + 50+ tools · JavaScript · MIT · 2026-10
- [michael-denyer/pstack-claude](https://github.com/michael-denyer/pstack-claude) ★2.6k — Claude Code, Codex, Copilot, Pi, OpenCode, Gemini, and Prime Agent versions of Poteto's pstack. Rigorous agent workflows with Cursor primiti · JavaScript · MIT · 2026-10

### MCP / Model Context Protocol (30)

- [n8n-io/n8n](https://github.com/n8n-io/n8n) ★207.6k — Fair-code workflow automation platform with native AI capabilities. Combine visual building with custom code, self-host or cloud, 400+ integ · TypeScript · NOASSERTION · 2026-10
- [open-webui/open-webui](https://github.com/open-webui/open-webui) ★155.9k — User-friendly AI Interface (Supports Ollama, OpenAI API, ...) · Python · NOASSERTION · 2026-10
- [farion1231/cc-switch](https://github.com/farion1231/cc-switch) ★145.0k — A cross-platform desktop All-in-One assistant for Claude Code, Codex, OpenCode, OpenClaw, Grok Build & Hermes Agent. Only official website:  · Rust · MIT · 2026-10
- [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) ★97.9k — Give your AI agent eyes to see the entire internet. Read & search Twitter, Reddit, YouTube, GitHub, Bilibili, XiaoHongShu — one CLI, zero AP · Python · MIT · 2026-10
- [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) ★96.4k — A collection of MCP servers. · MIT · 2026-10
- [D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling) ★88.0k — 🕷️ An adaptive Web Scraping framework that handles everything from a single request to a full-scale crawl! Don't be shy, join here: https:// · Python · BSD-3-Clause · 2026-10
- [netdata/netdata](https://github.com/netdata/netdata) ★81.0k — The fastest path to AI-powered full stack observability, even for lean teams. · Go · GPL-3.0 · 2026-10
- [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) ★64.9k — Write HTML. Render video. Built for agents. · TypeScript · Apache-2.0 · 2026-10
- [upstash/context7](https://github.com/upstash/context7) ★63.1k — Context7 Platform -- Up-to-date docs for AI agents · TypeScript · MIT · 2026-10
- [sansan0/TrendRadar](https://github.com/sansan0/TrendRadar) ★62.9k — ⭐AI-driven public opinion & trend monitor with multi-platform aggregation, RSS, and smart alerts.🎯 告别信息过载，你的 AI 舆情监控助手与热点筛选工具！聚合多平台热点 +  RSS · Python · GPL-3.0 · 2026-10
- [MemPalace/mempalace](https://github.com/MemPalace/mempalace) ★59.6k — The best-benchmarked open-source AI memory system. And it's free. · Python · MIT · 2026-10
- [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) ★53.6k — Chrome DevTools for coding agents · TypeScript · Apache-2.0 · 2026-10
- [mudler/LocalAI](https://github.com/mudler/LocalAI) ★49.6k — LocalAI is the open-source AI engine. Run any model - LLMs, vision, voice, image, video - on any hardware. No GPU required. · Go · MIT · 2026-10
- [siyuan-note/siyuan](https://github.com/siyuan-note/siyuan) ★46.8k — An open-source, privacy-first, self-hosted knowledge workspace where humans and AI agents work together 开源、隐私优先、自托管的知识工作空间，让人与智能体在此协作 · TypeScript · AGPL-3.0 · 2026-10
- [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) ★46.7k — High-performance code intelligence MCP server. Indexes codebases into a persistent knowledge graph — average repo in milliseconds. 162 langu · C · MIT · 2026-10
- [LibreChat-AI/LibreChat](https://github.com/LibreChat-AI/LibreChat) ★45.8k — Enhanced ChatGPT Clone: Features Agents, MCP, Skills, DeepSeek, Anthropic, AWS, OpenAI, Responses API, Azure, Groq, o1, GPT-5, Mistral, Open · TypeScript · MIT · 2026-10
- [Kong/kong](https://github.com/Kong/kong) ★44.3k — 🦍 The API and AI Gateway · Lua · Apache-2.0 · 2026-10
- [drawdb-io/drawdb](https://github.com/drawdb-io/drawdb) ★40.0k — Free, simple, and intuitive online database diagram editor and SQL generator. · JavaScript · AGPL-3.0 · 2026-10
- [mindsdb/mindshub](https://github.com/mindsdb/mindshub) ★39.8k — The unified workspace where open-source models get things done for you. · Makefile · MIT · 2026-10
- [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) ★39.6k — Official, Anthropic-managed directory of high quality Claude Code Plugins. · Python · Apache-2.0 · 2026-10
- [patchy631/ai-engineering-hub](https://github.com/patchy631/ai-engineering-hub) ★38.3k — In-depth tutorials on LLMs, RAGs and real-world AI agent applications. · Jupyter Notebook · MIT · 2026-10
- [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) ★38.2k — Playwright MCP server · TypeScript · Apache-2.0 · 2026-10
- [PDFMathTranslate/PDFMathTranslate](https://github.com/PDFMathTranslate/PDFMathTranslate) ★37.6k — [EMNLP 2025 Demo] PDF scientific paper translation with preserved formats - 基于 AI 完整保留排版的 PDF 文档全文双语翻译，支持 Google/DeepL/Ollama/OpenAI 等服务，提供  · Python · AGPL-3.0 · 2026-10
- [DayuanJiang/next-ai-draw-io](https://github.com/DayuanJiang/next-ai-draw-io) ★36.3k — Draw and edit draw.io diagrams by chatting with an AI. Web app, desktop app, and an MCP server for Claude Code, Cursor, Codex and VS Code. · TypeScript · Apache-2.0 · 2026-10
- [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi) ★35.6k — ⌥ Coding agent with the IDE wired in. Built by Stencil Labs. · TypeScript · MIT · 2026-10
- [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) ★35.6k — "Vibe-Trading: Your Personal Trading Agent" · Python · MIT · 2026-10
- [github/github-mcp-server](https://github.com/github/github-mcp-server) ★33.7k — GitHub's official MCP Server · Go · MIT · 2026-10
- [tirth8205/code-review-graph](https://github.com/tirth8205/code-review-graph) ★32.2k — Local-first code intelligence graph for MCP and CLI. Builds a persistent map of your codebase so AI coding tools read only what matters, wit · Python · MIT · 2026-10
- [78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) ★31.2k — An MCP-based chatbot | 一个基于MCP的聊天机器人 · C++ · MIT · 2026-10
- [ahujasid/mcp-for-blender](https://github.com/ahujasid/mcp-for-blender) ★31.0k — Community plugin to control Blender 3D with any LLM of your choice. Not affiliated with the official Blender Foundation. · Python · MIT · 2026-10

### MCP servers (30)

- [reactive-resume/reactive-resume](https://github.com/reactive-resume/reactive-resume) ★44.4k — A one-of-a-kind resume builder that keeps your privacy in mind. Completely secure, customizable, portable, open-source and free forever. Try · TypeScript · MIT · 2026-10
- [modelscope/FunASR](https://github.com/modelscope/FunASR) ★20.7k — Open-source speech recognition toolkit for training, inference, streaming ASR, VAD, punctuation, speaker diarization pipelines, and OpenAI-c · Python · MIT · 2026-10
- [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) ★20.7k — 🚀 抖音、TikTok 数据采集与无水印视频下载 API，自托管，支持 MCP 调用与 Docker 一键部署。| Self-hosted TikTok & Douyin scraper and no-watermark video downloader — async REST · Python · Apache-2.0 · 2026-10
- [xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) ★16.3k — MCP for xiaohongshu.com · Go · Apache-2.0 · 2026-10
- [budtmo/docker-android](https://github.com/budtmo/docker-android) ★16.0k — Android in docker solution with noVNC supported, video recording, mcp server and AI-agent · Python · NOASSERTION · 2026-10
- [open-metadata/OpenMetadata](https://github.com/open-metadata/OpenMetadata) ★15.5k — The Open Context Layer for Data and AI ,  OpenMetadata is the open platform for building trusted data context and business semantics for hum · TypeScript · Apache-2.0 · 2026-10
- [yusufkaraaslan/Skill_Seekers](https://github.com/yusufkaraaslan/Skill_Seekers) ★15.2k — Convert documentation websites, GitHub repositories, and PDFs into Claude AI skills with automatic conflict detection · Python · MIT · 2026-09
- [modelcontextprotocol/typescript-sdk](https://github.com/modelcontextprotocol/typescript-sdk) ★13.6k — The official TypeScript SDK for Model Context Protocol servers and clients · TypeScript · NOASSERTION · 2026-10
- [ccfos/nightingale](https://github.com/ccfos/nightingale) ★13.4k — Open-source, self-hosted alerting for metrics, logs, and databases. Includes a built-in AI agent and MCP server. · Go · Apache-2.0 · 2026-10
- [JoeanAmier/XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader) ★13.0k — 小红书（XiaoHongShu、RedNote）链接提取/作品采集工具 · JavaScript · GPL-3.0 · 2026-10
- [mrexodia/ida-pro-mcp](https://github.com/mrexodia/ida-pro-mcp) ★12.9k — AI-powered reverse engineering assistant that bridges IDA Pro with language models through MCP. · Python · MIT · 2026-09
- [0x4m4/hexstrike-ai](https://github.com/0x4m4/hexstrike-ai) ★12.8k — HexStrike AI MCP Agents is an advanced MCP server that lets AI agents (Claude, GPT, Copilot, etc.) autonomously run 150+ cybersecurity tools · Python · MIT · 2026-08
- [tadata-org/fastapi_mcp](https://github.com/tadata-org/fastapi_mcp) ★12.0k — Expose your FastAPI endpoints as Model Context Protocol (MCP) tools, with Auth! · Python · MIT · 2025-11
- [0xJacky/nginx-ui](https://github.com/0xJacky/nginx-ui) ★11.6k — Yet another WebUI for Nginx · Go · AGPL-3.0 · 2026-10
- [apify/apify-mcp-server](https://github.com/apify/apify-mcp-server) ★11.5k — The Apify MCP server enables your AI agents to extract data from social media, search engines, maps, e-commerce sites, or any other website  · TypeScript · MIT · 2026-10
- [xinnan-tech/xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server) ★10.9k — 本项目为xiaozhi-esp32提供后端服务，帮助您快速搭建ESP32设备控制服务器。Backend service for xiaozhi-esp32, helps you quickly build an ESP32 device control server. · JavaScript · MIT · 2026-10
- [mcp-use/mcp-use](https://github.com/mcp-use/mcp-use) ★10.8k — The fullstack MCP framework to develop MCP Apps for ChatGPT / Claude & MCP Servers for AI Agents. · TypeScript · MIT · 2026-10
- [Agents365-ai/drawio-skill](https://github.com/Agents365-ai/drawio-skill) ★10.2k — Agent skill that turns natural language, code, Terraform/K8s, SQL, OpenAPI, AsyncAPI, Protobuf and GraphQL sources into editable, tested dra · Python · MIT · 2026-10
- [trailhq/Trail-Code](https://github.com/trailhq/Trail-Code) ★10.1k — Turbocharge Claude Code, Cursor, Codex, Gemini & every coding agent: faster, cheaper, with contextual understanding specific to your codebas · TypeScript · MIT · 2026-10
- [awslabs/mcp](https://github.com/awslabs/mcp) ★9.8k — Open source MCP Servers for AWS · Python · Apache-2.0 · 2026-10
- [openstatusHQ/openstatus](https://github.com/openstatusHQ/openstatus) ★9.2k — Open-source status page, incident response and uptime monitoring · TypeScript · AGPL-3.0 · 2026-10
- [firerpa/lamda](https://github.com/firerpa/lamda) ★8.6k — Android Full-Stack Device Control Platform: WebRTC/H.264 remote desktop, UI/OCR/image-matching automation, one-click MITM, built-in Frida, p · Python · MIT · 2026-09
- [osaurus-ai/osaurus](https://github.com/osaurus-ai/osaurus) ★8.1k — Own your AI. The native macOS harness for AI agents -- any model, persistent memory, autonomous execution, cryptographic identity. Built in  · Swift · MIT · 2026-10
- [yzfly/Awesome-MCP-ZH](https://github.com/yzfly/Awesome-MCP-ZH) ★7.7k — MCP 资源精选， MCP指南，Claude MCP，MCP Servers, MCP Clients · MIT · 2026-10
- [firecrawl/firecrawl-mcp-server](https://github.com/firecrawl/firecrawl-mcp-server) ★7.6k — 🔥 Official Firecrawl MCP Server - Adds powerful web scraping and search to Cursor, Claude and any other LLM clients. · JavaScript · MIT · 2026-10
- [devlikeapro/waha](https://github.com/devlikeapro/waha) ★7.6k — WAHA - WhatsApp HTTP API (REST API) that you can configure in a click! Multiple engines: WEBJS (browser based), NOWEB (websocket nodejs), GO · TypeScript · Apache-2.0 · 2026-10
- [AgentDeskAI/browser-tools-mcp](https://github.com/AgentDeskAI/browser-tools-mcp) ★7.3k — Monitor browser logs directly from Cursor and other MCP compatible IDEs. · TypeScript · MIT · 2026-08
- [Zipstack/unstract](https://github.com/Zipstack/unstract) ★7.3k — LLM-Driven Extraction of Unstructured Data — Built for API Deployments & ETL Pipeline Workflows · Python · AGPL-3.0 · 2026-10
- [BrowserMCP/mcp](https://github.com/BrowserMCP/mcp) ★7.2k — Browser MCP is a Model Context Provider (MCP) server that allows AI applications to control your browser · TypeScript · Apache-2.0 · 2025-04
- [getsentry/MobileBuildMCP](https://github.com/getsentry/MobileBuildMCP) ★6.5k — A Model Context Protocol (MCP) server and CLI that provides tools for agent use when working on iOS and macOS projects. · TypeScript · MIT · 2026-10

### LLM tooling (broad) (30)

- [ollama/ollama](https://github.com/ollama/ollama) ★183.4k — Get up and running with Kimi, GLM, MiniMax, DeepSeek, gpt-oss, Qwen, Gemma and other models. · Go · MIT · 2026-10
- [f/prompts.chat](https://github.com/f/prompts.chat) ★173.1k — f.k.a. Awesome ChatGPT Prompts. Share, discover, and collect prompts from the community. Free and open source — self-host for your organizat · HTML · NOASSERTION · 2026-10
- [huggingface/transformers](https://github.com/huggingface/transformers) ★167.8k — 🤗 Transformers: the model-definition framework for state-of-the-art machine learning models in text, vision, audio, and multimodal models, f · Python · Apache-2.0 · 2026-10
- [harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) ★131.9k — 利用 AI 大模型和自动化工作流，根据主题或关键词一键生成高清短视频。Generate HD short videos from a topic or keyword with an automated AI workflow. · Python · MIT · 2026-10
- [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) ★112.9k — 🪨 why use many token when few token do trick. Viral skill + proxy for coding agents that cuts 65% of tokens by talking like a caveman. · Go · Apache-2.0 · 2026-10
- [rasbt/LLMs-from-scratch](https://github.com/rasbt/LLMs-from-scratch) ★106.6k — Implement a ChatGPT-like LLM in PyTorch from scratch, step by step · Jupyter Notebook · NOASSERTION · 2026-10
- [vllm-project/vllm](https://github.com/vllm-project/vllm) ★93.9k — A high-throughput and memory-efficient inference and serving engine for LLMs · Python · Apache-2.0 · 2026-10
- [mlabonne/llm-course](https://github.com/mlabonne/llm-course) ★83.6k — Course to get into Large Language Models (LLMs) with roadmaps and Colab notebooks. · Apache-2.0 · 2026-02
- [rtk-ai/rtk](https://github.com/rtk-ai/rtk) ★83.6k — CLI proxy that reduces LLM token consumption by 60-90% on common dev commands. Single Rust binary, zero dependencies · Rust · Apache-2.0 · 2026-10
- [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) ★66.5k — LLM 驱动的多市场股票智能分析系统：多源行情、实时新闻、决策看板与自动推送，支持零成本定时运行。  LLM-powered multi-market stock analysis system with multi-source market data, real-time n · Python · MIT · 2026-10
- [BerriAI/litellm](https://github.com/BerriAI/litellm) ★61.4k — The fastest, litest AI Gateway. Rust core with Python SDK. Call 100+ LLM APIs in OpenAI (or native) format with cost tracking, guardrails, l · Python · NOASSERTION · 2026-10
- [pathwaycom/serviette](https://github.com/pathwaycom/serviette) ★58.8k — Ready-to-run cloud templates for RAG, AI pipelines, and enterprise search with live data. 🐳Docker-friendly.⚡Always in sync with Sharepoint,  · Python · MIT · 2026-10
- [blader/humanizer](https://github.com/blader/humanizer) ★57.4k — Agent skill that removes signs of AI-generated writing from text · Python · MIT · 2026-09
- [run-llama/llama_index](https://github.com/run-llama/llama_index) ★52.5k — LlamaIndex is the document processing platform for AI · Python · MIT · 2026-10
- [paperless-ngx/paperless-ngx](https://github.com/paperless-ngx/paperless-ngx) ★46.7k — A community-supported supercharged document management system: scan, index and archive all your documents · Python · GPL-3.0 · 2026-10
- [milvus-io/milvus](https://github.com/milvus-io/milvus) ★46.4k — Milvus is a high-performance, cloud-native vector database built for scalable vector ANN search · Go · Apache-2.0 · 2026-10
- [janhq/jan](https://github.com/janhq/jan) ★45.0k — Jan is an open source alternative to ChatGPT that runs 100% offline on your computer. · Rust · NOASSERTION · 2026-10
- [ray-project/ray](https://github.com/ray-project/ray) ★44.0k — Ray is an AI compute engine. Ray consists of a core distributed runtime and a set of AI Libraries for accelerating ML workloads. · Python · Apache-2.0 · 2026-10
- [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) ★40.2k — [EMNLP2025] LightRAG: Simple and Fast Retrieval-Augmented Generation · Python · MIT · 2026-10
- [The-Vibe-Company/quivr](https://github.com/The-Vibe-Company/quivr) ★39.6k — An open-source engine that turns continuous content streams into search and monitoring. Durable ingestion, hybrid search, alerts, and plugin · Go · MIT · 2026-10
- [google/langextract](https://github.com/google/langextract) ★39.0k — A Python library for extracting structured information from unstructured text using LLMs with precise source grounding and interactive visua · Python · Apache-2.0 · 2026-10
- [lyogavin/airllm](https://github.com/lyogavin/airllm) ★38.9k — AirLLM 2.8T LLM inference with single 4GB GPU · Jupyter Notebook · Apache-2.0 · 2026-10
- [chatchat-space/Langchain-Chatchat](https://github.com/chatchat-space/Langchain-Chatchat) ★38.7k — Langchain-Chatchat（原Langchain-ChatGLM）基于 Langchain 与 ChatGLM, Qwen 与 Llama 等语言模型的 RAG 与 Agent 应用 | Langchain-Chatchat (formerly langchain-Ch · Python · Apache-2.0 · 2025-11
- [linshenkx/prompt-optimizer](https://github.com/linshenkx/prompt-optimizer) ★38.2k — An AI prompt optimizer for writing better prompts and getting better AI results. · TypeScript · NOASSERTION · 2026-10
- [AlexsJones/llmfit](https://github.com/AlexsJones/llmfit) ★38.0k — Hundreds of models & providers. One command to find what runs on your hardware. · Rust · MIT · 2026-10
- [sgl-project/sglang](https://github.com/sgl-project/sglang) ★37.2k — SGLang is a high-performance serving framework for large language models and multimodal models. · Python · Apache-2.0 · 2026-10
- [microsoft/graphrag](https://github.com/microsoft/graphrag) ★36.4k — A modular graph-based Retrieval-Augmented Generation (RAG) system · Python · MIT · 2026-10
- [langfuse/langfuse](https://github.com/langfuse/langfuse) ★35.9k — 🪢 Open source agent evals & observability: Trace, evaluate, and improve LLM applications with one open platform. · TypeScript · NOASSERTION · 2026-10
- [p-e-w/heretic](https://github.com/p-e-w/heretic) ★35.5k — Fully automatic censorship removal for language models · Python · AGPL-3.0 · 2026-10
- [SillyTavern/SillyTavern](https://github.com/SillyTavern/SillyTavern) ★34.5k — LLM Frontend for Power Users. · JavaScript · AGPL-3.0 · 2026-10

### Browser automation (30)

- [lightpanda-io/browser](https://github.com/lightpanda-io/browser) ★36.6k — Lightpanda: the headless browser designed for AI and automation · Zig · AGPL-3.0 · 2026-10
- [h4ckf0r0day/obscura](https://github.com/h4ckf0r0day/obscura) ★29.0k — The headless browser for AI agents and web scraping · Rust · Apache-2.0 · 2026-10
- [Skyvern-AI/skyvern](https://github.com/Skyvern-AI/skyvern) ★23.2k — Automate browser based workflows with AI · Python · AGPL-3.0 · 2026-10
- [AutomaApp/automa](https://github.com/AutomaApp/automa) ★21.7k — A browser extension for automating your browser by connecting blocks · Vue · NOASSERTION · 2026-03
- [getmaxun/maxun](https://github.com/getmaxun/maxun) ★17.9k — Turn any website into a structured API. Extract, automate, search and monitor the web. · TypeScript · AGPL-3.0 · 2026-10
- [citrolabs/ego-lite](https://github.com/citrolabs/ego-lite) ★17.5k — The fastest browser for AI agents to run browser automation, built for sharing your logged-in browser state with your AI agents, like Codex  · JavaScript · MIT · 2026-10
- [browser-use/web-ui](https://github.com/browser-use/web-ui) ★16.6k — 🖥️ Run AI Agent in your browser. · Python · MIT · 2026-09
- [lsdefine/GenericAgent](https://github.com/lsdefine/GenericAgent) ★14.3k — Self-evolving agent: grows skill tree from 3.3K-line seed, achieving full system control with 6x less token consumption · Python · MIT · 2026-10
- [jo-inc/camofox-browser](https://github.com/jo-inc/camofox-browser) ★11.6k — Stealth headless browser for AI agents — bypass Cloudflare, bot detection, and anti-scraping. Drop-in Puppeteer/Playwright replacement. · JavaScript · MIT · 2026-10
- [NopeCHALLC/nopecha-extension](https://github.com/NopeCHALLC/nopecha-extension) ★11.0k — Automated CAPTCHA solver for your browser. Works with Selenium, Puppeteer, Playwright, and more. · MIT · 2026-10
- [pinchtab/pinchtab](https://github.com/pinchtab/pinchtab) ★10.4k — High-performance browser automation bridge and multi-instance orchestrator with advanced stealth injection and real-time dashboard. · Go · MIT · 2026-10
- [steel-dev/steel-browser](https://github.com/steel-dev/steel-browser) ★7.8k — 🔥 Open Source Browser API for AI Agents & Apps. Steel Browser is a batteries-included browser sandbox that lets you automate the web without · TypeScript · Apache-2.0 · 2026-10
- [mishushakov/llm-scraper](https://github.com/mishushakov/llm-scraper) ★6.9k — Turn any webpage into structured data using LLMs · TypeScript · MIT · 2026-09
- [CopilotKit/OpenBot](https://github.com/CopilotKit/OpenBot) ★6.5k — Open-source AI coworkers that each get a computer of their own: a browser, files and tools, with every action decided before it happens and  · TypeScript · MIT · 2026-10
- [MontFerret/ferret](https://github.com/MontFerret/ferret) ★6.0k — Declarative data automation language and Go runtime for structured extraction workflows. · Go · Apache-2.0 · 2026-10
- [FellouAI/eko](https://github.com/FellouAI/eko) ★5.0k — Eko (Eko Keeps Operating) - Build Production-ready Agentic Workflow with Natural Language - eko.fellou.ai · TypeScript · MIT · 2026-03
- [browser-use/workflow-use](https://github.com/browser-use/workflow-use) ★4.2k — ⚙️ Create and run workflows (RPA 2.0) · Python · AGPL-3.0 · 2026-10
- [zhom/donutbrowser](https://github.com/zhom/donutbrowser) ★4.1k — The Most Private Anti-Detect Browser 🍩 · Rust · AGPL-3.0 · 2026-10
- [miyakogi/pyppeteer](https://github.com/miyakogi/pyppeteer) ★3.6k — Headless chrome/chromium automation library (unofficial port of puppeteer) · Python · NOASSERTION · 2021-08
- [mxschmitt/playwright-go](https://github.com/mxschmitt/playwright-go) ★3.5k — Playwright for Go a browser automation library to control Chromium, Firefox and WebKit with a single API. · Go · MIT · 2026-09
- [AtomicBot-ai/atomic-agent](https://github.com/AtomicBot-ai/atomic-agent) ★3.4k — Atomic Agent is a local-first AI agent. Runs open-weight models on your own machine via llama.cpp. · TypeScript · MIT · 2026-10
- [feder-cr/invisible_playwright](https://github.com/feder-cr/invisible_playwright) ★3.2k — Playwright that anti-bots cannot see, so no captchas: same API, anti-detect stealth headless Firefox, undetected fingerprint, bypass bot det · Python · MIT · 2026-10
- [keon/browser-control](https://github.com/keon/browser-control) ★3.2k — A tiny, fast Rust CLI that drives a real browser over the Chrome DevTools Protocol — built for coding agents. · Rust · MIT · 2026-08
- [feder-cr/invisible_selenium](https://github.com/feder-cr/invisible_selenium) ★3.1k — Selenium that anti-bots cannot see, so no captchas: same API, anti-detect stealth headless Firefox, undetected fingerprint, bypass bot detec · Python · MIT · 2026-10
- [zhizhuodemao/js-reverse-mcp](https://github.com/zhizhuodemao/js-reverse-mcp) ★3.0k — AI Agent-first JS 逆向 MCP Server：有头 Chrome 调试、断点、网络/WebSocket 分析、Patchright 反检测，可选 CloakBrowser。 · TypeScript · Apache-2.0 · 2026-09
- [agentrhq/webcmd](https://github.com/agentrhq/webcmd) ★2.7k — Self-learning agent browser · TypeScript · Apache-2.0 · 2026-09
- [brightdata/brightdata-mcp](https://github.com/brightdata/brightdata-mcp) ★2.7k — A powerful Model Context Protocol (MCP) server that provides an all-in-one solution for public web access. · JavaScript · MIT · 2026-10
- [saifyxpro/HeadlessX](https://github.com/saifyxpro/HeadlessX) ★2.3k — The undetected self-hosted browser automation platform. Powered by Camoufox (Firefox) for 0% detection rates. Built for speed, privacy, and  · TypeScript · NOASSERTION · 2026-10
- [vibheksoni/stealth-browser-mcp](https://github.com/vibheksoni/stealth-browser-mcp) ★2.2k — Stealth browser automation for AI agents over MCP and the Chrome DevTools Protocol: navigation, network hooks, DOM extraction, and pixel-acc · Python · MIT · 2026-10
- [A9T9/RPA](https://github.com/A9T9/RPA) ★2.1k — Browser and desktop automation with an MCP server for AI assistants. Record macros or write JavaScript to automate websites, extract data, a · TypeScript · NOASSERTION · 2026-10

### Headless browsers (27)

- [ariya/phantomjs](https://github.com/ariya/phantomjs) ★29.4k — Scriptable Headless Browser · C++ · BSD-3-Clause · 2022-11
- [ArchiveBox/ArchiveBox](https://github.com/ArchiveBox/ArchiveBox) ★28.8k — 🗃 Open source self-hosted web archiving. Takes URLs/browser history/bookmarks/Pocket/Pinboard/etc., saves HTML, JS, PDFs, media, and more... · Python · MIT · 2026-10
- [berstend/puppeteer-extra](https://github.com/berstend/puppeteer-extra) ★7.4k — 💯  Teach puppeteer new tricks through plugins. · JavaScript · MIT · 2024-07
- [scrapy-plugins/scrapy-playwright](https://github.com/scrapy-plugins/scrapy-playwright) ★1.5k — 🎭 Playwright integration for Scrapy · Python · BSD-3-Clause · 2026-10
- [ProxyShard/ShardBrowser](https://github.com/ProxyShard/ShardBrowser) ★1.3k — Free, open-source anti-detect browser launcher for web scraping and multi-accounting. By the ProxyShard team. Engine-level fingerprint spoof · TypeScript · MIT · 2026-09
- [cosmiciron/vmprint](https://github.com/cosmiciron/vmprint) ★673 — This layout engine can solve the hardest layout problems imaginable. Its output is DTP grade and deterministic. It's faster than engines wri · JavaScript · Apache-2.0 · 2026-08
- [oxylabs/agent-browser](https://github.com/oxylabs/agent-browser) ★662 — Execute complex automation scripts via remote cloud sessions , featuring integrated residential proxies , automated CAPTCHA solving , and na · NOASSERTION · 2026-09
- [vakra-dev/reader](https://github.com/vakra-dev/reader) ★557 — Open source web infrastructure for AI. Scrape, crawl, and automate the web, clean markdown, browser sessions, ready for your agents. · TypeScript · Apache-2.0 · 2026-10
- [vgalin/html2image](https://github.com/vgalin/html2image) ★455 — A package acting as a wrapper around the headless mode of existing web browsers to generate images from URLs and from HTML+CSS strings or fi · Python · MIT · 2026-03
- [dondai44423/bladebro](https://github.com/dondai44423/bladebro) ★314 — A Fully free agentic browser driver for AI , few tools, full control, real stealth, top-tier token efficiency. · Rust · Apache-2.0 · 2026-10
- [themrsami/scribd-downloader](https://github.com/themrsami/scribd-downloader) ★223 — Download Scribd documents as PDF for free. Fast, automated, headless Chrome browser - no login required. · Python · NOASSERTION · 2026-07
- [rayobyte-data/rayobrowse](https://github.com/rayobyte-data/rayobrowse) ★212 — Stealth Chromium browser for web scraping and AI agents. · Python · MIT · 2026-07
- [MarketingPipeline/Python-Selenium-Action](https://github.com/MarketingPipeline/Python-Selenium-Action) ★185 — Run Selenium with Python via Github Actions using Headless or Non-Headless browsers! · Python · MIT · 2025-05
- [watzon/marionette](https://github.com/watzon/marionette) ★184 — Selenium alternative for Crystal. Browser manipulation without the Java overhead. · Crystal · MIT · 2023-11
- [swimmwatch/cloakbrowser-mcp](https://github.com/swimmwatch/cloakbrowser-mcp) ★167 — ⚡ CloakBrowser MCP server for AI agents: Playwright-powered browsing, clean tool forwarding, Docker support, and multi-session HTTP transpor · TypeScript · MIT · 2026-10
- [html2rss/html2rss](https://github.com/html2rss/html2rss) ★165 — 📰 Build RSS 2.0 feeds from websites (and JSON APIs) automatically or with a few CSS selectors. · Ruby · MIT · 2026-10
- [sjdirect/abotx](https://github.com/sjdirect/abotx) ★141 — Cross Platform C# Web crawler framework, headless browser, parallel crawler. Please star this project! +1. · C# · NOASSERTION · 2023-10
- [praetorian-inc/vespasian](https://github.com/praetorian-inc/vespasian) ★138 — API discovery tool that maps attack surfaces from captured traffic and generates specs for REST, GraphQL, SOAP, and WebSocket APIs · Go · Apache-2.0 · 2026-10
- [PulseBeat02/mcav](https://github.com/PulseBeat02/mcav) ★132 — Java multimedia framework for video, audio, browsers and VMs · Java · GPL-3.0 · 2026-10
- [redf0x1/camofox-mcp](https://github.com/redf0x1/camofox-mcp) ★118 — Anti-detection browser MCP server for AI agents — navigate, interact, and automate the web without getting blocked · TypeScript · MIT · 2026-09
- [yfedoseev/browser_oxide](https://github.com/yfedoseev/browser_oxide) ★117 — Stealth headless browser engine in Rust — native BoringSSL TLS/JA4 fingerprint, real JS via deno_core, no Chromium, no CDP. Python + MCP bin · Rust · NOASSERTION · 2026-07
- [atagon-GmbH/kogiqa-mcp](https://github.com/atagon-GmbH/kogiqa-mcp) ★96 — This web browser has been designed to help your agent debug and develop complex web applications. (MCP Server) · JavaScript · MIT · 2026-10
- [anxuanzi/bua](https://github.com/anxuanzi/bua) ★85 — AI-powered browser automation for Go — describe tasks in plain English, let the agent handle the clicks. · Go · MIT · 2026-01
- [CoderLuii/HolyCode](https://github.com/CoderLuii/HolyCode) ★65 — AI coding workstation: OpenCode + Claude subscription support + 30+ tools + headless browser + multi-agent orchestration · Python · MIT · 2026-10
- [scrapfly/python-scrapfly](https://github.com/scrapfly/python-scrapfly) ★62 — Official Python SDK for the Scrapfly platform: web scraping, screenshots, AI extraction, crawling, and a remote anti-bot browser. Integrates · Python · NOASSERTION · 2026-10
- [elacuesta/scrapy-pyppeteer](https://github.com/elacuesta/scrapy-pyppeteer) ★58 — Pyppeteer integration for Scrapy · Python · BSD-3-Clause · 2021-02
- [axnoller32/AntiDetect-26](https://github.com/axnoller32/AntiDetect-26) ★56 — Multi Profile + ByPass + Free Prx + AI · MIT · 2026-04

### Chromium tooling (30)

- [microsoft/playwright](https://github.com/microsoft/playwright) ★97.8k — Playwright is a framework for Web Testing and Automation. It allows testing Chromium, Firefox and WebKit with a single API. · TypeScript · Apache-2.0 · 2026-10
- [gorhill/uBlock](https://github.com/gorhill/uBlock) ★68.6k — uBlock Origin - An efficient blocker for Chromium and Firefox. Fast and lean. · JavaScript · GPL-3.0 · 2026-10
- [ungoogled-software/ungoogled-chromium](https://github.com/ungoogled-software/ungoogled-chromium) ★28.0k — Google Chromium, sans integration with Google · Python · BSD-3-Clause · 2026-10
- [chromium/chromium](https://github.com/chromium/chromium) ★25.0k — The official GitHub mirror of the Chromium source · BSD-3-Clause · 2026-10
- [fathyb/carbonyl](https://github.com/fathyb/carbonyl) ★19.5k — Chromium running inside your terminal · Rust · BSD-3-Clause · 2024-07
- [cefsharp/CefSharp](https://github.com/cefsharp/CefSharp) ★10.3k — .NET (WPF and Windows Forms) bindings for the Chromium Embedded Framework · C# · NOASSERTION · 2026-10
- [dnschneid/crouton](https://github.com/dnschneid/crouton) ★8.6k — Chromium OS Universal Chroot Environment (EOL) · Shell · BSD-3-Clause · 2025-03
- [std-microblock/chromatic](https://github.com/std-microblock/chromatic) ★8.5k — Universal modifier for Chromium/V8 | 广谱注入 Chromium/V8 的通用修改器 · C++ · NOASSERTION · 2026-03
- [Alex313031/thorium](https://github.com/Alex313031/thorium) ★7.6k — Chromium fork named after radioactive element No. 90. Source code and Linux releases. Windows/MacOS/ARM builds served in different repos, li · C++ · BSD-3-Clause · 2026-10
- [autoscrape-labs/pydoll](https://github.com/autoscrape-labs/pydoll) ★7.1k — Pydoll is a library for automating chromium-based browsers without a WebDriver, offering realistic interactions. · HTML · MIT · 2026-10
- [bromite/bromite](https://github.com/bromite/bromite) ★6.3k — Bromite is a Chromium fork with ad blocking and privacy enhancements; take back your browser! · GPL-3.0 · 2024-01
- [chromiumembedded/cef](https://github.com/chromiumembedded/cef) ★4.8k — Chromium Embedded Framework (CEF). A simple framework for embedding Chromium-based browsers in other applications. · C++ · NOASSERTION · 2026-10
- [kiwibrowser/src.next](https://github.com/kiwibrowser/src.next) ★4.0k — Source-code for Kiwi Next, a Kiwi Browser auto-rebased with latest Chromium · C++ · BSD-3-Clause · 2025-06
- [pyppeteer/pyppeteer](https://github.com/pyppeteer/pyppeteer) ★3.9k — Headless chrome/chromium automation library (unofficial port of puppeteer) · Python · NOASSERTION · 2024-06
- [Experience-Monks/devtool](https://github.com/Experience-Monks/devtool) ★3.7k — [OBSOLETE] runs Node.js programs through Chromium DevTools · JavaScript · MIT · 2018-05
- [NeverDecaf/chromium-web-store](https://github.com/NeverDecaf/chromium-web-store) ★3.3k — Allows adding extensions from chrome web store on ungoogled-chromium. Also adds semi-automatic extension updating. · JavaScript · MIT · 2026-09
- [alixaxel/chrome-aws-lambda](https://github.com/alixaxel/chrome-aws-lambda) ★3.3k — Chromium Binary for AWS Lambda and Google Cloud Functions · TypeScript · MIT · 2024-09
- [cztomczak/cefpython](https://github.com/cztomczak/cefpython) ★3.2k — Python bindings for the Chromium Embedded Framework (CEF) · C++ · NOASSERTION · 2026-10
- [adryfish/fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium) ★3.2k — An open source fingerprint browser based on Ungoogled Chromium. 指纹浏览器 隐私浏览器 · BSD-3-Clause · 2026-10
- [JackyAndroid/AndroidChromium](https://github.com/JackyAndroid/AndroidChromium) ★3.1k — chrome browser of android version from chromium open project · Java · Apache-2.0 · 2020-09
- [chromium/badssl.com](https://github.com/chromium/badssl.com) ★3.1k — :lock: Memorable site for testing clients against bad SSL configs. · HTML · Apache-2.0 · 2026-06
- [rust-headless-chrome/rust-headless-chrome](https://github.com/rust-headless-chrome/rust-headless-chrome) ★3.0k — A high-level API to control headless Chrome or Chromium over the DevTools Protocol. It is the Rust equivalent of Puppeteer, a Node library m · Rust · MIT · 2026-06
- [adieuadieu/serverless-chrome](https://github.com/adieuadieu/serverless-chrome) ★2.9k — 🌐 Run headless Chrome/Chromium on AWS Lambda · JavaScript · MIT · 2022-12
- [breach/thrust](https://github.com/breach/thrust) ★2.8k — Chromium-based cross-platform / cross-language application framework · C++ · MIT · 2024-01
- [chrome-php/chrome](https://github.com/chrome-php/chrome) ★2.7k — Instrument headless chrome/chromium instances from PHP · PHP · MIT · 2026-07
- [ungoogled-software/ungoogled-chromium-windows](https://github.com/ungoogled-software/ungoogled-chromium-windows) ★2.6k — Windows packaging for ungoogled-chromium · Python · BSD-3-Clause · 2026-10
- [Alex313031/Thorium-Win](https://github.com/Alex313031/Thorium-Win) ★2.5k — Chromium fork for Windows named after radioactive element No. 90; Windows builds of https://github.com/Alex313031/Thorium · Batchfile · BSD-3-Clause · 2026-10
- [webmproject/libwebp](https://github.com/webmproject/libwebp) ★2.4k — Mirror only. Please do not send pull requests. See https://chromium.googlesource.com/webm/libwebp/+/HEAD/CONTRIBUTING.md. · C · BSD-3-Clause · 2026-10
- [macbre/phantomas](https://github.com/macbre/phantomas) ★2.3k — Headless Chromium-based web performance metrics collector and monitoring tool · JavaScript · BSD-2-Clause · 2026-10
- [1995eaton/chromium-vim](https://github.com/1995eaton/chromium-vim) ★2.3k — Vim bindings for Google Chrome. · JavaScript · MIT · 2022-10

### Electron apps & tooling (30)

- [microsoft/vscode](https://github.com/microsoft/vscode) ★193.7k — Visual Studio Code · TypeScript · MIT · 2026-10
- [electron/electron](https://github.com/electron/electron) ★123.4k — :electron: Build cross-platform desktop apps with JavaScript, HTML, and CSS · C++ · MIT · 2026-10
- [toeverything/AFFiNE](https://github.com/toeverything/AFFiNE) ★73.6k — There can be more than Notion and Miro. AFFiNE(pronounced [ə‘fain]) is a next-gen knowledge base that brings planning, sorting and creating  · TypeScript · NOASSERTION · 2026-10
- [marktext/marktext](https://github.com/marktext/marktext) ★62.7k — 📝A simple and elegant markdown editor, available for Linux, macOS and Windows. · TypeScript · MIT · 2026-10
- [atom/atom](https://github.com/atom/atom) ★60.7k — :atom: The hackable text editor · JavaScript · MIT · 2023-01
- [agalwood/Motrix](https://github.com/agalwood/Motrix) ★56.9k — A full-featured download manager. · TypeScript · NOASSERTION · 2026-10
- [laurent22/joplin](https://github.com/laurent22/joplin) ★56.8k — Joplin - the privacy-focused note taking app with sync capabilities for Windows, macOS, Linux, Android and iOS. · TypeScript · NOASSERTION · 2026-10
- [lyswhut/lx-music-desktop](https://github.com/lyswhut/lx-music-desktop) ★54.5k — 一个基于 Electron 的音乐软件 · TypeScript · Apache-2.0 · 2026-10
- [upscayl/upscayl](https://github.com/upscayl/upscayl) ★50.6k — 🆙 Upscayl - #1 Free and Open Source AI Image Upscaler for Linux, MacOS and Windows. · TypeScript · AGPL-3.0 · 2026-10
- [GitSquared/edex-ui](https://github.com/GitSquared/edex-ui) ★45.0k — A cross-platform, customizable science fiction terminal emulator with advanced monitoring & touchscreen support. · JavaScript · GPL-3.0 · 2021-10
- [siddharthvaddem/openscreen](https://github.com/siddharthvaddem/openscreen) ★39.9k — Create stunning demos for free. Open-source, no subscriptions, no watermarks, and free for commercial use. An alternative to Screen Studio. · TypeScript · MIT · 2026-06
- [TriliumNext/Trilium](https://github.com/TriliumNext/Trilium) ★38.3k — Build your personal knowledge base with Trilium Notes · TypeScript · AGPL-3.0 · 2026-10
- [nativefier/nativefier](https://github.com/nativefier/nativefier) ★35.2k — Make any web page a desktop application · TypeScript · MIT · 2023-09
- [webadderallorg/Recordly](https://github.com/webadderallorg/Recordly) ★33.9k — Create polished demo videos without editing skills. Mac/Windows/Linux · TypeScript · NOASSERTION · 2026-10
- [pear-devs/pear-desktop](https://github.com/pear-devs/pear-desktop) ★33.8k — Pear 🍐 is extension for music player · TypeScript · MIT · 2026-10
- [qier222/YesPlayMusic](https://github.com/qier222/YesPlayMusic) ★33.4k — 高颜值的第三方网易云播放器，支持 Windows / macOS / Linux :electron: · Vue · MIT · 2026-10
- [Molunerfinn/PicGo](https://github.com/Molunerfinn/PicGo) ★27.3k — :rocket: The Ultimate Image Uploader for Efficient Creators. Supports Obsidian, Typora, VS Code etc. and 60+ image hosting services  (S3, Gi · TypeScript · MIT · 2026-10
- [sindresorhus/awesome-electron](https://github.com/sindresorhus/awesome-electron) ★27.3k — Useful resources for creating apps with Electron [SUBMISSIONS ARE TEMPORARILY PAUSED BECAUSE I'M TIRED OF REVIEWING LOW-QUALITY STUFF] · CC0-1.0 · 2026-05
- [oldj/SwitchHosts](https://github.com/oldj/SwitchHosts) ★27.3k — Switch hosts quickly! · TypeScript · Apache-2.0 · 2026-10
- [quasarframework/quasar](https://github.com/quasarframework/quasar) ★27.2k — Quasar Framework - Build high-performance VueJS user interfaces in record time · JavaScript · MIT · 2026-10
- [mihomo-party-org/clash-party](https://github.com/mihomo-party-org/clash-party) ★26.8k — :electron: Another Mihomo GUI. · TypeScript · GPL-3.0 · 2026-10
- [zulip/zulip](https://github.com/zulip/zulip) ★26.1k — Zulip server and web application. Open-source team chat that helps teams stay productive and focused. · Python · Apache-2.0 · 2026-10
- [responsively-org/responsively-app](https://github.com/responsively-org/responsively-app) ★25.3k — A modified web browser that helps in responsive web development. A web developer's must have dev-tool. · TypeScript · AGPL-3.0 · 2026-10
- [nylas/nylas-mail](https://github.com/nylas/nylas-mail) ★24.7k — :love_letter: An extensible desktop mail app built on the modern web.  Forks welcome! · JavaScript · MIT · 2026-06
- [docmirror/dev-sidecar](https://github.com/docmirror/dev-sidecar) ★24.5k — 开发者边车，github打不开，github加速，git clone加速，git release下载加速，stackoverflow加速 · Vue · MPL-2.0 · 2026-10
- [electron-react-boilerplate/electron-react-boilerplate](https://github.com/electron-react-boilerplate/electron-react-boilerplate) ★24.3k — A Foundation for Scalable Cross-Platform Apps · TypeScript · MIT · 2026-10
- [beekeeper-studio/beekeeper-studio](https://github.com/beekeeper-studio/beekeeper-studio) ★23.8k — Modern and easy to use SQL client for MySQL, Postgres, SQLite, SQL Server, and more. Linux, MacOS, and Windows. · TypeScript · NOASSERTION · 2026-10
- [notable/notable](https://github.com/notable/notable) ★23.5k — The Markdown-based note-taking app that doesn't suck. · NOASSERTION · 2024-06
- [typicode/lowdb](https://github.com/typicode/lowdb) ★22.6k — Simple and fast JSON database · JavaScript · MIT · 2026-03
- [desktop/desktop](https://github.com/desktop/desktop) ★22.0k — Focus on what matters instead of fighting with Git. · TypeScript · MIT · 2026-10

### Browser extensions (30)

- [refined-github/refined-github](https://github.com/refined-github/refined-github) ★32.3k — :octocat: Browser extension that simplifies the GitHub interface and adds useful features · TypeScript · MIT · 2026-10
- [nextai-translator/nextai-translator](https://github.com/nextai-translator/nextai-translator) ★25.0k — 基于 ChatGPT API 的划词翻译浏览器插件和跨平台桌面端应用    -    Browser extension and cross-platform desktop application for translation based on ChatGPT API. · TypeScript · AGPL-3.0 · 2026-09
- [ovity/octotree](https://github.com/ovity/octotree) ★23.3k — GitHub on steroids · JavaScript · AGPL-3.0 · 2024-06
- [voyager-crew/voyager](https://github.com/voyager-crew/voyager) ★20.4k — Enhancement suite for Gemini, AI Studio, Claude, ChatGPT & DeepSeek — plus a prompt manager for any website, DeepSeek Harness included. / 面向 · TypeScript · GPL-3.0 · 2026-10
- [dailydotdev/daily](https://github.com/dailydotdev/daily) ★20.1k — daily.dev is the personalized developer news feed and community. Get the best tech content from all over the web in your browser new tab or  · JavaScript · AGPL-3.0 · 2026-10
- [moonD4rk/HackBrowserData](https://github.com/moonD4rk/HackBrowserData) ★14.6k — Extract and decrypt browser data, supporting multiple data types, runnable on various operating systems (macOS, Windows, Linux). · Go · MIT · 2026-10
- [PlasmoHQ/plasmo](https://github.com/PlasmoHQ/plasmo) ★13.2k — 🧩 The Browser Extension Framework · TypeScript · MIT · 2026-10
- [wong2/chatgpt-google-extension](https://github.com/wong2/chatgpt-google-extension) ★13.0k — This project is deprecated. Check my new project ChatHub: · TypeScript · GPL-3.0 · 2024-08
- [ChatGPTBox-dev/chatGPTBox](https://github.com/ChatGPTBox-dev/chatGPTBox) ★10.8k — Integrating ChatGPT into your browser deeply, everything you need is here · JavaScript · MIT · 2026-10
- [chathub-dev/chathub](https://github.com/chathub-dev/chathub) ★10.7k · TypeScript · GPL-3.0 · 2026-02
- [mengxi-ream/read-frog](https://github.com/mengxi-ream/read-frog) ★10.1k — 🐸 Read Frog - Open-source AI language learning & flashcards, an Immersive Translate alternative | 🐸 陪读蛙 - 开源 AI 语言学习与闪词卡，沉浸式翻译替代 · TypeScript · GPL-3.0 · 2026-10
- [dessant/buster](https://github.com/dessant/buster) ★9.3k — Captcha solver extension for humans, available for Chrome, Edge and Firefox · JavaScript · GPL-3.0 · 2026-06
- [BewlyBewly/BewlyBewly](https://github.com/BewlyBewly/BewlyBewly) ★8.8k — Just make a few small changes to your Bilibili homepage. (English | 简体中文 | 正體中文 | 廣東話) · Vue · MIT · 2025-02
- [DIYgod/RSSHub-Radar](https://github.com/DIYgod/RSSHub-Radar) ★7.4k — 🧡 Browser extension that simplifies finding and subscribing RSS and RSSHub · TypeScript · AGPL-3.0 · 2026-09
- [iorate/ublacklist](https://github.com/iorate/ublacklist) ★6.7k — Blocks specific sites from appearing in Google search results · TypeScript · MIT · 2026-10
- [victornpb/undiscord](https://github.com/victornpb/undiscord) ★6.7k — Undiscord - Delete all messages in a Discord server / channel or DM (Easy and fast) Bulk delete · JavaScript · NOASSERTION · 2025-12
- [interstellard/chatgpt-advanced](https://github.com/interstellard/chatgpt-advanced) ★6.4k — WebChatGPT: A browser extension that augments your ChatGPT prompts with web results. · TypeScript · MIT · 2024-08
- [hanydd/BilibiliSponsorBlock](https://github.com/hanydd/BilibiliSponsorBlock) ★6.2k — 一款跳过小电视视频中恰饭片段的浏览器插件，移植自 SponsorBlock。A browser extension to skip sponsored segments in videos, ported from the SponsorBlock · TypeScript · GPL-3.0 · 2026-10
- [OctoLinker/OctoLinker](https://github.com/OctoLinker/OctoLinker) ★5.4k — OctoLinker — Links together, what belongs together · HTML · MIT · 2023-10
- [obsidianmd/obsidian-clipper](https://github.com/obsidianmd/obsidian-clipper) ★5.3k — Highlight and capture the web in your favorite browser. The official Web Clipper extension for Obsidian. · TypeScript · MIT · 2026-09
- [extension-js/extension.js](https://github.com/extension-js/extension.js) ★5.2k — The cross-browser extension framework. · TypeScript · MIT · 2026-10
- [WorldBrain/Memex](https://github.com/WorldBrain/Memex) ★4.7k — Browser extension to curate, annotate, and discuss the most valuable content and ideas on the web. As individuals, teams and communities. · TypeScript · NOASSERTION · 2025-12
- [cavi-au/Consent-O-Matic](https://github.com/cavi-au/Consent-O-Matic) ★4.3k — Browser extension that automatically fills out cookie popups based on your preferences · JavaScript · NOASSERTION · 2026-02
- [OhMyGuus/I-Still-Dont-Care-About-Cookies](https://github.com/OhMyGuus/I-Still-Dont-Care-About-Cookies) ★4.3k — Debloated fork of the extension "I don't care about cookies" · JavaScript · GPL-3.0 · 2026-10
- [ansh/jiffyreader-public-archive](https://github.com/ansh/jiffyreader-public-archive) ★4.0k — A Browser Extension for faster reading on ANY website! · TypeScript · GPL-3.0 · 2025-07
- [dessant/search-by-image](https://github.com/dessant/search-by-image) ★3.8k — Browser extension for reverse image search, available for Chrome, Edge and Safari · JavaScript · GPL-3.0 · 2026-06
- [EhTagTranslation/EhSyringe](https://github.com/EhTagTranslation/EhSyringe) ★3.7k — E 站注射器，将中文翻译注入到 E 站体内 · TypeScript · MIT · 2026-10
- [fregante/GhostText](https://github.com/fregante/GhostText) ★3.6k — 👻 Use your text editor to write in your browser. Everything you type in the editor will be instantly updated in the browser (and vice versa) · JavaScript · MIT · 2026-05
- [stefanbuck/awesome-browser-extensions-for-github](https://github.com/stefanbuck/awesome-browser-extensions-for-github) ★3.3k — A collection of awesome browser extensions for GitHub. · JavaScript · NOASSERTION · 2024-08
- [aliasvault/aliasvault](https://github.com/aliasvault/aliasvault) ★3.3k — Privacy-first password manager with built-in email aliasing. Fully encrypted and self-hostable. · TypeScript · AGPL-3.0 · 2026-10

### Web scraping & crawling (30)

- [scrapy/scrapy](https://github.com/scrapy/scrapy) ★64.8k — Scrapy, a fast high-level web crawling & scraping framework for Python. · Python · BSD-3-Clause · 2026-10
- [dgtlmoon/changedetection.io](https://github.com/dgtlmoon/changedetection.io) ★35.1k — Best and simplest tool for website change detection, web page monitoring, and website change alerts. Perfect for tracking content changes, p · Python · Apache-2.0 · 2026-10
- [apify/crawlee](https://github.com/apify/crawlee) ★26.2k — Crawlee—A web scraping and browser automation library for Node.js to build reliable crawlers. In JavaScript and TypeScript. Extract data for · TypeScript · Apache-2.0 · 2026-10
- [seleniumbase/SeleniumBase](https://github.com/seleniumbase/SeleniumBase) ★13.1k — 📊 Python APIs for Web Automation, E2E Testing, and Data Scraping. CDP Mode bypasses bot-detection and handles CAPTCHAs. Includes a Stealth m · Python · MIT · 2026-10
- [jhy/jsoup](https://github.com/jhy/jsoup) ★11.4k — jsoup: the Java HTML parser, built for HTML editing, cleaning, scraping, and XSS safety. · Java · MIT · 2026-10
- [apify/crawlee-python](https://github.com/apify/crawlee-python) ★9.6k — Crawlee—A web scraping and browser automation library for Python to build reliable crawlers. Extract data for AI, LLMs, RAG, or GPTs. Downlo · Python · Apache-2.0 · 2026-10
- [mherrmann/helium](https://github.com/mherrmann/helium) ★8.3k — Lighter web automation with Python · Python · MIT · 2026-08
- [lorien/awesome-web-scraping](https://github.com/lorien/awesome-web-scraping) ★8.2k — List of libraries, tools and APIs for web scraping and data processing. · JavaScript · NOASSERTION · 2026-09
- [alirezamika/autoscraper](https://github.com/alirezamika/autoscraper) ★8.1k — A Smart, Automatic, Fast and Lightweight Web Scraper for Python · Python · MIT · 2026-07
- [cporter202/API-mega-list](https://github.com/cporter202/API-mega-list) ★7.8k — This GitHub repo is a powerhouse collection of APIs you can start using immediately to build everything from simple automations to full-scal · JavaScript · NOASSERTION · 2026-10
- [go-rod/rod](https://github.com/go-rod/rod) ★7.1k — A Chrome DevTools Protocol driver for web automation and scraping. · Go · MIT · 2026-08
- [adbar/trafilatura](https://github.com/adbar/trafilatura) ★7.0k — Python & Command-line tool to gather text and metadata on the Web: Crawling, scraping, extraction, output as CSV, JSON, HTML, MD, TXT, XML · Python · Apache-2.0 · 2026-10
- [lexiforest/curl_cffi](https://github.com/lexiforest/curl_cffi) ★6.7k — Python binding for curl-impersonate fork via cffi. A http client that can impersonate browser tls/ja3/http2 fingerprints. · Python · MIT · 2026-10
- [gosom/google-maps-scraper](https://github.com/gosom/google-maps-scraper) ★6.5k — scrape data  from Google Maps. Extracts data such as the name, address, phone number, website URL, rating,  reviews number, latitude and lon · Go · MIT · 2026-09
- [browser-act/skills](https://github.com/browser-act/skills) ★6.2k — Browser automation CLI built for AI agents. Break through anti-bot walls, hand off to humans across platforms when stuck. Parallel multi-tas · Python · MIT · 2026-08
- [jaypyles/Scraperr](https://github.com/jaypyles/Scraperr) ★4.9k — Self-hosted webscraper. · TypeScript · MIT · 2025-10
- [Kaliiiiiiiiii-Vinyzu/patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) ★4.9k — Undetected version of the Playwright testing and automation library. · TypeScript · Apache-2.0 · 2026-10
- [Anakin-Inc/anakin](https://github.com/Anakin-Inc/anakin) ★4.5k — Open-source web scraping API. Turn any website into clean markdown or structured JSON. Anti-detect browser, proxy auto-selection, self-hoste · Go · AGPL-3.0 · 2026-08
- [IonicaBizau/scrape-it](https://github.com/IonicaBizau/scrape-it) ★4.1k — 🔮 A Node.js scraper for humans. · JavaScript · MIT · 2026-10
- [snooppr/snoop](https://github.com/snooppr/snoop) ★4.0k — Snoop — инструмент разведки на основе открытых данных (OSINT world) · Python · NOASSERTION · 2026-10
- [oxylabs/amazon-scraper](https://github.com/oxylabs/amazon-scraper) ★3.4k — Free Trial Amazon Scraper API for extracting search, product, offer listing, reviews, question and answers, best sellers and sellers data. · Python · NOASSERTION · 2026-06
- [php-curl-class/php-curl-class](https://github.com/php-curl-class/php-curl-class) ★3.3k — PHP Curl Class makes it easy to send HTTP requests and integrate with web APIs · PHP · Unlicense · 2026-10
- [oxylabs/how-to-scrape-amazon-product-data](https://github.com/oxylabs/how-to-scrape-amazon-product-data) ★3.3k — The process of extracting product data from Amazon using Python, including titles, ratings, prices, images, and descriptions. · NOASSERTION · 2026-06
- [Virtual-Browser/VirtualBrowser](https://github.com/Virtual-Browser/VirtualBrowser) ★3.2k — Free anti fingerprint browser, 指纹浏览器, 隐私浏览器, 防识别浏览器, 反识别浏览器, 防关联浏览器, 免费的web3空投专用指纹浏览器 https://virtualbrowser.cc/?src=github · Vue · BSD-3-Clause · 2026-10
- [x4nth055/pythoncode-tutorials](https://github.com/x4nth055/pythoncode-tutorials) ★3.0k — The Python Code Tutorials · Jupyter Notebook · MIT · 2026-09
- [oxylabs/how-to-scrape-google-trends](https://github.com/oxylabs/how-to-scrape-google-trends) ★2.9k — Learn step-by-step how to scrape Google Trends data and make a result comparison using Python and Oxylabs SERP API. Extract keywords, their  · Python · NOASSERTION · 2025-12
- [vladkens/twscrape](https://github.com/vladkens/twscrape) ★2.9k — Python library and CLI for X/Twitter scraping with multi-account rotation and built-in rate-limit handling. · Python · MIT · 2026-10
- [spider-rs/spider](https://github.com/spider-rs/spider) ★2.8k — Foundational low latency web data collecting in Rust · Rust · MIT · 2026-10
- [codingforentrepreneurs/30-Days-of-Python](https://github.com/codingforentrepreneurs/30-Days-of-Python) ★2.5k — Learn Python for the next 30 (or so) Days. · HTML · MIT · 2024-02
- [lorien/grab](https://github.com/lorien/grab) ★2.5k — Web Scraping Framework · Python · MIT · 2025-09

### RAG & retrieval (30)

- [Shubhamsaboo/awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps) ★141.9k — 100+ AI Agents, Agent Skills and RAG Apps - Free and Open Source. · Python · Apache-2.0 · 2026-10
- [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) ★91.2k — Turn any PDF or image document into structured data for your AI. A powerful, lightweight OCR toolkit that bridges the gap between images/PDF · Python · Apache-2.0 · 2026-09
- [FlowiseAI/Flowise](https://github.com/FlowiseAI/Flowise) ★55.5k — Build AI Agents, Visually · TypeScript · NOASSERTION · 2026-08
- [getzep/graphiti](https://github.com/getzep/graphiti) ★31.8k — Build Real-Time Knowledge Graphs for AI Agents · Python · Apache-2.0 · 2026-10
- [simstudioai/sim](https://github.com/simstudioai/sim) ★29.8k — Sim is the collaborative workspace to build, deploy, and monitor AI agents and workflows. Used by 100,000+ builders. · TypeScript · Apache-2.0 · 2026-10
- [opendataloader-project/opendataloader-pdf](https://github.com/opendataloader-project/opendataloader-pdf) ★29.7k — PDF Parser for AI-ready data. Automate PDF accessibility. Open-source. · Java · Apache-2.0 · 2026-10
- [humanlayer/12-factor-agents](https://github.com/humanlayer/12-factor-agents) ★26.7k — What are the principles we can use to build LLM-powered software that is actually good enough to put in the hands of production customers? · TypeScript · NOASSERTION · 2025-09
- [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) ★26.0k — Test your prompts, agents, and RAGs. Red teaming/pentesting/vulnerability scanning for AI. Compare performance of GPT, Claude, Gemini, DeepS · TypeScript · MIT · 2026-10
- [Cinnamon/kotaemon](https://github.com/Cinnamon/kotaemon) ★25.8k — An open-source RAG-based tool for chatting with your documents. · Python · Apache-2.0 · 2026-07
- [eosphoros-ai/DB-GPT](https://github.com/eosphoros-ai/DB-GPT) ★20.2k — open-source agentic AI data assistant for the next generation of AI + Data products. · Python · MIT · 2026-10
- [arc53/DocsGPT](https://github.com/arc53/DocsGPT) ★18.3k — Private AI platform for agents, assistants and enterprise search. Built-in Agent Builder, Deep research, Document analysis, Multi-model supp · Python · MIT · 2026-10
- [RyanCodrai/turbovec](https://github.com/RyanCodrai/turbovec) ★17.4k — A vector index built on TurboQuant, written in Rust with Python bindings · Rust · MIT · 2026-10
- [memvid/memvid](https://github.com/memvid/memvid) ★16.6k — Memory layer for AI Agents. Replace complex RAG pipelines with a serverless, single-file memory layer. Give your agents instant retrieval an · Rust · Apache-2.0 · 2026-07
- [alibaba/zvec](https://github.com/alibaba/zvec) ★16.1k — A lightweight, lightning-fast, in-process vector database · C++ · Apache-2.0 · 2026-10
- [ConardLi/easy-dataset](https://github.com/ConardLi/easy-dataset) ★15.0k — A powerful tool for creating datasets for LLM fine-tuning 、RAG and Eval · JavaScript · NOASSERTION · 2026-05
- [datawhalechina/llm-universe](https://github.com/datawhalechina/llm-universe) ★14.2k — 本项目是一个面向小白开发者的大模型应用开发教程，在线阅读地址：https://datawhalechina.github.io/llm-universe/ · Jupyter Notebook · NOASSERTION · 2026-08
- [EverMind-AI/EverOS](https://github.com/EverMind-AI/EverOS) ★13.4k — One portable memory layer for every AI agent: local-first, Markdown-native, user-owned, and self-evolving across apps, tools, and workflows. · Python · Apache-2.0 · 2026-10
- [StarTrail-org/LEANN](https://github.com/StarTrail-org/LEANN) ★13.0k — [MLsys2026 Best Paper]: https://arxiv.org/abs/2506.08276. RAG on Everything with LEANN. Enjoy 97% storage savings while running a fast, accu · Python · MIT · 2026-10
- [neuml/txtai](https://github.com/neuml/txtai) ★13.0k — 💡 All-in-one AI framework for semantic search, LLM orchestration and language model workflows · Python · Apache-2.0 · 2026-10
- [datawhalechina/all-in-rag](https://github.com/datawhalechina/all-in-rag) ★12.2k — 🔍大模型应用开发实战一：RAG 技术全栈指南，在线阅读地址：https://datawhalechina.github.io/all-in-rag/ · Python · NOASSERTION · 2026-09
- [cocoindex-io/cocoindex](https://github.com/cocoindex-io/cocoindex) ★11.7k — Incremental engine for long horizon agents 🌟 Star if you like it! · Rust · Apache-2.0 · 2026-10
- [adongwanai/AgentGuide](https://github.com/adongwanai/AgentGuide) ★10.9k — https://adongwanai.github.io/AgentGuide | AI Agent开发指南 | LangGraph实战 | 高级RAG | 转行大模型 | 大模型面试 | 算法工程师 | 面试题库 | 强化学习｜数据合成 · MDX · NOASSERTION · 2026-09
- [VoltAgent/voltagent](https://github.com/VoltAgent/voltagent) ★10.8k — AI Agent Engineering Platform built on an Open Source TypeScript AI Agent Framework · TypeScript · MIT · 2026-10
- [sigoden/aichat](https://github.com/sigoden/aichat) ★10.5k — All-in-one LLM CLI tool featuring Shell Assistant, Chat-REPL, RAG, AI Tools & Agents, with access to OpenAI, Claude, Gemini, Ollama, Groq, a · Rust · Apache-2.0 · 2026-02
- [StarTrail-org/PixelRAG](https://github.com/StarTrail-org/PixelRAG) ★10.3k — https://arxiv.org/abs/2606.28344. The end of web parsing. The beginning of scalable pixel-native search. link: https://pixelrag.ai/ · Python · Apache-2.0 · 2026-10
- [xberg-io/xberg](https://github.com/xberg-io/xberg) ★9.4k — Polyglot document intelligence with a Rust core: extract text, metadata, images, tables, and structured data from 106 formats across 140 fil · Rust · MIT · 2026-10
- [Future-House/paper-qa](https://github.com/Future-House/paper-qa) ★9.4k — High accuracy RAG for answering questions from scientific documents with citations · Python · Apache-2.0 · 2026-10
- [activeloopai/deeplake](https://github.com/activeloopai/deeplake) ★9.3k — Deeplake is AI Data Runtime for Agents. It provides serverless postgres with a multimodal datalake, enabling scalable retrieval and training · C++ · Apache-2.0 · 2026-05
- [WangRongsheng/awesome-LLM-resources](https://github.com/WangRongsheng/awesome-LLM-resources) ★9.0k — 🧑‍🚀 全世界最好的LLM资料总结（多模态生成、Agent、辅助编程、AI审稿、数据处理、模型训练、模型推理、o1 模型、MCP、小语言模型、视觉语言模型） | Summary of the world's best LLM resources. · Apache-2.0 · 2026-10
- [reorproject/reor](https://github.com/reorproject/reor) ★8.5k — Private & local AI personal knowledge management app for high entropy people. · JavaScript · AGPL-3.0 · 2025-05

### Vector databases (30)

- [meilisearch/meilisearch](https://github.com/meilisearch/meilisearch) ★59.6k — A lightning-fast search engine API bringing AI-powered hybrid search to your sites and applications. · Rust · NOASSERTION · 2026-10
- [volcengine/OpenViking](https://github.com/volcengine/OpenViking) ★40.1k — Self-evolving Context Database for AI Agents. Unify Agent Memory, Knowledge RAG and Skills. · Python · AGPL-3.0 · 2026-10
- [qdrant/qdrant](https://github.com/qdrant/qdrant) ★35.1k — Qdrant - High-performance, massive-scale Vector Database and Vector Search Engine for the next generation of AI. Also available in the cloud · Rust · Apache-2.0 · 2026-10
- [weaviate/weaviate](https://github.com/weaviate/weaviate) ★16.9k — Weaviate is an open-source vector database that stores both objects and vectors, allowing for the combination of vector search with structur · Go · NOASSERTION · 2026-10
- [langchain4j/langchain4j](https://github.com/langchain4j/langchain4j) ★13.3k — LangChain4j is an idiomatic, open-source Java library for building LLM-powered applications on the JVM. It offers a unified API over popular · Java · Apache-2.0 · 2026-10
- [lancedb/lancedb](https://github.com/lancedb/lancedb) ★11.7k — Developer-friendly OSS embedded retrieval library for multimodal AI. Search More; Manage Less. · Rust · Apache-2.0 · 2026-10
- [oramasearch/orama](https://github.com/oramasearch/orama) ★10.6k — 🌌  A complete search engine and RAG pipeline in your browser, server or edge network with support for full-text, vector, and hybrid search i · TypeScript · NOASSERTION · 2026-10
- [oceanbase/oceanbase](https://github.com/oceanbase/oceanbase) ★10.3k — OceanBase is the unified distributed database for the AI era — open-source, multi-model, one engine for your most demanding workloads. · C++ · Apache-2.0 · 2026-10
- [databendlabs/databend](https://github.com/databendlabs/databend) ★9.5k — Data Agent Ready Warehouse : One for  Analytics, Search, AI, Python Sandbox.  — rebuilt from scratch. Unified architecture on your S3. · Rust · Apache-2.0 · 2026-10
- [paradedb/paradedb](https://github.com/paradedb/paradedb) ★9.4k — One Postgres for your application data, full-text search, vector retrieval, and aggregations. Home of the pg_search extension. · Rust · AGPL-3.0 · 2026-10
- [MariaDB/server](https://github.com/MariaDB/server) ★8.4k — MariaDB server is a community developed fork of MySQL server. Started by core members of the original MySQL team, MariaDB actively works wit · C++ · GPL-2.0 · 2026-10
- [RediSearch/RediSearch](https://github.com/RediSearch/RediSearch) ★6.2k — A query and indexing engine for Redis, providing secondary indexing, full-text search, vector similarity search and aggregations. · Rust · NOASSERTION · 2026-10
- [xerj-org/xerj](https://github.com/xerj-org/xerj) ★6.1k — XERJ is the new way for AI to search data. Its autoindex capability activates agents to know your data without the token waste of grep and s · Rust · Apache-2.0 · 2026-10
- [volcengine/MineContext](https://github.com/volcengine/MineContext) ★5.5k — MineContext is your proactive context-aware AI partner（Context-Engineering+ChatGPT Pulse） · Python · Apache-2.0 · 2026-05
- [infiniflow/infinity](https://github.com/infiniflow/infinity) ★4.7k — The AI-native database built for LLM applications, providing incredibly fast hybrid search of dense vector, sparse vector, tensor (multi-vec · C++ · Apache-2.0 · 2026-10
- [CaviraOSS/LongMemory](https://github.com/CaviraOSS/LongMemory) ★4.5k — Local persistent memory store for LLM applications including claude desktop, github copilot, codex, antigravity, etc. · TypeScript · Apache-2.0 · 2026-09
- [crate/crate](https://github.com/crate/crate) ★4.4k — CrateDB is a distributed and scalable SQL database for storing and analyzing massive amounts of data in near real-time, even with complex qu · Java · Apache-2.0 · 2026-10
- [Ontos-AI/knowhere](https://github.com/Ontos-AI/knowhere) ★3.7k — Knowhere extracts, parses, and outputs structured chunks ready for AI Agents and RAG. · Python · Apache-2.0 · 2026-10
- [giancarloerra/SocratiCode](https://github.com/giancarloerra/SocratiCode) ★3.3k — Enterprise-grade (40m+ LOC) codebase intelligence, zero-setup, local & private Plugin/Skill/Extension or MCP: hybrid semantic search, polygl · TypeScript · AGPL-3.0 · 2026-10
- [zilliztech/attu](https://github.com/zilliztech/attu) ★3.2k — The Best GUI for Milvus · Shell · NOASSERTION · 2026-09
- [pinecone-io/examples](https://github.com/pinecone-io/examples) ★3.0k — Jupyter Notebooks to help you get hands-on with Pinecone vector databases · Jupyter Notebook · MIT · 2026-10
- [pingcap/autoflow](https://github.com/pingcap/autoflow) ★3.0k — pingcap/autoflow is a Graph RAG based and conversational knowledge base tool built with TiDB Serverless Vector Storage. Demo: https://tidb.a · TypeScript · Apache-2.0 · 2026-04
- [liyupi/yu-ai-agent](https://github.com/liyupi/yu-ai-agent) ★2.7k — 编程导航 AI 开发实战新项目，基于 Spring Boot 3 + Java 21 + Spring AI 构建 AI 恋爱大师应用和 ReAct 模式自主规划智能体YuManus，覆盖 AI 大模型接入、Spring AI 核心特性、Prompt 工程和优化、RAG 检索增强 · Java · NOASSERTION · 2026-01
- [milvus-io/bootcamp](https://github.com/milvus-io/bootcamp) ★2.4k — Dealing with all unstructured data, such as reverse image search, audio search, molecular search, video analysis, question and answer system · Jupyter Notebook · Apache-2.0 · 2026-09
- [vearch/vearch](https://github.com/vearch/vearch) ★2.3k — Distributed vector search for AI-native applications · Python · Apache-2.0 · 2026-07
- [vasu-devs/JustHireMe](https://github.com/vasu-devs/JustHireMe) ★2.3k — Local-first AI job intelligence workbench for scraping roles, ranking fit, and generating tailored application materials. · Python · AGPL-3.0 · 2026-10
- [Mintplex-Labs/vector-admin](https://github.com/Mintplex-Labs/vector-admin) ★2.2k — The universal tool suite for vector database management. Manage Pinecone, Chroma, Qdrant, Weaviate and more vector databases with ease. · TypeScript · MIT · 2025-04
- [tensorchord/pgvecto.rs](https://github.com/tensorchord/pgvecto.rs) ★2.2k — Scalable, Low-latency and Hybrid-enabled Vector Search in Postgres. Revolutionize Vector Search, not Database. · Rust · Apache-2.0 · 2025-02
- [neuron-core/neuron-ai](https://github.com/neuron-core/neuron-ai) ★2.1k — The Agentic Framework of the PHP ecosystem to build production-ready AI driven applications. Connect components (LLMs, Tools, vector DBs, me · PHP · MIT · 2026-10
- [matrixorigin/matrixone](https://github.com/matrixorigin/matrixone) ★2.1k — AI-native HTAP database with Git-for-Data and built-in vector search, serving as the data and memory backbone for intelligent agents and app · Go · Apache-2.0 · 2026-10

### Agent memory (topic) (30)

- [Mirix-AI/MIRIX](https://github.com/Mirix-AI/MIRIX) ★3.5k — Mirix is a multi-agent personal assistant designed to track on-screen activities and answer user questions intelligently. By capturing real- · Python · Apache-2.0 · 2026-10
- [memodb-io/memobase](https://github.com/memodb-io/memobase) ★2.9k — User Profile-Based Long-Term Memory for AI Chatbot Applications. · Python · Apache-2.0 · 2026-01
- [AutoArk/TinyEngram](https://github.com/AutoArk/TinyEngram) ★1.4k — Research of DeepSeek Engram Architecture based on Qwen-3 and Stable Diffusion series. · Python · NOASSERTION · 2026-05
- [IAAR-Shanghai/Awesome-AI-Memory](https://github.com/IAAR-Shanghai/Awesome-AI-Memory) ★1.3k — Awesome AI Memory | LLM Memory | A curated knowledge base on AI memory for LLMs and agents, covering long-term memory, reasoning, retrieval, · Python · Apache-2.0 · 2026-10
- [okf-memory/okf-agent-memory](https://github.com/okf-memory/okf-agent-memory) ★808 — Git-native persistent memory for AI coding agents. Implements Google OKF v0.2 with sub-300µs in-memory BM25 search, embedded MCP server, and · Go · MIT · 2026-10
- [TeleAI-UAGI/Awesome-Agent-Memory](https://github.com/TeleAI-UAGI/Awesome-Agent-Memory) ★679 — Curated systems, benchmarks, and papers etc. on memory for LLMs/MLLMs --- long-term context, retrieval, and reasoning. · Python · Apache-2.0 · 2026-10
- [memvid/claude-brain](https://github.com/memvid/claude-brain) ★578 — Give Claude Code photographic memory in ONE portable file. No database, no SQLite, no ChromaDB - just a single .mv2 file you can git commit, · TypeScript · MIT · 2026-01
- [omdsh-dev/dsh-mnemon](https://github.com/omdsh-dev/dsh-mnemon) ★554 — Composable, view-based memory for DeepSeek Harness. Pluggable sources and strategies, with three-tier memory out of the box. · TypeScript · MIT · 2026-10
- [caura-ai/caura](https://github.com/caura-ai/caura) ★498 — Caura (formerly MemClaw) — governed shared memory for AI agent fleets. Multi-agent, multi-tenant, MCP-native. Trust tiers, keystone policies · Python · Apache-2.0 · 2026-10
- [grpcer/ownmem](https://github.com/grpcer/ownmem) ★429 — Open-source, Git-native memory for AI coding agents — deterministic local recall for Claude Code, Codex, Cursor, Gemini CLI, and compatible  · JavaScript · Apache-2.0 · 2026-10
- [rush-db/rushdb](https://github.com/rush-db/rushdb) ★325 — RushDB is a graph + vector database and memory layer for AI agents. Push any JSON, get typed, searchable, relationship-aware records back —  · TypeScript · NOASSERTION · 2026-10
- [divagr18/memlayer](https://github.com/divagr18/memlayer) ★302 — Plug-and-play memory for LLMs in 3 lines of code. Add persistent, intelligent, human-like memory and recall to any model in minutes. · Python · MIT · 2026-02
- [sachitrafa/YourMemory](https://github.com/sachitrafa/YourMemory) ★270 — Agentic AI memory with Ebbinghaus forgetting curve decay. +16pp better recall than Mem0 on LoCoMo. · Python · NOASSERTION · 2026-09
- [qualixar/superlocalmemory](https://github.com/qualixar/superlocalmemory) ★248 — Open-source governed, local-first memory control plane for AI agents and teams. arXiv:2608.08253 · Python · AGPL-3.0 · 2026-10
- [alibaizhanov/mengram](https://github.com/alibaizhanov/mengram) ★204 — Human-like memory for AI agents — semantic, episodic & procedural. Experience-driven procedures that learn from failures. Free API, Python & · Python · Apache-2.0 · 2026-09
- [bowen-upenn/PersonaMem](https://github.com/bowen-upenn/PersonaMem) ★202 — [COLM 2025] Know Me, Respond to Me: Benchmarking LLMs for Dynamic User Profiling and Personalized Responses at Scale · Python · MIT · 2026-09
- [tinqiao-oss/engramory](https://github.com/tinqiao-oss/engramory) ★195 — A portable memory protocol for AI agents — load it as standing rules; a curation discipline + reference spec + optional cap hook. · Python · MIT · 2026-09
- [jayzeng/pi-memory](https://github.com/jayzeng/pi-memory) ★192 — Persistent memory extension for pi with daily logs, scratchpad, and optional qmd‑powered semantic search. · TypeScript · MIT · 2026-09
- [offendingcommit/openconcho](https://github.com/offendingcommit/openconcho) ★189 — Fast, privacy-first desktop & web UI for self-hosted Honcho — browse memories, peers, sessions, conclusions, and chat with memory context. · TypeScript · MIT · 2026-10
- [MemTensor/HaluMem](https://github.com/MemTensor/HaluMem) ★176 — HaluMem is the first operation level hallucination evaluation benchmark tailored to agent memory systems. · Python · NOASSERTION · 2026-09
- [wuxuyun0606-collab/lmc-5](https://github.com/wuxuyun0606-collab/lmc-5) ★151 — Living Memory Coordinate-5: five-axis memory architecture for long-running LLM agents. Minimal SQLite + production PostgreSQL/pgvector refer · Python · AGPL-3.0 · 2026-08
- [memoket/memoket-kite](https://github.com/memoket/memoket-kite) ★144 — An open-source, vector-free long-term memory engine for AI agents, achieving SOTA on LoCoMo and LongMemEval with significantly less context. · Python · Apache-2.0 · 2026-10
- [aru-labs/lossless-memory](https://github.com/aru-labs/lossless-memory) ★143 — Lossless long-term memory for a personal AI: never summarize, keep every line, put a timestamp on everything. · Python · MIT · 2026-09
- [ucsandman/markdown-agent-memory](https://github.com/ucsandman/markdown-agent-memory) ★129 — Markdown-only hierarchical memory for long-running AI agents. Zero dependencies, 7 months in production. Copy-paste install prompt for any a · JavaScript · MIT · 2026-09
- [deepmemteam/deepmem](https://github.com/deepmemteam/deepmem) ★114 — Drop-in AI memory layer with 2x faster retrieval and 10x lower cost. Fully compatible with Mem0 API. Migrate in 5 minutes without any code c · Python · MIT · 2026-08
- [dimknaf/braindb](https://github.com/dimknaf/braindb) ★112 — An "LLM wiki" upgraded to a real database — typed entities, graph relations, HTTP API, and a built-in natural-language agent. · Python · Apache-2.0 · 2026-10
- [zero11924065-dev/VetarAI](https://github.com/zero11924065-dev/VetarAI) ★99 — VetarAI 是一款全原生 Swift 的本地桌面应用：多 Agent 协作、可视化工作流、拉模式知识仓库+本地语义检索、多模型超级工作室、CU 电脑操作。数据保存在本地磁盘。 · Swift · GPL-3.0 · 2026-09
- [pinkpixel-dev/mem0-mcp](https://github.com/pinkpixel-dev/mem0-mcp) ★97 — A memory system using mem0 for AI applications. Enables long-term memory for AI agents as a drop-in MCP server. · TypeScript · MIT · 2026-07
- [vcache-project/vCache](https://github.com/vcache-project/vCache) ★82 — Reliable and Efficient Semantic Prompt Caching with vCache · Python · NOASSERTION · 2026-07
- [Da7-Tech/mind](https://github.com/Da7-Tech/mind) ★77 — Persistent memory for AI coding agents: automatic capture, explainable recall, knowledge consolidation, privacy controls, and portable offli · Python · MIT · 2026-07

### Long-term memory (30)

- [akitaonrails/ai-memory](https://github.com/akitaonrails/ai-memory) ★9.5k — Solution for long term memory for agent coding CLIs and to facilitate handoff between different agent vendors · Rust · MIT · 2026-10
- [OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG) ★4.1k — [NeurIPS'24] HippoRAG is a novel RAG framework inspired by human long-term memory that enables LLMs to continuously integrate knowledge acro · Python · MIT · 2026-10
- [tigerless-labs/agent-memory](https://github.com/tigerless-labs/agent-memory) ★3.9k — Long-term memory runtime for AI agents — plain Markdown as the source of truth, local ranked retrieval, and an independent sleep-time Manage · Python · MIT · 2026-10
- [pashpashpash/vault-ai](https://github.com/pashpashpash/vault-ai) ★3.4k — OP Vault ChatGPT: Give ChatGPT long-term memory using the OP Stack (OpenAI + Pinecone Vector Database). Upload your own custom knowledge bas · JavaScript · MIT · 2025-07
- [rlaope/oh-my-hermes](https://github.com/rlaope/oh-my-hermes) ★3.4k — All in one plugin for Hermes Agent ⚚ the coding intelligence, a long-term memory system and model optimized workflow packages · Python · MIT · 2026-10
- [felinics/Memoh](https://github.com/felinics/Memoh) ★2.7k — ✨ The open-source multi-agent platform. Every agent gets its own computer, desktop, network, and long-term memory.  You can bring your own k · Go · AGPL-3.0 · 2026-10
- [Dataojitori/nocturne_memory](https://github.com/Dataojitori/nocturne_memory) ★1.4k — A lightweight, rollbackable, and visual Long-Term Memory Server for MCP Agents. Say goodbye to Vector RAG and amnesia. Empower your AI with  · Python · MIT · 2026-09
- [morettt/my-neuro](https://github.com/morettt/my-neuro) ★1.4k — This project lets you create your own AI desktop companion with customizable characters and voice conversations that respond in just 1 secon · JavaScript · MIT · 2026-10
- [moyangzhan/langchain4j-aideepin](https://github.com/moyangzhan/langchain4j-aideepin) ★1.4k — AI 应用平台（聊天、绘画、知识库、工作流、 MCP服务市场、语音输入输出、长期记忆） | AI application platform (Chat,Draw,RAG,Workflow,MCP marketplace, ASR,TTS, Long-term memory etc · Java · MIT · 2026-10
- [DasterProkio/awesome-ai-companion](https://github.com/DasterProkio/awesome-ai-companion) ★983 — Open-source AI companions, desktop pets, long-term memory & proactive chat. 人机恋开源项目大全。让你的家机能够脱离官端自主存在，拥有记忆和主动性。 · HTML · CC-BY-4.0 · 2026-10
- [death34018-hue/AionsHome](https://github.com/death34018-hue/AionsHome) ★896 — Aion — 一个支持长期记忆、语音交互、摄像头视觉的伴侣。 A self-hosted AI companion with long-term memory, voice interaction, camera vision, and smart home integratio · Python · MIT · 2026-10
- [thedivergentai/Game-Dev-Agentic-Skills](https://github.com/thedivergentai/Game-Dev-Agentic-Skills) ★857 — Multi-engine long-term memory for game AI agents. Deep Godot 4.7+ (99 skills, 27 genre blueprints) + Bevy docs-first parity — audited patter · GDScript · LGPL-3.0 · 2026-10
- [Victorwz/LongMem](https://github.com/Victorwz/LongMem) ★829 — Official implementation of our NeurIPS 2023 paper "Augmenting Language Models with Long-Term Memory". · Python · Apache-2.0 · 2024-03
- [supermemoryai/openclaw-supermemory](https://github.com/supermemoryai/openclaw-supermemory) ★797 — OpenClaw Supermemory lets to have long-term memory and recall for your openclaw agent. · TypeScript · NOASSERTION · 2026-10
- [mem0ai/mem0-chrome-extension](https://github.com/mem0ai/mem0-chrome-extension) ★678 — OpenMemory Chrome Extension: Long-term memory for ChatGPT, Claude, Perplexity, Grok etc · TypeScript · MIT · 2026-03
- [Arvincreator/project-golem](https://github.com/Arvincreator/project-golem) ★641 — OS-level autonomous AI agent with long-term memory, multi-agent coordination, Titan Chronos scheduler & Moltbot Social Core · JavaScript · NOASSERTION · 2026-06
- [daveshap/LongtermChatExternalSources](https://github.com/daveshap/LongtermChatExternalSources) ★621 — GPT-3 chatbot with long-term memory and external sources · Python · MIT · 2023-01
- [LeoYeAI/talewell](https://github.com/LeoYeAI/talewell) ★548 — Plugin-first long-term memory for agent platforms — reference implementation of AMP (Agent Memory Protocol). · JavaScript · MIT · 2026-10
- [MagicCube/agentara](https://github.com/MagicCube/agentara) ★517 — Your 24/7 personal assistant powered by Claude Code and OpenAI Codex. Multi-channel messaging, long-term memory, skills, task scheduling, se · TypeScript · NOASSERTION · 2026-05
- [vercel-labs/personal-agent-template](https://github.com/vercel-labs/personal-agent-template) ★475 — Open-source template for a durable personal AI agent — web chat, Slack, Linear, and long-term memory with user-approved saves. Eve, Nuxt, Be · TypeScript · MIT · 2026-09
- [MemTensor/MemOS-Cloud-OpenClaw-Plugin](https://github.com/MemTensor/MemOS-Cloud-OpenClaw-Plugin) ★367 — Official MemOS Cloud plugin for OpenClaw. Enables long-term memory for agents by recalling context before execution and saving conversations · JavaScript · Apache-2.0 · 2026-09
- [410979729/scope-recall-hermes](https://github.com/410979729/scope-recall-hermes) ★366 — Local long-term memory for Hermes, Codex, Claude Code, WorkBuddy and dsh agents: one SQLite store, source-backed recall, and tools to inspec · Python · MIT · 2026-10
- [LagPixelLOL/ChatGPTCLIBot](https://github.com/LagPixelLOL/ChatGPTCLIBot) ★337 — ChatGPT Bot in CLI with long term memory support using Embeddings. · C++ · MIT · 2024-07
- [wangyu-ustc/MemoryLLM](https://github.com/wangyu-ustc/MemoryLLM) ★327 — The official implementation of the ICML 2024 paper "MemoryLLM: Towards Self-Updatable Large Language Models" and "M+: Extending MemoryLLM wi · Python · MIT · 2025-07
- [edoliberty/long-term-memory-in-ai](https://github.com/edoliberty/long-term-memory-in-ai) ★324 — Class notes for the course "Long Term Memory in AI - Vector Search and Databases" COS 597A @ Princeton Fall 2023 · TeX · MIT · 2026-10
- [AGI-is-going-to-arrive/Memory-Palace](https://github.com/AGI-is-going-to-arrive/Memory-Palace) ★315 — Memory Palace is a long-term memory operating system purpose-built for AI Agents. · Python · MIT · 2026-05
- [libraryofcelsus/Aetherius_AI_Assistant](https://github.com/libraryofcelsus/Aetherius_AI_Assistant) ★312 — A completely private, locally-operated Ai Assistant/Chatbot/Sub-Agent Framework with realistic Long Term Memory and thought formation using  · Python · NOASSERTION · 2024-09
- [TIMAN-group/PlugMem](https://github.com/TIMAN-group/PlugMem) ★303 — ICML 2026 | PALM@NeurIPS2026 Oral | Plug-and-play long-term memory for LLM agents · Python · Apache-2.0 · 2026-07
- [groupzer0/vs-code-agents](https://github.com/groupzer0/vs-code-agents) ★291 — A multi-agent workflow system for GitHub Copilot in VS Code that brings structure, quality gates, and long-term memory to AI-assisted develo · Shell · MIT · 2026-01
- [Aaryanverma/graybox](https://github.com/Aaryanverma/graybox) ★263 — A local-first, long-term memory for anything you'd otherwise forget. · Python · MIT · 2026-09

### Knowledge graphs (30)

- [Egonex-AI/Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) ★86.5k — Graphs that teach > graphs that impress. Turn any code into an interactive knowledge graph you can explore, search, and ask questions about. · TypeScript · MIT · 2026-10
- [666ghj/MiroFish](https://github.com/666ghj/MiroFish) ★79.6k — A Simple and Universal Swarm Intelligence Engine, Predicting Anything. 简洁通用的群体智能引擎，预测万物 · Python · AGPL-3.0 · 2026-10
- [logseq/logseq](https://github.com/logseq/logseq) ★45.3k — A privacy-first, open-source platform for knowledge management and collaboration. Download link:  http://github.com/logseq/logseq/releases.  · Clojure · AGPL-3.0 · 2026-10
- [dgraph-io/dgraph](https://github.com/dgraph-io/dgraph) ★21.8k — high-performance graph database for real-time use cases · Go · Apache-2.0 · 2026-10
- [AgriciDaniel/claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) ★15.6k — Self-organizing AI second brain for Obsidian + Claude Code. Drop any source and Claude reads, links, and files it into one connected knowled · Python · MIT · 2026-09
- [semantica-agi/semantica](https://github.com/semantica-agi/semantica) ★14.1k — Graph-Native Infrastructure for Context and Accountable AI Systems · Python · MIT · 2026-10
- [vesoft-inc/nebula](https://github.com/vesoft-inc/nebula) ★12.4k — A distributed, fast open-source graph database featuring horizontal scalability and high availability · C++ · Apache-2.0 · 2026-09
- [FalkorDB/FalkorDB](https://github.com/FalkorDB/FalkorDB) ★10.2k — A super fast Graph Database uses GraphBLAS under the hood for its sparse adjacency matrix graph representation. Our goal is to provide the b · Rust · NOASSERTION · 2026-10
- [OpenSPG/KAG](https://github.com/OpenSPG/KAG) ★9.1k — KAG is a logical form-guided reasoning and retrieval framework based on OpenSPG engine and LLMs.  It is used to build logical reasoning and  · Python · Apache-2.0 · 2026-01
- [athensresearch/athens](https://github.com/athensresearch/athens) ★6.3k — Athens is no longer maintainted. Athens was an open-source, collaborative knowledge graph, backed by YC W21 · Clojure · NOASSERTION · 2023-02
- [potpie-ai/potpie](https://github.com/potpie-ai/potpie) ★5.7k — Context Graph for AI Native SDLC · Python · Apache-2.0 · 2026-10
- [neo4j-labs/llm-graph-builder](https://github.com/neo4j-labs/llm-graph-builder) ★5.3k — Neo4j graph construction from unstructured data using LLMs · Jupyter Notebook · Apache-2.0 · 2026-10
- [eugeniughelbur/obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) ★4.8k — Persistent memory for Claude Code and 6 other CLI agents, stored as plain markdown in your Obsidian vault. Stop re-explaining your projects, · Python · MIT · 2026-10
- [RUCAIBox/RecBole](https://github.com/RUCAIBox/RecBole) ★4.6k — A unified, comprehensive and efficient recommendation library · Python · MIT · 2025-02
- [FlowElement-xinliuyuansu/m_flow](https://github.com/FlowElement-xinliuyuansu/m_flow) ★4.5k — A bio-inspired cognitive memory engine — a new paradigm for Graph RAG. · Python · Apache-2.0 · 2026-09
- [zjunlp/DeepKE](https://github.com/zjunlp/DeepKE) ★4.5k — [EMNLP 2022] An Open Toolkit for Knowledge Graph Extraction and Construction · Python · MIT · 2026-07
- [CLUEbenchmark/CLUEDatasetSearch](https://github.com/CLUEbenchmark/CLUEDatasetSearch) ★4.5k — 搜索所有中文NLP数据集，附常用英文NLP数据集 · Python · NOASSERTION · 2022-11
- [varunshenoy/GraphGPT](https://github.com/varunshenoy/GraphGPT) ★4.4k — Extrapolating knowledge graphs from unstructured text using GPT-3 🕵️‍♂️ · JavaScript · MIT · 2024-05
- [qq547276542/Agriculture_KnowledgeGraph](https://github.com/qq547276542/Agriculture_KnowledgeGraph) ★4.4k — 农业知识图谱(AgriKG)：农业领域的信息检索，命名实体识别，关系抽取，智能问答，辅助决策 · Python · GPL-3.0 · 2025-02
- [GitJournal/GitJournal](https://github.com/GitJournal/GitJournal) ★4.2k — Mobile first Note Taking integrated with Git · Dart · AGPL-3.0 · 2026-05
- [yifanfeng97/Hyper-Extract](https://github.com/yifanfeng97/Hyper-Extract) ★4.2k — Hypergraph is more powerful. Transform unstructured text into structured knowledge with LLMs. Graphs, hypergraphs, and spatio-temporal extra · Python · NOASSERTION · 2026-10
- [aiming-lab/SimpleMem](https://github.com/aiming-lab/SimpleMem) ★3.8k — [ICML'26] SimpleMem: Efficient Lifelong Memory for LLM Agents — Text & Multimodal · Python · MIT · 2026-07
- [SamurAIGPT/llm-wiki-agent](https://github.com/SamurAIGPT/llm-wiki-agent) ★3.6k — A personal knowledge base that builds and maintains itself. Drop in sources — Claude (or Codex/Gemini) reads them, extracts knowledge, and m · Python · MIT · 2026-10
- [Ar9av/obsidian-wiki](https://github.com/Ar9av/obsidian-wiki) ★3.6k — Framework for AI agents to build and maintain a digital brain through Obsidian wiki | Memory System for Agents · Python · MIT · 2026-10
- [wx-chevalier/Developer-Zero-To-Mastery](https://github.com/wx-chevalier/Developer-Zero-To-Mastery) ★3.2k — :books: To Be Professional Developer From Zero To Mastery, Interactive MindMap, RoadMap(Learning Path/Interview Questions), xCompass, Weekly · HTML · NOASSERTION · 2026-05
- [GH05TCREW/pentestagent](https://github.com/GH05TCREW/pentestagent) ★3.2k — PentestAgent is an AI agent framework for black-box security testing, supporting bug bounty, red-team, and penetration testing workflows. · Python · MIT · 2026-10
- [robert-mcdermott/ai-knowledge-graph](https://github.com/robert-mcdermott/ai-knowledge-graph) ★3.1k — AI Powered Knowledge Graph Generator · Python · Apache-2.0 · 2026-09
- [MemMachine/MemMachine](https://github.com/MemMachine/MemMachine) ★3.1k — Universal memory layer for AI Agents. It provides scalable, extensible, and interoperable memory storage and retrieval to streamline AI agen · Python · Apache-2.0 · 2026-10
- [TriliumNext/Notes](https://github.com/TriliumNext/Notes) ★2.9k — Build your personal knowledge base with TriliumNext Notes · TypeScript · AGPL-3.0 · 2025-06
- [trustgraph-ai/trustgraph](https://github.com/trustgraph-ai/trustgraph) ★2.8k — Connect ontology-grounded context graphs with deterministic AI agent governance to enforce business rules before execution and preserve deci · Python · Apache-2.0 · 2026-10

### Embeddings (30)

- [supabase/supabase](https://github.com/supabase/supabase) ★111.6k — The Postgres development platform. Supabase gives you a dedicated Postgres database to build your web, mobile, and AI applications. · TypeScript · Apache-2.0 · 2026-10
- [InsForge/InsForge](https://github.com/InsForge/InsForge) ★13.1k — The all-in-one, open-source backend platform for agentic coding. InsForge gives your coding agent database, auth, storage, compute, hosting, · TypeScript · Apache-2.0 · 2026-10
- [FlagOpen/FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) ★12.3k — Retrieval and Retrieval-augmented LLMs · Python · MIT · 2026-08
- [Embedding/Chinese-Word-Vectors](https://github.com/Embedding/Chinese-Word-Vectors) ★12.2k — 100+ Chinese Word Vectors 上百种预训练中文词向量 · Python · Apache-2.0 · 2023-10
- [h2oai/h2ogpt](https://github.com/h2oai/h2ogpt) ★11.9k — Private chat with local GPT with document, images, video, etc. 100% private, Apache 2.0. Supports oLLaMa, Mixtral, llama.cpp, and more. Demo · Python · Apache-2.0 · 2025-10
- [apache/seatunnel](https://github.com/apache/seatunnel) ★9.7k — SeaTunnel is a multimodal, high-performance, distributed, massive data integration tool. · Java · Apache-2.0 · 2026-10
- [lance-format/lance](https://github.com/lance-format/lance) ★7.2k — Open Lakehouse Format for Multimodal AI. Convert from Parquet in 2 lines of code for 100x faster random access, vector index, and data versi · Rust · Apache-2.0 · 2026-10
- [KevinMusgrave/pytorch-metric-learning](https://github.com/KevinMusgrave/pytorch-metric-learning) ★6.3k — The easiest way to use deep metric learning in your application. Modular, flexible, and extensible. Written in PyTorch. · Python · MIT · 2025-08
- [Eventual-Inc/Daft](https://github.com/Eventual-Inc/Daft) ★5.8k — High-performance data engine for AI and multimodal workloads. Process images, audio, video, and structured data at any scale · Rust · Apache-2.0 · 2026-10
- [brianpetro/obsidian-smart-connections](https://github.com/brianpetro/obsidian-smart-connections) ★5.5k — Find related notes and excerpts while writing. Your link building copilot displays relevant content in graph + list view. A local embedding  · JavaScript · NOASSERTION · 2026-10
- [Marker-Inc-Korea/AutoRAG](https://github.com/Marker-Inc-Korea/AutoRAG) ★5.1k — AutoRAG: Now your agent can find anything in your computer. It gets smarter if you are using it frequently. · TypeScript · Apache-2.0 · 2026-10
- [huggingface/text-embeddings-inference](https://github.com/huggingface/text-embeddings-inference) ★5.1k — A blazing fast inference solution for text embeddings models · Rust · Apache-2.0 · 2026-10
- [shibing624/text2vec](https://github.com/shibing624/text2vec) ★5.0k — text2vec, text to vector. 文本向量表征工具，把文本转化为向量矩阵，实现了Word2Vec、RankBM25、Sentence-BERT、CoSENT等文本表征、文本相似度计算模型，开箱即用。 · Python · Apache-2.0 · 2026-02
- [ARahim3/DigUp](https://github.com/ARahim3/DigUp) ★4.2k — Search your computer by what's in your files: photos, PDFs, documents, recordings, videos and code. On-device on Mac, Windows and Linux, bui · Swift · MIT · 2026-10
- [lightly-ai/lightly](https://github.com/lightly-ai/lightly) ★3.8k — A python library for self-supervised learning on images. · Python · MIT · 2026-10
- [twinnydotdev/twinny](https://github.com/twinnydotdev/twinny) ★3.7k — Open-source AI coding assistant for VS Code. Coding agent, code completion, chat, edits and reviews with local or hosted models. Your models · TypeScript · MIT · 2026-10
- [filipecalegario/awesome-generative-ai](https://github.com/filipecalegario/awesome-generative-ai) ★3.6k — A curated list of Generative AI tools, works, models, and references · CC0-1.0 · 2025-12
- [tensorflow/hub](https://github.com/tensorflow/hub) ★3.5k — A library for transfer learning by reusing parts of TensorFlow models. · Python · Apache-2.0 · 2025-01
- [embeddings-benchmark/mteb](https://github.com/embeddings-benchmark/mteb) ★3.5k — MTEB: State-of-the-art evaluation of embeddings across languages and modalities · Python · Apache-2.0 · 2026-10
- [towhee-io/towhee](https://github.com/towhee-io/towhee) ★3.5k — Towhee is a framework that is dedicated to making neural data processing pipelines simple and fast. · Python · Apache-2.0 · 2024-10
- [superlinked/sie](https://github.com/superlinked/sie) ★3.4k — Open-source inference server and production cluster for all the models your agent needs. · Python · Apache-2.0 · 2026-10
- [qdrant/fastembed](https://github.com/qdrant/fastembed) ★3.2k — Fast, Accurate, Lightweight Python library to make State of the Art Embedding · Python · Apache-2.0 · 2026-10
- [hegelai/prompttools](https://github.com/hegelai/prompttools) ★3.1k — Open-source tools for prompt testing and experimentation, with support for both LLMs (e.g. OpenAI, LLaMA) and vector databases (e.g. Chroma, · Python · Apache-2.0 · 2026-02
- [eugeneyan/ml-surveys](https://github.com/eugeneyan/ml-surveys) ★2.9k — 📋 Survey papers summarizing advances in deep learning, NLP, CV, graphs, reinforcement learning, recommendations, graphs, etc. · MIT · 2023-03
- [codedogQBY/ReadAny](https://github.com/codedogQBY/ReadAny) ★2.8k — AI-powered cross-platform e-book reader with semantic search, RAG chat, local vector store, notes, TTS, and WebDAV sync. · TypeScript · NOASSERTION · 2026-10
- [zilliztech/memsearch](https://github.com/zilliztech/memsearch) ★2.8k — A persistent, unified memory layer for all your AI agents (e.g. Claude Code, Codex, DSH), backed by Markdown and Milvus. · Python · MIT · 2026-10
- [ailia-ai/ailia-models](https://github.com/ailia-ai/ailia-models) ★2.4k — The collection of pre-trained, state-of-the-art AI models for ailia SDK · Python · NOASSERTION · 2026-10
- [google/generative-ai-docs](https://github.com/google/generative-ai-docs) ★2.3k — This repository is deprecated and will be archived · Jupyter Notebook · Apache-2.0 · 2026-01
- [MinishLab/model2vec](https://github.com/MinishLab/model2vec) ★2.2k — Fast State-of-the-Art Static Embeddings · Python · MIT · 2026-10
- [PetrochukM/PyTorch-NLP](https://github.com/PetrochukM/PyTorch-NLP) ★2.2k — Basic Utilities for PyTorch Natural Language Processing (NLP) · Python · BSD-3-Clause · 2023-07

### TUIs (30)

- [Textualize/rich](https://github.com/Textualize/rich) ★57.5k — Rich is a Python library for rich text and beautiful formatting in the terminal. · Python · MIT · 2026-06
- [wagoodman/dive](https://github.com/wagoodman/dive) ★54.6k — A tool for exploring each layer in a docker image · Go · MIT · 2025-12
- [charmbracelet/bubbletea](https://github.com/charmbracelet/bubbletea) ★45.4k — A powerful little TUI framework 🏗 · Go · MIT · 2026-10
- [sxyazi/yazi](https://github.com/sxyazi/yazi) ★42.9k — 💥 Blazing fast terminal file manager written in Rust, based on async I/O. · Rust · MIT · 2026-10
- [Textualize/textual](https://github.com/Textualize/textual) ★37.5k — The lean application framework for Python.  Build sophisticated user interfaces with a simple Python API. Run your apps in the terminal and  · Python · MIT · 2026-10
- [yorukot/superfile](https://github.com/yorukot/superfile) ★23.8k — Pretty fancy and modern terminal file manager · Go · MIT · 2026-10
- [ratatui/ratatui](https://github.com/ratatui/ratatui) ★23.0k — A Rust crate for cooking up terminal user interfaces (TUIs) 👨‍🍳🐀 https://ratatui.rs · Rust · MIT · 2026-10
- [pranshuparmar/witr](https://github.com/pranshuparmar/witr) ★22.7k — Why is this running? Trace any process, port, container, or file back to what started it - CLI + TUI. · Go · Apache-2.0 · 2026-10
- [gitui-org/gitui](https://github.com/gitui-org/gitui) ★22.6k — Blazing 💥 fast terminal-ui for git written in rust 🦀 · Rust · MIT · 2026-10
- [jarun/nnn](https://github.com/jarun/nnn) ★22.1k — n³ The unorthodox terminal file manager · C · BSD-2-Clause · 2026-10
- [allinurl/goaccess](https://github.com/allinurl/goaccess) ★21.1k — GoAccess is a real-time web log analyzer and interactive viewer that runs in a terminal in *nix systems or through your browser. · C · MIT · 2026-10
- [antonmedv/fx](https://github.com/antonmedv/fx) ★20.7k — Terminal JSON viewer & processor · Go · MIT · 2026-10
- [wtfutil/wtf](https://github.com/wtfutil/wtf) ★17.1k — The personal information dashboard for your terminal · Go · MPL-2.0 · 2026-09
- [muesli/duf](https://github.com/muesli/duf) ★15.3k — Disk Usage/Free Utility - a better 'df' alternative · Go · NOASSERTION · 2026-01
- [ClementTsang/bottom](https://github.com/ClementTsang/bottom) ★14.1k — Yet another cross-platform graphical process/system monitor. · Rust · MIT · 2026-10
- [anomalyco/opentui](https://github.com/anomalyco/opentui) ★13.6k — OpenTUI is a library to build terminal user interfaces (TUI) · TypeScript · MIT · 2026-10
- [jonas/tig](https://github.com/jonas/tig) ★13.4k — Text-mode interface for git · C · GPL-2.0 · 2026-10
- [dlvhdr/gh-dash](https://github.com/dlvhdr/gh-dash) ★12.6k — A rich terminal UI for GitHub that doesn't break your flow. · Go · MIT · 2026-10
- [darrenburns/posting](https://github.com/darrenburns/posting) ★12.5k — The modern API client that lives in your terminal. · Go · Apache-2.0 · 2026-10
- [charmbracelet/lipgloss](https://github.com/charmbracelet/lipgloss) ★11.9k — Style definitions for nice terminal layouts 👄 · Go · MIT · 2026-10
- [tui-cs/Terminal.Gui](https://github.com/tui-cs/Terminal.Gui) ★11.3k — Cross Platform Terminal UI toolkit for .NET · C# · MIT · 2026-10
- [modelcontextprotocol/inspector](https://github.com/modelcontextprotocol/inspector) ★11.1k — Visual testing tool for MCP servers · TypeScript · NOASSERTION · 2026-10
- [fdehau/tui-rs](https://github.com/fdehau/tui-rs) ★10.9k — Build terminal user interfaces and dashboards using Rust · Rust · MIT · 2023-08
- [ArthurSonzogni/FTXUI](https://github.com/ArthurSonzogni/FTXUI) ★10.8k — :computer: C++ Functional Terminal User Interface. :heart: · C++ · MIT · 2026-10
- [tstack/lnav](https://github.com/tstack/lnav) ★10.7k — Log file navigator · C++ · BSD-2-Clause · 2026-10
- [hatoo/oha](https://github.com/hatoo/oha) ★10.6k — Ohayou(おはよう), HTTP load generator, inspired by rakyll/hey with tui animation. · Rust · MIT · 2026-10
- [Kuberwastaken/claurst](https://github.com/Kuberwastaken/claurst) ★10.3k — Agentic Coding for Builders who Ship · Rust · GPL-3.0 · 2026-10
- [gcla/termshark](https://github.com/gcla/termshark) ★10.0k — A terminal UI for tshark, inspired by Wireshark · Go · MIT · 2024-04
- [aksakalli/gtop](https://github.com/aksakalli/gtop) ★9.9k — System monitoring dashboard for terminal · JavaScript · MIT · 2025-11
- [modem-dev/hunk](https://github.com/modem-dev/hunk) ★9.6k — Review-first terminal diff viewer for agentic coders · TypeScript · MIT · 2026-10

### Terminal emulators (30)

- [alacritty/alacritty](https://github.com/alacritty/alacritty) ★66.0k — A cross-platform, OpenGL terminal emulator. · Rust · Apache-2.0 · 2026-10
- [termux/termux-app](https://github.com/termux/termux-app) ★62.7k — Termux - a terminal emulator application for Android OS extendible by variety of packages. · Java · NOASSERTION · 2026-09
- [ghostty-org/ghostty](https://github.com/ghostty-org/ghostty) ★62.3k — 👻 Ghostty is a fast, feature-rich, and cross-platform terminal emulator that uses platform-native UI and GPU acceleration. · Zig · MIT · 2026-10
- [wezterm/wezterm](https://github.com/wezterm/wezterm) ★29.2k — A GPU-accelerated cross-platform terminal emulator and multiplexer written by @wez and implemented in Rust · Rust · NOASSERTION · 2026-10
- [Swordfish90/cool-retro-term](https://github.com/Swordfish90/cool-retro-term) ★26.5k — A good looking terminal emulator which mimics the old cathode display... · QML · NOASSERTION · 2026-05
- [gnachman/iTerm2](https://github.com/gnachman/iTerm2) ★18.2k — iTerm2 is a terminal emulator for Mac OS X that does amazing things. · Swift · GPL-2.0 · 2026-10
- [Gogh-Co/Gogh](https://github.com/Gogh-Co/Gogh) ★10.3k — Gogh is a collection of color schemes for various terminal emulators, including Gnome Terminal, Pantheon Terminal, Tilix, and XFCE4 Terminal · Shell · NOASSERTION · 2026-10
- [felixse/FluentTerminal](https://github.com/felixse/FluentTerminal) ★9.6k — A Terminal Emulator based on UWP and web technologies. · C# · GPL-3.0 · 2026-10
- [raphamorim/rio](https://github.com/raphamorim/rio) ★7.6k — A hardware-accelerated GPU terminal emulator focusing to run in desktops and browsers. · Rust · MIT · 2026-10
- [liftoff/GateOne](https://github.com/liftoff/GateOne) ★6.3k — Gate One is an HTML5-powered terminal emulator and SSH client · JavaScript · NOASSERTION · 2023-03
- [gnunn1/tilix](https://github.com/gnunn1/tilix) ★5.7k — A tiling terminal emulator for Linux using GTK+ 3 · D · MPL-2.0 · 2026-07
- [TermoraDev/termora](https://github.com/TermoraDev/termora) ★3.8k — Termora is a terminal emulator and SSH client for Windows, macOS and Linux. · Kotlin · NOASSERTION · 2026-09
- [p-e-w/finalterm](https://github.com/p-e-w/finalterm) ★3.8k — At last – a modern terminal emulator (NO LONGER MAINTAINED) · Vala · GPL-3.0 · 2015-09
- [vercel-labs/wterm](https://github.com/vercel-labs/wterm) ★3.5k — A terminal emulator for the web · TypeScript · Apache-2.0 · 2026-10
- [Kuddev/pebrel](https://github.com/Kuddev/pebrel) ★3.4k — AI-native, GPU-accelerated terminal emulator for Windows with SSH, persistent sessions, split panes, and first-class AI CLI workflows. · Rust · GPL-3.0 · 2026-10
- [orhun/ratty](https://github.com/orhun/ratty) ★3.3k — A GPU-rendered terminal emulator with inline 3D graphics 🐀🧀 · Rust · MIT · 2026-10
- [jackpal/Android-Terminal-Emulator](https://github.com/jackpal/Android-Terminal-Emulator) ★3.2k — A VT-100 terminal emulator for the Android OS · Java · Apache-2.0 · 2022-01
- [mskyaxl/wsl-terminal](https://github.com/mskyaxl/wsl-terminal) ★3.1k — Terminal emulator for Windows Subsystem for Linux (WSL) · Shell · MIT · 2020-09
- [liamg/darktile](https://github.com/liamg/darktile) ★3.1k — :waning_crescent_moon: Darktile is an experimental/abandoned GPU rendered terminal emulator designed for tiling window managers. · Go · MIT · 2023-03
- [contour-terminal/contour](https://github.com/contour-terminal/contour) ★3.0k — Modern C++ Terminal Emulator · C++ · Apache-2.0 · 2026-10
- [cdleon/awesome-terminals](https://github.com/cdleon/awesome-terminals) ★3.0k — Terminal Emulators · NOASSERTION · 2026-09
- [sedwards2009/extraterm](https://github.com/sedwards2009/extraterm) ★2.8k — The swiss army chainsaw of terminal emulators · TypeScript · MIT · 2026-06
- [subhra74/snowflake](https://github.com/subhra74/snowflake) ★2.2k — Graphical SFTP client and terminal emulator with helpful utilities · Java · GPL-3.0 · 2024-05
- [mintty/mintty](https://github.com/mintty/mintty) ★1.8k — The Cygwin Terminal – terminal emulator for Cygwin, MSYS, and WSL · C · NOASSERTION · 2026-10
- [migueldeicaza/SwiftTerm](https://github.com/migueldeicaza/SwiftTerm) ★1.7k — Xterm/VT100 Terminal emulator library in Swift with AppKit, UIKit, WebAssembly, Web, headless frontends. · Swift · MIT · 2026-10
- [termstandard/colors](https://github.com/termstandard/colors) ★1.5k — Color standards for terminal emulators · Unlicense · 2026-08
- [libtcod/libtcod](https://github.com/libtcod/libtcod) ★1.2k — A collection of tools and algorithms for developing traditional roguelikes.  Such as field-of-view, pathfinding, and a tile-based terminal e · C · BSD-3-Clause · 2026-10
- [ghostty-org/ghostling](https://github.com/ghostty-org/ghostling) ★1.1k — A minimum viable terminal emulator built on top of the libghostty C API. Ex minimo, infinita nascuntur. 👻🐣 · C · MIT · 2026-08
- [cosmos72/twin](https://github.com/cosmos72/twin) ★1.1k — Text mode window environment. A terminal emulator and multiplexer with mouse support, overlapped windows and networked clients. Text-mode eq · C · GPL-2.0 · 2026-08
- [dakra/ghostel](https://github.com/dakra/ghostel) ★993 — Terminal emulator powered by libghostty · Emacs Lisp · GPL-3.0 · 2026-10

### Terminal UI frameworks (30)

- [ohmyzsh/ohmyzsh](https://github.com/ohmyzsh/ohmyzsh) ★190.0k — 🙃   A delightful community-driven (with 2,500+ contributors) framework for managing your zsh configuration. Includes 300+ optional plugins ( · Shell · MIT · 2026-10
- [microsoft/terminal](https://github.com/microsoft/terminal) ★105.2k — The new Windows Terminal and the original Windows console host, all in the same place! · C++ · MIT · 2026-10
- [jesseduffield/lazygit](https://github.com/jesseduffield/lazygit) ★83.2k — simple terminal UI for git commands · Go · MIT · 2026-10
- [career-ops-hq/career-ops](https://github.com/career-ops-hq/career-ops) ★75.1k — Open-source AI job search agent and job finder: scan job boards, score each job 1-5 against your CV before you apply, tailor an ATS-friendly · JavaScript · MIT · 2026-10
- [Eugeny/tabby](https://github.com/Eugeny/tabby) ★75.0k — A terminal for a more modern age · TypeScript · MIT · 2026-10
- [warpdotdev/warp](https://github.com/warpdotdev/warp) ★65.5k — Warp is an agentic development environment, born out of the terminal. · Rust · AGPL-3.0 · 2026-10
- [tldr-pages/tldr](https://github.com/tldr-pages/tldr) ★64.0k — Collaborative cheatsheets for console commands 📚. · Markdown · NOASSERTION · 2026-10
- [sharkdp/bat](https://github.com/sharkdp/bat) ★60.8k — A cat(1) clone with wings. · Rust · Apache-2.0 · 2026-10
- [sharkdp/fd](https://github.com/sharkdp/fd) ★44.8k — A simple, fast and user-friendly alternative to 'find' · Rust · Apache-2.0 · 2026-10
- [vercel/hyper](https://github.com/vercel/hyper) ★44.7k — A terminal built on web technologies · TypeScript · MIT · 2026-08
- [chubin/cheat.sh](https://github.com/chubin/cheat.sh) ★41.8k — the only cheat sheet you need · Python · MIT · 2026-09
- [httpie/cli](https://github.com/httpie/cli) ★38.6k — 🥧 HTTPie CLI  — modern, user-friendly command-line HTTP client for the API era. JSON support, colors, sessions, downloads, plugins & more. · Python · BSD-3-Clause · 2024-12
- [zellij-org/zellij](https://github.com/zellij-org/zellij) ★35.7k — A terminal workspace with batteries included · Rust · MIT · 2026-10
- [kovidgoyal/kitty](https://github.com/kovidgoyal/kitty) ★35.3k — If you live in the terminal, kitty is made for you! Cross-platform, fast, feature-rich, GPU based. · Python · GPL-3.0 · 2026-10
- [fish-shell/fish-shell](https://github.com/fish-shell/fish-shell) ★34.3k — The user-friendly command line shell. · Rust · NOASSERTION · 2026-10
- [nicolargo/glances](https://github.com/nicolargo/glances) ★33.8k — Glances an Eye on your system. A top/htop alternative for GNU/Linux, BSD, macOS and Windows operating systems. · Python · NOASSERTION · 2026-10
- [ibraheemdev/modern-unix](https://github.com/ibraheemdev/modern-unix) ★33.0k — A collection of modern/faster/saner alternatives to common unix commands. · NOASSERTION · 2024-09
- [kingToolbox/WindTerm](https://github.com/kingToolbox/WindTerm) ★32.5k — A professional cross-platform SSH/Sftp/Shell/Telnet/Tmux/Serial terminal. · C · NOASSERTION · 2025-03
- [jumpserver/jumpserver](https://github.com/jumpserver/jumpserver) ★31.8k — JumpServer is an Open-source Privileged Access Management (PAM) platform with AI-powered capabilities, providing DevOps and IT teams a unifi · Python · GPL-3.0 · 2026-10
- [tqdm/tqdm](https://github.com/tqdm/tqdm) ★31.4k — :zap: A Fast, Extensible Progress Bar for Python and CLI · Python · NOASSERTION · 2026-10
- [herrbischoff/awesome-macos-command-line](https://github.com/herrbischoff/awesome-macos-command-line) ★31.0k — Use your macOS terminal shell to do awesome things. · NOASSERTION · 2026-03
- [chubin/wttr.in](https://github.com/chubin/wttr.in) ★30.7k — :partly_sunny: The right way to check the weather · Go · Apache-2.0 · 2026-09
- [micro-editor/micro](https://github.com/micro-editor/micro) ★29.7k — A modern and intuitive terminal-based text editor · Go · MIT · 2026-10
- [sharkdp/hyperfine](https://github.com/sharkdp/hyperfine) ★29.1k — A command-line benchmarking tool · Rust · Apache-2.0 · 2026-10
- [manaflow-ai/cmux](https://github.com/manaflow-ai/cmux) ★28.2k — Open source Ghostty-based macOS terminal with vertical tabs and notifications for AI coding agents. Built for multitasking, organization, an · Swift · NOASSERTION · 2026-10
- [mbadolato/iTerm2-Color-Schemes](https://github.com/mbadolato/iTerm2-Color-Schemes) ★27.3k — Our next-generation, interactive app is currently in beta!  Come try it out at terminalthemes.com! Over 750 terminal color schemes/themes fo · Shell · NOASSERTION · 2026-10
- [gpakosz/.tmux](https://github.com/gpakosz/.tmux) ★25.4k — Oh my tmux! My self-contained, pretty & versatile tmux configuration made with 💛🩷💙🖤❤️🤍 · Shell · MIT · 2026-08
- [withfig/autocomplete](https://github.com/withfig/autocomplete) ★25.2k — IDE-style autocomplete for your existing terminal & shell · TypeScript · MIT · 2025-05
- [fastfetch-cli/fastfetch](https://github.com/fastfetch-cli/fastfetch) ★25.0k — A maintained, feature-rich and performance oriented, neofetch like system information tool. · C · MIT · 2026-10
- [eza-community/eza](https://github.com/eza-community/eza) ★23.6k — A modern alternative to ls · Rust · EUPL-1.2 · 2026-08

### CLI tools (high quality) (30)

- [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) ★198.3k — A feature-rich command-line audio/video downloader · Python · Unlicense · 2026-10
- [sherlock-project/sherlock](https://github.com/sherlock-project/sherlock) ★94.2k — Hunt down social media accounts by username across social networks · Python · MIT · 2026-10
- [junegunn/fzf](https://github.com/junegunn/fzf) ★83.6k — :cherry_blossom: A command-line fuzzy finder · Go · MIT · 2026-10
- [BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep) ★69.1k — ripgrep recursively searches directories for a regex pattern while respecting your gitignore · Rust · Unlicense · 2026-08
- [Raphire/Win11Debloat](https://github.com/Raphire/Win11Debloat) ★59.4k — A simple, lightweight PowerShell script that allows you to remove pre-installed apps, disable telemetry, as well as perform various other ch · PowerShell · MIT · 2026-10
- [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) ★49.6k — Agent skills for Obsidian. Teach your agent to use Obsidian CLI and open formats including Markdown, Bases, JSON Canvas. · MIT · 2026-09
- [Aider-AI/aider](https://github.com/Aider-AI/aider) ★49.6k — aider is AI pair programming in your terminal · Python · Apache-2.0 · 2026-05
- [cli/cli](https://github.com/cli/cli) ★46.7k — GitHub’s official command line tool · Go · MIT · 2026-10
- [google/zx](https://github.com/google/zx) ★45.8k — A tool for writing better scripts · JavaScript · Apache-2.0 · 2026-10
- [spf13/cobra](https://github.com/spf13/cobra) ★44.7k — A Commander for modern Go CLI interactions · Go · Apache-2.0 · 2026-07
- [ajeetdsouza/zoxide](https://github.com/ajeetdsouza/zoxide) ★40.1k — A smarter cd command. Supports all major shells. · Rust · MIT · 2026-10
- [vadimdemedes/ink](https://github.com/vadimdemedes/ink) ★40.1k — 🌈 React for interactive command-line apps · TypeScript · MIT · 2026-10
- [soxoj/maigret](https://github.com/soxoj/maigret) ★39.1k — 🕵️‍♂️ Collect a dossier on a person by username from 6K websites · Python · MIT · 2026-10
- [alebcay/awesome-shell](https://github.com/alebcay/awesome-shell) ★37.8k — A curated list of awesome command-line frameworks, toolkits, guides and gizmos. Inspired by awesome-php. · CC0-1.0 · 2025-08
- [Twigpine/openclaude](https://github.com/Twigpine/openclaude) ★33.9k — runs anywhere. uses anything · TypeScript · NOASSERTION · 2026-10
- [FujiwaraChoki/MoneyPrinterV2](https://github.com/FujiwaraChoki/MoneyPrinterV2) ★32.1k — Automate the process of making money online. · Python · AGPL-3.0 · 2026-09
- [googleworkspace/cli](https://github.com/googleworkspace/cli) ★31.5k — Google Workspace CLI — one command-line tool for Drive, Gmail, Calendar, Sheets, Docs, Chat, Admin, and more. Dynamically built from Google  · Rust · Apache-2.0 · 2026-10
- [nrwl/nx](https://github.com/nrwl/nx) ★29.4k — The Monorepo Platform that amplifies both developers and AI agents. Nx optimizes your builds, scales your CI, and fixes failed PRs automatic · TypeScript · MIT · 2026-10
- [t3-oss/create-t3-app](https://github.com/t3-oss/create-t3-app) ★29.2k — The best way to start a full-stack, typesafe Next.js app · TypeScript · MIT · 2025-12
- [jarrodwatts/claude-hud](https://github.com/jarrodwatts/claude-hud) ★28.6k — A Claude Code plugin that shows what's happening - context usage, active tools, running agents, and todo progress · JavaScript · MIT · 2026-10
- [ifixai-ai/iFixAi](https://github.com/ifixai-ai/iFixAi) ★28.5k — Independent Auditing of AI Agents. Run by human or the agent itself, to answer the most crucial question in the AI Agent Economy. Is the age · Python · Apache-2.0 · 2026-10
- [google/python-fire](https://github.com/google/python-fire) ★28.2k — Python Fire is a library for automatically generating command line interfaces (CLIs) from absolutely any Python object. · Python · NOASSERTION · 2026-07
- [acheong08/ChatGPT](https://github.com/acheong08/ChatGPT) ★27.9k — Reverse engineered ChatGPT API · Python · GPL-2.0 · 2023-08
- [charmbracelet/glow](https://github.com/charmbracelet/glow) ★27.7k — Render markdown on the CLI, with pizzazz! 💅🏻 · Go · MIT · 2026-10
- [Kilo-Org/kilocode](https://github.com/Kilo-Org/kilocode) ★27.6k — Kilo is the all-in-one agentic engineering platform. Build, ship, and iterate faster with the most popular open source coding agent. · TypeScript · MIT · 2026-10
- [angular/angular-cli](https://github.com/angular/angular-cli) ★27.0k — CLI tool for Angular · TypeScript · MIT · 2026-10
- [Devolutions/UniGetUI](https://github.com/Devolutions/UniGetUI) ★26.6k — UniGetUI: The Graphical Interface for your package managers. Could be terribly described as a package manager manager to manage your package · C# · MIT · 2026-10
- [asdf-vm/asdf](https://github.com/asdf-vm/asdf) ★25.6k — Extendable version manager with support for Ruby, Node.js, Elixir, Erlang & more · Go · MIT · 2026-10
- [vercel/pkg](https://github.com/vercel/pkg) ★24.3k — Package your Node.js project into an executable · JavaScript · MIT · 2024-01
- [qeeqbox/social-analyzer](https://github.com/qeeqbox/social-analyzer) ★24.3k — API, CLI, and Web App for analyzing and finding a person's profile in 1000 social media \ websites · JavaScript · AGPL-3.0 · 2026-01

### LLM evaluation (29)

- [Arize-ai/phoenix](https://github.com/Arize-ai/phoenix) ★11.9k — AI Observability & Evaluation · Python · NOASSERTION · 2026-10
- [open-compass/opencompass](https://github.com/open-compass/opencompass) ★7.5k — OpenCompass is an LLM evaluation platform, supporting a wide range of models from OpenAI, Anthropic, Gemini, Qwen, GLM, DeepSeek, etc, acros · Python · Apache-2.0 · 2026-10
- [Giskard-AI/giskard-oss](https://github.com/Giskard-AI/giskard-oss) ★5.9k — 🐢 Open-Source Evaluation & Testing library for LLM Agents · Python · Apache-2.0 · 2026-10
- [truera/trulens](https://github.com/truera/trulens) ★3.6k — Evaluation and Tracking for LLM Experiments and AI Agents · Python · MIT · 2026-10
- [uptrain-ai/uptrain](https://github.com/uptrain-ai/uptrain) ★2.4k — UpTrain is an open-source unified platform to evaluate and improve Generative AI applications. We provide grades for 20+ preconfigured check · Python · Apache-2.0 · 2024-08
- [AI-QL/tuui](https://github.com/AI-QL/tuui) ★1.2k — A desktop MCP client designed as a tool unitary utility integration, accelerating AI adoption through the Model Context Protocol (MCP) and e · TypeScript · Apache-2.0 · 2026-05
- [verifywise-ai/verifywise](https://github.com/verifywise-ai/verifywise) ★364 — Complete AI governance and LLM Evals platform with support for EU AI Act, ISO 42001, NIST AI RMF and 20+ more AI frameworks and regulations. · TypeScript · NOASSERTION · 2026-10
- [athina-ai/athina-evals](https://github.com/athina-ai/athina-evals) ★302 — Python SDK for running evaluations on LLM generated responses · Python · NOASSERTION · 2025-06
- [QuesmaOrg/BinaryAudit](https://github.com/QuesmaOrg/BinaryAudit) ★104 — An open-source benchmark for evaluating AI agents' ability to find backdoors hidden in compiled binaries. · Shell · NOASSERTION · 2026-07
- [Re-Align/just-eval](https://github.com/Re-Align/just-eval) ★90 — A simple GPT-based evaluation tool for multi-aspect, interpretable assessment of LLMs. · Python · MIT · 2024-01
- [whitecircle/circle-guard-bench](https://github.com/whitecircle/circle-guard-bench) ★82 — First-of-its-kind AI benchmark for evaluating the protection capabilities of large language model (LLM) guard systems (guardrails and safegu · Python · Apache-2.0 · 2026-03
- [parea-ai/parea-sdk-py](https://github.com/parea-ai/parea-sdk-py) ★82 — Python SDK for experimenting, testing, evaluating & monitoring LLM-powered applications - Parea AI (YC S23) · Python · Apache-2.0 · 2025-02
- [fastxyz/skill-optimizer](https://github.com/fastxyz/skill-optimizer) ★81 — Benchmark, evaluate, and optimize skills to ensure reliable performance across all LLMs · TypeScript · MIT · 2026-05
- [grigio/llm-eval-simple](https://github.com/grigio/llm-eval-simple) ★72 — llm-eval-simple is a simple LLM evaluation framework with intermediate actions and prompt pattern selection · Python · MIT · 2026-02
- [kuk/rulm-sbs2](https://github.com/kuk/rulm-sbs2) ★61 — Бенчмарк сравнивает русские аналоги ChatGPT: Saiga, YandexGPT, Gigachat · Jupyter Notebook · NOASSERTION · 2023-09
- [izam-mohammed/ragrank](https://github.com/izam-mohammed/ragrank) ★47 — 🎯 Your free LLM evaluation toolkit helps you assess the accuracy of facts, how well it understands context, its tone, and more. This helps y · Python · Apache-2.0 · 2026-10
- [multinear/multinear](https://github.com/multinear/multinear) ★45 — Develop reliable AI apps · Python · MIT · 2025-09
- [sunxin-ai/dsh-design-qa](https://github.com/sunxin-ai/dsh-design-qa) ★44 — Design-fidelity QA for DeepSeek Harness: lend any text-only model an eye, then judge whether the implementation matches the mock. Ships the  · JavaScript · MIT · 2026-09
- [Striveworks/valor](https://github.com/Striveworks/valor) ★40 — Valor is a lightweight, numpy-based library designed for fast and seamless evaluation of machine learning models. · Python · MIT · 2026-10
- [harnexa/nexa-gauge](https://github.com/harnexa/nexa-gauge) ★40 — An graph-eval framework for LLM's · Python · MIT · 2026-08
- [alan-turing-institute/prompto](https://github.com/alan-turing-institute/prompto) ★38 — An open source library for asynchronous querying of LLM endpoints · Python · MIT · 2025-07
- [paradime-io/dbt-llm-evals](https://github.com/paradime-io/dbt-llm-evals) ★35 — The warehouse-native LLM evaluation package for dbt™ - monitor AI quality without data egress · Python · NOASSERTION · 2026-02
- [thedataquarry/structured-outputs](https://github.com/thedataquarry/structured-outputs) ★29 — Structured output benchmarks comparing DSPy and BAML with different LLMs · Python · MIT · 2025-12
- [sx4im/skillcheck](https://github.com/sx4im/skillcheck) ★29 — Blind A/B testing for AI agent skills, .cursorrules, CLAUDE.md, and system prompts. Detects placebo and harmful instructions. · TypeScript · MIT · 2026-10
- [genia-dev/vibraniumdome](https://github.com/genia-dev/vibraniumdome) ★29 — LLM Security Platform. · Python · GPL-3.0 · 2024-10
- [HumphreySun98/repoagentbench](https://github.com/HumphreySun98/repoagentbench) ★28 — SWE-bench for your codebase — mine your merged PRs into local, contamination-free coding-agent benchmarks. Adapters: claude-code, aider (Opu · Python · MIT · 2026-04
- [multivon-ai/multivon-eval](https://github.com/multivon-ai/multivon-eval) ★26 — Practical LLM evaluation for teams that ship to production. Deterministic + LLM-as-judge evaluators, dataset support, CI/CD integration. · Python · NOASSERTION · 2026-09
- [amplifying-ai/ai-product-bench](https://github.com/amplifying-ai/ai-product-bench) ★24 · HTML · NOASSERTION · 2025-05
- [Supahands/llm-comparison-backend](https://github.com/Supahands/llm-comparison-backend) ★23 — This is an opensource project allowing you to compare two LLM's head to head with a given prompt, this section will be regarding the backend · Python · Apache-2.0 · 2026-01

### Prompt engineering (30)

- [microsoft/generative-ai-for-beginners](https://github.com/microsoft/generative-ai-for-beginners) ★121.4k — 21 Lessons, Get Started Building with Generative AI · Jupyter Notebook · MIT · 2026-10
- [Imbad0202/academic-research-skills](https://github.com/Imbad0202/academic-research-skills) ★52.3k — Academic Research Skills for Claude Code: research → write → review → revise → finalize · Python · NOASSERTION · 2026-10
- [elder-plinius/CL4R1T4S](https://github.com/elder-plinius/CL4R1T4S) ★51.3k — LEAKED SYSTEM PROMPTS FOR CHATGPT, CLAUDE, GEMINI, GROK, PERPLEXITY, CURSOR, LOVABLE, REPLIT, AND MORE! - AI SYSTEMS TRANSPARENCY FOR ALL! 👐 · AGPL-3.0 · 2026-09
- [github/awesome-copilot](https://github.com/github/awesome-copilot) ★40.1k — Community-contributed instructions, agents, skills, and configurations to help you make the most of GitHub Copilot. · JavaScript · MIT · 2026-10
- [freestylefly/awesome-gpt-image-2](https://github.com/freestylefly/awesome-gpt-image-2) ★34.6k — Prompt as Code | GPT Image 2 / 2.5 提示词与案例库，530+ 个案例、20+ 套工业级模板与可复用 Skills，新增 2.5 同提示词对比专区，附完整提示词与生成记录，持续更新。 · JavaScript · MIT · 2026-10
- [mlflow/mlflow](https://github.com/mlflow/mlflow) ★28.4k — The open source AI engineering platform for agents, LLMs, and ML models. MLflow enables teams of all sizes to debug, evaluate, monitor, and  · Python · Apache-2.0 · 2026-10
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) ★28.3k — 380 Claude Code skills & agent skills & plugins (30+ Agents, 70+ custom commands, 380+ skills, customizable references, scripts)for Claude C · Python · MIT · 2026-08
- [comet-ml/opik](https://github.com/comet-ml/opik) ★22.6k — Debug, evaluate, and monitor your LLM applications, RAG systems, and agentic workflows with comprehensive tracing, automated evaluations, an · Python · Apache-2.0 · 2026-10
- [AI4Finance-Foundation/FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) ★21.4k — FinGPT: Open-Source Financial Large Language Models!  Revolutionize 🔥    We release the trained model on HuggingFace. · Jupyter Notebook · MIT · 2026-09
- [tradecatlabs/vibe-coding-cn](https://github.com/tradecatlabs/vibe-coding-cn) ★17.6k — Vibe Coding 从入门到精通教程｜AI 结对编程工作流｜Prompt、Skill、Workflow、上下文管理、codex实战指南 · Makefile · MIT · 2026-10
- [EvoLinkAI/awesome-gpt-image-2-API-and-Prompts](https://github.com/EvoLinkAI/awesome-gpt-image-2-API-and-Prompts) ★17.3k — GPT-Image-2 API and Prompts · Python · CC0-1.0 · 2026-07
- [dottxt-ai/outlines](https://github.com/dottxt-ai/outlines) ★15.9k — Structured Outputs · Python · Apache-2.0 · 2026-09
- [nidhinjs/prompt-master](https://github.com/nidhinjs/prompt-master) ★14.5k — A Claude skill that writes the accurate prompts for any AI tool. Zero tokens or credits wasted. Full context and memory retention · MIT · 2026-10
- [YouMind-OpenLab/awesome-nano-banana-pro-prompts](https://github.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts) ★13.6k — 🍌 World's largest Nano Banana Pro prompt library — 10,000+ curated prompts with preview images, 16 languages. Google Gemini AI image generat · TypeScript · NOASSERTION · 2026-10
- [Imbad0202/academic-research-skills-codex](https://github.com/Imbad0202/academic-research-skills-codex) ★13.0k — Codex-native Academic Research Skills suite for human-in-the-loop academic research workflows · Python · NOASSERTION · 2026-10
- [langgptai/LangGPT](https://github.com/langgptai/LangGPT) ★12.6k — LangGPT: Empowering everyone to become a prompt expert! 🚀  📌 结构化提示词（Structured Prompt）提出者 📌 元提示词（Meta-Prompt）发起者   📌 最流行的提示词落地范式 | Language  · Jupyter Notebook · Apache-2.0 · 2026-09
- [EmbraceAGI/awesome-chatgpt-zh](https://github.com/EmbraceAGI/awesome-chatgpt-zh) ★11.8k — ChatGPT 中文指南🔥，ChatGPT 中文调教指南，指令指南，应用开发指南，精选资源清单，更好的使用 chatGPT 让你的生产力 up up up! 🚀 · Python · MIT · 2026-10
- [cobusgreyling/loop-engineering](https://github.com/cobusgreyling/loop-engineering) ★11.6k — Practical patterns, starters & CLI tools for loop engineering with AI coding agents. Design systems that prompt and orchestrate agents (insp · TypeScript · MIT · 2026-10
- [kangarooking/cangjie-skill](https://github.com/kangarooking/cangjie-skill) ★11.4k — 把书、长视频、播客等高价值内容蒸馏成可执行的 Agent Skills（Distill high-value content from books, long-form videos, podcasts, and more into executable Agent Skills · Python · MIT · 2026-10
- [microsoft/promptflow](https://github.com/microsoft/promptflow) ★11.3k — Build high-quality LLM apps - from prototyping, testing to production deployment and monitoring. · Python · MIT · 2026-10
- [LouisShark/chatgpt_system_prompt](https://github.com/LouisShark/chatgpt_system_prompt) ★10.8k — A collection of GPT system prompts and various prompt injection/leaking knowledge. · HTML · MIT · 2026-10
- [ZeroLu/awesome-nanobanana-pro](https://github.com/ZeroLu/awesome-nanobanana-pro) ★10.3k — 🚀 An awesome list of curated Nano Banana pro prompts and examples. Your go-to resource for mastering prompt engineering and exploring the cr · MIT · 2026-10
- [YouMind-OpenLab/awesome-gpt-image-2](https://github.com/YouMind-OpenLab/awesome-gpt-image-2) ★10.1k — 🚀 World's largest GPT Image 2 prompt library, updated daily — 2000+ curated prompts with preview images, 16 languages. OpenAI's next-gen ima · TypeScript · NOASSERTION · 2026-10
- [ai-boost/awesome-prompts](https://github.com/ai-boost/awesome-prompts) ★9.1k — Curated list of chatgpt prompts from the top-rated GPTs in the GPTs Store. Prompt Engineering, prompt attack & prompt protect. Advanced Prom · GPL-3.0 · 2026-10
- [rockbenben/ChatGPT-Shortcut](https://github.com/rockbenben/ChatGPT-Shortcut) ★8.8k — Stop writing prompts from scratch — a searchable prompt library for ChatGPT, Claude, Gemini and Cursor · Русский 한국어 العربية हिन्दी ไทย ｜ 别再 · TypeScript · MIT · 2026-10
- [jnMetaCode/superpowers-zh](https://github.com/jnMetaCode/superpowers-zh) ★8.3k — 🦸 AI 编程超能力 · 中文增强版 — superpowers（250k+ ⭐）完整汉化 + 4 个中国原创 skills，让 Claude Code / Copilot CLI / Hermes Agent / Cursor / Windsurf / Kiro / Gemin · JavaScript · MIT · 2026-10
- [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) ★8.2k — FinRobot: An Open-Source AI Agent Platform for Financial Applications using Large Language Models · Python · Apache-2.0 · 2026-09
- [jamez-bondos/awesome-gpt4o-images](https://github.com/jamez-bondos/awesome-gpt4o-images) ★8.1k — Awesome curated collection of images and prompts generated by GPT-4o and gpt-image-1. Explore AI generated visuals created with ChatGPT and  · JavaScript · NOASSERTION · 2025-05
- [NirDiamant/Prompt_Engineering](https://github.com/NirDiamant/Prompt_Engineering) ★7.9k — 22 prompt engineering techniques with hands-on Jupyter Notebook tutorials, from fundamental concepts to advanced strategies for leveraging L · Jupyter Notebook · NOASSERTION · 2026-10
- [mufeedvh/code2prompt](https://github.com/mufeedvh/code2prompt) ★7.7k — A CLI tool to convert your codebase into a single LLM prompt with source tree, prompt templating, and token counting. · Rust · MIT · 2026-09

### Local LLM runners (30)

- [mozilla-ai/llamafile](https://github.com/mozilla-ai/llamafile) ★26.3k — Distribute and run LLMs with a single file. · C++ · NOASSERTION · 2026-10
- [LearningCircuit/local-deep-research](https://github.com/LearningCircuit/local-deep-research) ★9.2k — ~95% on SimpleQA (e.g. Qwen3.6-27B on a 3090). Supports all local and cloud LLMs (llama.cpp, Ollama, Google, ...). 10+ search engines - arXi · Python · MIT · 2026-10
- [MakazhanAlpamys/Soup](https://github.com/MakazhanAlpamys/Soup) ★9.1k — Fine-tune LLMs from one YAML. Layer streaming trains an 8B model on a 4 GB laptop GPU. · Python · Apache-2.0 · 2026-10
- [dograh-hq/dograh](https://github.com/dograh-hq/dograh) ★5.9k — Open source voice AI platform. Self-hosted alternative to Vapi and Retell. On Prem, BYOK across  Speech to Speech or LLM/STT/TTS, with a vis · Python · BSD-2-Clause · 2026-10
- [maziyarpanahi/openmed](https://github.com/maziyarpanahi/openmed) ★5.7k — Local-first healthcare AI: clinical NER and HIPAA PII de-identification on hardware you control. 2,200+ medical models, 35 model-backed PII  · Python · Apache-2.0 · 2026-10
- [vinta/pangu.js](https://github.com/vinta/pangu.js) ★4.9k — Opinionated paranoid text spacing in JavaScript, with on-device AI semantic judgment · TypeScript · MIT · 2026-10
- [langroid/langroid](https://github.com/langroid/langroid) ★4.1k — Harness LLMs with Multi-Agent Programming · Python · MIT · 2026-10
- [raullenchai/Rapid-MLX](https://github.com/raullenchai/Rapid-MLX) ★4.0k — Rapid-MLX is an open-source (Apache 2.0) OpenAI- and Anthropic-compatible LLM inference server for Apple Silicon, built on MLX, focused on r · Python · NOASSERTION · 2026-10
- [deta/surf](https://github.com/deta/surf) ★3.6k — Personal AI Notebooks. Organize files & webpages and generate notes from them. Open source, local & open data, open model choice (incl. loca · TypeScript · Apache-2.0 · 2026-08
- [nicedreamzapp/claude-code-local](https://github.com/nicedreamzapp/claude-code-local) ★3.4k — Run Claude Code 100% on-device with local AI on Apple Silicon. MLX-native Anthropic-API server. 6 fighters incl. Muse-Glimmer 30B (now multi · Python · MIT · 2026-10
- [xyproto/algernon](https://github.com/xyproto/algernon) ★3.0k — Small self-contained pure-Go web server with Lua, Teal, Markdown, HTTP/2, QUIC, Redis, TypeScript, npm-less React 19, SQLite, and PostgreSQL · JavaScript · BSD-3-Clause · 2026-10
- [rafska/awesome-local-llm](https://github.com/rafska/awesome-local-llm) ★3.0k — A curated list of awesome platforms, tools, practices and resources that helps run LLMs locally · MIT · 2026-10
- [youssofal/MTPLX](https://github.com/youssofal/MTPLX) ★2.6k — The fastest way to run Qwen 3.8 Flash Next, Qwen 3.8 27B and Ternary Bonsai 2 27B on a Mac: 125 tok/s in OpenCode on an M5 Max, and a 27B mo · Python · Apache-2.0 · 2026-10
- [travisvn/openai-edge-tts](https://github.com/travisvn/openai-edge-tts) ★2.1k — Free, high-quality text-to-speech API endpoint to replace OpenAI, Azure, or ElevenLabs · Python · GPL-3.0 · 2025-07
- [fikrikarim/parlor](https://github.com/fikrikarim/parlor) ★2.1k — On-device, real-time multimodal AI with features similar to GPT-Live · Python · Apache-2.0 · 2026-08
- [techjarves/USB-Uncensored-LLM](https://github.com/techjarves/USB-Uncensored-LLM) ★2.1k — The ultimate zero-install, portable local AI environment. Run high-quality, uncensored LLMs (Gemma, Qwen, NemoMix) directly from any USB dri · HTML · NOASSERTION · 2026-07
- [syv-ai/HyperQwen](https://github.com/syv-ai/HyperQwen) ★2.0k — Serve large Qwen models fast on the GPUs you actually own. Qwen3.8-27B on a single 24 GB card with vLLM: 127 tok/s single-user (381 when the · Python · Apache-2.0 · 2026-10
- [ddalcu/mlx-serve](https://github.com/ddalcu/mlx-serve) ★1.9k — Native LLM inference server for Apple Silicon. OpenAI + Anthropic API compatible. No Python. Zig backend, Swift frontend macOS app with chat · Zig · NOASSERTION · 2026-10
- [AtomicBot-ai/Atomic-Chat](https://github.com/AtomicBot-ai/Atomic-Chat) ★1.8k — Local AI app and inference engine for agents. Run open-weight LLMs locally — private, 100% offline on your computer. Join our Discord: https · TypeScript · NOASSERTION · 2026-10
- [siddsachar/row-bot](https://github.com/siddsachar/row-bot) ★1.6k — Row-Bot - Personal AI Sovereignty. A local-first AI assistant with integrated tools, a personal knowledge graph, voice, vision, shell, brows · Python · Apache-2.0 · 2026-10
- [waybarrios/vllm-mlx](https://github.com/waybarrios/vllm-mlx) ★1.6k — High-performance OpenAI and Anthropic compatible LLM inference server for Apple Silicon. Native MLX, continuous batching, multimodal models, · Python · Apache-2.0 · 2026-10
- [nobodywho-ooo/nobodywho](https://github.com/nobodywho-ooo/nobodywho) ★1.6k — NobodyWho is an inference engine that lets you run LLMs locally and efficiently on any device. · Rust · EUPL-1.2 · 2026-10
- [ARahim3/mlx-tune](https://github.com/ARahim3/mlx-tune) ★1.4k — Fine-tune LLMs on your Mac with Apple Silicon. SFT, DPO, GRPO, Vision, TTS, STT, Embedding, and OCR fine-tuning — natively on MLX. Unsloth-c · Python · Apache-2.0 · 2026-06
- [jofizcd/Soul-of-Waifu](https://github.com/jofizcd/Soul-of-Waifu) ★1.4k — 🌌 Give a soul to your favorite characters. Soul of Waifu is a desktop roleplay & AI companion app featuring Live2D/VRM avatars, voice chat & · Python · GPL-3.0 · 2026-08
- [feder-cr/jev](https://github.com/feder-cr/jev) ★1.3k — jevos: an open-source alternative to Jev and Microsoft-Decision-1. Yes/no decisions, choices and scores with probabilities, on your laptop's · C++ · MIT · 2026-10
- [HelgeSverre/ollama-gui](https://github.com/HelgeSverre/ollama-gui) ★1.3k — A Web Interface for chatting with your local LLMs via the ollama API · TypeScript · MIT · 2026-10
- [mrkrsl/web-search-mcp](https://github.com/mrkrsl/web-search-mcp) ★1.2k — A simple, locally hosted Web Search MCP server for use with Local LLMs · TypeScript · MIT · 2025-08
- [agents-io/PokeClaw](https://github.com/agents-io/PokeClaw) ★1.1k — PokeClaw (PocketClaw) — first on-device AI that controls your Android phone. Gemma 4, no cloud, no API key. Poke is short for Pocket. · Kotlin · Apache-2.0 · 2026-06
- [pguso/agents-from-scratch](https://github.com/pguso/agents-from-scratch) ★1.0k — Build AI agents from first principles using a local LLM - no frameworks, no cloud APIs, no hidden reasoning. · Python · MIT · 2026-07
- [ASCIT31/Dark-Moon](https://github.com/ASCIT31/Dark-Moon) ★1.0k — Open-source autonomous AI penetration testing. 50 specialist agents across web, API, cloud, Active Directory, Kubernetes, CI/CD and AI/LLM ( · Python · GPL-3.0 · 2026-10

### Ollama ecosystem (30)

- [ChatGPTNextWeb/NextChat](https://github.com/ChatGPTNextWeb/NextChat) ★88.9k — ✨ Zero-config AI chat assistant. No API key needed — sign up and instantly chat with GPT-5, Claude 4, Gemini 2.5, DeepSeek & 100+ top models · TypeScript · MIT · 2026-10
- [chatboxai/chatbox](https://github.com/chatboxai/chatbox) ★42.0k — Powerful AI Client · TypeScript · GPL-3.0 · 2026-09
- [dyad-sh/dyad](https://github.com/dyad-sh/dyad) ★21.9k — Local, open-source AI app builder for power users ✨ v0 / Lovable / Replit / Bolt alternative 🌟 Star if you like it! · TypeScript · NOASSERTION · 2026-10
- [lss233/kirara-ai](https://github.com/lss233/kirara-ai) ★19.1k — 🤖 可 DIY 的 多模态 AI 聊天机器人 | 🚀 快速接入 微信、 QQ、Telegram、等聊天平台 | 🦈支持DeepSeek、Grok、Claude、Ollama、Gemini、OpenAI | 工作流系统、网页搜索、AI画图、人设调教、虚拟女仆、语音对话 | · Python · AGPL-3.0 · 2025-06
- [AsyncFuncAI/deepwiki-open](https://github.com/AsyncFuncAI/deepwiki-open) ★18.2k — Open Source DeepWiki: AI-Powered Wiki Generator for GitHub/Gitlab/Bitbucket Repositories. Join the discord: https://discord.gg/gMwThUMeme · Python · MIT · 2026-09
- [lidge-jun/opencodex](https://github.com/lidge-jun/opencodex) ★17.5k — Universal provider proxy for OpenAI Codex & Claude Code — use any LLM (Claude, Gemini, Grok, DeepSeek, Ollama…) with Codex CLI, App, SDK, an · TypeScript · MIT · 2026-10
- [GaiZhenbiao/ChuanhuChatGPT](https://github.com/GaiZhenbiao/ChuanhuChatGPT) ★15.3k — GUI for ChatGPT API and many LLMs. Supports agents, file-based QA, GPT finetuning and query with web search. All with a neat UI. · Python · GPL-3.0 · 2026-09
- [Open-LLM-VTuber/Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) ★14.1k — Talk to any LLM with hands-free voice interaction, voice interruption, and Live2D avatar running locally across platforms · Python · NOASSERTION · 2026-05
- [The-PR-Agent/pr-agent](https://github.com/The-PR-Agent/pr-agent) ★13.4k — 🚀 PR Agent: The Original Open-Source PR Reviewer. This project is not the Qodo free tier. · Python · MIT · 2026-10
- [ollama/ollama-python](https://github.com/ollama/ollama-python) ★10.6k — Ollama Python library · Python · MIT · 2026-09
- [mnfst/awesome-free-llm-apis](https://github.com/mnfst/awesome-free-llm-apis) ★10.4k — List of Permanent Free LLM API  (API Keys) · JavaScript · CC0-1.0 · 2026-10
- [RunanywhereAI/runanywhere-sdks](https://github.com/RunanywhereAI/runanywhere-sdks) ★10.3k — Production ready toolkit to run AI locally · C++ · NOASSERTION · 2026-10
- [miurla/morphic](https://github.com/miurla/morphic) ★9.2k — An AI-powered search engine with a generative UI · TypeScript · Apache-2.0 · 2026-10
- [n4ze3m/page-assist](https://github.com/n4ze3m/page-assist) ★8.3k — Use your locally running AI models to assist you in your web browsing · TypeScript · MIT · 2026-10
- [ArvinLovegood/go-stock](https://github.com/ArvinLovegood/go-stock) ★7.8k — 🦄🦄🦄AI赋能股票分析：AI加持的股票分析/选股工具。股票行情获取，AI热点资讯分析，AI资金/财务分析，涨跌报警推送。支持A股，港股，美股。支持市场整体/个股情绪分析，AI辅助选股等。数据全部保留在本地。支持DeepSeek，OpenAI， Ollama，LMStudio，An · Go · GPL-3.0 · 2026-10
- [JerryZLiu/Dayflow](https://github.com/JerryZLiu/Dayflow) ★7.3k — The automatic work journal/time tracker. Privately turns your screen into a timeline of what you actually accomplished. Open-source and loca · Swift · MIT · 2026-10
- [olimorris/codecompanion.nvim](https://github.com/olimorris/codecompanion.nvim) ★6.9k — ✨ AI Coding, Vim Style · Lua · Apache-2.0 · 2026-10
- [vas3k/TaxHacker](https://github.com/vas3k/TaxHacker) ★6.7k — Self-hosted AI accounting app. LLM analyzer for receipts, invoices, transactions with custom prompts and categories · TypeScript · MIT · 2026-09
- [gluonfield/enchanted](https://github.com/gluonfield/enchanted) ★6.0k — Enchanted is iOS and macOS app for chatting with private self hosted language models such as Llama2, Mistral or Vicuna using Ollama. · Swift · Apache-2.0 · 2026-07
- [clusterzx/paperless-ai](https://github.com/clusterzx/paperless-ai) ★6.0k — An automated document analyzer for Paperless-ngx using OpenAI API, Ollama, Deepseek-r1, Azure and all OpenAI API compatible Services to auto · JavaScript · MIT · 2026-10
- [AgentOps-AI/agentops](https://github.com/AgentOps-AI/agentops) ★5.9k — Python SDK for AI agent monitoring, LLM cost tracking, benchmarking, and more. Integrates with most LLMs and agent frameworks including Crew · Python · MIT · 2026-06
- [PySpur-Dev/pyspur](https://github.com/PySpur-Dev/pyspur) ★5.8k — A visual playground for agentic workflows: Iterate over your agents 10x faster · TypeScript · Apache-2.0 · 2026-06
- [buxuku/SmartSub](https://github.com/buxuku/SmartSub) ★5.7k — 视频转字幕、字幕翻译、AI 配音与声音克隆、字幕烧录——免费开源的一站式桌面工具。基于 Whisper / FunASR 等本地模型离线语音转文字，批量处理 + 全平台 GPU 加速，跨 Windows / macOS / Linux。Free, open-source desk · TypeScript · MIT · 2026-10
- [JetBrains/koog](https://github.com/JetBrains/koog) ★4.6k — Koog is a JVM (Java and Kotlin) framework for building predictable, fault-tolerant and enterprise-ready AI agents across all platforms – fro · Kotlin · Apache-2.0 · 2026-10
- [ollama/ollama-js](https://github.com/ollama/ollama-js) ★4.4k — Ollama JavaScript library · TypeScript · MIT · 2026-09
- [umlx5h/LLPlayer](https://github.com/umlx5h/LLPlayer) ★4.4k — The media player for language learning, with dual subtitles, AI-generated subtitles, real-time translation, and more! · C# · GPL-3.0 · 2026-09
- [GiovanniPasq/agentic-rag-for-dummies](https://github.com/GiovanniPasq/agentic-rag-for-dummies) ★4.3k — A modular Agentic RAG built with LangGraph — learn Retrieval-Augmented Generation Agents in minutes. · Jupyter Notebook · MIT · 2026-10
- [nyldn/claude-octopus](https://github.com/nyldn/claude-octopus) ★4.2k — Run multiple AI models against the same research, design, or coding task. Surface disagreements before you ship. · Shell · MIT · 2026-10
- [yuruotong1/autoMate](https://github.com/yuruotong1/autoMate) ★4.0k — Like Manus, Computer Use Agent(CUA) and Omniparser, we are computer-using agents.AI-driven local automation assistant that uses natural lang · Python · MIT · 2026-09
- [lemony-ai/cascadeflow](https://github.com/lemony-ai/cascadeflow) ★3.9k — Cascading runtime for AI agents. Optimize cost, latency, quality, and policy decisions inside the agent loop. · Python · MIT · 2026-09

### LLM UIs (17)

- [rikkahub/rikkahub](https://github.com/rikkahub/rikkahub) ★8.2k — RikkaHub is an Android APP that supports for multiple LLM providers. · Kotlin · AGPL-3.0 · 2026-10
- [AGenUI/AGenUI](https://github.com/AGenUI/AGenUI) ★1.2k — Native A2UI Renderer for iOS/Android/HarmonyOS. High performance streaming Generative UI. Custom Components, Styles and more. · C++ · Apache-2.0 · 2026-10
- [Cocolalilal/LastChat](https://github.com/Cocolalilal/LastChat) ★378 — A Fork of Rikkahub with an overhauled UI and feature additions · Kotlin · AGPL-3.0 · 2026-10
- [mrdjohnson/llm-x](https://github.com/mrdjohnson/llm-x) ★297 — LLMX; Easiest 3rd party Local LLM UI for the web! · TypeScript · MIT · 2026-09
- [PromptPasture/llama.ui](https://github.com/PromptPasture/llama.ui) ★217 — A minimal interface for AI Companion that runs entirely in your browser. · TypeScript · MIT · 2026-08
- [ai-joe-git/Belullama](https://github.com/ai-joe-git/Belullama) ★209 — Belullama is a comprehensive AI application that bundles Ollama, Open WebUI, and Automatic1111 (Stable Diffusion WebUI) into a single, easy- · Shell · NOASSERTION · 2025-05
- [yoziru/nextjs-vllm-ui](https://github.com/yoziru/nextjs-vllm-ui) ★185 — Fully-featured, beautiful web interface for vLLM - built with NextJS. · TypeScript · MIT · 2026-08
- [1337hero/faster-chat](https://github.com/1337hero/faster-chat) ★175 — A blazingly fast, privacy first & OPEN AI Chat Interface · JavaScript · MIT · 2026-08
- [codecentric/c4-genai-suite](https://github.com/codecentric/c4-genai-suite) ★174 — [archived] c4 GenAI Suite · TypeScript · Apache-2.0 · 2026-08
- [willdady/platypus](https://github.com/willdady/platypus) ★120 — Self-hosted AI Agents for your whole team — on your infrastructure, your models, around the clock. · TypeScript · MIT · 2026-10
- [pinkfuwa/llumen](https://github.com/pinkfuwa/llumen) ★99 — 🕯️ A lightweight but powerful LLM chat application · Rust · NOASSERTION · 2026-10
- [Unagi-cq/THChatUI](https://github.com/Unagi-cq/THChatUI) ★67 — 项目不再维护，可以作为大家以后二开WebUI、AgentUI的蓝本，也可以很方便的打包成浏览器插件、桌面端应用。 · JavaScript · Apache-2.0 · 2025-06
- [on-panda/on-panda](https://github.com/on-panda/on-panda) ★61 — 🐼 Steer your LLMs and agents at the token level: A web tool for token visualization & control, model inspection, and LLM & agent trajectory  · JavaScript · MIT · 2026-10
- [Elumenotion/GuideAnts](https://github.com/Elumenotion/GuideAnts) ★61 — AI work that doesn't evaporate. A workspace for building, tuning, and publishing governed AI products. · C# · Apache-2.0 · 2026-10
- [CES-Ltd/Lumi](https://github.com/CES-Ltd/Lumi) ★37 — Unified native desktop UI for Claude Code, Gemini CLI, Hermes, Crush, Codex, and Cursor — multi-agent, MCP-native, written in Rust + GPUI. · Rust · MIT · 2026-05
- [haoxiang-xu/PuPu](https://github.com/haoxiang-xu/PuPu) ★36 — PuPu is a lightweight, cross-platform desktop AI client that works with both local and cloud-hosted models. Whether you prefer running model · JavaScript · Apache-2.0 · 2026-10
- [lennyerik/crawl4ai-proxy](https://github.com/lennyerik/crawl4ai-proxy) ★33 — A simple proxy server to integrate crawl4ai with OpenWebUI · Go · NOASSERTION · 2025-11

### Chat UIs & chatbots (30)

- [xtekky/gpt4free](https://github.com/xtekky/gpt4free) ★66.9k — The official gpt4free repository | various collection of powerful language models | opus 4.6 gpt 5.3 kimi 2.5 deepseek v3.2 gemini 3 · Python · GPL-3.0 · 2026-10
- [python-telegram-bot/python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) ★29.5k — We have made you a wrapper you can't refuse · Python · GPL-3.0 · 2026-10
- [haotian-liu/LLaVA](https://github.com/haotian-liu/LLaVA) ★25.1k — [NeurIPS'23 Oral] Visual Instruction Tuning (LLaVA) built towards GPT-4V level capabilities and beyond. · Python · Apache-2.0 · 2024-08
- [QwenAudio/CosyVoice](https://github.com/QwenAudio/CosyVoice) ★24.0k — Multi-lingual large voice generation model, providing inference, training and deployment full-stack ability. · Python · Apache-2.0 · 2026-05
- [wechaty/wechaty](https://github.com/wechaty/wechaty) ★23.4k — Conversational RPA SDK for Chatbot Makers. Join our Discord: https://discord.gg/7q8NBZbQzt · TypeScript · Apache-2.0 · 2025-12
- [RasaHQ/rasa](https://github.com/RasaHQ/rasa) ★21.4k — 💬   Open source machine learning framework to automate text- and voice-based conversations: NLU, dialogue management, connect to Slack, Face · Python · Apache-2.0 · 2026-07
- [leon-ai/leon](https://github.com/leon-ai/leon) ★17.6k — 🧠 Leon is your open-source personal assistant. · TypeScript · MIT · 2026-10
- [mayooear/ai-pdf-chatbot-langchain](https://github.com/mayooear/ai-pdf-chatbot-langchain) ★16.6k — AI PDF chatbot agent built with LangChain & LangGraph · TypeScript · MIT · 2026-03
- [stackblitz/bolt.new](https://github.com/stackblitz/bolt.new) ★16.6k — Prompt, run, edit, and deploy full-stack web applications. -- bolt.new -- Help Center: https://support.bolt.new/ -- Community Support: https · TypeScript · MIT · 2024-12
- [mamoe/mirai](https://github.com/mamoe/mirai) ★14.8k — 高效率 QQ 机器人支持库 · Kotlin · AGPL-3.0 · 2024-09
- [gunthercox/ChatterBot](https://github.com/gunthercox/ChatterBot) ★14.5k — ChatterBot is a machine learning, conversational dialog engine for creating chat bots · Python · BSD-3-Clause · 2026-08
- [assistant-ui/assistant-ui](https://github.com/assistant-ui/assistant-ui) ★12.6k — Typescript/React Library for AI Chat 💬🚀 · TypeScript · MIT · 2026-10
- [howdyai/botkit](https://github.com/howdyai/botkit) ★11.6k — Botkit is an open source developer tool for building chat bots, apps and custom integrations for major messaging platforms. · TypeScript · MIT · 2024-07
- [databrickslabs/dolly](https://github.com/databrickslabs/dolly) ★10.8k — Databricks’ Dolly, a large language model trained on the Databricks Machine Learning Platform · Python · Apache-2.0 · 2023-06
- [bigscience-workshop/petals](https://github.com/bigscience-workshop/petals) ★10.6k — 🌸 Run LLMs at home, BitTorrent-style. Fine-tuning and inference up to 10x faster than offloading · Python · MIT · 2024-09
- [baptisteArno/typebot.io](https://github.com/baptisteArno/typebot.io) ★10.5k — 💬 Typebot is a powerful chatbot builder that you can self-host. · TypeScript · NOASSERTION · 2026-10
- [chiphuyen/stanford-tensorflow-tutorials](https://github.com/chiphuyen/stanford-tensorflow-tutorials) ★10.4k — This repository contains code examples for the Stanford's course: TensorFlow for Deep Learning Research. · Python · MIT · 2020-12
- [sfyc23/EverydayWechat](https://github.com/sfyc23/EverydayWechat) ★10.3k — 微信助手：1.每日定时给好友（女友）发送定制消息。2.机器人自动回复好友。3.群助手功能（例如：查询垃圾分类、天气、日历、电影实时票房、快递物流、PM2.5等） · Python · MIT · 2021-06
- [evolution-foundation/evolution-api](https://github.com/evolution-foundation/evolution-api) ★9.9k — Evolution API is an open-source WhatsApp integration API · TypeScript · NOASSERTION · 2026-07
- [friuns2/BlackFriday-GPTs-Prompts](https://github.com/friuns2/BlackFriday-GPTs-Prompts) ★9.8k — List of free GPTs that doesn't require plus subscription · MIT · 2026-03
- [BlinkDL/ChatRWKV](https://github.com/BlinkDL/ChatRWKV) ★9.5k — ChatRWKV is like ChatGPT but powered by RWKV (100% RNN) language model, and open source. · Python · Apache-2.0 · 2026-07
- [shaxiu/XianyuAutoAgent](https://github.com/shaxiu/XianyuAutoAgent) ★9.4k — 智能闲鱼客服机器人系统：专为闲鱼平台打造的AI值守解决方案，实现闲鱼平台7×24小时自动化值守，支持多专家协同决策、智能议价和上下文感知对话。 · Python · GPL-3.0 · 2026-06
- [yagop/node-telegram-bot-api](https://github.com/yagop/node-telegram-bot-api) ★9.2k — Telegram Bot API for NodeJS · TypeScript · MIT · 2026-09
- [ztjhz/BetterChatGPT](https://github.com/ztjhz/BetterChatGPT) ★8.4k — An amazing UI for OpenAI's ChatGPT (Website + Windows + MacOS + Linux) · TypeScript · CC0-1.0 · 2024-08
- [zilliztech/GPTCache](https://github.com/zilliztech/GPTCache) ★8.2k — Semantic cache for LLMs. Fully integrated with LangChain and llama_index. · Python · MIT · 2026-09
- [2FastLabs/agent-squad](https://github.com/2FastLabs/agent-squad) ★7.8k — Flexible and powerful framework for managing multiple AI agents and handling complex conversations · Python · Apache-2.0 · 2026-10
- [HuLaSpark/HuLa](https://github.com/HuLaSpark/HuLa) ★7.8k — 🍀 A cross-platform instant messaging desktop application with exceptional performance built on Rust + Vue3, compatible with Windows, macOS,  · Vue · Apache-2.0 · 2026-10
- [nonebot/nonebot2](https://github.com/nonebot/nonebot2) ★7.7k — 跨平台 Python 异步聊天机器人框架 / Asynchronous multi-platform chatbot framework written in Python · Python · MIT · 2026-10
- [xiangsx/gpt4free-ts](https://github.com/xiangsx/gpt4free-ts) ★7.7k — Providing a free OpenAI GPT-4 API !   This is a replication project for the typescript version of xtekky/gpt4free · TypeScript · GPL-3.0 · 2024-09
- [tensorlayer/TensorLayer](https://github.com/tensorlayer/TensorLayer) ★7.4k — Deep Learning and Reinforcement Learning Library for Scientists and Engineers · Python · NOASSERTION · 2023-02

### Sandboxes & code exec (30)

- [firecracker-microvm/firecracker](https://github.com/firecracker-microvm/firecracker) ★37.4k — Secure and fast microVMs for serverless computing. · Rust · Apache-2.0 · 2026-10
- [teableio/teable](https://github.com/teableio/teable) ★21.9k — ✨ AI Spreadsheet for Business · TypeScript · NOASSERTION · 2026-10
- [google/gvisor](https://github.com/google/gvisor) ★19.7k — Application Kernel for Containers · Go · Apache-2.0 · 2026-10
- [bytecodealliance/wasmtime](https://github.com/bytecodealliance/wasmtime) ★18.7k — A lightweight WebAssembly runtime that is fast, secure, and standards-compliant · Rust · Apache-2.0 · 2026-10
- [opensandbox-group/OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) ★15.9k — Secure, Fast, and Extensible Sandbox runtime for AI agents. · Python · Apache-2.0 · 2026-10
- [NevaMind-AI/memU](https://github.com/NevaMind-AI/memU) ★14.5k — Personal memory across agents · Python · NOASSERTION · 2026-10
- [TencentCloud/CubeSandbox](https://github.com/TencentCloud/CubeSandbox) ★13.0k — Instant, Concurrent, Secure & Lightweight Sandbox for AI Agents. · Go · NOASSERTION · 2026-10
- [astrid-runtime/astrid](https://github.com/astrid-runtime/astrid) ★10.3k — Astrid is a portable, capability-secure operating system for composable software. · Rust · Apache-2.0 · 2026-10
- [ntegrals/openbrowser](https://github.com/ntegrals/openbrowser) ★9.6k — Let AI agents browse the web. An autonomous toolkit for browser-based AI agents. · TypeScript · MIT · 2026-04
- [superradcompany/microsandbox](https://github.com/superradcompany/microsandbox) ★8.7k — 🧱 easy, fast, programmable and local-first microVM runtime and library · Rust · Apache-2.0 · 2026-10
- [react-cosmos/react-cosmos](https://github.com/react-cosmos/react-cosmos) ★8.7k — Sandbox for developing and testing UI components in isolation · TypeScript · MIT · 2026-09
- [pydantic/monty](https://github.com/pydantic/monty) ★8.7k — A secure Python sandbox, written in Rust, for code written by AI. · Rust · MIT · 2026-10
- [OpenTTD/OpenTTD](https://github.com/OpenTTD/OpenTTD) ★8.4k — OpenTTD is an open source simulation game based upon Transport Tycoon Deluxe · C++ · NOASSERTION · 2026-10
- [wasm3/wasm3](https://github.com/wasm3/wasm3) ★8.1k — 🚀 A fast WebAssembly interpreter and the most universal WASM runtime · C · MIT · 2026-09
- [smol-machines/smolvm](https://github.com/smol-machines/smolvm) ★6.7k — An embeddable, portable, branchable virtual machine to safely run Agents locally. · Rust · Apache-2.0 · 2026-10
- [e2b-dev/fragments](https://github.com/e2b-dev/fragments) ★6.4k — Open-source Next.js template for building apps that are fully generated by AI. By E2B. · TypeScript · Apache-2.0 · 2026-10
- [mviereck/x11docker](https://github.com/mviereck/x11docker) ★6.3k — Run GUI applications and desktops in docker and podman containers. Focus on security. · Shell · MIT · 2026-07
- [codesandbox/sandpack](https://github.com/codesandbox/sandpack) ★6.3k — A component toolkit for creating live-running code editing experiences, using the power of CodeSandbox. · TypeScript · Apache-2.0 · 2025-04
- [agent-infra/sandbox](https://github.com/agent-infra/sandbox) ★6.2k — All-in-One Sandbox for AI Agents that combines Browser, Shell, File, MCP and VSCode Server in a single Docker container. · Python · Apache-2.0 · 2026-09
- [vercel/eve](https://github.com/vercel/eve) ★5.6k — The Open Framework for Building Agents · TypeScript · Apache-2.0 · 2026-10
- [The-Powder-Toy/The-Powder-Toy](https://github.com/The-Powder-Toy/The-Powder-Toy) ★5.4k — Written in C++ and using SDL, The Powder Toy is a desktop version of the classic 'falling sand' physics sandbox, it simulates air pressure a · C++ · GPL-3.0 · 2026-10
- [dtyq/magic](https://github.com/dtyq/magic) ★5.1k — Magicrew. The first open-source all-in-one AI productivity platform (Generalist AI Agent + Workflow Engine + IM + Online collaborative offic · TypeScript · NOASSERTION · 2026-08
- [rivet-dev/agentos](https://github.com/rivet-dev/agentos) ★4.8k — Tiny, fast, Linux-compatible sandboxes. Powered by WebAssembly. · Rust · Apache-2.0 · 2026-10
- [kubernetes-sigs/agent-sandbox](https://github.com/kubernetes-sigs/agent-sandbox) ★4.3k — agent-sandbox enables easy management of isolated, stateful, singleton workloads, ideal for use cases like AI agent runtimes  and reinforcem · Go · Apache-2.0 · 2026-10
- [arcboxlabs/arcbox](https://github.com/arcboxlabs/arcbox) ★4.2k — Run AI agents on real and isolated machines — own kernel, filesystem, and network — with <100ms boot. Local first, OCI compatible, pure Rust · Rust · Apache-2.0 · 2026-10
- [CocoaDebug/CocoaDebug](https://github.com/CocoaDebug/CocoaDebug) ★4.1k — iOS Debugging Tool 🚀 · Swift · NOASSERTION · 2023-06
- [patriksimek/vm2](https://github.com/patriksimek/vm2) ★4.1k — Advanced vm/sandbox for Node.js · JavaScript · MIT · 2026-09
- [a0rtega/pafish](https://github.com/a0rtega/pafish) ★3.9k — Pafish is a testing tool that uses different techniques to detect virtual machines and malware analysis environments in the same way that ma · C · GPL-3.0 · 2024-06
- [MovingBlocks/Terasology](https://github.com/MovingBlocks/Terasology) ★3.9k — Terasology - open source voxel world · Java · Apache-2.0 · 2026-10
- [Revolutionary-Games/Thrive](https://github.com/Revolutionary-Games/Thrive) ★3.8k — The main repository for the development of the evolution game Thrive. · C# · NOASSERTION · 2026-10

### Static analysis (30)

- [WerWolv/ImHex](https://github.com/WerWolv/ImHex) ★55.3k — 🔍 A Hex Editor for Reverse Engineers, Programmers and people who value their retinas when working at 3 AM. · C++ · GPL-2.0 · 2026-10
- [astral-sh/ruff](https://github.com/astral-sh/ruff) ★50.1k — An extremely fast Python linter and code formatter, written in Rust. · Rust · MIT · 2026-10
- [koalaman/shellcheck](https://github.com/koalaman/shellcheck) ★40.2k — ShellCheck, a static analysis tool for shell scripts · Haskell · GPL-3.0 · 2026-10
- [MobSF/Mobile-Security-Framework-MobSF](https://github.com/MobSF/Mobile-Security-Framework-MobSF) ★22.0k — Mobile Security Framework (MobSF) is an automated, all-in-one mobile application (Android/iOS/Windows) pen-testing, malware analysis and sec · JavaScript · GPL-3.0 · 2026-10
- [realm/SwiftLint](https://github.com/realm/SwiftLint) ★19.8k — A tool to enforce Swift style and conventions. · Swift · MIT · 2026-10
- [nikic/PHP-Parser](https://github.com/nikic/PHP-Parser) ★17.5k — A PHP parser written in PHP · PHP · BSD-3-Clause · 2026-10
- [semgrep/semgrep](https://github.com/semgrep/semgrep) ★17.1k — Lightweight static analysis for many languages. Find bug variants with patterns that look like source code. · C · LGPL-2.1 · 2026-10
- [ast-grep/ast-grep](https://github.com/ast-grep/ast-grep) ★16.2k — ⚡A CLI tool for code structural search, lint and rewriting. Written in Rust · Rust · MIT · 2026-10
- [facebook/infer](https://github.com/facebook/infer) ★15.7k — A static analyzer for Java, C, C++, and Objective-C · OCaml · MIT · 2026-10
- [Konloch/bytecode-viewer](https://github.com/Konloch/bytecode-viewer) ★15.7k — A Java 8+ Jar & Android APK Reverse Engineering Suite (Decompiler, Editor, Debugger & More) · Java · GPL-3.0 · 2026-07
- [analysis-tools-dev/static-analysis](https://github.com/analysis-tools-dev/static-analysis) ★14.8k — ⚙️ A curated list of static analysis (SAST) tools and linters for all programming languages, config files, build tools, and more. The focus  · Rust · MIT · 2026-10
- [rshipp/awesome-malware-analysis](https://github.com/rshipp/awesome-malware-analysis) ★14.3k — Defund the Police. · NOASSERTION · 2024-06
- [phpstan/phpstan](https://github.com/phpstan/phpstan) ★14.1k — PHP Static Analysis Tool - discover bugs in your code without running it! · PHP · MIT · 2026-10
- [PHP-CS-Fixer/PHP-CS-Fixer](https://github.com/PHP-CS-Fixer/PHP-CS-Fixer) ★13.6k — A tool to automatically fix PHP Coding Standards issues · PHP · MIT · 2026-10
- [OWASP/mastg](https://github.com/OWASP/mastg) ★13.3k — The OWASP Mobile Application Security Testing Guide (MASTG) is a comprehensive manual for mobile app security testing and reverse engineerin · Python · CC-BY-SA-4.0 · 2026-10
- [ttroy50/cmake-examples](https://github.com/ttroy50/cmake-examples) ★13.1k — Useful CMake Examples · CMake · MIT · 2024-02
- [anchore/grype](https://github.com/anchore/grype) ★13.0k — A vulnerability scanner for container images and filesystems · Go · Apache-2.0 · 2026-10
- [hadolint/hadolint](https://github.com/hadolint/hadolint) ★12.5k — Dockerfile linter, validate inline bash, written in Haskell · Haskell · GPL-3.0 · 2026-10
- [horsicq/Detect-It-Easy](https://github.com/horsicq/Detect-It-Easy) ★11.7k — Program for determining types of files for Windows, Linux and MacOS. · JavaScript · MIT · 2026-10
- [quay/clair](https://github.com/quay/clair) ★11.1k — Vulnerability Static Analysis for Containers · Go · Apache-2.0 · 2026-10
- [SonarSource/sonarqube](https://github.com/SonarSource/sonarqube) ★11.1k — Continuous Inspection · Java · LGPL-3.0 · 2026-10
- [squizlabs/PHP_CodeSniffer](https://github.com/squizlabs/PHP_CodeSniffer) ★10.8k — PHP_CodeSniffer tokenizes PHP files and detects violations of a defined set of coding standards. · PHP · BSD-3-Clause · 2024-04
- [anchore/syft](https://github.com/anchore/syft) ★9.7k — CLI tool and library for generating a Software Bill of Materials from container images and filesystems · Go · Apache-2.0 · 2026-10
- [reviewdog/reviewdog](https://github.com/reviewdog/reviewdog) ★9.7k — 🐶 Automated code review tool integrated with any code analysis tools regardless of programming language · Go · MIT · 2026-10
- [checkstyle/checkstyle](https://github.com/checkstyle/checkstyle) ★9.6k — Checkstyle is a development tool to help programmers write Java code that adheres to a coding standard. By default it supports the Google Ja · Java · LGPL-2.1 · 2026-10
- [bridgecrewio/checkov](https://github.com/bridgecrewio/checkov) ★9.1k — Prevent cloud misconfigurations and find vulnerabilities during build-time in infrastructure as code, container images and open source packa · Python · Apache-2.0 · 2026-10
- [securego/gosec](https://github.com/securego/gosec) ★9.0k — Go security checker · Go · Apache-2.0 · 2026-10
- [repowise-dev/repowise](https://github.com/repowise-dev/repowise) ★7.8k — Codebase intelligence for AI and humans: code health scores, auto-generated docs, git analytics, dead code detection, and architectural deci · Python · AGPL-3.0 · 2026-10
- [Col-E/Recaf](https://github.com/Col-E/Recaf) ★7.4k — The modern Java bytecode editor · Java · MIT · 2026-10
- [sverweij/dependency-cruiser](https://github.com/sverweij/dependency-cruiser) ★7.3k — Validate and visualize dependencies. Your rules. JavaScript, TypeScript, CoffeeScript. ES6, CommonJS, AMD. · JavaScript · MIT · 2026-10

### Secret scanning (13)

- [momenbasel/keyFinder](https://github.com/momenbasel/keyFinder) ★725 — Passive API key and secret discovery browser extension for Chrome and Firefox. 80+ detection patterns, zero config. · JavaScript · MIT · 2026-07
- [Hainrixz/cyber-neo](https://github.com/Hainrixz/cyber-neo) ★286 — Open-source cybersecurity analysis agent for Claude Code. Scans projects for vulnerabilities across all OWASP 2025 Top 10 and CWE Top 25 cat · Python · MIT · 2026-07
- [Amal-David/keyleak-detector](https://github.com/Amal-David/keyleak-detector) ★273 — Runtime leak detector for modern web apps - finds exposed API keys, validates BaaS misconfigurations (Supabase/Firebase RLS), and catches se · Python · MIT · 2026-10
- [filipi86/drogonsec](https://github.com/filipi86/drogonsec) ★185 — High-performance open-source security scanner combining SAST, SCA, Secret Detection, and IaC analysis, built for developers and CI/CD pipeli · Go · NOASSERTION · 2026-10
- [dinosn/leaklens](https://github.com/dinosn/leaklens) ★66 — Bug bounty focused JavaScript security analysis for crawling web assets, source maps, and secret discovery · Go · Apache-2.0 · 2026-10
- [AngusKit/AngusSecurity](https://github.com/AngusKit/AngusSecurity) ★49 — Application security and governance platform — one check covers code flaws, leaked secrets, and dependency/image vulnerabilities, with merge · GPL-3.0 · 2026-09
- [mayankjain0141/nixis](https://github.com/mayankjain0141/nixis) ★39 — AI agent firewall that intercepts tool calls (file, shell, network) and enforces deterministic policies at sub-microsecond latency using CEL · Go · MIT · 2026-09
- [gitsint-rs/gitsint-rs](https://github.com/gitsint-rs/gitsint-rs) ★37 — 🔍 Gitsint is a cutting-edge OSINT platform designed for security researchers, threat intelligence teams, and developers. Uncover hidden conn · NOASSERTION · 2026-01
- [Lercas/prowl](https://github.com/Lercas/prowl) ★31 — High-precision secret scanner for code, tickets, logs, and web app with ml validation · Go · NOASSERTION · 2026-07
- [EdamAme-x/pentect](https://github.com/EdamAme-x/pentect) ★29 — Local security proxy that keeps secrets and sensitive data out of AI requests. Supports Codex, Claude Code and more. · Rust · MIT · 2026-10
- [huntridge-labs/argus](https://github.com/huntridge-labs/argus) ★28 — Argus brings “a hundred eyes” to your project, combining leading open source security tools into a scalable, automated, continuous security  · Python · NOASSERTION · 2026-10
- [ab2pentest/BurpJSReconRadar](https://github.com/ab2pentest/BurpJSReconRadar) ★27 — Burp Suite extension for passive JS reconnaissance - detects 1,600+ secret patterns, API keys, endpoints, and security misconfigurations in  · Python · NOASSERTION · 2026-04
- [pipelab-org/agent-egress-bench](https://github.com/pipelab-org/agent-egress-bench) ★22 — Open Apache-2.0 corpus, runner, scoring, and result-verification contracts for measuring AI-agent egress controls. A PipeLab open project. · Go · Apache-2.0 · 2026-10

### LLMOps & observability (30)

- [GokuMohandas/Made-With-ML](https://github.com/GokuMohandas/Made-With-ML) ★49.7k — Learn how to develop, deploy and iterate on production-grade ML applications. · Jupyter Notebook · MIT · 2026-03
- [liguodongiot/llm-action](https://github.com/liguodongiot/llm-action) ★25.2k — 本项目旨在分享大模型相关技术原理以及实战经验（大模型工程化、大模型应用落地） · HTML · Apache-2.0 · 2026-10
- [jina-ai/serve](https://github.com/jina-ai/serve) ★21.9k — ☁️ Build multimodal AI applications with cloud-native stack · Python · Apache-2.0 · 2025-03
- [raga-ai-hub/RagaAI-Catalyst](https://github.com/raga-ai-hub/RagaAI-Catalyst) ★16.2k — Python SDK for Agent AI Observability, Monitoring and Evaluation Framework. Includes features like agent, llm and tools tracing, debugging m · Python · Apache-2.0 · 2026-02
- [vibrantlabsai/ragas](https://github.com/vibrantlabsai/ragas) ★16.0k — Supercharge Your LLM Application Evaluations 🚀 · Python · Apache-2.0 · 2026-02
- [Portkey-AI/gateway](https://github.com/Portkey-AI/gateway) ★13.2k — A blazing fast AI Gateway with integrated guardrails. Route to 1,600+ LLMs, 50+ AI Guardrails with 1 fast & friendly API. · TypeScript · MIT · 2026-05
- [bentoml/OpenLLM](https://github.com/bentoml/OpenLLM) ★12.6k — Run any open-source LLMs, such as DeepSeek and Llama, as OpenAI compatible API endpoint in the cloud. · Python · Apache-2.0 · 2026-10
- [tensorzero/tensorzero](https://github.com/tensorzero/tensorzero) ★11.7k — TensorZero is an open-source LLMOps platform that unifies an LLM gateway, observability, evaluation, optimization, and experimentation. · Rust · Apache-2.0 · 2026-06
- [Netflix/metaflow](https://github.com/Netflix/metaflow) ★10.3k — Build, Manage and Deploy AI/ML Systems · Python · Apache-2.0 · 2026-10
- [bentoml/BentoML](https://github.com/bentoml/BentoML) ★8.9k — The easiest way to serve AI apps and models - Build Model Inference APIs, Job queues, LLM apps, Multi-model pipelines, and more! · Python · Apache-2.0 · 2026-10
- [0xPlaygrounds/rig](https://github.com/0xPlaygrounds/rig) ★8.9k — ⚙️🦀 Build modular and scalable LLM Applications in Rust · Rust · MIT · 2026-10
- [evidentlyai/evidently](https://github.com/evidentlyai/evidently) ★8.0k — Evidently is ​​an open-source ML and LLM observability framework. Evaluate, test, and monitor any AI-powered system or data pipeline. From t · Jupyter Notebook · Apache-2.0 · 2026-09
- [traceloop/openllmetry](https://github.com/traceloop/openllmetry) ★7.5k — Open-source observability for your GenAI or LLM application, based on OpenTelemetry · Python · Apache-2.0 · 2026-10
- [katanemo/plano](https://github.com/katanemo/plano) ★7.1k — Plano is an AI-native proxy server and data plane for agentic apps. Smart LLM routing, observability, agent orchestration, and guardrails so · Rust · Apache-2.0 · 2026-10
- [clearml/clearml](https://github.com/clearml/clearml) ★6.9k — ClearML - Auto-Magical CI/CD to streamline your AI workload. Experiment Management, Data Management, Pipeline, Orchestration, Scheduling & S · Python · Apache-2.0 · 2026-10
- [GoogleCloudPlatform/agent-starter-pack](https://github.com/GoogleCloudPlatform/agent-starter-pack) ★6.6k — Ship AI Agents to Google Cloud in minutes, not months. Production-ready templates with built-in CI/CD, evaluation, and observability. · Python · Apache-2.0 · 2026-07
- [tensorchord/Awesome-LLMOps](https://github.com/tensorchord/Awesome-LLMOps) ★6.0k — An awesome & curated list of best LLMOps tools for developers · Shell · CC0-1.0 · 2026-10
- [coze-dev/coze-loop](https://github.com/coze-dev/coze-loop) ★5.8k — Next-generation AI Agent Optimization Platform: Cozeloop addresses challenges in AI agent development by providing full-lifecycle management · Go · Apache-2.0 · 2026-10
- [zenml-io/zenml](https://github.com/zenml-io/zenml) ★5.6k — ZenML 🙏: One AI Platform from Pipelines to Agents. https://zenml.io. · Python · Apache-2.0 · 2026-10
- [PacktPublishing/LLM-Engineers-Handbook](https://github.com/PacktPublishing/LLM-Engineers-Handbook) ★5.4k — The LLM's practical guide: From the fundamentals to deploying advanced LLM and RAG apps to AWS using LLMOps best practices · Python · MIT · 2026-04
- [tencentmusic/cube-studio](https://github.com/tencentmusic/cube-studio) ★5.1k — cube studio开源云原生一站式机器学习/深度学习/大模型AI平台，mlops算法链路全流程，算力租赁平台，notebook在线开发，拖拉拽任务流pipeline编排，多机多卡分布式训练，超参搜索，推理服务VGPU虚拟化，边缘计算，标注平台自动化标注，deepseek等大模 · NOASSERTION · 2026-10
- [truefoundry/cognita](https://github.com/truefoundry/cognita) ★4.4k — RAG (Retrieval Augmented Generation) Framework for building modular, open source applications for production by TrueFoundry · Python · Apache-2.0 · 2026-03
- [decodingai-magazine/llm-twin-course](https://github.com/decodingai-magazine/llm-twin-course) ★4.4k — 🤖 𝗟𝗲𝗮𝗿𝗻 for 𝗳𝗿𝗲𝗲 how to 𝗯𝘂𝗶𝗹𝗱 an end-to-end 𝗽𝗿𝗼𝗱𝘂𝗰𝘁𝗶𝗼𝗻-𝗿𝗲𝗮𝗱𝘆 𝗟𝗟𝗠 & 𝗥𝗔𝗚 𝘀𝘆𝘀𝘁𝗲𝗺 using 𝗟𝗟𝗠𝗢𝗽𝘀 best practices: ~ 𝘴𝘰𝘶𝘳𝘤𝘦 𝘤𝘰𝘥𝘦 + 12 𝘩𝘢𝘯𝘥𝘴-𝘰𝘯 𝘭𝘦𝘴𝘴𝘰 · Python · MIT · 2026-04
- [predibase/lorax](https://github.com/predibase/lorax) ★3.8k — Multi-LoRA inference server that scales to 1000s of fine-tuned LLMs · Python · Apache-2.0 · 2026-05
- [memodb-io/Acontext](https://github.com/memodb-io/Acontext) ★3.7k — Agent Skills as a Memory Layer · JavaScript · Apache-2.0 · 2026-07
- [iusztinpaul/hands-on-llms](https://github.com/iusztinpaul/hands-on-llms) ★3.4k — 🦖 𝗟𝗲𝗮𝗿𝗻 about 𝗟𝗟𝗠𝘀, 𝗟𝗟𝗠𝗢𝗽𝘀, and 𝘃𝗲𝗰𝘁𝗼𝗿 𝗗𝗕𝘀 for free by designing, training, and deploying a real-time financial advisor LLM system ~ 𝘴𝘰𝘶𝘳𝘤𝘦  · Jupyter Notebook · MIT · 2024-12
- [lmnr-ai/lmnr](https://github.com/lmnr-ai/lmnr) ★3.4k — Laminar - open-source observability platform purpose-built for AI agents. YC S24. · TypeScript · Apache-2.0 · 2026-10
- [Josh-XT/AGiXT](https://github.com/Josh-XT/AGiXT) ★3.2k — AGiXT is a dynamic AI Agent Automation Platform that seamlessly orchestrates instruction management and complex task execution across divers · Python · MIT · 2026-07
- [decodingai-magazine/second-brain-ai-assistant-course](https://github.com/decodingai-magazine/second-brain-ai-assistant-course) ★3.1k — Learn to build your Second Brain AI assistant with LLMs, agents, RAG, fine-tuning, LLMOps and AI systems techniques. · Jupyter Notebook · MIT · 2026-04
- [vllm-project/vllm-ascend](https://github.com/vllm-project/vllm-ascend) ★3.0k — Community maintained hardware plugin for vLLM on Huawei Ascend · Python · Apache-2.0 · 2026-10

### Workflow automation (30)

- [ToolJet/ToolJet](https://github.com/ToolJet/ToolJet) ★41.1k — Open-source foundation of ToolJet AI - the enterprise app generation platform for internal tools, dashboards, business applications, workflo · HTML · AGPL-3.0 · 2026-10
- [conductor-oss/conductor](https://github.com/conductor-oss/conductor) ★32.3k — Conductor is an event driven agentic workflow engine providing durable and highly resilient execution engine for applications and AI Agents · Java · Apache-2.0 · 2026-10
- [Budibase/budibase](https://github.com/Budibase/budibase) ★28.3k — AI agents, automations and apps that run your operations. Model agnostic. · TypeScript · NOASSERTION · 2026-10
- [temporalio/temporal](https://github.com/temporalio/temporal) ★23.7k — Temporal service · Go · MIT · 2026-10
- [HBAI-Ltd/Toonflow-app](https://github.com/HBAI-Ltd/Toonflow-app) ★17.9k — 短剧、漫剧制作工具 Toonflow：开源 AI 视频创作平台，集成剧本创作、智能分镜、角色与场景资产管理、图像生成和视频生成。融合无限画布、AI Agent 与可视化工作流，支持本地部署、自选模型、跨平台客户端、MCP 与插件扩展。Open-source AI short dr · TypeScript · MIT · 2026-10
- [dagster-io/dagster](https://github.com/dagster-io/dagster) ★16.3k — An orchestration platform for the development, production, and observation of data assets. · Python · Apache-2.0 · 2026-10
- [alicevision/Meshroom](https://github.com/alicevision/Meshroom) ★13.0k — Node-based Visual Programming Toolbox · Python · NOASSERTION · 2026-10
- [Netflix/conductor](https://github.com/Netflix/conductor) ★12.7k — Conductor is a microservices orchestration engine. · Java · Apache-2.0 · 2023-12
- [keephq/keep](https://github.com/keephq/keep) ★12.4k — The open-source AIOps and alert management platform · Python · NOASSERTION · 2026-09
- [cadence-workflow/cadence](https://github.com/cadence-workflow/cadence) ★9.5k — Cadence is a distributed, scalable, durable, and highly available orchestration engine to execute asynchronous long-running business logic i · Go · Apache-2.0 · 2026-10
- [bytedance/flowgram.ai](https://github.com/bytedance/flowgram.ai) ★8.5k — FlowGram is an extensible workflow development framework with built-in canvas, form, variable, and materials that helps developers build AI  · TypeScript · MIT · 2026-10
- [superplanehq/superplane](https://github.com/superplanehq/superplane) ★7.8k — Open source factory for one-shot engineering · Go · NOASSERTION · 2026-10
- [czlonkowski/n8n-skills](https://github.com/czlonkowski/n8n-skills) ★6.4k — n8n skillset for Claude Code to build flawless n8n workflows · Shell · MIT · 2026-10
- [loopx-project/loopx](https://github.com/loopx-project/loopx) ★6.3k — A control plane with a durable state kernel for long-horizon agents and teams. Keep work moving and improving across sessions, with less hum · Python · Apache-2.0 · 2026-10
- [breaking-brake/cc-wf-studio](https://github.com/breaking-brake/cc-wf-studio) ★5.4k — CC Workflow Studio · TypeScript · NOASSERTION · 2026-10
- [Agenta-AI/agenta](https://github.com/Agenta-AI/agenta) ★4.8k — Agenta is a workspace where you and your team build agents and automations. · TypeScript · NOASSERTION · 2026-10
- [AlexAnys/awesome-openclaw-usecases-zh](https://github.com/AlexAnys/awesome-openclaw-usecases-zh) ★4.4k — 🇨🇳 OpenClaw中文用例大全 | 50个真实场景 | 国内特色 + 海外案例的国内适配 | 自动化办公·内容创作·运维·AI助理·知识管理 | 新手友好 · MIT · 2026-07
- [composio-community/open-claude-cowork](https://github.com/composio-community/open-claude-cowork) ★4.3k — Open Source version of Claude Cowork with 500+ SaaS app integrations · JavaScript · MIT · 2026-05
- [ScrapeCreators/social-media-research-skills](https://github.com/ScrapeCreators/social-media-research-skills) ★3.8k — AI agent skills for social media research. Outlier posts, comment mining, competitor teardowns, ad libraries & trends across TikTok, Instagr · Python · MIT · 2026-08
- [lowdefy/lowdefy](https://github.com/lowdefy/lowdefy) ★3.0k — Build apps that AI can generate, humans can review, and teams can maintain. Config that works between code and natural language. · JavaScript · Apache-2.0 · 2026-10
- [yaojingang/yao-meta-skill](https://github.com/yaojingang/yao-meta-skill) ★2.7k — YAO = Yielding AI Outcomes. A rigorous engineering, evaluation, governance, and portability system for reusable agent skills. · Python · MIT · 2026-08
- [argoproj/argo-events](https://github.com/argoproj/argo-events) ★2.7k — Event-driven Automation Framework for Kubernetes · Go · Apache-2.0 · 2026-10
- [moazbuilds/CodeMachine-CLI](https://github.com/moazbuilds/CodeMachine-CLI) ★2.5k — CodeMachine is an open-source tool that orchestrates AI coding agents into repeatable, long-running workflows. ⚡️ · TypeScript · Apache-2.0 · 2026-02
- [shepherd-agents/shepherd](https://github.com/shepherd-agents/shepherd) ★2.5k — A runtime substrate that turns an agent's execution into a reversible, Git-like trace, so meta-agents can observe, fork, replay, and revert  · Python · MIT · 2026-09
- [catlog22/Claude-Code-Workflow](https://github.com/catlog22/Claude-Code-Workflow) ★2.1k — JSON-driven multi-agent  cadence-team development framework with   intelligent CLI orchestration (Gemini/Qwen/Codex),   context-first archit · TypeScript · MIT · 2026-06
- [pydoit/doit](https://github.com/pydoit/doit) ★2.1k — CLI task management & automation tool · Python · MIT · 2026-09
- [rulego/rulego](https://github.com/rulego/rulego) ★1.6k — ⛓️RuleGo is a lightweight, high-performance, embedded, next-generation component orchestration rule engine framework for Go. · Go · Apache-2.0 · 2026-10
- [EtienneLescot/n8n-as-code](https://github.com/EtienneLescot/n8n-as-code) ★1.6k — Give your AI agent n8n superpowers. 537 nodes with full schemas, 7,700+ templates, Git-like sync, and TypeScript workflows. · TypeScript · MIT · 2026-10
- [869413421/ai-moive-studio](https://github.com/869413421/ai-moive-studio) ★1.6k — 自然语言驱动的无限画布工作流 Agent，让 AI 视频创作第一次真正变成可编辑的工作流。   AICON 面向创作者，提供从剧本拆解、分镜生成、素材生成、视频合成到内容分发的一整套能力。   不是只给你一个输入框，而是让你用自然语言和无限画布一起驱动创作，把文本、图片、视频节点 · Python · Apache-2.0 · 2026-09
- [nocode-js/sequential-workflow-designer](https://github.com/nocode-js/sequential-workflow-designer) ★1.5k — Customizable no-code component for building flow-based programming applications or workflow automation. 0 external dependencies. Check out h · TypeScript · MIT · 2026-09

### Voice assistants (30)

- [pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat) ★16.5k — Open Source framework for voice agents, multimodal apps, and realtime AI. Maintained by Daily and the community. · Python · BSD-2-Clause · 2026-10
- [jianchang512/clone-voice](https://github.com/jianchang512/clone-voice) ★9.0k — A sound cloning tool with a web interface, using your voice or any sound to record audio / 一个带web界面的声音克隆工具，使用你的音色或任意声音来录制音频 · Python · NOASSERTION · 2025-08
- [MycroftAI/mycroft-core](https://github.com/MycroftAI/mycroft-core) ★6.6k — Mycroft Core, the Mycroft Artificial Intelligence platform. · Python · Apache-2.0 · 2024-09
- [Priler/jarvis](https://github.com/Priler/jarvis) ★3.0k — Offline voice assistant that respects your privacy. Forged in Rust. WIP. · Rust · NOASSERTION · 2026-02
- [xzf-thu/VoiceMem](https://github.com/xzf-thu/VoiceMem) ★2.5k — Infrastructure for the next generation of voice agents, designed to provide universal memory. It is divided into a left brain and a right br · Python · Apache-2.0 · 2026-09
- [jim-schwoebel/voice_datasets](https://github.com/jim-schwoebel/voice_datasets) ★2.2k — 🔊 A comprehensive list of open-source datasets for voice and sound computing (95+ datasets). · NOASSERTION · 2024-06
- [isair/jarvis](https://github.com/isair/jarvis) ★2.1k — Private local AI assistant for your desktop. Voice and text chat, personal memory, dictation and MCP tools. Runs offline with Ollama or Open · Python · NOASSERTION · 2026-10
- [AutoArk/EVA-OS](https://github.com/AutoArk/EVA-OS) ★1.9k — EVA OS — A real-time multimodal AIOS for next-generation hardware, enabling your devices being “alive” and as intelligent as a real brain. · MIT · 2026-08
- [alan-ai/alan-sdk-ios](https://github.com/alan-ai/alan-sdk-ios) ★1.9k — The Self-Coding System for Your App — Alan AI SDK for iOS · Objective-C · NOASSERTION · 2025-04
- [alan-ai/alan-sdk-android](https://github.com/alan-ai/alan-sdk-android) ★1.8k — The Self-Coding System for Your App — Alan AI SDK for Android · NOASSERTION · 2025-04
- [wwbin2017/bailing](https://github.com/wwbin2017/bailing) ★1.8k — 百聆 是一个类似GPT-4o的语音对话机器人，通过ASR+LLM+TTS实现，集成DeepSeek R1等优秀大模型，接入openClaw，真正的个人语音助手，时延低至800ms，Mac等低配置也可运行，支持打断 · Python · MIT · 2026-04
- [alan-ai/alan-sdk-flutter](https://github.com/alan-ai/alan-sdk-flutter) ★1.8k — The Self-Coding System for Your App — Alan AI SDK for Flutter · Ruby · NOASSERTION · 2025-04
- [Lynpoint/CyberVerse](https://github.com/Lynpoint/CyberVerse) ★1.7k — Self hosted, real-time digital human agent platform. Build voice-first AI agents with WebRTC, persona memory, tools, RAG, and optional digit · Python · GPL-3.0 · 2026-09
- [jovotech/jovo-framework](https://github.com/jovotech/jovo-framework) ★1.7k — 🔈 The React for Voice and Chat: Build Apps for Alexa, Messenger, Instagram, the Web, and more · TypeScript · Apache-2.0 · 2025-04
- [alan-ai/alan-sdk-ionic](https://github.com/alan-ai/alan-sdk-ionic) ★1.6k — The Self-Coding System for Your App — Alan AI SDK for Ionic · TypeScript · NOASSERTION · 2025-04
- [jxlarrea/kiosk-satellite](https://github.com/jxlarrea/kiosk-satellite) ★1.6k — Turn any Android device into a beautiful, dedicated Home Assistant kiosk. Purpose-built for Home Assistant from the ground up. · Dart · NOASSERTION · 2026-10
- [DicioTeam/dicio-android](https://github.com/DicioTeam/dicio-android) ★1.5k — Dicio assistant app for Android · Kotlin · GPL-3.0 · 2026-10
- [wilbowes/EchoMuse](https://github.com/wilbowes/EchoMuse) ★1.2k — Alexa replacement and controller for Echo Dot 2nd Generation device. · Python · MIT · 2026-10
- [janvarev/Irene-Voice-Assistant](https://github.com/janvarev/Irene-Voice-Assistant) ★1.2k — Ирина - русский голосовой ассистент для работы оффлайн. Поддерживает скиллы через плагины. · Python · NOASSERTION · 2026-07
- [alan-ai/alan-sdk-cordova](https://github.com/alan-ai/alan-sdk-cordova) ★1.1k — The Self-Coding System for Your App — Alan AI SDK for Cordova · Ruby · NOASSERTION · 2025-04
- [dext0r/yandex_smart_home](https://github.com/dext0r/yandex_smart_home) ★1.1k — Управление устройствами из Home Assistant через Алису (Умный дом Яндекса) или Марусю · Python · MIT · 2026-09
- [ggeop/Python-ai-assistant](https://github.com/ggeop/Python-ai-assistant) ★1.0k — Python AI assistant 🧠 · Python · MIT · 2024-11
- [xvirobotics/metabot](https://github.com/xvirobotics/metabot) ★997 — 构建受监督的、自我进化的 Agent 组织的基础设施 | Infrastructure for supervised, self-improving agent organization. 飞书/Telegram 手机端运行 Claude Code 或 Kimi Code（双引擎 · TypeScript · MIT · 2026-09
- [kishanrajput23/Jarvis-Desktop-Voice-Assistant](https://github.com/kishanrajput23/Jarvis-Desktop-Voice-Assistant) ★995 — A python based desktop voice assistant capable of executing system-level commands, integrating speech recognition and text-to-speech, and ha · Python · MIT · 2026-10
- [Ayush0Chaudhary/blurr](https://github.com/Ayush0Chaudhary/blurr) ★993 — This app can now use Android, just like a human. · Kotlin · NOASSERTION · 2026-01
- [synesthesiam/rhasspy](https://github.com/synesthesiam/rhasspy) ★952 — Rhasspy voice assistant for offline home automation · HTML · MIT · 2020-07
- [hehehai/voxt](https://github.com/hehehai/voxt) ★894 — We've moved to SGLang Omni Voxt: https://github.com/sgl-project/sglang-omni/tree/main/Voxt · Swift · NOASSERTION · 2026-10
- [re50urces/Awesome-AI](https://github.com/re50urces/Awesome-AI) ★894 — A curated list of awesome things related to artificial intelligence tools · NOASSERTION · 2024-08
- [jxlarrea/voice-satellite-card-integration](https://github.com/jxlarrea/voice-satellite-card-integration) ★888 — Voice Satellite turns any tablet, phone, or browser into a hands-free voice assistant for Home Assistant · JavaScript · AGPL-3.0 · 2026-09
- [ethanplusai/jarvis](https://github.com/ethanplusai/jarvis) ★877 — JARVIS — a voice assistant for Claude Code. Talk to your Mac and he brainstorms a project with you, builds it, and tells you out loud when a · Python · NOASSERTION · 2026-09

### Speech recognition (30)

- [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) ★54.4k — Port of OpenAI's Whisper model in C/C++ · C++ · MIT · 2026-10
- [mozilla/DeepSpeech](https://github.com/mozilla/DeepSpeech) ★26.8k — DeepSpeech is an open source embedded (offline, on-device) speech-to-text engine which can run in real time on devices ranging from a Raspbe · C++ · MPL-2.0 · 2025-06
- [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) ★25.9k — Faster Whisper transcription with CTranslate2 · Python · MIT · 2026-10
- [m-bain/whisperX](https://github.com/m-bain/whisperX) ★24.6k — WhisperX:  Automatic Speech Recognition with Word-level Timestamps (& Diarization) · Python · BSD-2-Clause · 2026-09
- [kaldi-asr/kaldi](https://github.com/kaldi-asr/kaldi) ★15.5k — kaldi-asr/kaldi is the official location of the Kaldi project. · Shell · NOASSERTION · 2025-09
- [alphacep/vosk-api](https://github.com/alphacep/vosk-api) ★15.2k — Offline speech recognition API for Android, iOS, Raspberry Pi and servers with Python, Java, C# and Node · Jupyter Notebook · Apache-2.0 · 2026-10
- [NVIDIA/DeepLearningExamples](https://github.com/NVIDIA/DeepLearningExamples) ★14.9k — State-of-the-Art Deep Learning scripts organized by models - easy to train and deploy with reproducible accuracy and performance on enterpri · Jupyter Notebook · NOASSERTION · 2024-08
- [abus-aikorea/voice-pro](https://github.com/abus-aikorea/voice-pro) ★13.0k — Gradio WebUI for creators and developers, featuring key TTS (Edge-TTS, kokoro) and zero-shot Voice Cloning (E2 & F5-TTS, CosyVoice), with Wh · Python · GPL-3.0 · 2026-07
- [kmario23/deep-learning-drizzle](https://github.com/kmario23/deep-learning-drizzle) ★13.0k — Drench yourself in Deep Learning, Reinforcement Learning, Machine Learning, Computer Vision, and NLP by learning from these exciting lecture · HTML · NOASSERTION · 2026-08
- [PaddlePaddle/PaddleSpeech](https://github.com/PaddlePaddle/PaddleSpeech) ★12.7k — Easy-to-use Speech Toolkit including Self-Supervised Learning model, SOTA/Streaming ASR with punctuation, Streaming TTS with text frontend,  · Python · Apache-2.0 · 2026-08
- [speechbrain/speechbrain](https://github.com/speechbrain/speechbrain) ★11.9k — A PyTorch-based Speech Toolkit · Python · Apache-2.0 · 2026-10
- [QuentinFuxa/WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit) ★11.1k — Real-time, local speech-to-text with streaming ASR, speaker diarization, translation, and OpenAI/Deepgram-compatible APIs. · Python · Apache-2.0 · 2026-10
- [openvinotoolkit/openvino](https://github.com/openvinotoolkit/openvino) ★11.0k — OpenVINO™ is an open source toolkit for optimizing and deploying AI inference · C++ · Apache-2.0 · 2026-10
- [espnet/espnet](https://github.com/espnet/espnet) ★10.0k — End-to-End Speech Processing Toolkit · Python · Apache-2.0 · 2026-10
- [QwenAudio/SenseVoice](https://github.com/QwenAudio/SenseVoice) ★9.5k — Open-source SenseVoiceSmall model for Mandarin, Cantonese, English, Japanese, and Korean ASR, language ID, emotion recognition, and audio ev · C · MIT · 2026-09
- [Uberi/speech_recognition](https://github.com/Uberi/speech_recognition) ★9.0k — Speech recognition module for Python, supporting several engines and APIs, online and offline. · Python · BSD-3-Clause · 2026-09
- [nl8590687/ASRT_SpeechRecognition](https://github.com/nl8590687/ASRT_SpeechRecognition) ★8.4k — A Deep-Learning-Based Chinese Speech Recognition System 基于深度学习的中文语音识别系统 · Python · GPL-3.0 · 2026-04
- [Blaizzy/mlx-audio](https://github.com/Blaizzy/mlx-audio) ★8.1k — A text-to-speech (TTS), speech-to-text (STT) and speech-to-speech (STS) library built on Apple's MLX framework, providing efficient speech a · Python · MIT · 2026-10
- [TalAter/annyang](https://github.com/TalAter/annyang) ★6.8k — 💬 Speech recognition for your site · TypeScript · MIT · 2026-10
- [flashlight/wav2letter](https://github.com/flashlight/wav2letter) ★6.4k — Facebook AI Research's Automatic Speech Recognition Toolkit · C++ · NOASSERTION · 2026-08
- [argmaxinc/argmax-oss-swift](https://github.com/argmaxinc/argmax-oss-swift) ★6.4k — On-device Speech AI for Apple Silicon · Swift · MIT · 2026-10
- [modelscope/FunClip](https://github.com/modelscope/FunClip) ★6.4k — FunASR-powered video transcription, subtitle generation, and LLM-assisted clipping tool with a local Gradio UI. · Python · MIT · 2026-10
- [PaddlePaddle/PaddleX](https://github.com/PaddlePaddle/PaddleX) ★6.3k — All-in-One Development Tool based on PaddlePaddle · Python · Apache-2.0 · 2026-10
- [MahmoudAshraf97/whisper-diarization](https://github.com/MahmoudAshraf97/whisper-diarization) ★5.7k — Automatic Speech Recognition with Speaker Diarization based on OpenAI Whisper · Jupyter Notebook · BSD-2-Clause · 2026-08
- [wenet-e2e/wenet](https://github.com/wenet-e2e/wenet) ★5.2k — Production First and Production Ready End-to-End Speech Recognition Toolkit · Python · Apache-2.0 · 2026-09
- [yanshengjia/ml-road](https://github.com/yanshengjia/ml-road) ★5.0k — Machine Learning and Agentic AI Resources, Practice and Research · Python · MIT · 2026-08
- [Picovoice/porcupine](https://github.com/Picovoice/porcupine) ★5.0k — On-device wake word detection powered by deep learning · Python · Apache-2.0 · 2026-10
- [jianchang512/stt](https://github.com/jianchang512/stt) ★4.8k — Voice Recognition to Text Tool / 一个离线运行的本地音视频转字幕工具，输出json、srt字幕、纯文字格式 · Python · GPL-3.0 · 2026-01
- [sanchit-gandhi/whisper-jax](https://github.com/sanchit-gandhi/whisper-jax) ★4.7k — JAX implementation of OpenAI's Whisper model for up to 70x speed-up on TPU. · Jupyter Notebook · Apache-2.0 · 2024-04
- [cmusphinx/pocketsphinx](https://github.com/cmusphinx/pocketsphinx) ★4.3k — A small speech recognizer · C · NOASSERTION · 2026-10

### Personal AI assistants (30)

- [MagicMirrorOrg/MagicMirror](https://github.com/MagicMirrorOrg/MagicMirror) ★24.1k — MagicMirror² is an open source modular smart mirror platform. With a growing list of installable modules, the MagicMirror² allows you to con · JavaScript · MIT · 2026-10
- [elie222/inbox-zero](https://github.com/elie222/inbox-zero) ★12.6k — The world's best AI personal assistant for email. Open source app to help you reach inbox zero fast. · TypeScript · NOASSERTION · 2026-10
- [Prince-Mendiratta/BotsApp](https://github.com/Prince-Mendiratta/BotsApp) ★5.5k — Your personal assistant, on WhatsApp! The most user friendly userbot for the platform! · TypeScript · GPL-3.0 · 2026-06
- [claritylab/lucida](https://github.com/claritylab/lucida) ★4.8k — Speech and Vision Based Intelligent Personal Assistant · Java · NOASSERTION · 2022-12
- [sukeesh/Jarvis](https://github.com/sukeesh/Jarvis) ★3.8k — Personal Assistant for Linux and macOS · Python · MIT · 2025-12
- [fossasia/susi_server](https://github.com/fossasia/susi_server) ★2.5k — SUSI.AI server backend - the Artificial Intelligence server for personal assistants  https://susi.ai · Java · LGPL-2.1 · 2021-08
- [RTGS2017/NagaAgent](https://github.com/RTGS2017/NagaAgent) ★1.5k — A simple yet powerful agent framework for personal assistants, designed to enable intelligent interaction, multi-agent collaboration, and se · Python · AGPL-3.0 · 2026-08
- [manparvesh/yoda](https://github.com/manparvesh/yoda) ★749 — Wise and powerful personal assistant, available in your nearest terminal · Python · NOASSERTION · 2025-07
- [rohanarun/phoneclaw](https://github.com/rohanarun/phoneclaw) ★573 — A version of openClaw/Clawdbot that automates android phones entirely without root, including all apps from a side-loaded APK. Acts as your  · Kotlin · MIT · 2026-08
- [29decibel/assistant](https://github.com/29decibel/assistant) ★522 — Simple, extensible and powerful one stop personal assistant · JavaScript · MIT · 2021-01
- [HITsz-TMG/KnowAct](https://github.com/HITsz-TMG/KnowAct) ★480 — Recursive Self-Improvement Personal Assistant · Python · MIT · 2026-08
- [Merit-Systems/OpenInstinct](https://github.com/Merit-Systems/OpenInstinct) ★456 — iMessage personal assistant + password vault · TypeScript · MIT · 2026-10
- [micro/mu](https://github.com/micro/mu) ★436 — The runtime for Micro, an open personal assistant · Go · AGPL-3.0 · 2026-10
- [ironman5366/W.I.L.L](https://github.com/ironman5366/W.I.L.L) ★378 — A python written personal assistant · Python · MIT · 2019-07
- [MegaSuperKitty/WeClaw](https://github.com/MegaSuperKitty/WeClaw) ★368 — WeClaw: A Personal Assistant Powered by Mobile QQ and Windows PC Collaboration✨inspired by OpenClaw✨ · Python · MIT · 2026-05
- [ashutoshkrris/Virtual-Personal-Assistant-using-Python](https://github.com/ashutoshkrris/Virtual-Personal-Assistant-using-Python) ★344 — In this project, we'll be creating a virtual personal assistant for ourselves using our favorite programming language, Python. We can perfor · Python · MIT · 2024-05
- [nihal111/J.A.R.V.I.S](https://github.com/nihal111/J.A.R.V.I.S) ★319 — A personal assistant with simple, rudimentary AI · Python · NOASSERTION · 2021-09
- [adamyodinsky/TerminalGPT](https://github.com/adamyodinsky/TerminalGPT) ★273 — TerminalGPT - Terminal-based ChatGPT personal assistant app. Provides optimized, tailored answers for your machine's terminal. · Python · MIT · 2025-09
- [AFK-surf/Comma](https://github.com/AFK-surf/Comma) ★263 — Best free & open source AI personal assistant. Always-on, proactive, sessionless. Browser, computer use, files, remote control. Compatible w · Elixir · AGPL-3.0 · 2026-10
- [HouzuoGuo/laitos](https://github.com/HouzuoGuo/laitos) ★260 — Top geek's chindogu - personal assistant over satellite/telephone/SMS/chatbot, plus web infrastructure servers (web & mail, ad-free DNS, TCP · Go · MPL-2.0 · 2026-10
- [Maseshi/Shioru](https://github.com/Maseshi/Shioru) ★250 — 🧸 (Discord) Your personal assistant that will make your discord never lonely again. · JavaScript · MIT · 2026-09
- [UrbanCircles/igor](https://github.com/UrbanCircles/igor) ★226 — Simple, distraction free personal assistant to keep you focused and smiling. · C++ · MIT · 2025-02
- [zelon88/HRCloud2](https://github.com/zelon88/HRCloud2) ★218 — A full-featured home hosted Cloud Drive, Personal Assistant, App Launcher, File Converter, Streamer, Share Tool & More! · PHP · GPL-3.0 · 2023-10
- [Run-Tu/MindFlow](https://github.com/Run-Tu/MindFlow) ★207 — A multimodal personal assistant that allows Large Language Models (LLMs) to run code locally, acting as an autonomous agent capable of compl · Python · MIT · 2025-01
- [leon-ai/leon-cli](https://github.com/leon-ai/leon-cli) ★197 — ⌨️ Command-line interface (CLI) for a better use of Leon, your open-source personal assistant. GNU/Linux, macOS and Windows supported. · TypeScript · MIT · 2023-11
- [skorokithakis/stavrobot](https://github.com/skorokithakis/stavrobot) ★184 — An AI personal assistant with a focus on security. · TypeScript · AGPL-3.0 · 2026-10
- [momo-personal-assistant/momo-research](https://github.com/momo-personal-assistant/momo-research) ★178 — All insights extracted from relevant context engineering and memory papers · NOASSERTION · 2026-02
- [oratis/LISA](https://github.com/oratis/LISA) ★176 — Open-source AI Personal Assistant for planning, writing and personal knowledge. Use LISA Cloud or connect your own Mac. · TypeScript · MIT · 2026-10
- [daxaur/openpaw](https://github.com/daxaur/openpaw) ★173 — Personal Assistant Wizard for Claude Code — npx pawmode · TypeScript · MIT · 2026-05
- [Gentleman-Programming/gentle-dot](https://github.com/Gentleman-Programming/gentle-dot) ★173 — A personal assistant that lives on your desktop, remembers what matters, and can use your Mac for you. · TypeScript · MIT · 2026-10

### JARVIS-like projects (30)

- [microsoft/JARVIS](https://github.com/microsoft/JARVIS) ★25.4k — JARVIS, a system to connect LLMs with ML community. Paper: https://arxiv.org/pdf/2303.17580.pdf · Python · MIT · 2025-07
- [open-jarvis/OpenJarvis](https://github.com/open-jarvis/OpenJarvis) ★11.3k — Personal AI, On Personal Devices · Python · Apache-2.0 · 2026-10
- [jev-chat/jev-chat-jarvis](https://github.com/jev-chat/jev-chat-jarvis) ★7.8k — The chat decision assistant: before you reply, Jev reads the chat, judges intent and risk, and drafts replies you fill in with one tap. You  · Kotlin · MIT · 2026-10
- [zouhir/jarvis](https://github.com/zouhir/jarvis) ★5.5k — A very intelligent browser based Webpack dashboard · JavaScript · NOASSERTION · 2023-02
- [ascending-llc/jarvis-registry](https://github.com/ascending-llc/jarvis-registry) ★3.6k — Connect any AI copilot or autonomous agent to your enterprise tools — through a single, secure MCP/Agent gateway with built-in identity, acc · Python · Apache-2.0 · 2026-10
- [swapagarwal/JARVIS-on-Messenger](https://github.com/swapagarwal/JARVIS-on-Messenger) ★1.4k — :speech_balloon: A community-driven python bot that aims to be as simple as possible to serve humans with their everyday tasks · Python · MIT · 2024-04
- [LYL1015/JarvisArt](https://github.com/LYL1015/JarvisArt) ★871 — [NeurIPS' 2025] JarvisArt: Liberating Human Artistic Creativity via an Intelligent Photo Retouching Agent · Python · NOASSERTION · 2026-04
- [alexylem/jarvis](https://github.com/alexylem/jarvis) ★851 — Jarvis.sh is a simple configurable multi-lang assistant. · Shell · MIT · 2021-05
- [ctaylo21/jarvis](https://github.com/ctaylo21/jarvis) ★726 — Dotfiles for a powerful, web development-focused environment powered by Neovim, iTerm2, tmux, and zsh · Vim script · MIT · 2021-05
- [vierisid/jarvis](https://github.com/vierisid/jarvis) ★672 · TypeScript · NOASSERTION · 2026-10
- [Gladiator07/JARVIS](https://github.com/Gladiator07/JARVIS) ★670 — Personal Voice Assistant made with Python and has a cool looking GUI · Python · MIT · 2024-05
- [danilofalcao/jarvis](https://github.com/danilofalcao/jarvis) ★651 — J.A.R.V.I.S. is an intelligent coding assistant that leverages multiple state-of-the-art language models to help you with code generation, m · Python · MIT · 2025-01
- [akshayaggarwal99/jarvis-ai-assistant](https://github.com/akshayaggarwal99/jarvis-ai-assistant) ★651 — Jarvis AI Assistant - Voice-powered AI assistant for Mac · TypeScript · MIT · 2026-09
- [spectresystems/jarvis](https://github.com/spectresystems/jarvis) ★647 — Your robotic butler. · C# · MIT · 2022-12
- [LYL1015/JarvisHub](https://github.com/LYL1015/JarvisHub) ★616 — JarvisHub: An Open Harness for Canvas-Native Multimodal Creative Agents · TypeScript · Apache-2.0 · 2026-08
- [huwprosser/jarvis-mlx](https://github.com/huwprosser/jarvis-mlx) ★519 — An all-in-one solution to stark-level productivity running offline on your MacBook using SOTA technology. · Python · NOASSERTION · 2026-05
- [LYiHub/pub-local-jarvis](https://github.com/LYiHub/pub-local-jarvis) ★512 — Windows 本地多模态 AI 桌面桌宠，支持屏幕与音频感知。 · Python · MIT · 2026-07
- [affaan-m/JARVIS](https://github.com/affaan-m/JARVIS) ★504 — JARVIS: a real-time agentic intelligence-gathering platform powered by autonomous web scraping & OSINT, streamed via Meta Ray-Ban smart glas · Python · NOASSERTION · 2026-06
- [adewaskar/jarvis](https://github.com/adewaskar/jarvis) ★503 — J.A.R.V.I.S for automating your daily tasks using Claude Code · TypeScript · MIT · 2026-08
- [jev-chat/jev-chat-jarvis-mac](https://github.com/jev-chat/jev-chat-jarvis-mac) ★495 — 聊天悬浮窗助手（macOS）：屏幕感知 + 本地小模型判断意图与风险，按话术生成回复候选。纯只读。 · Python · MIT · 2026-10
- [phord/Jarvis](https://github.com/phord/Jarvis) ★483 — Hacking the Jarvis standup desk from fully.com for home automation using an ESP8266 arduino interface · C++ · GPL-3.0 · 2023-03
- [gia-guar/JARVIS-ChatGPT](https://github.com/gia-guar/JARVIS-ChatGPT) ★463 — A Conversational Assistant equipped with synthetic voices including J.A.R.V.I.S's. Powered by OpenAI and IBM Watson APIs and a Tacotron mode · Python · MIT · 2023-09
- [CraftJarvis/JARVIS-1](https://github.com/CraftJarvis/JARVIS-1) ★417 — JARVIS-1: Open-world Multi-task Agents with Memory-Augmented Multimodal Language Models · Java · NOASSERTION · 2024-04
- [Dipeshpal/Jarvis_AI](https://github.com/Dipeshpal/Jarvis_AI) ★411 — Jarvis AI is a Python Module which is able to perform task like Chatbot, Assistant etc. It provides base functionality for any assistant app · Python · MIT · 2023-06
- [LYL1015/JarvisEvo](https://github.com/LYL1015/JarvisEvo) ★410 — [CVPR' 2026]  JarvisEvo: Towards a Self-Evolving Photo Editing Agent with Synergistic Editor-Evaluator Optimization · Python · NOASSERTION · 2026-02
- [usnistgov/jarvis](https://github.com/usnistgov/jarvis) ★401 — About JARVIS-Tools: an open-source software package for data-driven atomistic materials design. Publications: https://scholar.google.com/cit · Python · NOASSERTION · 2025-08
- [hectorg2211/jarvis](https://github.com/hectorg2211/jarvis) ★395 · Python · NOASSERTION · 2026-06
- [debugger22/Jarvis](https://github.com/debugger22/Jarvis) ★372 — As the name suggests · Python · MIT · 2022-09
- [alondmnt/joplin-plugin-jarvis](https://github.com/alondmnt/joplin-plugin-jarvis) ★364 — Joplin (note-taking) assistant running a very intelligent system (GPT, Claude, Gemini, Ollama, Hugging Face) · TypeScript · AGPL-3.0 · 2026-09
- [llm-guy/jarvis](https://github.com/llm-guy/jarvis) ★337 — Jarvis is a voice-activated, conversational AI assistant powered by a local LLM (Qwen via Ollama). It listens for a wake word, processes spo · Python · NOASSERTION · 2025-09

### Password managers (30)

- [keepassxreboot/keepassxc](https://github.com/keepassxreboot/keepassxc) ★29.3k — KeePassXC is a cross-platform community-driven port of the Windows application “KeePass Password Safe”. · C++ · NOASSERTION · 2026-10
- [Kunzisoft/KeePassDX](https://github.com/Kunzisoft/KeePassDX) ★7.5k — Lightweight vault and password manager for Android, KeePassDX allows editing encrypted data in a single file in KeePass format and fill in t · Kotlin · GPL-3.0 · 2026-10
- [gopasspw/gopass](https://github.com/gopasspw/gopass) ★7.3k — The slightly more awesome standard unix password manager for teams · Go · MIT · 2026-10
- [MacPass/MacPass](https://github.com/MacPass/MacPass) ★6.9k — A native macOS KeePass client · Objective-C · NOASSERTION · 2026-10
- [PhilippC/keepass2android](https://github.com/PhilippC/keepass2android) ★6.3k — Password manager app for Android · C# · GPL-3.0 · 2026-10
- [passbolt/passbolt_api](https://github.com/passbolt/passbolt_api) ★6.2k — Passbolt Community Edition (CE) API. The JSON API for the open source password manager for teams! · PHP · AGPL-3.0 · 2026-10
- [lesspass/lesspass](https://github.com/lesspass/lesspass) ★6.1k — :key: stateless open source password manager · TypeScript · GPL-3.0 · 2026-10
- [buttercup/buttercup-desktop](https://github.com/buttercup/buttercup-desktop) ★4.4k — :key: Cross-Platform Passwords & Secrets Vault · TypeScript · GPL-3.0 · 2025-03
- [Volmarg/personal-management-system](https://github.com/Volmarg/personal-management-system) ★4.2k — Your web application for managing personal data. · PHP · MIT · 2026-10
- [shuaiplus/nodewarden](https://github.com/shuaiplus/nodewarden) ★3.9k — Bitwarden-compatible server running on Cloudflare Workers · TypeScript · NOASSERTION · 2026-10
- [padloc/padloc](https://github.com/padloc/padloc) ★2.9k — A modern, open source password manager for individuals and teams. · JavaScript · AGPL-3.0 · 2026-10
- [authpass/authpass](https://github.com/authpass/authpass) ★2.8k — AuthPass - Password Manager based on Flutter for all platforms. Keepass 2.x (KDBX 3 and KDBX 4) compatible. · Dart · GPL-3.0 · 2026-09
- [android-password-store/Android-Password-Store](https://github.com/android-password-store/Android-Password-Store) ★2.7k — Android application compatible with ZX2C4's Pass command line application · Kotlin · GPL-3.0 · 2024-10
- [cloudflare/gokey](https://github.com/cloudflare/gokey) ★2.4k — A simple vaultless password manager in Go · Go · BSD-3-Clause · 2026-07
- [mprimi/portable-secret](https://github.com/mprimi/portable-secret) ★1.7k — Better privacy without special software · HTML · MIT · 2024-07
- [keepassium/KeePassium](https://github.com/keepassium/KeePassium) ★1.7k — KeePass-compatible password manager for iOS and macOS · Swift · NOASSERTION · 2026-05
- [Lifeforge-app/lifeforge](https://github.com/Lifeforge-app/lifeforge) ★1.7k — A self-hosted solution to streamline and organize all aspects of your life. · TypeScript · NOASSERTION · 2026-10
- [mssun/passforios](https://github.com/mssun/passforios) ★1.6k — Pass for iOS - an iOS client compatible with Pass command line application. · Swift · MIT · 2026-09
- [drduh/pwd.sh](https://github.com/drduh/pwd.sh) ★1.6k — Manage secrets with Bash and GnuPG symmetric encryption · Shell · MIT · 2026-08
- [strongbox-password-safe/Strongbox](https://github.com/strongbox-password-safe/Strongbox) ★1.5k — A KeePass/Password Safe Client for iOS and OS X · Objective-C · AGPL-3.0 · 2026-07
- [passff/passff](https://github.com/passff/passff) ★1.3k — Read-only mirror of https://codeberg.org/PassFF/passff Pull requests and issues on GitHub cannot be accepted and will be automatically close · JavaScript · GPL-2.0 · 2026-08
- [sakurity/securelogin](https://github.com/sakurity/securelogin) ★1.2k — moved -> · JavaScript · MIT · 2019-06
- [IJHack/QtPass](https://github.com/IJHack/QtPass) ★1.2k — QtPass is a multi-platform GUI for pass, the standard unix password manager. · C++ · GPL-3.0 · 2026-10
- [Lyndir/MasterPassword](https://github.com/Lyndir/MasterPassword) ★1.1k — Project moved to https://gitlab.com/spectre.app · Objective-C · GPL-3.0 · 2022-06
- [Monica-Pass/Monica](https://github.com/Monica-Pass/Monica) ★1.1k — Monica Pass，Password Management, 2FA Generator · Kotlin · GPL-3.0 · 2026-10
- [unosquare/passcore](https://github.com/unosquare/passcore) ★1.0k — A self-service password management tool for Active Directory · C# · MIT · 2023-06
- [nuxsmin/sysPass](https://github.com/nuxsmin/sysPass) ★994 — Systems Password Manager · PHP · GPL-3.0 · 2024-12
- [quexten/goldwarden](https://github.com/quexten/goldwarden) ★990 — A feature-packed Bitwarden compatible desktop client · Go · MIT · 2025-08
- [fwdai/rowel](https://github.com/fwdai/rowel) ★952 — 🔑   Local-first Secrets Manager · Rust · GPL-3.0 · 2026-10
- [roddhjav/pass-import](https://github.com/roddhjav/pass-import) ★916 — A pass extension for importing data from most existing password managers · Python · GPL-3.0 · 2026-06

### Privacy tooling (30)

- [awesome-selfhosted/awesome-selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted) ★327.1k — A list of Free Software network services and web applications which can be hosted on your own servers · NOASSERTION · 2026-10
- [caddyserver/caddy](https://github.com/caddyserver/caddy) ★78.0k — Fast and extensible multi-platform HTTP/1-2-3 web server with automatic HTTPS · Go · Apache-2.0 · 2026-10
- [searxng/searxng](https://github.com/searxng/searxng) ★38.5k — SearXNG is a free internet metasearch engine which aggregates results from various search services and databases. Users are neither tracked  · Python · AGPL-3.0 · 2026-10
- [AdguardTeam/AdGuardHome](https://github.com/AdguardTeam/AdGuardHome) ★37.5k — Network-wide ads & trackers blocking DNS server · TypeScript · GPL-3.0 · 2026-10
- [lissy93/web-check](https://github.com/lissy93/web-check) ★35.1k — 🕵️‍♂️ All-in-one OSINT tool for analysing any website · TypeScript · MIT · 2026-10
- [StevenBlack/hosts](https://github.com/StevenBlack/hosts) ★31.2k — 🔒 Consolidating and extending hosts files from several well-curated sources. Optionally pick extensions for porn, social media, and other ca · Python · MIT · 2026-10
- [plausible/analytics](https://github.com/plausible/analytics) ★29.5k — Open source, privacy-first web analytics. Lightweight, cookie-free Google Analytics alternative. Self-hosted or cloud. · Elixir · AGPL-3.0 · 2026-10
- [ente/ente](https://github.com/ente/ente) ★29.4k — 💚 End-to-end encrypted cloud for everything. · Dart · AGPL-3.0 · 2026-10
- [hwdsl2/setup-ipsec-vpn](https://github.com/hwdsl2/setup-ipsec-vpn) ★28.7k — Set up your own IPsec VPN server in just a few minutes, with IPsec/L2TP, Cisco IPsec and IKEv2. Supports Ubuntu, Debian, CentOS/RHEL, Alpine · Shell · NOASSERTION · 2026-10
- [hagezi/dns-blocklists](https://github.com/hagezi/dns-blocklists) ★27.4k — DNS-Blocklists: For a better internet - keep the internet clean! · Text · GPL-3.0 · 2026-10
- [zama-ai/fhevm](https://github.com/zama-ai/fhevm) ★24.8k — FHEVM, a full-stack framework for integrating Fully Homomorphic Encryption (FHE) with blockchain applications · Rust · NOASSERTION · 2026-10
- [AprilNEA/OpenLogi](https://github.com/AprilNEA/OpenLogi) ★23.7k — ⚡️A native, local-first alternative to Logitech Options+, written in Rust 🦀 — remap buttons, DPI, and SmartShift over HID++. No account, no  · Rust · Apache-2.0 · 2026-10
- [mikeroyal/Self-Hosting-Guide](https://github.com/mikeroyal/Self-Hosting-Guide) ★23.1k — Self-Hosting Guide. Learn all about  locally hosting (on premises & private web servers) and managing software applications by yourself or y · Dockerfile · NOASSERTION · 2025-06
- [super-productivity/super-productivity](https://github.com/super-productivity/super-productivity) ★22.9k — Super Productivity is an advanced todo list app with integrated Timeboxing and time tracking capabilities. It also comes with integrations f · TypeScript · MIT · 2026-10
- [drduh/macOS-Security-and-Privacy-Guide](https://github.com/drduh/macOS-Security-and-Privacy-Guide) ★22.6k — Community guide to securing and improving privacy on macOS. · Shell · MIT · 2026-10
- [lissy93/personal-security-checklist](https://github.com/lissy93/personal-security-checklist) ★22.5k — 🔒 A compiled checklist of 300+ tips for protecting digital security and privacy in 2026 · TypeScript · NOASSERTION · 2026-10
- [FreeTubeApp/FreeTube](https://github.com/FreeTubeApp/FreeTube) ★22.1k — An Open Source YouTube app for privacy · Vue · AGPL-3.0 · 2026-10
- [matomo-org/matomo](https://github.com/matomo-org/matomo) ★22.0k — Empowering People Ethically 🚀 — Matomo is hiring! Join us → https://matomo.org/jobs Matomo is the leading open-source alternative to Google  · PHP · GPL-3.0 · 2026-10
- [Atlas-OS/Atlas](https://github.com/Atlas-OS/Atlas) ★21.8k — 🚀 An open and lightweight modification to Windows, designed to optimize performance, privacy and usability. · Batchfile · GPL-3.0 · 2026-10
- [imputnet/helium](https://github.com/imputnet/helium) ★21.6k — Private, fast, and honest web browser · C++ · GPL-3.0 · 2026-10
- [ImranR98/Obtainium](https://github.com/ImranR98/Obtainium) ★20.5k — Get Android app updates straight from the source. · Dart · GPL-3.0 · 2026-10
- [0x192/universal-android-debloater](https://github.com/0x192/universal-android-debloater) ★20.0k — Cross-platform GUI written in Rust using ADB to debloat non-rooted android devices. Improve your privacy, the security and battery life of y · Rust · GPL-3.0 · 2024-08
- [pluja/awesome-privacy](https://github.com/pluja/awesome-privacy) ★20.0k — Awesome Privacy - A curated list of services and alternatives that respect your privacy because PRIVACY MATTERS. · Python · CC0-1.0 · 2026-10
- [simplex-chat/simplex-chat](https://github.com/simplex-chat/simplex-chat) ★19.6k — SimpleX - the first messaging network operating without user identifiers of any kind - 100% private by design! iOS, Android and desktop apps · Haskell · AGPL-3.0 · 2026-10
- [hellzerg/optimizer](https://github.com/hellzerg/optimizer) ★18.2k — The finest Windows Optimizer · C# · GPL-3.0 · 2026-01
- [cryptomator/cryptomator](https://github.com/cryptomator/cryptomator) ★16.3k — Cryptomator for Windows, macOS, and Linux: Secure client-side encryption for your cloud storage, ensuring privacy and control over your data · Java · GPL-3.0 · 2026-10
- [angristan/openvpn-install](https://github.com/angristan/openvpn-install) ★16.2k — Set up your own OpenVPN server on Debian, Ubuntu, Fedora, CentOS, Arch Linux and more · Shell · MIT · 2026-10
- [gotify/server](https://github.com/gotify/server) ★16.1k — A simple server for sending and receiving messages in real-time per WebSocket. (Includes a sleek web-ui) · Go · NOASSERTION · 2026-10
- [alam00000/bentopdf](https://github.com/alam00000/bentopdf) ★16.1k — The Privacy First PDF Toolkit · JavaScript · AGPL-3.0 · 2026-10
- [organicmaps/organicmaps](https://github.com/organicmaps/organicmaps) ★15.7k — 🍃 Organic Maps is a free Android & iOS offline maps app for more than 6M travelers, tourists, hikers, and cyclists. It uses crowd-sourced Op · C++ · NOASSERTION · 2026-10

### Desktop app frameworks (30)

- [jaywcjlove/awesome-mac](https://github.com/jaywcjlove/awesome-mac) ★116.3k —  This project is dedicated to collecting high-quality macOS software and organizing them systematically by different categories for easy se · Swift · CC0-1.0 · 2026-10
- [tauri-apps/tauri](https://github.com/tauri-apps/tauri) ★111.9k — Build smaller, faster, and more secure desktop and mobile applications with a web frontend. · Rust · Apache-2.0 · 2026-10
- [nexu-io/open-design](https://github.com/nexu-io/open-design) ★101.4k — The 1st Collaborative AI Design Agent Workspace. Local-first and open source. Create prototypes, websites, apps, dashboards, presentations,  · TypeScript · Apache-2.0 · 2026-10
- [tw93/Pake](https://github.com/tw93/Pake) ★62.1k — 🤱🏻 Turn any website into a tiny, fast desktop app. · Rust · GPL-3.0 · 2026-10
- [lencx/ChatGPT](https://github.com/lencx/ChatGPT) ★54.6k — ❄️ ChatGPT Desktop Application (Mac, Windows and Linux) · Rust · NOASSERTION · 2024-08
- [DevToys-app/DevToys](https://github.com/DevToys-app/DevToys) ★32.1k — A Swiss Army knife for developers. · C# · MIT · 2026-09
- [ayangweb/BongoCat](https://github.com/ayangweb/BongoCat) ★24.0k — 🐱 BongoCat — A cross-platform interactive desktop pet that brings fun to your desktop! · Rust · Apache-2.0 · 2026-10
- [amir1376/ab-download-manager](https://github.com/amir1376/ab-download-manager) ★18.6k — A Download Manager that speeds up your downloads · Kotlin · Apache-2.0 · 2026-10
- [listen1/listen1_desktop](https://github.com/listen1/listen1_desktop) ★11.4k — one for all free music in china (Windows, Mac, Linux desktop) · JavaScript · MIT · 2026-04
- [zhouxiaoka/autoclip](https://github.com/zhouxiaoka/autoclip) ★9.5k — AutoClip｜一个链接，一键出片。开源 AI 视频剪辑桌面工具，将播客、访谈、课程等长视频自动剪成短视频，生成字幕、封面和发布文案，适配抖音、小红书、TikTok、Reels 与 YouTube Shorts。Open-source AI video clipping & c · Python · MIT · 2026-10
- [crmne/spotifast](https://github.com/crmne/spotifast) ★8.3k — Spotify, native and fast. One lightweight Rust app for your whole library, local playback, and Spotify Connect on Linux, macOS, and Windows. · Rust · MIT · 2026-10
- [lightningpixel/modly](https://github.com/lightningpixel/modly) ★8.2k — Desktop app to generate 3D models from images or prompt using local AI — runs entirely on your GPU · TypeScript · NOASSERTION · 2026-10
- [EcoPasteHub/EcoPaste](https://github.com/EcoPasteHub/EcoPaste) ★7.5k — 🎉跨平台的剪贴板管理工具 | Cross-platform clipboard management tool · Rust · Apache-2.0 · 2026-08
- [reqable/reqable-app](https://github.com/reqable/reqable-app) ★6.9k — Reqable issue track repo · NOASSERTION · 2026-10
- [LaoFeng-mouse/flyingmouse-format](https://github.com/LaoFeng-mouse/flyingmouse-format) ★6.7k — 飞鼠格式 FlyingMouse Format - Windows 免费文件格式转换工具（离线可用，内置 FFmpeg/LibreOffice/Poppler/Tesseract）。图片/文档/表格/PPT/PDF/音视频/WPS 格式互转 + OCR + 批量转换；音频仅支持普 · JavaScript · NOASSERTION · 2026-10
- [op7418/CodePilot](https://github.com/op7418/CodePilot) ★6.5k — A multi-model AI agent desktop client — connect any AI provider, extend with MCP & skills, control from your phone. Built with Electron + Ne · TypeScript · NOASSERTION · 2026-09
- [nextapps-de/winbox](https://github.com/nextapps-de/winbox) ★6.5k — WinBox is a modern HTML5 window manager for the Web. · JavaScript · Apache-2.0 · 2024-08
- [Sylinko/Everywhere](https://github.com/Sylinko/Everywhere) ★6.3k — On-screen aware AI assistant for your desktop. Uses current app context, multiple LLMs, and MCP tools to help you act across apps. · C# · NOASSERTION · 2026-10
- [belnadris/angular-electron](https://github.com/belnadris/angular-electron) ★5.7k — Ultra-fast bootstrapping with Angular and Electron :speedboat: · TypeScript · MIT · 2026-09
- [Soundnode/soundnode-app](https://github.com/Soundnode/soundnode-app) ★5.3k — Soundnode App is the Soundcloud for desktop. Built with Electron, Angular.js and Soundcloud API. · JavaScript · NOASSERTION · 2026-08
- [NaoTu/DesktopNaotu](https://github.com/NaoTu/DesktopNaotu) ★5.1k — 桌面版脑图 (百度脑图离线版，思维导图) 跨平台支持 Windows/Linux/Mac OS. (A cross-platform multilingual Mind Map Tool) · TypeScript · GPL-2.0 · 2026-09
- [aipoch/open-science](https://github.com/aipoch/open-science) ★4.9k — The open-source AI research workbench for scientific research and agent workflows. Local-first, model-agnostic desktop app with extensible s · TypeScript · Apache-2.0 · 2026-10
- [asticode/go-astilectron](https://github.com/asticode/go-astilectron) ★4.9k — Build cross platform GUI apps with GO and HTML/JS/CSS (powered by Electron) · Go · MIT · 2024-02
- [anmolkapil/plexo](https://github.com/anmolkapil/plexo) ★4.5k — Speed up downloads by combining multiple network connections in parallel · TypeScript · MIT · 2026-10
- [zhukunpenglinyutong/desktop-cc-gui](https://github.com/zhukunpenglinyutong/desktop-cc-gui) ★4.5k — Multi-engine AI coding desktop client (Tauri). Claude Code, Codex, Gemini, OpenCode, DeepSeek Harness and more in one GUI. · TypeScript · NOASSERTION · 2026-10
- [irbis-sh/zen-desktop](https://github.com/irbis-sh/zen-desktop) ★4.3k — System-wide ad-blocker and privacy guard for Windows, macOS and Linux. · Go · MIT · 2026-10
- [harry0703/MangoDisk](https://github.com/harry0703/MangoDisk) ★4.2k — Safety-first disk cleaner and space analyzer for macOS and Windows, with duplicate cleanup, app uninstall, startup management, system optimi · Rust · GPL-3.0 · 2026-10
- [matt1398/claude-devtools](https://github.com/matt1398/claude-devtools) ★4.0k — The missing DevTools for Claude Code — inspect session logs, tool calls, token usage, subagents, and context window in a visual UI. Free, op · TypeScript · MIT · 2026-09
- [julyx10/lap](https://github.com/julyx10/lap) ★3.9k — An offline-first photo manager for large local libraries · Vue · GPL-3.0 · 2026-10
- [ilysenko/codex-desktop-linux](https://github.com/ilysenko/codex-desktop-linux) ★3.9k — Unofficial ChatGPT desktop app for Linux (formerly the Codex app), built locally from OpenAI’s official macOS app. Includes Chat, Work, and  · JavaScript · MIT · 2026-10

### Monitoring & dashboards (30)

- [ruvnet/RuView](https://github.com/ruvnet/RuView) ★98.3k — π RuView turns commodity WiFi signals into real-time spatial intelligence, vital sign monitoring, and presence detection — all without a sin · Rust · MIT · 2026-10
- [louislam/uptime-kuma](https://github.com/louislam/uptime-kuma) ★92.5k — A fancy self-hosted monitoring tool · JavaScript · MIT · 2026-10
- [grafana/grafana](https://github.com/grafana/grafana) ★77.3k — The open and composable observability and data visualization platform. Visualize metrics, logs, and traces from multiple sources like Promet · TypeScript · AGPL-3.0 · 2026-10
- [prometheus/prometheus](https://github.com/prometheus/prometheus) ★66.6k — The Prometheus monitoring system and time series database. · Go · Apache-2.0 · 2026-10
- [getsentry/sentry](https://github.com/getsentry/sentry) ★45.6k — Developer-first error tracking and performance monitoring · Python · NOASSERTION · 2026-10
- [Unitech/pm2](https://github.com/Unitech/pm2) ★43.3k — Node.js/Typescript/Bun Production Process Manager with a built-in Load Balancer. · JavaScript · NOASSERTION · 2026-09
- [glanceapp/glance](https://github.com/glanceapp/glance) ★37.5k — A self-hosted dashboard that puts all your feeds in one place · Go · AGPL-3.0 · 2026-10
- [SigNoz/signoz](https://github.com/SigNoz/signoz) ★32.4k — SigNoz is an open-source, OpenTelemetry-native observability platform for your team and their AI agents. Get logs, metrics, and traces in on · TypeScript · NOASSERTION · 2026-10
- [influxdata/influxdb](https://github.com/influxdata/influxdb) ★31.8k — Scalable datastore for metrics, events, and real-time analytics · Rust · Apache-2.0 · 2026-10
- [henrygd/beszel](https://github.com/henrygd/beszel) ★26.2k — Lightweight server monitoring with historical data, docker stats, and alerts. · Go · MIT · 2026-10
- [cilium/cilium](https://github.com/cilium/cilium) ★25.7k — eBPF-based Networking, Security, and Observability · Go · Apache-2.0 · 2026-10
- [taosdata/TDengine](https://github.com/taosdata/TDengine) ★25.2k — High-performance, scalable time-series database designed for Industrial IoT (IIoT) scenarios · C · AGPL-3.0 · 2026-10
- [osquery/osquery](https://github.com/osquery/osquery) ★23.6k — SQL powered operating system instrumentation, monitoring, and analytics. · C++ · NOASSERTION · 2026-10
- [openobserve/openobserve](https://github.com/openobserve/openobserve) ★22.4k — Open source observability platform for logs, metrics, traces, RUM (web, android, ios), Session replay, pipelines, SLO and LLM observability. · TypeScript · AGPL-3.0 · 2026-10
- [didi/DoKit](https://github.com/didi/DoKit) ★20.4k — 一款面向泛前端产品研发全生命周期的效率平台。 · Java · Apache-2.0 · 2026-10
- [bettercap/bettercap](https://github.com/bettercap/bettercap) ★20.1k — The Swiss Army knife for 802.11, BLE, HID, CAN-bus, IPv4 and IPv6 networks reconnaissance and MITM attacks. · Go · NOASSERTION · 2026-08
- [dianping/cat](https://github.com/dianping/cat) ★18.9k — CAT 作为服务端项目基础组件，提供了 Java, C/C++, Node.js, Python, Go 等多语言客户端，已经在美团点评的基础架构中间件框架（MVC框架，RPC框架，数据库框架，缓存框架等，消息队列，配置系统等）深度集成，为美团点评各业务线提供系统丰富的性能指标、 · Java · Apache-2.0 · 2025-01
- [fail2ban/fail2ban](https://github.com/fail2ban/fail2ban) ★18.8k — Daemon to ban hosts that cause multiple authentication errors · Python · NOASSERTION · 2026-10
- [VictoriaMetrics/VictoriaMetrics](https://github.com/VictoriaMetrics/VictoriaMetrics) ★17.9k — VictoriaMetrics: fast, cost-effective monitoring solution and time series database · Go · Apache-2.0 · 2026-10
- [influxdata/telegraf](https://github.com/influxdata/telegraf) ★17.9k — Agent for collecting, processing, aggregating, and writing metrics, logs, and other arbitrary data. · Go · MIT · 2026-10
- [bcicen/ctop](https://github.com/bcicen/ctop) ★17.8k — Top-like interface for container metrics · Go · MIT · 2024-07
- [winsiderss/systeminformer](https://github.com/winsiderss/systeminformer) ★16.3k — A free, powerful, multi-purpose tool that helps you monitor system resources, debug software and detect malware. Brought to you by Winsider  · C · MIT · 2026-10
- [thanos-io/thanos](https://github.com/thanos-io/thanos) ★14.2k — Highly available Prometheus setup with long term storage capabilities. A CNCF Incubating project. · Go · Apache-2.0 · 2026-10
- [dastergon/awesome-sre](https://github.com/dastergon/awesome-sre) ★13.7k — A curated list of Site Reliability and Production Engineering resources. · CC0-1.0 · 2025-08
- [TwiN/gatus](https://github.com/TwiN/gatus) ★12.3k — Automated developer-oriented status page with alerting and incident support · Go · Apache-2.0 · 2026-10
- [grafana/pyroscope](https://github.com/grafana/pyroscope) ★11.7k — Continuous Profiling Platform. Debug performance issues down to a single line of code · Go · AGPL-3.0 · 2026-10
- [giampaolo/psutil](https://github.com/giampaolo/psutil) ★11.3k — Cross-platform lib for process and system monitoring in Python · Python · BSD-3-Clause · 2026-10
- [SigmaHQ/sigma](https://github.com/SigmaHQ/sigma) ★11.3k — Main Sigma Rule Repository · Python · NOASSERTION · 2026-10
- [Syllo/nvtop](https://github.com/Syllo/nvtop) ★11.1k — GPU & Accelerator process monitoring for AMD, Apple, Huawei, Intel, NVIDIA and Qualcomm · C · NOASSERTION · 2026-10
- [tariqbuilds/linux-dash](https://github.com/tariqbuilds/linux-dash) ★10.6k — A beautiful web dashboard for Linux · JavaScript · MIT · 2024-04

### PKM / note-taking (29)

- [foambubble/foam](https://github.com/foambubble/foam) ★17.4k — A personal knowledge management and sharing system for VSCode · TypeScript · NOASSERTION · 2026-10
- [dendronhq/dendron](https://github.com/dendronhq/dendron) ★7.5k — The personal knowledge management (PKM) tool that grows as you do! · TypeScript · Apache-2.0 · 2025-11
- [org-roam/org-roam](https://github.com/org-roam/org-roam) ★6.0k — Rudimentary Roam replica with Org-mode · Emacs Lisp · GPL-3.0 · 2026-04
- [pbek/QOwnNotes](https://github.com/pbek/QOwnNotes) ★5.9k — QOwnNotes is a plain-text file notepad and todo-list manager with Markdown support and Nextcloud / ownCloud integration. · C++ · GPL-2.0 · 2026-10
- [inkeep/open-knowledge](https://github.com/inkeep/open-knowledge) ★4.6k — Beautiful, AI-native markdown IDE and LLM wiki · TypeScript · GPL-3.0 · 2026-10
- [revezone/revezone](https://github.com/revezone/revezone) ★2.7k — A lightweight local-first graphic-centric  productivity tool to build your second brain. Supporting Excalidraw/Tldraw whiteboard and notion- · TypeScript · AGPL-3.0 · 2024-01
- [oldwinter/knowledge-garden](https://github.com/oldwinter/knowledge-garden) ★2.5k — 我的第二大脑 second brain，我的数字花园 digital garden，用obsidian双链笔记软件写作而成 · TypeScript · MIT · 2026-09
- [org-roam/org-roam-ui](https://github.com/org-roam/org-roam-ui) ★2.3k — A graphical frontend for exploring your org-roam Zettelkasten · TypeScript · GPL-3.0 · 2026-01
- [blacksmithgu/datacore](https://github.com/blacksmithgu/datacore) ★2.2k — Work-in-progress successor to Dataview with a focus on UX and speed. · TypeScript · MIT · 2026-06
- [nhaouari/obsidian-textgenerator-plugin](https://github.com/nhaouari/obsidian-textgenerator-plugin) ★2.0k — Text Generator is a versatile plugin for Obsidian that allows you to generate text content using various AI providers, including OpenAI, Ant · TypeScript · MIT · 2026-08
- [karlicoss/promnesia](https://github.com/karlicoss/promnesia) ★1.9k — Another piece of your extended mind · Python · MIT · 2026-09
- [ballred/obsidian-claude-pkm](https://github.com/ballred/obsidian-claude-pkm) ★1.9k — A complete starter kit for an Obsidian + Claude Code personal knowledge management system. · Shell · MIT · 2026-02
- [tehtbl/awesome-note-taking](https://github.com/tehtbl/awesome-note-taking) ★995 — A curated list of 100+ awesome note-taking apps, PKM tools & knowledge management software — open source and proprietary. Updated regularly. · CC0-1.0 · 2026-04
- [AgriciDaniel/compass](https://github.com/AgriciDaniel/compass) ★975 — Compass: run your whole life out of Obsidian. Daily questions, quarterly retreats, planning, habits, tasks, writing, and an AI assistant in  · JavaScript · MIT · 2026-09
- [TuanManhCao/digital-garden](https://github.com/TuanManhCao/digital-garden) ★816 — Free Obisidian Publish alternative, for publishing your digital garden. · JavaScript · MIT · 2023-12
- [InlitX/Obsidian-Dashboard-Gallery](https://github.com/InlitX/Obsidian-Dashboard-Gallery) ★796 — Beautiful, ready-to-use dashboard templates for Obsidian PKM✨ · MIT · 2026-10
- [memex-lab/memex](https://github.com/memex-lab/memex) ★790 — Open-source, local-first AI journal app for iOS and Android. Capture text, photos, and voice — AI agents organize them into timeline cards a · Dart · GPL-3.0 · 2026-10
- [ppeetteerrs/obsidian-zola](https://github.com/ppeetteerrs/obsidian-zola) ★777 — A no-brainer solution to turning your Obsidian PKM into a Zola site. · SCSS · MIT · 2023-12
- [dotpm/obsidian-pm](https://github.com/dotpm/obsidian-pm) ★748 — Project management inside Obsidian. Table, Gantt and Kanban over plain Markdown notes, with a local API for agents and scripts. · TypeScript · MIT · 2026-10
- [jason-effi-lab/karpathy-llm-wiki-vault](https://github.com/jason-effi-lab/karpathy-llm-wiki-vault) ★725 — 基于 Karpathy LLM Wiki 理念构建的 SKILL 和 Obsidian 知识库，将碎片信息整理为结构化、互联的知识网络。 · NOASSERTION · 2026-04
- [swarmclawai/swarmvault](https://github.com/swarmclawai/swarmvault) ★719 — The local-first LLM Wiki: open-source knowledge graph builder, RAG knowledge base, and agent memory store. Built on Andrej Karpathy's patter · TypeScript · MIT · 2026-06
- [lumen-notes/lumen](https://github.com/lumen-notes/lumen) ★718 — A free, open-source note-taking app that syncs with markdown files in your GitHub repository · TypeScript · MIT · 2026-02
- [jaredrhod/ai-memory-vault](https://github.com/jaredrhod/ai-memory-vault) ★702 — Give your AI a real, persistent memory. The open-source system plus templates that turn an Obsidian vault into your AI's working memory. No  · CC-BY-SA-4.0 · 2026-08
- [cyanheads/obsidian-mcp-server](https://github.com/cyanheads/obsidian-mcp-server) ★695 — Read, write, search, and surgically edit Obsidian vault notes, tags, and frontmatter via MCP. STDIO or Streamable HTTP. · TypeScript · Apache-2.0 · 2026-10
- [3xpyth0n/ideon](https://github.com/3xpyth0n/ideon) ★650 — Your project is scattered across too many tools. Map the chaos on an infinite canvas where notes, files, TO-DOs (and more!) finally live tog · TypeScript · AGPL-3.0 · 2026-10
- [chenxiachan/thoughtdag](https://github.com/chenxiachan/thoughtdag) ★632 — Your thinking deserves a map: an infinite canvas where LLM conversations grow into an editable thought graph. Wires are the context. · TypeScript · MIT · 2026-10
- [zosmaai/pi-llm-wiki](https://github.com/zosmaai/pi-llm-wiki) ★612 — Self-maintaining, Obsidian-compatible knowledge base for pi — turn raw sources into an interlinked wiki that compounds. Native Open Knowledg · TypeScript · MIT · 2026-10
- [suchnsuch/Tangent](https://github.com/suchnsuch/Tangent) ★576 — The Tangent monorepo. · TypeScript · Apache-2.0 · 2026-10
- [davidmyersdev/octo](https://github.com/davidmyersdev/octo) ★514 — A local-first knowledge management app · Vue · MPL-2.0 · 2025-08

### RPA / automation (30)

- [NaiboWang/EasySpider](https://github.com/NaiboWang/EasySpider) ★44.7k — A visual no-code/code-free web crawler/spider易采集：一个可视化浏览器自动化测试/数据采集/网页爬虫软件，可以无代码图形化的设计和执行爬虫任务。别名：ServiceWrapper面向Web应用的智能化服务封装系统。 · JavaScript · AGPL-3.0 · 2026-10
- [robotframework/robotframework](https://github.com/robotframework/robotframework) ★11.9k — Generic automation framework for acceptance testing and RPA · Python · Apache-2.0 · 2026-10
- [go-vgo/robotgo](https://github.com/go-vgo/robotgo) ★10.9k — RobotGo, Go Native cross-platform RPA, GUI automation, Auto test and Computer use  @vcaesar · Go · Apache-2.0 · 2026-10
- [iflytek/astron-agent](https://github.com/iflytek/astron-agent) ★8.9k — Enterprise-grade, commercial-friendly agentic workflow platform for building next-generation SuperAgents. · Java · Apache-2.0 · 2026-10
- [TeamWiseFlow/xiaobei](https://github.com/TeamWiseFlow/xiaobei) ★8.6k — 为OPC/中小微企业量身打造的自媒体获客智能体 · Python · NOASSERTION · 2026-10
- [cluic/wxauto](https://github.com/cluic/wxauto) ★7.4k — Windows版本微信客户端（非网页版）自动化，可实现简单的发送、接收微信消息，简单微信机器人 · Python · Apache-2.0 · 2026-04
- [aisingapore/TagUI](https://github.com/aisingapore/TagUI) ★6.3k — Free RPA tool by AI Singapore · JavaScript · Apache-2.0 · 2026-09
- [tebelorg/RPA-Python](https://github.com/tebelorg/RPA-Python) ★5.5k — Python package for doing RPA · Python · Apache-2.0 · 2026-07
- [iflytek/astron-rpa](https://github.com/iflytek/astron-rpa) ★5.3k — Agent-ready RPA suite with out-of-the-box automation tools. Built for individuals and enterprises. · Python · Apache-2.0 · 2026-10
- [Integuru-AI/Integuru](https://github.com/Integuru-AI/Integuru) ★4.8k — The first AI agent that builds permissionless integrations through reverse engineering platforms' internal APIs. · Python · AGPL-3.0 · 2026-06
- [magnitudedev/browser-agent](https://github.com/magnitudedev/browser-agent) ★4.1k — Open-source, vision-first browser agent · TypeScript · Apache-2.0 · 2026-02
- [xlang-ai/OSWorld](https://github.com/xlang-ai/OSWorld) ★3.2k — [NeurIPS 2024] OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in Real Computer Environments · Python · Apache-2.0 · 2026-09
- [automagica/automagica](https://github.com/automagica/automagica) ★3.1k — AI-powered Smart Robotic Process Automation 🤖 · Python · NOASSERTION · 2020-10
- [open-rpa/openrpa](https://github.com/open-rpa/openrpa) ★3.1k — Free Open Source Enterprise Grade RPA · C# · MPL-2.0 · 2026-04
- [geekgeekrun/geekgeekrun](https://github.com/geekgeekrun/geekgeekrun) ★2.7k — 牛人快跑 - GeekGeekRun，求职找工作自动化工具，基于 Puppeteer、Electron。界面友好，简单易用！开源，免费！快速海投、自动开聊、已读不回提醒、职位信息抓取、不合适职位标记、僵尸职位清理；让你即刻变身成为一台冇得感情的求职机器🤖，找工作不内耗。宝宝不用动 · Vue · NOASSERTION · 2026-07
- [Pulover/PuloversMacroCreator](https://github.com/Pulover/PuloversMacroCreator) ★2.0k — Automation Utility - Recorder & Script Generator · AutoHotkey · NOASSERTION · 2022-07
- [robocorp/rpaframework](https://github.com/robocorp/rpaframework) ★1.6k — Collection of open-source libraries and tools for Robotic Process Automation (RPA), designed to be used with both Robot Framework and Python · Python · Apache-2.0 · 2026-10
- [tstanislawek/awesome-document-understanding](https://github.com/tstanislawek/awesome-document-understanding) ★1.5k — A curated list of resources for Document Understanding (DU) topic · NOASSERTION · 2023-06
- [xlrpa/FlowBot](https://github.com/xlrpa/FlowBot) ★1.4k — 微信，企微，企微机器人，微信机器人，workbot，worktool，wetool，RPA，协议，vbot，逆向，hook，安全稳定零封号的RPA机器人，支持通过API控制企业微信来实现聚合聊天、自动回复、群发消息、自动通过好友、定时发布朋友圈等 · Java · NOASSERTION · 2026-10
- [saucepleez/taskt](https://github.com/saucepleez/taskt) ★1.4k — taskt (pronounced 'tasked' and formely sharpRPA) is free and open-source robotic process automation (rpa) built in C# powered by the .NET Fr · C# · NOASSERTION · 2025-07
- [test-zeus-ai/testzeus-hercules](https://github.com/test-zeus-ai/testzeus-hercules) ★1.2k — Hercules is the world’s first open-source testing agent, enabling UI, API, Security, Accessibility, and Visual validations – all without cod · Python · AGPL-3.0 · 2026-10
- [needleworm/bhban_rpa](https://github.com/needleworm/bhban_rpa) ★1.2k — <6개월 치 업무를 하루 만에 끝내는 업무 자동화(생능출판사, 2020)>의 예제 코드입니다. 파이썬을 한 번도 배워본 적 없는 분들을 위한 예제이며, 엑셀부터 디자인, 매크로, 크롤링까지 업무 자동화와 관련된 다양한 분야 예제가 제공됩니다. · Python · NOASSERTION · 2026-08
- [cashew-labs/libretto](https://github.com/cashew-labs/libretto) ★904 — The AI toolkit for building reliable browser automations · TypeScript · MIT · 2026-08
- [claw-codes/wx4py](https://github.com/claw-codes/wx4py) ★771 — 微信4.x自动化机器人：群聊机器人、批量群发（支持文件）、批量设置群公告、聊天记录导出、群管理 | 5分钟上手 · Python · AGPL-3.0 · 2026-04
- [Lattyware/unrpa](https://github.com/Lattyware/unrpa) ★767 — A program to extract files from the RPA archive format. · Python · GPL-3.0 · 2022-06
- [sheying2013/OpenBrowser](https://github.com/sheying2013/OpenBrowser) ★760 — 本地指纹浏览器 · 多环境隔离 · 代理 / 指纹 / 同步 / RPA · JavaScript · MIT · 2026-10
- [vignshwarar/AI-Employe](https://github.com/vignshwarar/AI-Employe) ★583 — Create browser automation as if you were teaching a human using GPT-4 Vision. · TypeScript · AGPL-3.0 · 2024-02
- [askui/python-sdk](https://github.com/askui/python-sdk) ★556 — Enable AI to control your desktop, mobile and HMI devices · Python · MIT · 2026-10
- [microsoft/OCR-Form-Tools](https://github.com/microsoft/OCR-Form-Tools) ★540 — A set of tools to use in Microsoft Azure Form Recognizer and OCR services. · TypeScript · MIT · 2025-07
- [Jici-Zeroten/XiaoFeiShu](https://github.com/Jici-Zeroten/XiaoFeiShu) ★530 — 小飞薯RPA是一款紧贴小红书优质用户规则开发的自动化运营软件 · NOASSERTION · 2026-08

### Developer tools (30)

- [puppeteer/puppeteer](https://github.com/puppeteer/puppeteer) ★95.7k — JavaScript API for Chrome and Firefox · TypeScript · Apache-2.0 · 2026-10
- [hoppscotch/hoppscotch](https://github.com/hoppscotch/hoppscotch) ★80.6k — Open-Source API Development Ecosystem • https://hoppscotch.io • Offline, On-Prem & Cloud • Web, Desktop & CLI • Open-Source Alternative to P · TypeScript · MIT · 2026-10
- [localstack/localstack](https://github.com/localstack/localstack) ★65.1k — 💻 A fully functional local AWS cloud stack. Develop and test your cloud & Serverless apps offline · Python · NOASSERTION · 2026-03
- [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd) ★57.4k — A skill to stop your coding agent from burying the answer. ADHD-friendly output. · Python · MIT · 2026-10
- [GitHubDaily/GitHubDaily](https://github.com/GitHubDaily/GitHubDaily) ★48.2k — 坚持分享 GitHub 上高质量、有趣实用的开源技术教程、开发者工具、编程网站、技术资讯。A list cool, interesting projects of GitHub. · NOASSERTION · 2025-12
- [usebruno/bruno](https://github.com/usebruno/bruno) ★47.7k — Opensource IDE For Exploring and Testing API's (lightweight alternative to Postman/Insomnia) · JavaScript · MIT · 2026-10
- [files-community/Files](https://github.com/files-community/Files) ★46.0k — A modern file manager that helps users organize their files and folders. · C# · MIT · 2026-10
- [streamlit/streamlit](https://github.com/streamlit/streamlit) ★46.0k — Streamlit — A faster way to build and share data apps. · Python · Apache-2.0 · 2026-10
- [appsmithorg/appsmith](https://github.com/appsmithorg/appsmith) ★41.1k — Platform to build admin panels, internal tools, and dashboards. Integrates with 25+ databases and any API. · TypeScript · Apache-2.0 · 2026-10
- [CorentinTh/it-tools](https://github.com/CorentinTh/it-tools) ★40.9k — Collection of handy online tools for developers, with great UX. · Vue · GPL-3.0 · 2026-10
- [freeCodeCamp/devdocs](https://github.com/freeCodeCamp/devdocs) ★39.6k — API Documentation Browser · Ruby · MPL-2.0 · 2026-10
- [lapce/lapce](https://github.com/lapce/lapce) ★38.9k — Lightning-fast and Powerful Code Editor written in Rust · Rust · Apache-2.0 · 2026-10
- [refinedev/refine](https://github.com/refinedev/refine) ★35.9k — A React Framework for building  internal tools, admin panels, dashboards & B2B apps with unmatched flexibility. · TypeScript · MIT · 2026-09
- [TabbyML/tabby](https://github.com/TabbyML/tabby) ★33.9k — Self-hosted AI coding assistant · Rust · NOASSERTION · 2026-06
- [Pythagora-io/gpt-pilot](https://github.com/Pythagora-io/gpt-pilot) ★33.7k — The first real AI developer · Python · NOASSERTION · 2026-06
- [surrealdb/surrealdb](https://github.com/surrealdb/surrealdb) ★33.2k — A scalable, distributed, collaborative, document-graph database, for the realtime web · Rust · NOASSERTION · 2026-10
- [GoogleChrome/lighthouse](https://github.com/GoogleChrome/lighthouse) ★30.9k — Automated auditing, performance metrics, and best practices for the web. · JavaScript · Apache-2.0 · 2026-10
- [reflex-dev/reflex](https://github.com/reflex-dev/reflex) ★29.0k — 🕸️ Web apps in pure Python 🐍 · Python · Apache-2.0 · 2026-10
- [voideditor/void](https://github.com/voideditor/void) ★28.8k · TypeScript · Apache-2.0 · 2026-06
- [d2lang/d2](https://github.com/d2lang/d2) ★25.6k — D2 is a modern diagram scripting language that turns text to diagrams. · Go · MPL-2.0 · 2026-10
- [marimo-team/marimo](https://github.com/marimo-team/marimo) ★23.2k — A reactive notebook for Python — run reproducible experiments, query with SQL, execute as a script, deploy as an app, and version with git.  · Python · Apache-2.0 · 2026-10
- [liriliri/eruda](https://github.com/liriliri/eruda) ★21.2k — Console for mobile browsers · JavaScript · MIT · 2025-08
- [getpaseo/paseo](https://github.com/getpaseo/paseo) ★21.1k — Orchestrate multiple coding agents from desktop and mobile · TypeScript · NOASSERTION · 2026-10
- [Avaiga/taipy](https://github.com/Avaiga/taipy) ★19.4k — Turns Data and AI algorithms into production-ready web applications in no time. · Python · Apache-2.0 · 2026-08
- [iii-hq/iii](https://github.com/iii-hq/iii) ★18.8k — Effortlessly compose, extend, and observe every service in real-time for the first time ever. · Rust · NOASSERTION · 2026-10
- [ahmedkhaleel2004/gitdiagram](https://github.com/ahmedkhaleel2004/gitdiagram) ★18.3k — Visualize any GitHub codebase: free interactive architecture diagrams and one-minute explainer videos. Replace 'hub' with 'diagram' in any G · TypeScript · MIT · 2026-10
- [source-foundry/Hack](https://github.com/source-foundry/Hack) ★17.4k — A typeface designed for source code · Shell · NOASSERTION · 2022-11
- [Automattic/harper](https://github.com/Automattic/harper) ★16.5k — Offline, privacy-first grammar checker. Fast, open-source, Rust-powered · Rust · Apache-2.0 · 2026-10
- [public-api-lists/public-api-lists](https://github.com/public-api-lists/public-api-lists) ★16.1k — A curated list of free public APIs — searchable, community-maintained, with a free JSON API. · MIT · 2026-09
- [treeverse/dvc](https://github.com/treeverse/dvc) ★15.9k — 🦉 Data Versioning and ML Experiments · Python · Apache-2.0 · 2026-10

### Chromium-based browsers (30)

- [brave/brave-browser](https://github.com/brave/brave-browser) ★23.9k — Brave browser for Android, iOS, Linux, macOS, Windows. · MPL-2.0 · 2026-10
- [FlareSolverr/FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) ★15.9k — Proxy server to bypass Cloudflare protection · Python · MIT · 2026-09
- [microsoft/playwright-python](https://github.com/microsoft/playwright-python) ★15.0k — Python version of the Playwright testing and automation library. · Python · Apache-2.0 · 2026-10
- [ajayyy/SponsorBlock](https://github.com/ajayyy/SponsorBlock) ★13.9k — Skip YouTube video sponsors (browser extension) · TypeScript · GPL-3.0 · 2026-10
- [gotenberg/gotenberg](https://github.com/gotenberg/gotenberg) ★13.3k — A developer-friendly API for converting many document formats into PDF files, and more! · Go · MIT · 2026-10
- [RelaxedJS/ReLaXed](https://github.com/RelaxedJS/ReLaXed) ★11.8k — Create PDF documents using web technologies · JavaScript · ISC · 2025-09
- [brookhong/Surfingkeys](https://github.com/brookhong/Surfingkeys) ★6.2k — Map your keys for web surfing, expand your browser with javascript and keyboard. · JavaScript · MIT · 2026-10
- [michenriksen/aquatone](https://github.com/michenriksen/aquatone) ★6.0k — A Tool for Domain Flyovers · Go · MIT · 2022-05
- [antiwork/shortest](https://github.com/antiwork/shortest) ★5.7k — QA via natural language AI tests · TypeScript · MIT · 2026-08
- [yujiosaka/headless-chrome-crawler](https://github.com/yujiosaka/headless-chrome-crawler) ★5.6k — Distributed crawler powered by Headless Chrome · JavaScript · MIT · 2023-04
- [hardkoded/puppeteer-sharp](https://github.com/hardkoded/puppeteer-sharp) ★3.9k — Headless Chrome .NET API · C# · MIT · 2026-10
- [XuanchenLin/NanUI](https://github.com/XuanchenLin/NanUI) ★3.8k — NanUI is an open source .NET project for developers who want to create Windows desktop applications with HTML, CSS and JavaScript. · C# · MIT · 2025-11
- [alexflint/gallium](https://github.com/alexflint/gallium) ★3.6k — Build desktop applications in Go and HTML. · Go · MIT · 2025-01
- [browserbase/mcp-server-browserbase](https://github.com/browserbase/mcp-server-browserbase) ★3.4k — Allow LLMs to control a browser with Browserbase and Stagehand · TypeScript · Apache-2.0 · 2026-07
- [microsoft/playwright-dotnet](https://github.com/microsoft/playwright-dotnet) ★3.0k — .NET version of the Playwright testing and automation library. · C# · MIT · 2026-10
- [chromelyapps/Chromely](https://github.com/chromelyapps/Chromely) ★3.0k — Build Cross Platform HTML Desktop Apps on .NET using native GUI, HTML5, JavaScript, CSS, Owin, AspNetCore (MVC, RazorPages, Blazor) · C# · MIT · 2023-01
- [cztomczak/phpdesktop](https://github.com/cztomczak/phpdesktop) ★2.9k — Develop desktop GUI applications using PHP, HTML5, JavaScript and SQLite · NOASSERTION · 2026-07
- [wexond/browser-base](https://github.com/wexond/browser-base) ★2.7k — Modern and feature-rich web browser base based on Electron · TypeScript · NOASSERTION · 2023-06
- [esbenp/pdf-bot](https://github.com/esbenp/pdf-bot) ★2.6k — 🤖 A Node queue API for generating PDFs using headless Chrome. Comes with a CLI, S3 storage and webhooks for notifying subscribers about gene · JavaScript · MIT · 2024-03
- [anticensority/runet-censorship-bypass](https://github.com/anticensority/runet-censorship-bypass) ★2.4k — Web-extension for bypassing censorship in Russia · JavaScript · GPL-3.0 · 2026-08
- [dnakov/little-rat](https://github.com/dnakov/little-rat) ★2.3k — 🐀 Small chrome extension to monitor (and optionally block) other extensions' network calls · JavaScript · MIT · 2025-03
- [SimonBrazell/privacy-redirect](https://github.com/SimonBrazell/privacy-redirect) ★2.2k — A simple web extension that redirects Twitter, YouTube, Instagram & Google Maps requests to privacy friendly alternatives. · JavaScript · GPL-3.0 · 2023-09
- [rubycdp/ferrum](https://github.com/rubycdp/ferrum) ★2.1k — Headless Chrome Ruby API · Ruby · MIT · 2026-10
- [reactopt/reactopt](https://github.com/reactopt/reactopt) ★2.0k — A CLI React performance optimization tool that identifies potential unnecessary re-rendering · JavaScript · NOASSERTION · 2018-03
- [coder-hxl/x-crawl](https://github.com/coder-hxl/x-crawl) ★1.9k — Flexible Node.js crawler library · TypeScript · MIT · 2026-10
- [ShunCai/QZoneExport](https://github.com/ShunCai/QZoneExport) ★1.9k — QQ空间导出助手，用于备份QQ空间的说说、日志、私密日记、相册、视频、留言板、QQ好友、收藏夹、分享、最近访客为文件，便于迁移与保存 · TypeScript · Apache-2.0 · 2026-10
- [Jelmerro/Vieb](https://github.com/Jelmerro/Vieb) ★1.6k — Vim Inspired Electron Browser - Vim bindings for the web by design · JavaScript · GPL-3.0 · 2026-08
- [TraceMachina/nativelink](https://github.com/TraceMachina/nativelink) ★1.6k — NativeLink is a Nix-powered, open source, high-performance build cache and remote execution server, compatible with Bazel, Soong, Pants, Buc · Rust · NOASSERTION · 2026-10
- [zohaibbashir/Google-Maps-Scrapper](https://github.com/zohaibbashir/Google-Maps-Scrapper) ★1.6k — This code is used to perform web scraping and data extraction from Google Maps. It is particularly designed for obtaining information about  · Python · MIT · 2026-05
- [CTF-MissFeng/bayonet](https://github.com/CTF-MissFeng/bayonet) ★1.5k — bayonet是一款src资产管理系统，从子域名、端口服务、漏洞、爬虫等一体化的资产管理系统 · Python · NOASSERTION · 2022-11

### Web browsers (topic) (27)

- [atlas-engineer/nyxt](https://github.com/atlas-engineer/nyxt) ★11.0k — Nyxt - the hacker's browser. · Common Lisp · NOASSERTION · 2026-02
- [BrowserWorks/waterfox](https://github.com/BrowserWorks/waterfox) ★6.4k — The official Waterfox 💧 source code repository · JavaScript · NOASSERTION · 2026-10
- [BrowserBox/BrowserBox](https://github.com/BrowserBox/BrowserBox) ★3.9k — 💚🇺🇸🗽Secure remote browsing anywhere, any way you like it. · Shell · NOASSERTION · 2026-10
- [da2x/EdgeDeflector](https://github.com/da2x/EdgeDeflector) ★2.9k — A tiny helper application to force Windows 10 to use your preferred web browser instead of ignoring the setting to promote Microsoft Edge. O · NSIS · MIT · 2022-03
- [OnionBrowser/OnionBrowser](https://github.com/OnionBrowser/OnionBrowser) ★2.7k — An open-source, privacy-enhancing web browser for iOS, utilizing the Tor anonymity network · Swift · NOASSERTION · 2026-10
- [luakit/luakit](https://github.com/luakit/luakit) ★2.3k — Fast, small, webkit based browser framework extensible by Lua. · Lua · GPL-3.0 · 2026-06
- [minh-ton/reynard-browser](https://github.com/minh-ton/reynard-browser) ★1.8k — An experimental Gecko-based web browser for iOS 13+. · Swift · GPL-3.0 · 2026-10
- [LadybirdBrowser/ancient-history](https://github.com/LadybirdBrowser/ancient-history) ★1.6k — The Ladybird web browser · C++ · BSD-2-Clause · 2022-12
- [Alex313031/Mercury](https://github.com/Alex313031/Mercury) ★1.5k — Firefox fork with compiler optimizations and patches from Librewolf, Waterfox, and GNU IceCat. · JavaScript · MPL-2.0 · 2026-08
- [danfragoso/thdwb](https://github.com/danfragoso/thdwb) ★1.1k — 🌭 The hotdog web browser and browser engine 🌭 · Go · MIT · 2023-03
- [FaFre/WebLibre](https://github.com/FaFre/WebLibre) ★1.0k — A libre Android browser built from scratch on Gecko. Privacy by default, powerful tab containers, and a local-first search engine. · Dart · AGPL-3.0 · 2026-10
- [alexch33/super-video-downloader](https://github.com/alexch33/super-video-downloader) ★963 — Video & Audio downloader for Android with web browser and player. M3U8 and MPD supported, live stream supported, using youtube-dlp and custo · Kotlin · GPL-3.0 · 2026-09
- [goxr3plus/XR3Player](https://github.com/goxr3plus/XR3Player) ★771 — 🎧 🎼  The MOST ADVANCED JavaFX Media Player · Java · LGPL-3.0 · 2025-04
- [pulse-browser/browser](https://github.com/pulse-browser/browser) ★753 — Pulse Browser: An experimental firefox fork · JavaScript · MPL-2.0 · 2024-05
- [yessGlory17/programmer-browser](https://github.com/yessGlory17/programmer-browser) ★596 — A fast-searching and space-saving browser specially designed for programmers. · TypeScript · MIT · 2023-06
- [b0o/surfingkeys-conf](https://github.com/b0o/surfingkeys-conf) ★474 — 🏄 A SurfingKeys config which adds 180+ key mappings & 50+ search engines · JavaScript · MIT · 2026-05
- [Alex313031/Thorium-Win-AVX2](https://github.com/Alex313031/Thorium-Win-AVX2) ★423 — Repo to serve AVX2 Windows builds of Thorium. https://github.com/Alex313031/Thorium/ · Batchfile · BSD-3-Clause · 2024-01
- [psilva261/mycel](https://github.com/psilva261/mycel) ★412 — Rudimentary web browser written in Golang · Go · BSD-3-Clause · 2026-01
- [goastian/midori-desktop](https://github.com/goastian/midori-desktop) ★407 — Midori for Windows, Linux & Mac, web browser focused on lightness and privacy. · JavaScript · MPL-2.0 · 2026-10
- [BrowserWorks/waterfox-android](https://github.com/BrowserWorks/waterfox-android) ★382 — Waterfox for Android · JavaScript · NOASSERTION · 2026-09
- [Alex313031/thorium-legacy](https://github.com/Alex313031/thorium-legacy) ★358 — Repo for Windows XP/Vista & 7/8/8.1 Thorium Builds · C++ · BSD-3-Clause · 2024-11
- [mplsllc/macsurf](https://github.com/mplsllc/macsurf) ★284 — A modern web browser for Classic Mac OS 9 PowerPC. Real CSS3, ES5 JavaScript, native HTTPS. Built with CodeWarrior on the Carbon API. · C · NOASSERTION · 2026-10
- [jcs/endless](https://github.com/jcs/endless) ★270 — iOS web browser with a focus on security and privacy · Objective-C · NOASSERTION · 2021-11
- [Picovoice/web-voice-processor](https://github.com/Picovoice/web-voice-processor) ★249 — A library for real-time voice processing in web browsers · TypeScript · Apache-2.0 · 2026-10
- [HeyPuter/browser.js](https://github.com/HeyPuter/browser.js) ★248 — Highly Configurable Browser Environment for the Web · TypeScript · AGPL-3.0 · 2026-10
- [phibrowser/phibrowser-mac](https://github.com/phibrowser/phibrowser-mac) ★236 — A modern browser for macOS. Agentic, local-first, native Swift, Chromium powered · Swift · Apache-2.0 · 2026-10
- [celenityy/Phoenix](https://github.com/celenityy/Phoenix) ★210 — Phoenix is a suite of configurations & advanced modifications for Mozilla Firefox, designed to put the user first - with a focus on privacy, · JavaScript · GPL-3.0 · 2026-10

### Userscript managers (30)

- [XIU2/UserScript](https://github.com/XIU2/UserScript) ★10.1k — 🐵 自用的一些乱七八糟 油猴脚本~ · JavaScript · GPL-3.0 · 2026-09
- [violentmonkey/violentmonkey](https://github.com/violentmonkey/violentmonkey) ★9.0k — Violentmonkey provides userscripts support for browsers. It works on browsers with WebExtensions support. · JavaScript · MIT · 2026-10
- [Tampermonkey/tampermonkey](https://github.com/Tampermonkey/tampermonkey) ★5.8k — Tampermonkey is the most popular userscript manager, with over 10 million users. It's available for Chrome, Microsoft Edge, Safari, Opera Ne · JavaScript · GPL-3.0 · 2025-03
- [scriptscat/scriptcat](https://github.com/scriptscat/scriptcat) ★5.6k — ScriptCat, a browser extension that can execute userscript; 脚本猫，一个可以执行用户脚本的浏览器扩展 · TypeScript · GPL-3.0 · 2026-10
- [quoid/userscripts](https://github.com/quoid/userscripts) ★4.8k — An open-source userscript manager for Safari · Swift · GPL-3.0 · 2026-10
- [hoothin/UserScripts](https://github.com/hoothin/UserScripts) ★4.3k — Greasemonkey scripts ( Pagetual / Picviewer CE+ / DownloadAllContent ) 油猴腳本集 ユーザースクリプト集 · JavaScript · NOASSERTION · 2026-10
- [ipcjs/oh-my-userscripts](https://github.com/ipcjs/oh-my-userscripts) ★4.1k — 我的油猴脚本仓库 · JavaScript · NOASSERTION · 2026-10
- [awesome-scripts/awesome-userscripts](https://github.com/awesome-scripts/awesome-userscripts) ★3.6k — 📖  A curated list of Awesome Userscripts. · JavaScript · NOASSERTION · 2026-10
- [0xCUB3/wBlock](https://github.com/0xCUB3/wBlock) ★3.1k — The next-generation ad blocker for Safari. Free and open source on macOS, iOS, iPadOS, and visionOS, with 750,000 rules, userscripts, userst · Swift · GPL-3.0 · 2026-10
- [YePpHa/YouTubeCenter](https://github.com/YePpHa/YouTubeCenter) ★2.9k — YouTube Center is a userscript designed to expand the functionality of YouTube. It includes the ability to download the video you're watchin · HTML · MIT · 2018-04
- [ChinaGodMan/UserScripts](https://github.com/ChinaGodMan/UserScripts) ★2.1k — 🐒一些修改自网络的油猴脚本 Some Tampermonkey scripts modified from the internet · JavaScript · NOASSERTION · 2026-10
- [lisonge/vite-plugin-monkey](https://github.com/lisonge/vite-plugin-monkey) ★2.1k — A vite plugin server and build your.user.js for userscript engine like Tampermonkey, Violentmonkey, Greasemonkey, ScriptCat · TypeScript · MIT · 2026-09
- [Mottie/GitHub-userscripts](https://github.com/Mottie/GitHub-userscripts) ★2.0k — Userscripts to add functionality to GitHub · JavaScript · MIT · 2024-07
- [jae-jae/Userscript-Plus](https://github.com/jae-jae/Userscript-Plus) ★1.9k — :monkey: Show current site all UserJS，The easier way to install UserJs for Tampermonkey. 显示当前网站的所有可用Tampermonkey脚本 · Vue · NOASSERTION · 2022-12
- [redphx/better-xcloud](https://github.com/redphx/better-xcloud) ★1.8k — Userscript to improve Xbox Cloud Gaming (xCloud) and Remote Play experiences on web browsers · TypeScript · MIT · 2026-10
- [F9y4ng/GreasyFork-Scripts](https://github.com/F9y4ng/GreasyFork-Scripts) ★1.5k — The open source code of this project is used for userscripts (油猴脚本) for desktop browsers, including Font Rendering (Customized) (字体渲染（自用脚本）- · JavaScript · GPL-3.0 · 2026-10
- [shenruisi/Stay](https://github.com/shenruisi/Stay) ★1.3k — Stay is a local userscript manager and an extension sample for Safari on iOS/iPadOS. · JavaScript · MPL-2.0 · 2024-06
- [Mapaler/PixivUserBatchDownload](https://github.com/Mapaler/PixivUserBatchDownload) ★1.2k — P站画师个人作品批量下载工具，UserScript + Aria2。可高度自定义重命名，发送到本地或远程(如路由器)下载。 · JavaScript · GPL-3.0 · 2025-07
- [xob0t/Google-Photos-Toolkit](https://github.com/xob0t/Google-Photos-Toolkit) ★1.1k — Userscript to filter, search, organize, or delete your Google Photos library · TypeScript · MIT · 2026-08
- [tiansh/yawf](https://github.com/tiansh/yawf) ★886 — 药方 Yet Another Weibo Filter 用户脚本，微博过滤和版面改造等 userscript, filter weibo and modify layout · JavaScript · NOASSERTION · 2026-02
- [mengzonefire/rapid-upload-userscript](https://github.com/mengzonefire/rapid-upload-userscript) ★868 — 秒传链接提取脚本, 使用typescript + webpack重构 · NOASSERTION · 2023-06
- [magicdawn/Bilibili-Gate](https://github.com/magicdawn/Bilibili-Gate) ★814 — [UserScript]  Bilibili 自定义首页 · TypeScript · MIT · 2026-10
- [murdos/musicbrainz-userscripts](https://github.com/murdos/musicbrainz-userscripts) ★756 — Collection of userscripts for MusicBrainz, by various authors · JavaScript · NOASSERTION · 2026-10
- [SukkaW/Make-Bilibili-Great-Than-Ever-Before](https://github.com/SukkaW/Make-Bilibili-Great-Than-Ever-Before) ★740 — A fork of the userscript "Make Bilibili Great Again", but with some experimental features · TypeScript · MIT · 2026-10
- [machsix/Super-preloader](https://github.com/machsix/Super-preloader) ★649 — Userscript to enable autopagerizing as well as preloading · JavaScript · GPL-3.0 · 2026-08
- [FugiTech/google-meet-grid-view](https://github.com/FugiTech/google-meet-grid-view) ★617 — Userscript to offer a grid-view layout in Google Meets · JavaScript · NOASSERTION · 2021-07
- [anghunk/UserScript](https://github.com/anghunk/UserScript) ★579 — 这是一个实用的油猴脚本（UserScript）集合仓库，包含了多个实用的浏览器增强脚本。这些脚本旨在提升网页浏览体验，增加网站功能，优化用户界面等。 · Vue · Apache-2.0 · 2026-09
- [nyxxbit/discord-quest-completer](https://github.com/nyxxbit/discord-quest-completer) ★556 — Completes Discord Quests without playing them. All five types, including achievement-in-activity, which is the reason it exists. Userscript  · TypeScript · MIT · 2026-09
- [ywzhaiqi/userscript](https://github.com/ywzhaiqi/userscript) ★551 — 本人原创或修改的 GM 脚本，包括小说阅读脚本等。 · JavaScript · NOASSERTION · 2026-10
- [indefined/UserScripts](https://github.com/indefined/UserScripts) ★541 — 基于Chrome下的Tampermonkey写的一些个人用户脚本 · JavaScript · MIT · 2026-07

### Web archiving (30)

- [CodingTrain/website-archive](https://github.com/CodingTrain/website-archive) ★5.7k — Archive of the Coding Train website (first version) · JavaScript · MIT · 2022-07
- [devanshbatham/ParamSpider](https://github.com/devanshbatham/ParamSpider) ★3.2k — Mining URLs from dark corners of Web Archives for bug hunting/fuzzing/further probing · Python · MIT · 2026-03
- [iipc/awesome-web-archiving](https://github.com/iipc/awesome-web-archiving) ★2.7k — An Awesome List for getting started with web archiving · CC0-1.0 · 2026-09
- [webrecorder/pywb](https://github.com/webrecorder/pywb) ★1.7k — Core Python Web Archiving Toolkit for replay and recording of web archives · Python · GPL-3.0 · 2026-10
- [webrecorder/browsertrix-crawler](https://github.com/webrecorder/browsertrix-crawler) ★1.2k — Run a high-fidelity browser-based web archiving crawler in a single Docker container · TypeScript · AGPL-3.0 · 2026-10
- [webrecorder/replayweb.page](https://github.com/webrecorder/replayweb.page) ★997 — Serverless replay of web archives directly in the browser · TypeScript · AGPL-3.0 · 2026-09
- [Ray-D-Song/web-archive](https://github.com/Ray-D-Song/web-archive) ★931 — Selfhost web archiving and sharing service. · TypeScript · GPL-3.0 · 2026-04
- [hamsterbase/hamsterbase](https://github.com/hamsterbase/hamsterbase) ★675 — self-hosted, local-first web archive application. · TypeScript · NOASSERTION · 2026-05
- [webrecorder/browsertrix](https://github.com/webrecorder/browsertrix) ★484 — Browsertrix is the hosted, high-fidelity, browser-based crawling service from Webrecorder designed to make web archiving easier and more acc · TypeScript · AGPL-3.0 · 2026-10
- [webrecorder/warcio](https://github.com/webrecorder/warcio) ★480 — Streaming WARC/ARC library for fast web archive IO · Python · Apache-2.0 · 2026-06
- [oduwsdl/archivenow](https://github.com/oduwsdl/archivenow) ★436 — A Tool To Push Web Resources Into Web Archives · Python · MIT · 2024-01
- [machawk1/wail](https://github.com/machawk1/wail) ★401 — :whale2: Web Archiving Integration Layer: One-Click User Instigated Preservation · Roff · MIT · 2026-06
- [robrohan/WebArchiveExtractor](https://github.com/robrohan/WebArchiveExtractor) ★346 — Mac OS X utility to un-archive .webarchive files (like when saving from Safari) · Objective-C · NOASSERTION · 2026-03
- [charlesroelli/org-board](https://github.com/charlesroelli/org-board) ★287 — Org mode's web archiver. · Emacs Lisp · GPL-3.0 · 2023-04
- [harvard-lil/warc-gpt](https://github.com/harvard-lil/warc-gpt) ★281 — WARC + AI - Experimental Retrieval Augmented Generation Pipeline for Web Archive Collections. · Python · MIT · 2025-02
- [carbon-design-system/carbon-website-archive](https://github.com/carbon-design-system/carbon-website-archive) ★237 — The old website for the Carbon Design System. This repo is archived. · JavaScript · NOASSERTION · 2024-02
- [harvard-lil/scoop](https://github.com/harvard-lil/scoop) ★215 — 🍨 High-fidelity, browser-based, single-page web archiving library and CLI for witnessing the web. · JavaScript · MIT · 2026-09
- [PKHarsimran/website-downloader](https://github.com/PKHarsimran/website-downloader) ★214 — Website-downloader is a powerful and versatile Python script designed to download entire websites along with all their assets. This tool all · Python · MIT · 2026-07
- [ikreymer/webarchiveplayer](https://github.com/ikreymer/webarchiveplayer) ★203 — NOTE: This project is no longer being actively developed.. Check out https://replayweb.page / https://github.com/webrecorder/replayweb.page  · Python · GPL-3.0 · 2025-01
- [karust/gogetcrawl](https://github.com/karust/gogetcrawl) ★186 — Extract web archive data using Wayback Machine and Common Crawl · Go · MIT · 2024-11
- [raphaelsalaja/pond](https://github.com/raphaelsalaja/pond) ★168 — Your personal web archiver. · TypeScript · MIT · 2026-10
- [chfoo/warcat](https://github.com/chfoo/warcat) ★167 — Tool and library for handling Web ARChive (WARC) files. · Python · GPL-3.0 · 2024-10
- [0xKayala/ParamSpider](https://github.com/0xKayala/ParamSpider) ★167 — Mining URLs from dark corners of Web Archives for bug hunting/fuzzing/further probing · Python · GPL-3.0 · 2025-03
- [singpolyma/mnemonicode](https://github.com/singpolyma/mnemonicode) ★167 — Fork of http://web.archive.org/web/20101031205747/http://www.tothink.com/mnemonic/ · C · MIT · 2023-02
- [helgeho/ArchiveSpark](https://github.com/helgeho/ArchiveSpark) ★163 — An Apache Spark framework for easy data processing, extraction as well as derivation for web archives and archival collections, developed at · Scala · MIT · 2025-10
- [lintool/warcbase](https://github.com/lintool/warcbase) ★162 — Warcbase is an open-source platform for managing analyzing web archives · Java · NOASSERTION · 2017-12
- [vegetableman/vandal](https://github.com/vegetableman/vandal) ★159 — Navigator for Web Archive · JavaScript · AGPL-3.0 · 2023-11
- [archivesunleashed/aut](https://github.com/archivesunleashed/aut) ★157 — The Archives Unleashed Toolkit is an open-source toolkit for analyzing web archives. · Scala · Apache-2.0 · 2026-09
- [D4RK-R4BB1T/Dark-Web-Archives](https://github.com/D4RK-R4BB1T/Dark-Web-Archives) ★152 · PHP · NOASSERTION · 2024-03
- [chatnoir-eu/chatnoir-resiliparse](https://github.com/chatnoir-eu/chatnoir-resiliparse) ★152 — A robust web archive analytics toolkit · Rust · Apache-2.0 · 2026-08

### RSS & feed readers (30)

- [RSSNext/Folo](https://github.com/RSSNext/Folo) ★39.1k — 🧡 Folo is the AI RSS Reader · TypeScript · AGPL-3.0 · 2026-10
- [FreshRSS/FreshRSS](https://github.com/FreshRSS/FreshRSS) ★16.3k — A free, self-hostable news aggregator… · PHP · AGPL-3.0 · 2026-10
- [Ranchero-Software/NetNewsWire](https://github.com/Ranchero-Software/NetNewsWire) ★10.5k — RSS reader for macOS and iOS. · Swift · MIT · 2026-10
- [samuelclay/NewsBlur](https://github.com/samuelclay/NewsBlur) ★7.7k — NewsBlur is a personal news reader that brings people together to talk about the world. A new sound of an old instrument. · HTML · MIT · 2026-10
- [ReadYouApp/ReadYou](https://github.com/ReadYouApp/ReadYou) ★7.6k — An Android RSS reader presented in Material You style. · Kotlin · GPL-3.0 · 2026-08
- [plainhub/plain-app](https://github.com/plainhub/plain-app) ★6.9k — 🔥 PlainApp is an open-source app that lets you securely manage your phone from a web browser. Access files, media, contacts, SMS, calls, and · Kotlin · AGPL-3.0 · 2026-10
- [weekend-project-space/top-rss-list](https://github.com/weekend-project-space/top-rss-list) ★6.7k — 订阅人数最多的rss源，中文优质rss源 · NOASSERTION · 2026-08
- [AboutRSS/ALL-about-RSS](https://github.com/AboutRSS/ALL-about-RSS) ★5.9k — A list of RSS related stuff: tools, services, communities and tutorials, etc. · Python · CC-BY-4.0 · 2026-09
- [stringer-rss/stringer](https://github.com/stringer-rss/stringer) ★4.1k — A self-hosted, anti-social RSS reader. · Ruby · MIT · 2026-10
- [Athou/commafeed](https://github.com/Athou/commafeed) ★3.6k — Google Reader inspired self-hosted personal RSS reader. · Java · Apache-2.0 · 2026-10
- [emacs-eaf/emacs-application-framework](https://github.com/emacs-eaf/emacs-application-framework) ★3.5k — EAF, an extensible framework that revolutionizes the graphical capabilities of Emacs · Python · GPL-3.0 · 2026-08
- [guanguans/favorite-link](https://github.com/guanguans/favorite-link) ★3.4k — ❤️ 每天收集喜欢的开源项目。 · PHP · GPL-3.0 · 2026-10
- [plenaryapp/awesome-rss-feeds](https://github.com/plenaryapp/awesome-rss-feeds) ★2.8k — Awesome RSS feeds - A curated list of RSS feeds (and OPML files) used in Recommended Feeds and local news sections of Plenary - an RSS reade · Shell · CC0-1.0 · 2026-10
- [martinrotter/rssguard](https://github.com/martinrotter/rssguard) ★2.8k — Feed reader (podcast player, basic XMPP client and also Gemini protocol client) which supports RSS/ATOM/JSON and many web-based feed service · C++ · GPL-3.0 · 2026-10
- [DevXDojo/MrRSS](https://github.com/DevXDojo/MrRSS) ★2.6k — A modern, cross-platform, and free AI RSS reader. 一个现代化、跨平台且免费的 AI RSS 阅读器. · Go · GPL-3.0 · 2026-10
- [HenryQW/Awesome-TTRSS](https://github.com/HenryQW/Awesome-TTRSS) ★2.6k — 🐋 Awesome TTRSS, a powerful Dockerised all-in-one RSS solution. · PHP · MIT · 2026-09
- [fossar/selfoss](https://github.com/fossar/selfoss) ★2.5k — multipurpose rss reader, live stream, mashup, aggregation web application · HTML · GPL-3.0 · 2026-10
- [msasikanth/twine](https://github.com/msasikanth/twine) ★2.4k — Twine: A multiplatform RSS reader built using Kotlin and Compose · Kotlin · GPL-3.0 · 2026-10
- [0x2E/fusion](https://github.com/0x2E/fusion) ★2.2k — A lightweight, self-hosted friendly RSS reader · TypeScript · MIT · 2026-10
- [Rongronggg9/RSS-to-Telegram-Bot](https://github.com/Rongronggg9/RSS-to-Telegram-Bot) ★2.2k — A Telegram RSS bot that cares about your reading experience (calling for new maintainers: https://github.com/Rongronggg9/RSS-to-Telegram-Bot · Python · AGPL-3.0 · 2026-10
- [ViennaRSS/vienna-rss](https://github.com/ViennaRSS/vienna-rss) ★2.0k — Vienna is a free and open-source RSS/Atom/JSON feed newsreader for macOS. · Objective-C · Apache-2.0 · 2026-10
- [zhanglun/lettura](https://github.com/zhanglun/lettura) ★1.8k — another rss reader · TypeScript · GPL-3.0 · 2026-10
- [yang991178/fluent-reader-lite](https://github.com/yang991178/fluent-reader-lite) ★1.8k — Simplistic mobile RSS client built with Flutter · Dart · BSD-3-Clause · 2026-03
- [glidea/zenfeed](https://github.com/glidea/zenfeed) ★1.7k — Make RSS 📰 great again with AI 🧠✨!! 数据打标请联系 glidea123 (数万并发随时狂飙) · Go · AGPL-3.0 · 2026-07
- [rbren/rss-parser](https://github.com/rbren/rss-parser) ★1.5k — A lightweight RSS parser, for Node and the browser · JavaScript · MIT · 2026-08
- [Panonim/dynacat](https://github.com/Panonim/dynacat) ★1.5k — Dynacat is a dashboard focused on dynamic reloading and easy integration with external applications. · Go · AGPL-3.0 · 2026-10
- [jocmp/capyreader](https://github.com/jocmp/capyreader) ★1.4k — A smallish Android RSS reader · Kotlin · GPL-3.0 · 2026-10
- [nmdias/FeedKit](https://github.com/nmdias/FeedKit) ★1.4k — FeedKit is a Swift library for Reading and Generating RSS, Atom, and JSON feeds. · Swift · MIT · 2026-09
- [ZGQ-inc/source](https://github.com/ZGQ-inc/source) ★1.3k — :package:个人搜集 | 书源、图源、订阅源、规则、直播源、各种源 大型整合 · JavaScript · NOASSERTION · 2025-09
- [nextcloud/news](https://github.com/nextcloud/news) ★1.0k — 📰 RSS/Atom feed reader · PHP · AGPL-3.0 · 2026-10

### Chat UI components (30)

- [ant-design/x](https://github.com/ant-design/x) ★4.8k — Craft AI-driven interface effortlessly🤖 · TypeScript · NOASSERTION · 2026-10
- [CommandCodeAI/langui](https://github.com/CommandCodeAI/langui) ★3.1k — UI for your AI. Open Source Tailwind components tailored for your GPT, generative AI, and LLM projects. · HTML · MIT · 2024-07
- [wzc520pyfm/ant-design-x-vue](https://github.com/wzc520pyfm/ant-design-x-vue) ★1.8k — Ant Design X For Vue. 🔥 · TypeScript · MIT · 2026-10
- [Detaysoft/react-chat-elements](https://github.com/Detaysoft/react-chat-elements) ★1.4k — Reactjs chat elements chat UI, react chat components · TypeScript · MIT · 2026-02
- [deeplethe/solid-glass](https://github.com/deeplethe/solid-glass) ★1.2k — A design system for AI applications. Material, physical, tactile, technical. · TypeScript · MIT · 2026-10
- [intelligo-dev/intelligo](https://github.com/intelligo-dev/intelligo) ★432 — The application framework for vertical AI SaaS | auth, workspaces, billing, credits, execution boundary, page registry. You build the agent. · TypeScript · Apache-2.0 · 2026-10
- [thesysdev/open-intelligent-ui](https://github.com/thesysdev/open-intelligent-ui) ★424 — An open-source take on ChatGPT's Intelligent UI: answers stream as interactive UI (maps, photos, charts, drawings and working tools). Built  · TypeScript · NOASSERTION · 2026-10
- [SimformSolutionsPvtLtd/chatview](https://github.com/SimformSolutionsPvtLtd/chatview) ★389 — Highly customisable chat UI with reply and reaction functionality. · Dart · MIT · 2026-06
- [receptron/mulmoclaude](https://github.com/receptron/mulmoclaude) ★376 — Nurture your own AI assistant on your own computer. Local-first and MIT: memories, data and apps stay as plain files in your workspace. Chat · TypeScript · MIT · 2026-10
- [EnesKaraosman/SwiftyChat](https://github.com/EnesKaraosman/SwiftyChat) ★354 — A lightweight SwiftUI chat UI framework with 11 built-in message types, 8 themes, and cross-platform iOS/macOS support · Swift · Apache-2.0 · 2026-10
- [sendbird/sendbird-uikit-react](https://github.com/sendbird/sendbird-uikit-react) ★240 — Build chat in minutes with Sendbird UIKit open source code. · TypeScript · MIT · 2026-10
- [shrikanth7698/ChatView](https://github.com/shrikanth7698/ChatView) ★232 — This is an Android library which can be used to add chat functionality to your android application with just a few lines of code. · Java · MIT · 2022-04
- [vpeschenkov/LetterAvatarKit](https://github.com/vpeschenkov/LetterAvatarKit) ★222 — Beautiful deterministic letter avatars for iOS and tvOS · Swift · MIT · 2026-06
- [Appllama/liquid-glass-chat-ui](https://github.com/Appllama/liquid-glass-chat-ui) ★216 — Explore liquid-glass chat UIs with animated portraits, interactive stories, and floating composers. · TypeScript · MIT · 2026-09
- [pubnub/react-chat-components](https://github.com/pubnub/react-chat-components) ★183 — Chat UI Components to build chat applications with PubNub on React with TypeScript support · TypeScript · NOASSERTION · 2024-10
- [ai-markdown/ai-markdown](https://github.com/ai-markdown/ai-markdown) ★169 — Markdown rendering for AI applications: incremental streaming, LaTeX math, GFM, and CJK typography. Shared engine and core, React and Mantin · TypeScript · MIT · 2026-10
- [LemonNekoGH/flow-chat](https://github.com/LemonNekoGH/flow-chat) ★154 — Chat UI in graph 🌲. Unlike traditional chat UIs, users don’t need to delete messages to explore different responses—they can simply create n · TypeScript · MIT · 2026-09
- [MuhammedKpln/react-native-chatty](https://github.com/MuhammedKpln/react-native-chatty) ★142 — 💬 Full-featured high performance chat UI for React Native · TypeScript · MIT · 2023-11
- [agents-ui/agents-kit](https://github.com/agents-ui/agents-kit) ★127 — React components for voice agents, chat, and generative UI. LiveKit, ElevenLabs, and OrbKit in one kit. Copy the source and make it yours. · TypeScript · NOASSERTION · 2026-09
- [sendbird/sendbird-uikit-ios](https://github.com/sendbird/sendbird-uikit-ios) ★125 — Sendbird UIKit for iOS is a development kit with a user interface, offering a simplified integration into chat. · Swift · NOASSERTION · 2026-09
- [sendbird/sendbird-uikit-react-native](https://github.com/sendbird/sendbird-uikit-react-native) ★97 — Build chat in minutes with Sendbird UIKit open source code. · TypeScript · NOASSERTION · 2026-10
- [AI-QL/chat-ui](https://github.com/AI-QL/chat-ui) ★96 — Single-File AI Chatbot UI with Multimodal & MCP Support: An All-in-One HTML File for a Streamlined Chatbot Conversational Interface · HTML · Apache-2.0 · 2026-08
- [Laplace-bit/dsh-smooth-stream](https://github.com/Laplace-bit/dsh-smooth-stream) ★82 — DeepSeek Harness Web UI plugin for streaming rendering and scroll handling. · JavaScript · MIT · 2026-10
- [Kommunicate-io/Kommunicate-Android-Chat-SDK](https://github.com/Kommunicate-io/Kommunicate-Android-Chat-SDK) ★80 — Kommunicate Android AI Agent SDK · Java · BSD-3-Clause · 2026-10
- [moeru-ai/chat](https://github.com/moeru-ai/chat) ★79 — 🥽🖼️ WebXR Voice Call UI, Make AI-Powered characters appear to you. · TypeScript · MIT · 2025-08
- [kesha-antonov/react-native-chat](https://github.com/kesha-antonov/react-native-chat) ★71 — The most complete chat UI for React Native & Web - streaming AI messages, emoji reactions, replies, quick replies, and full customization. T · TypeScript · MIT · 2026-10
- [dytlabs/Messenger-Android-XML-Template](https://github.com/dytlabs/Messenger-Android-XML-Template) ★70 — Free android xml template for chat/messenger app. · Java · GPL-3.0 · 2017-03
- [RYOITABASHI/Shelly](https://github.com/RYOITABASHI/Shelly) ★66 — AI-powered chat-first terminal IDE for Android. Built entirely on a phone, by someone who can't write code. · TypeScript · GPL-3.0 · 2026-10
- [zvzuola/acp-components](https://github.com/zvzuola/acp-components) ★64 — UI component library for the Agent Client Protocol (ACP), providing a complete set of components to build agentic coding interfaces that com · TypeScript · MIT · 2026-09
- [it-at-m/mucgpt](https://github.com/it-at-m/mucgpt) ★63 — MUCGPT is an assistant-focused AI toolkit aimed at public administration. It includes different modes of interaction and lets users create a · TypeScript · MIT · 2026-10

### AI SDK / streaming UI (30)

- [steven-tey/novel](https://github.com/steven-tey/novel) ★16.5k — Notion-style WYSIWYG editor with AI-powered autocompletion. · TypeScript · Apache-2.0 · 2025-01
- [mnfst/llm-gateway](https://github.com/mnfst/llm-gateway) ★7.6k — Open Source LLM Gateway 🦚 · TypeScript · MIT · 2026-10
- [ThinkInAIXYZ/deepchat](https://github.com/ThinkInAIXYZ/deepchat) ★6.4k — 🐬DeepChat - A smart assistant that connects powerful AI to your personal world · TypeScript · Apache-2.0 · 2026-10
- [TanStack/ai](https://github.com/TanStack/ai) ★3.2k — 🤖 Type-safe, provider-agnostic TypeScript AI SDK for streaming chat, tool calling, agents, and multimodal apps across OpenAI, Anthropic, Gem · TypeScript · MIT · 2026-10
- [dzhng/jevgrep](https://github.com/dzhng/jevgrep) ★2.7k — Find code by asking what it does. A CLI for coding agents that uses Jev to discover relevant files and source context. · TypeScript · MIT · 2026-10
- [GCWing/OpenBitFun](https://github.com/GCWing/OpenBitFun) ★2.7k — OpenBitFun combines a high-performance agent runtime written in Rust with a polished desktop application. It pairs the depth of a Code Agent · Rust · MIT · 2026-10
- [microsoft/foundry-local](https://github.com/microsoft/foundry-local) ★2.6k · C++ · NOASSERTION · 2026-10
- [midday-ai/ai-sdk-tools](https://github.com/midday-ai/ai-sdk-tools) ★2.1k — Essential utilities for building production-ready AI applications with Vercel AI SDK. State management, debugging, structured streaming, int · TypeScript · NOASSERTION · 2025-12
- [steven-tey/chathn](https://github.com/steven-tey/chathn) ★1.2k — Chat with Hacker News using natural language. Built with OpenAI Functions and Vercel AI SDK. · TypeScript · MIT · 2023-10
- [Blazity/shadcn-chatbot-kit](https://github.com/Blazity/shadcn-chatbot-kit) ★805 — 🤖 Beautifully designed chatbot components based on shadcn/ui · TypeScript · MIT · 2026-02
- [lumpinif/deepcrawl](https://github.com/lumpinif/deepcrawl) ★690 — 100% free and full open-source edge Firecrawl alternative with better links extraction for agents - that you can deploy to cloudflare or ver · TypeScript · MIT · 2026-08
- [crafter-station/elements](https://github.com/crafter-station/elements) ★526 — Full-stack shadcn/ui blocks for auth, payments, AI, logos, and more · TypeScript · MIT · 2026-08
- [growthxai/output](https://github.com/growthxai/output) ★443 — The open-source TypeScript framework for building AI workflows and agents. Designed for Claude Code describe what you want, Claude builds it · JavaScript · Apache-2.0 · 2026-10
- [vercel-labs/ai-sdk-preview-rag](https://github.com/vercel-labs/ai-sdk-preview-rag) ★409 — Retrieval-augmented generation (RAG) template powered by the AI SDK. · TypeScript · MIT · 2026-04
- [nuxt-ui-templates/chat](https://github.com/nuxt-ui-templates/chat) ★379 — Nuxt AI Chatbot Template made with Nuxt UI and Vercel AI SDK. · Vue · MIT · 2026-10
- [ben-vargas/ai-sdk-provider-claude-code](https://github.com/ben-vargas/ai-sdk-provider-claude-code) ★367 — Vercel AI SDK community provider for Claude Agent SDK · TypeScript · MIT · 2026-09
- [vargHQ/sdk](https://github.com/vargHQ/sdk) ★342 — AI video generation SDK — JSX for videos. One API for Kling, Flux, ElevenLabs, Veed. Built on Vercel AI SDK. · TypeScript · Apache-2.0 · 2026-10
- [pensarai/apex](https://github.com/pensarai/apex) ★316 — AI-powered offensive security testing using autonomous agents, directly in your terminal. · TypeScript · Apache-2.0 · 2026-10
- [jakejarvis/domainstack.io](https://github.com/jakejarvis/domainstack.io) ★292 — 🧰 All-in-one domain name intelligence as a service · TypeScript · MIT · 2026-10
- [zendev-sh/goai](https://github.com/zendev-sh/goai) ★226 — Go AI SDK, the Go way.  One unified API across 21+ providers. Streaming, structured output, MCP support, stdlib only. Go AI SDK for AI appli · Go · MIT · 2026-10
- [xn1cklas/ai-tools-registry](https://github.com/xn1cklas/ai-tools-registry) ★207 — Install AI tools and UI components for the AI SDK via the shadcn registry · TypeScript · NOASSERTION · 2025-12
- [jakobhoeg/browser-ai](https://github.com/jakobhoeg/browser-ai) ★204 — In-browser AI model providers for the Vercel AI SDK, built to make client-side AI integration simpler and more consistent across vendors. · TypeScript · NOASSERTION · 2026-10
- [SouravBeraAkaSpeed/xiryn](https://github.com/SouravBeraAkaSpeed/xiryn) ★182 — Xiryn — the open-source personal agent. Does everything Muse, Grok Bot and Dots do, on your own computer: each agent gets its own Linux desk · TypeScript · MIT · 2026-10
- [nuxt-ui-templates/editor](https://github.com/nuxt-ui-templates/editor) ★171 — Notion-like WYSIWYG editor with AI-powered completions and real-time collaboration in Vue & Nuxt. · TypeScript · MIT · 2026-10
- [vercel-labs/ai-facts](https://github.com/vercel-labs/ai-facts) ★168 — Real-time fact checking on spoken statements with the AI SDK, Perplexity and DeepGram · TypeScript · NOASSERTION · 2026-04
- [grok-php/laravel](https://github.com/grok-php/laravel) ★167 — Seamlessly integrate Grok AI into Laravel applications with an elegant, developer-friendly package. Leverage powerful AI models for chat, au · PHP · MIT · 2025-02
- [neplexlabs/commandkit](https://github.com/neplexlabs/commandkit) ★165 — The discord.js meta-framework with features such as AI-powered command handler, analytics, feature flags, and more · TypeScript · MIT · 2026-10
- [juspay/neurolink](https://github.com/juspay/neurolink) ★157 — The pipe layer of an AI nervous system — one interface connecting provider neurons to your application, across three inference types: genera · TypeScript · MIT · 2026-10
- [realZachi/shotluma](https://github.com/realZachi/shotluma) ★148 — Open-source, local-first AI App Store screenshot editor. · TypeScript · MIT · 2026-09
- [vercel-labs/ai-sdk-slackbot](https://github.com/vercel-labs/ai-sdk-slackbot) ★132 — AI Slack Agent powered by the AI SDK. · TypeScript · NOASSERTION · 2026-06

### AI browser agents (30)

- [lmnr-ai/index](https://github.com/lmnr-ai/index) ★2.4k — The SOTA Open-Source Browser Agent for autonomously performing complex tasks on the web · Python · Apache-2.0 · 2025-06
- [Player-YN/BrowserKitten](https://github.com/Player-YN/BrowserKitten) ★2.4k — Paw Work - selection-first web agent for Chrome: select on the live page, describe the outcome, take away an editable office file. BYOK, san · JavaScript · MIT · 2026-09
- [platonai/Browser4](https://github.com/platonai/Browser4) ★1.2k — Browser4 — an AI-native browser engine for autonomous agents, intelligent extraction, and large-scale web automation. · Kotlin · Apache-2.0 · 2026-10
- [browser-use/desktop](https://github.com/browser-use/desktop) ★701 — Browser Use Desktop App · TypeScript · MIT · 2026-10
- [OS-Agent-Survey/OS-Agent-Survey](https://github.com/OS-Agent-Survey/OS-Agent-Survey) ★488 — This is the repo for the paper "OS Agents: A Survey on MLLM-based Agents for Computer, Phone and Browser Use" (ACL 2025 Oral). · NOASSERTION · 2025-08
- [OyadotAI/oya-browser](https://github.com/OyadotAI/oya-browser) ★353 — The browser control plane for AI agents. One API over Oya Cloud, Browserbase, Steel, Anchor, Browser Use and your own Chrome, with persisten · TypeScript · NOASSERTION · 2026-10
- [BrowserCash/teracrawl](https://github.com/BrowserCash/teracrawl) ★285 — High-performance web crawler API optimized for LLMs. Turn any search or website into clean Markdown using remote browsers. Firecrawl alterna · TypeScript · MIT · 2025-12
- [socai-io/socai](https://github.com/socai-io/socai) ★242 — Agent that actually understands social platforms. Fast. Precise. Deep. · Rust · Apache-2.0 · 2026-10
- [MigoXLab/webqa-agent](https://github.com/MigoXLab/webqa-agent) ★234 — Autonomous web browser agent that audits performance, functionality & UX for engineers and vibe-coding creators. 网站自主评估测试 Agent，支持 GUI/CLI 一 · Python · Apache-2.0 · 2026-07
- [fullselfbrowsing/FSB](https://github.com/fullselfbrowsing/FSB) ★193 — DOM-first AI browser automation for Chrome and MCP clients. · JavaScript · MIT · 2026-10
- [ai-naymul/BrowserPilot](https://github.com/ai-naymul/BrowserPilot) ★180 — Open‑source alternative to Perplexity Comet, director.ai and firecrawl combined · TypeScript · MIT · 2026-07
- [tubecreate/tubecli](https://github.com/tubecreate/tubecli) ★174 — ⚡ TubeCLI — The Ultimate Open Source AI Agents Ecosystem | Agents Browser · Agents Workflow · Agents Studio World · Python · MIT · 2026-10
- [socai-io/jev-social](https://github.com/socai-io/jev-social) ★171 — Open-source, local-first social media research agent for Instagram, TikTok, and LinkedIn. Jev routes read-only steps; socai CLI captures cit · JavaScript · MIT · 2026-10
- [browser-use/benchmark](https://github.com/browser-use/benchmark) ★151 — Open benchmarks for browser agents: BU Bench V2.1, 200 real web tasks. Rerun them with your own API keys. · Python · NOASSERTION · 2026-10
- [ThinkFlowLab/system1-agents](https://github.com/ThinkFlowLab/system1-agents) ★147 — System 1 decision models (Jev, Laya, Cua-S1) as brain for agents: Browser use, computer use, games and robotics · Python · Apache-2.0 · 2026-10
- [dom-actions/doma](https://github.com/dom-actions/doma) ★146 — The open-source of DomA, an AI automation agent for the browser. · TypeScript · NOASSERTION · 2026-10
- [lidge-jun/aside-codemode](https://github.com/lidge-jun/aside-codemode) ★129 — One call where Aside used to spend fifty — rg-backed search, Aside-shaped file tools, and batched browser work inside a single sandboxed Jav · JavaScript · MIT · 2026-10
- [agent-labs-dev/fastbrowse](https://github.com/agent-labs-dev/fastbrowse) ★120 — A fast browser agent: Jev picks each action from what is on the page, an LLM reads and plans, and every claim in an answer cites a quote fro · Python · MIT · 2026-10
- [OpenBrowserAI/openbrowser](https://github.com/OpenBrowserAI/openbrowser) ★72 — OpenBrowser is an open-source, AI-native browser built on Chromium — a truly privacy-first alternative to ChatGPT Atlas, Perplexity Comet, a · TypeScript · MIT · 2026-09
- [tubecreate/zhiying](https://github.com/tubecreate/zhiying) ★71 — ⚡ ZhiYing — 终极开源 AI Agents 生态协同系统 | Agents Browser · Agents Workflow · Agents Studio World · JavaScript · NOASSERTION · 2026-04
- [alanhuangyoo/OpenJev](https://github.com/alanhuangyoo/OpenJev) ★66 — OpenJev: open-source, local alternative to Jev. System-One decision models: typed questions in, calibrated probabilities out; general decisi · Python · Apache-2.0 · 2026-10
- [reacher-z/HarnessBench](https://github.com/reacher-z/HarnessBench) ★62 — Benchmark for comparing agent harnesses on everyday online tasks — fixes the base model, varies the harness. Sister project of ClawBench, sa · Python · Apache-2.0 · 2026-07
- [hooosberg/AgentLimb](https://github.com/hooosberg/AgentLimb) ★54 — Let any AI coding tool — Claude Code, Cursor, Codex — drive your real Chrome. One-prompt setup, muscle memory, local-first. · JavaScript · NOASSERTION · 2026-10
- [AliSharjeell/OpenBUA](https://github.com/AliSharjeell/OpenBUA) ★46 — Open-source autonomous AI browser agent Chrome extension running locally in your authenticated browser. Researches web data, fills forms, au · TypeScript · NOASSERTION · 2026-10
- [alibaba/qz-browser-agent](https://github.com/alibaba/qz-browser-agent) ★45 — Local-first AI agent for Chrome: browser automation, web research, and data extraction with your own model. · JavaScript · Apache-2.0 · 2026-10
- [chy4pro/jev-for-chrome](https://github.com/chy4pro/jev-for-chrome) ★40 — Jev for Chrome: drives the tab you are looking at with TypeSafe Jev, a sub-second decision model. Community port of browser-use/jev-ultrafas · TypeScript · MIT · 2026-10
- [7757/Fan-Browser-Agent](https://github.com/7757/Fan-Browser-Agent) ★39 — Open-source desktop AI agent with an embedded browser runtime and human-in-the-loop control. · Python · MIT · 2026-10
- [browser-use/contact-use](https://github.com/browser-use/contact-use) ★37 — ✉️ Use the power of browser-use to contact any person or organization... by any means necessary · HTML · NOASSERTION · 2025-07
- [imshaikot/browsentic](https://github.com/imshaikot/browsentic) ★37 — An agentic browser harness: an AI side panel & orb in your own logged-in Chrome, Edge, Arc, Brave or even Firefox run by the agent/subscript · TypeScript · Apache-2.0 · 2026-10
- [rkvalandas/browser_agent](https://github.com/rkvalandas/browser_agent) ★37 — A smart AI agent that controls your browser with natural language, using Playwright and advanced LLMs to navigate, analyze, and perform task · Python · MIT · 2025-11

### Code intelligence (tree-sitter) (30)

- [tree-sitter/tree-sitter](https://github.com/tree-sitter/tree-sitter) ★27.2k — An incremental parsing system for programming tools · Rust · MIT · 2026-10
- [Wilfred/difftastic](https://github.com/Wilfred/difftastic) ★26.0k — a structural diff that understands syntax 🟥🟩 · Rust · MIT · 2026-10
- [nvim-treesitter/nvim-treesitter](https://github.com/nvim-treesitter/nvim-treesitter) ★14.5k — Nvim Treesitter configurations and abstraction layer · Tree-sitter Query · Apache-2.0 · 2026-10
- [curlconverter/curlconverter](https://github.com/curlconverter/curlconverter) ★8.2k — Transpile curl commands into Python, JavaScript and 27 other languages · TypeScript · MIT · 2026-03
- [biomejs/gritql](https://github.com/biomejs/gritql) ★4.6k — GritQL is a query language for searching, linting, and modifying code. · Rust · MIT · 2026-10
- [Ataraxy-Labs/sem](https://github.com/Ataraxy-Labs/sem) ★3.4k — Semantic version control => entity-level diffs, blame, and impact analysis on top of git. 28 languages via tree-sitter. Built for coding age · Rust · Apache-2.0 · 2026-10
- [simonbs/Runestone](https://github.com/simonbs/Runestone) ★3.2k — 📝 Performant plain text editor for iOS with syntax highlighting, line numbers, invisible characters and much more. · Swift · MIT · 2026-03
- [nvim-treesitter/nvim-treesitter-textobjects](https://github.com/nvim-treesitter/nvim-treesitter-textobjects) ★2.8k · Tree-sitter Query · Apache-2.0 · 2026-09
- [jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp) ★2.8k — Cut AI token costs 95%+ on code exploration. The leading MCP server for precise, symbol-level GitHub code retrieval via tree-sitter AST. Wor · Python · NOASSERTION · 2026-10
- [neurocyte/flow](https://github.com/neurocyte/flow) ★2.5k — Flow Control: a programmer's text editor · Zig · MIT · 2026-10
- [afnanenayet/diffsitter](https://github.com/afnanenayet/diffsitter) ★2.4k — A tree-sitter based AST difftool to get meaningful semantic diffs · Rust · MIT · 2026-10
- [open-compress/claw-compactor](https://github.com/open-compress/claw-compactor) ★2.0k — 14-stage Fusion Pipeline for LLM token compression — reversible compression, AST-aware code analysis, intelligent content routing. Zero LLM  · Python · MIT · 2026-04
- [zee-editor/zee](https://github.com/zee-editor/zee) ★1.8k — A modern text editor for the terminal written in Rust · Rust · Apache-2.0 · 2025-02
- [unhappychoice/gittype](https://github.com/unhappychoice/gittype) ★1.6k — A CLI code-typing game that turns your source code into typing challenges · Rust · MIT · 2026-10
- [folke/twilight.nvim](https://github.com/folke/twilight.nvim) ★1.5k — 🌅  Twilight is a Lua plugin for Neovim 0.5 that dims inactive portions of the code you're editing using TreeSitter. · Lua · Apache-2.0 · 2025-10
- [tree-sitter/py-tree-sitter](https://github.com/tree-sitter/py-tree-sitter) ★1.5k — Python bindings to the Tree-sitter parsing library · C · MIT · 2026-08
- [salesforce/CodeTF](https://github.com/salesforce/CodeTF) ★1.5k — CodeTF: One-stop Transformer Library for State-of-the-art Code LLM · Python · Apache-2.0 · 2025-05
- [chunkhound/chunkhound](https://github.com/chunkhound/chunkhound) ★1.4k — Your entire engineering context, deeply understood · Python · MIT · 2026-10
- [Ataraxy-Labs/weave](https://github.com/Ataraxy-Labs/weave) ★1.3k — Entity-level git merge driver. Resolves false conflicts git invents when independent agents edit the same file. ~95% reduction vs. line-base · Rust · Apache-2.0 · 2026-10
- [JoosepAlviste/nvim-ts-context-commentstring](https://github.com/JoosepAlviste/nvim-ts-context-commentstring) ★1.3k — Neovim treesitter plugin for setting the commentstring based on the cursor location in a file. · Lua · MIT · 2026-04
- [mickeynp/combobulate](https://github.com/mickeynp/combobulate) ★1.2k — Structured Editing and Navigation in Emacs with Tree-Sitter · Emacs Lisp · GPL-3.0 · 2026-10
- [cshuaimin/ssr.nvim](https://github.com/cshuaimin/ssr.nvim) ★1.0k — Treesitter based structural search and replace plugin for Neovim. · Lua · MIT · 2026-04
- [nvim-treesitter/playground](https://github.com/nvim-treesitter/playground) ★921 — Treesitter playground integrated into Neovim · Lua · Apache-2.0 · 2023-09
- [alexpovel/srgn](https://github.com/alexpovel/srgn) ★913 — A grep-like tool which understands source code syntax and allows for manipulation in addition to search · Rust · MIT · 2026-10
- [sourcegraph/doctree](https://github.com/sourcegraph/doctree) ★879 — First-class library documentation for every language (based on tree-sitter), with symbol search & more. Lightweight single binary, run local · Go · Apache-2.0 · 2024-08
- [tree-sitter/node-tree-sitter](https://github.com/tree-sitter/node-tree-sitter) ★878 — Node.js bindings for tree-sitter · JavaScript · MIT · 2026-07
- [topiary/topiary](https://github.com/topiary/topiary) ★874 · Rust · MIT · 2026-10
- [emacs-tree-sitter/elisp-tree-sitter](https://github.com/emacs-tree-sitter/elisp-tree-sitter) ★855 — Emacs Lisp bindings for tree-sitter · Emacs Lisp · MIT · 2026-09
- [dchinmay2/nvim-ts-rainbow](https://github.com/dchinmay2/nvim-ts-rainbow) ★849 — Rainbow parentheses for neovim using tree-sitter. Use https://sr.ht/~p00f/nvim-ts-rainbow instead · Lua · Apache-2.0 · 2023-01
- [Enter-tainer/cxx2flow](https://github.com/Enter-tainer/cxx2flow) ★821 — 将 C/C++ 代码转换成流程图 / Turn your C/C++ code into flowchart · Rust · MIT · 2026-04

### Code search & indexing (30)

- [sourcegraph/sourcegraph-public-snapshot](https://github.com/sourcegraph/sourcegraph-public-snapshot) ★10.3k — Code AI platform with Code Search & Cody · Go · NOASSERTION · 2024-09
- [sweepai/sweep](https://github.com/sweepai/sweep) ★7.7k — Sweep: AI coding assistant for JetBrains · Jupyter Notebook · NOASSERTION · 2025-09
- [zvec-ai/zvec-grep](https://github.com/zvec-ai/zvec-grep) ★4.1k — Local-first search across your workspace, built for humans and AI agents. · Rust · Apache-2.0 · 2026-10
- [sourcebot-dev/sourcebot](https://github.com/sourcebot-dev/sourcebot) ★4.0k — Sourcebot is a self-hosted tool that helps humans and agents understand your codebase. · Python · MIT · 2026-10
- [openrewrite/rewrite](https://github.com/openrewrite/rewrite) ★3.8k — Automated mass refactoring of source code. · Java · Apache-2.0 · 2026-10
- [yinwang0/pysonar2](https://github.com/yinwang0/pysonar2) ★1.4k — PySonar2: a semantic indexer for Python with interprocedual type inference · Java · Apache-2.0 · 2026-03
- [bgauryy/octocode](https://github.com/bgauryy/octocode) ★950 — Code research platform for AI agents; find, understand, and prove context across your code and all of GitHub, in a fraction of the tokens. O · TypeScript · MIT · 2026-10
- [ruben2020/codequery](https://github.com/ruben2020/codequery) ★775 — A code-understanding,  code-browsing or code-search tool. This is a tool to index, then query or search C, C++, Java, Python, Ruby, Go and J · C++ · MPL-2.0 · 2026-07
- [bartolli/codanna](https://github.com/bartolli/codanna) ★755 — Local code intelligence MCP server and CLI for AI coding agents · Rust · Apache-2.0 · 2026-10
- [OpenGenus/quark](https://github.com/OpenGenus/quark) ★642 — Stay happy while offline | World's first offline search engine. · C++ · GPL-3.0 · 2022-10
- [marcoaapfortes/Mantic.sh](https://github.com/marcoaapfortes/Mantic.sh) ★555 — A structural code search engine for Al agents. · TypeScript · MIT · 2026-07
- [hamelsmu/code_search](https://github.com/hamelsmu/code_search) ★491 — Code For Medium Article: "How To Create Natural Language Semantic Search for Arbitrary Objects With Deep Learning" · Jupyter Notebook · MIT · 2022-12
- [oschina/kooder](https://github.com/oschina/kooder) ★437 — 🔍An open source GitLab/Gitee/Gitea code search tool. Kooder 是一个为 Gitee/GitLab 开发的开源代码搜索工具，这是一个镜像仓库，主仓库在 Gitee。 · Java · Apache-2.0 · 2021-10
- [boyter/searchcode-server](https://github.com/boyter/searchcode-server) ★393 — The offical home of searchcode-server where you can run searchcode locally. Note that master is generally unstable in the sense that it is n · Java · NOASSERTION · 2025-07
- [7df-lab/devo](https://github.com/7df-lab/devo) ★321 — Model-neutral agent desktop/runtime for private, enterprise, and OpenAI-compatible / Anthropic-compatible model API. Tested on DeepSeek, Qwe · Rust · MIT · 2026-10
- [403errors/repomind](https://github.com/403errors/repomind) ★291 — An open-source, AI-powered application using Agentic CAG to chat with any public GitHub repository or developer profile, offering deep code  · TypeScript · MIT · 2026-10
- [borkdude/grasp](https://github.com/borkdude/grasp) ★250 — Grep Clojure code using clojure.spec regexes · Clojure · EPL-1.0 · 2026-07
- [quasilyte/phpgrep](https://github.com/quasilyte/phpgrep) ★241 — Syntax-aware grep for PHP code. · Go · MIT · 2024-04
- [FarhanAliRaza/claude-context-local](https://github.com/FarhanAliRaza/claude-context-local) ★238 — Code search MCP for Claude Code. Make entire codebase the context for any coding agent. Embeddings are created and stored locally. No API co · Python · NOASSERTION · 2025-11
- [Helweg/open-codebase-index](https://github.com/Helweg/open-codebase-index) ★223 — Semantic codebase indexing and search for OpenCode, Claude, Codex, Pi, Jcode, and MCP hosts. Powered by Rust and tree-sitter. · TypeScript · MIT · 2026-10
- [johunsang/semble_rs](https://github.com/johunsang/semble_rs) ★214 — Fast, AI-agent-native code search in Rust — hybrid BM25 + semantic, Tree-sitter AST chunking, dependency & impact analysis. Drop-in replacem · Rust · NOASSERTION · 2026-06
- [yinwang0/rubysonar](https://github.com/yinwang0/rubysonar) ★200 — A semantic indexer for Ruby with interprocedual type inference · Java · NOASSERTION · 2022-11
- [Graphicle-AI/graphicle](https://github.com/Graphicle-AI/graphicle) ★180 — Code graph and memory for your coding agents, in one Rust program. For Claude Code, Codex, Cursor and any MCP client. · Rust · Apache-2.0 · 2026-10
- [Lisprez/so_stupid_search](https://github.com/Lisprez/so_stupid_search) ★178 — It's my honor to drive you fucking fire faster, to have more time with your Family and Sunshine.This tool is for those who often want to sea · Rust · LGPL-2.1 · 2026-03
- [definitive-io/code-indexer-loop](https://github.com/definitive-io/code-indexer-loop) ★175 — Code Indexer Loop is a Python library for indexing and retrieving source code files through an integrated vector database that's continuousl · Python · Apache-2.0 · 2024-04
- [AxiomCodeAI/axiomcodegraph](https://github.com/AxiomCodeAI/axiomcodegraph) ★170 — Turn any codebase into a knowledge graph grounded in formal methods. Your AI agents get exact answers for any code-related task, ensure corr · TypeScript · NOASSERTION · 2026-10
- [zilliztech/mfs](https://github.com/zilliztech/mfs) ★155 — A context harness for AI agents: all your scattered context — code, memory, docs, databases, SaaS — in one searchable, browsable, file-like  · Python · Apache-2.0 · 2026-07
- [bfontaine/grape](https://github.com/bfontaine/grape) ★153 — :grapes: Syntax-aware grep-like for Clojure · Clojure · EPL-2.0 · 2023-01
- [Regsorm/code-index-mcp](https://github.com/Regsorm/code-index-mcp) ★147 — Поиск по коду для ИИ-агентов: 32 инструмента MCP, индекс на SQLite, один бинарник без зависимостей. Разбирает выгрузки 1С:Предприятие — Конф · Rust · MIT · 2026-10
- [Wilfred/elisp-refs](https://github.com/Wilfred/elisp-refs) ★131 — semantic code search for emacs lisp · Emacs Lisp · NOASSERTION · 2023-09

### Local-first & sync (30)

- [debpalash/VoiceStudio](https://github.com/debpalash/VoiceStudio) ★69.9k — VoiceStudio is the open-source, fully-local ElevenLabs alternative — voice cloning, voice design, video dubbing, dictation, transcription &  · Python · AGPL-3.0 · 2026-10
- [pubkey/rxdb](https://github.com/pubkey/rxdb) ★23.4k — The local-first database that runs on every JS runtime and replicates with your existing backend - no vendor, no lock-in - https://rxdb.info · TypeScript · Apache-2.0 · 2026-10
- [genspark-ai/genoffice](https://github.com/genspark-ai/genoffice) ★9.8k — Free, open-source AI Office suite: Docs, Sheets, Slides, PDF, Markdown and HTML editors with a built-in AI agent, plus a `genoffice` CLI and · TypeScript · Apache-2.0 · 2026-10
- [TencentCloud/Octop](https://github.com/TencentCloud/Octop) ★9.6k — A smarter, self-hosted AI assistant — multi-user, multi-agent. · Python · MIT · 2026-10
- [fastrepl/anarlog](https://github.com/fastrepl/anarlog) ★9.5k — Open source Granola AI Alternative · Rust · MIT · 2026-10
- [nexu-io/html-anything](https://github.com/nexu-io/html-anything) ★9.1k — ✨ The agentic HTML editor — your local AI agent writes the HTML, you ship it. 🚀 75 Skills × 9 Surfaces (magazine · deck · poster · XHS / twe · HTML · Apache-2.0 · 2026-10
- [tw93/MiaoYan](https://github.com/tw93/MiaoYan) ★8.7k — ⛷ A quiet, local-first Markdown writing app for Mac, to help you write great sentences. · Swift · MIT · 2026-10
- [loro-dev/loro](https://github.com/loro-dev/loro) ★6.2k — Make your JSON data collaborative and version-controlled with CRDTs · Rust · MIT · 2026-10
- [toeverything/blocksuite](https://github.com/toeverything/blocksuite) ★6.1k — 🧩 Content editing tech stack for the web - BlockSuite is a toolkit for building editors and collaborative applications. · TypeScript · MPL-2.0 · 2026-10
- [apache/maka](https://github.com/apache/maka) ★5.8k — Apache Maka (Incubating) is a high-performance agent workspace that keeps a complete record of everything it did. · TypeScript · Apache-2.0 · 2026-10
- [tinyplex/tinybase](https://github.com/tinyplex/tinybase) ★5.2k — A reactive data store & sync engine. · TypeScript · MIT · 2026-10
- [colanode/colanode](https://github.com/colanode/colanode) ★5.2k — Open-source and local-first Slack and Notion alternative that puts you in control of your data · TypeScript · Apache-2.0 · 2026-04
- [fspecii/ace-step-ui](https://github.com/fspecii/ace-step-ui) ★5.1k — 🎵 The Ultimate Open Source Suno Alternative - Professional UI for ACE-Step 1.5 AI Music Generation. Free, local, unlimited. Stop paying for  · JavaScript · NOASSERTION · 2026-06
- [totec448-spec/chat-on-steroids](https://github.com/totec448-spec/chat-on-steroids) ★4.9k — Cross-platform local MCP capabilities for ChatGPT with Chrome integration, Goal, Compact & Resume, and durable multi-agent workflows. · TypeScript · MIT · 2026-10
- [onejs/one](https://github.com/onejs/one) ★4.6k — ❶ One lets you target React web and React Native with a single Vite plugin. Everything you need to build great websites and apps with unifie · TypeScript · NOASSERTION · 2026-10
- [nuttyartist/notes](https://github.com/nuttyartist/notes) ★4.3k — Fast and beautiful note-taking app written in C++. Write down your thoughts. · C++ · MPL-2.0 · 2026-05
- [basicmachines-co/basic-memory](https://github.com/basicmachines-co/basic-memory) ★4.2k — AI conversations that actually remember. Never re-explain your project to your AI again. Join our Discord: https://discord.gg/tyvKNccgqN · Python · AGPL-3.0 · 2026-10
- [livestorejs/livestore](https://github.com/livestorejs/livestore) ★3.7k — LiveStore is a next-generation state management framework based on reactive SQLite and built-in sync engine. · TypeScript · Apache-2.0 · 2026-10
- [whiteguo233/OpenBiliClaw](https://github.com/whiteguo233/OpenBiliClaw) ★3.5k — 本地私有、开源的自进化跨平台 AI 内容发现 Agent：先理解你，再主动从 B站、小红书、抖音、YouTube、X、知乎、Reddit、微博等平台与开放 Web 寻找内容。（支持 deepseek harness 插件） | Local-first open-source cr · Python · MIT · 2026-10
- [mayneyao/eidos](https://github.com/mayneyao/eidos) ★3.2k — A single-file relational spreadsheet for you and your agent. · TypeScript · AGPL-3.0 · 2026-10
- [warp-drive-data/warp-drive](https://github.com/warp-drive-data/warp-drive) ★3.2k — WarpDrive is the lightweight data library for ambitious web apps — universal, typed, reactive, and ready to scale. · TypeScript · MIT · 2026-10
- [Javis603/token-monitor](https://github.com/Javis603/token-monitor) ★3.1k — Local-first desktop widget for tracking token usage, costs, limits, and session activity across 46+ AI coding tools—including Claude Code, C · JavaScript · MIT · 2026-10
- [viperrcrypto/Siftly](https://github.com/viperrcrypto/Siftly) ★3.1k — Local Twitter/X bookmark organizer with AI categorization and mindmap visualization · TypeScript · MIT · 2026-04
- [orbitinghail/sqlsync](https://github.com/orbitinghail/sqlsync) ★2.9k — SQLSync is a collaborative offline-first wrapper around SQLite. It is designed to synchronize web application state between users, devices,  · Rust · Apache-2.0 · 2025-11
- [hello245m/free-stockdb](https://github.com/hello245m/free-stockdb) ★2.9k — 面向 A 股日K、分钟K与ETF分钟数据的本地量化引擎，集成增量同步、本地缓存、复权、批量查询、回测与指标计算。 · HTML · MIT · 2026-10
- [goniszewski/grimoire](https://github.com/goniszewski/grimoire) ★2.9k — Bookmark manager for the wizards 🧙 · TypeScript · MIT · 2026-09
- [lennney/stop-that-shit](https://github.com/lennney/stop-that-shit) ★2.7k — Stop That Shit（别再造史了）｜面向 Codex/GPT 场景的多平台 Hook + Skill Guard：拦截 AI coding agent 无需求的哈希、校验和与任务范围膨胀。 A multi-platform Hook + Skill Guard for A · JavaScript · MIT · 2026-10
- [TryQuiet/quiet](https://github.com/TryQuiet/quiet) ★2.7k — A private, p2p alternative to Slack and Discord built on Tor & IPFS · TypeScript · GPL-3.0 · 2026-10
- [CrossPaste/crosspaste-desktop](https://github.com/CrossPaste/crosspaste-desktop) ★2.6k — Cross-device clipboard sync for macOS, Windows & Linux — end-to-end encrypted, LAN-only, no cloud. OCR, CLI and MCP server built in. · Kotlin · AGPL-3.0 · 2026-10
- [org2AI/ORG2](https://github.com/org2AI/ORG2) ★2.6k — System of record for how agents build software: Built-in rust harness & 20+ CLIs. · TypeScript · AGPL-3.0 · 2026-10

### Self-hosted search (30)

- [elastic/elasticsearch](https://github.com/elastic/elasticsearch) ★78.3k — Free and Open Source, Distributed, RESTful Search Engine · Java · NOASSERTION · 2026-10
- [typesense/typesense](https://github.com/typesense/typesense) ★26.9k — Open Source alternative to Algolia + Pinecone and an Easier-to-Use alternative to ElasticSearch ⚡ 🔍 ✨ Fast, typo tolerant, in-memory fuzzy S · C++ · GPL-3.0 · 2026-10
- [valeriansaliou/sonic](https://github.com/valeriansaliou/sonic) ★21.4k — 🦔 Fast, lightweight & schema-less search backend. An alternative to Elasticsearch that runs on a few MBs of RAM. · Rust · MPL-2.0 · 2026-10
- [quickwit-oss/tantivy](https://github.com/quickwit-oss/tantivy) ★16.2k — Tantivy is a full-text search engine library inspired by Apache Lucene and written in Rust · Rust · MIT · 2026-10
- [opensearch-project/OpenSearch](https://github.com/opensearch-project/OpenSearch) ★13.9k — 🔎 Open source distributed and RESTful search engine. · Java · Apache-2.0 · 2026-10
- [nextapps-de/flexsearch](https://github.com/nextapps-de/flexsearch) ★13.8k — Next-generation full-text search library for Browser and Node.js · JavaScript · Apache-2.0 · 2026-06
- [searx/searx](https://github.com/searx/searx) ★13.6k — Privacy-respecting metasearch engine · Python · AGPL-3.0 · 2026-05
- [PaddlePaddle/PaddleNLP](https://github.com/PaddlePaddle/PaddleNLP) ★13.0k — Easy-to-use and powerful LLM and SLM library with awesome model zoo. · Python · Apache-2.0 · 2026-05
- [manticoresoftware/manticoresearch](https://github.com/manticoresoftware/manticoresearch) ★12.1k — Open-source search database for full-text, vector, and hybrid search with real-time indexing and SQL. · C++ · GPL-3.0 · 2026-10
- [zaidmukaddam/scira](https://github.com/zaidmukaddam/scira) ★11.9k — Scira (Formerly MiniPerplx) is a minimalistic AI-powered search engine that helps you find information on the internet and cites it too. Pow · TypeScript · AGPL-3.0 · 2026-08
- [quickwit-oss/quickwit](https://github.com/quickwit-oss/quickwit) ★11.7k — Cloud-native OSS search engine for observability · Rust · Apache-2.0 · 2026-10
- [edoardottt/awesome-hacker-search-engines](https://github.com/edoardottt/awesome-hacker-search-engines) ★11.3k — A curated list of awesome search engines useful during Penetration testing, Vulnerability assessments, Red/Blue Team operations, Bug Bounty  · Shell · MIT · 2026-10
- [mailpile/Mailpile](https://github.com/mailpile/Mailpile) ★8.8k — A free & open modern, fast email client with user-friendly encryption and privacy features · Python · NOASSERTION · 2023-11
- [qbittorrent/search-plugins](https://github.com/qbittorrent/search-plugins) ★7.1k — Search plugins for qBittorrent search feature · Python · GPL-2.0 · 2026-10
- [lucaong/minisearch](https://github.com/lucaong/minisearch) ★6.2k — Tiny and powerful JavaScript full-text search engine for browser and Node · TypeScript · MIT · 2025-09
- [vcaesar/riot](https://github.com/vcaesar/riot) ★6.1k — Go Open Source, Distributed, Simple and efficient Search Engine · Go · Apache-2.0 · 2026-09
- [nilsherzig/LLocalSearch](https://github.com/nilsherzig/LLocalSearch) ★5.9k — LLocalSearch is a completely locally running search aggregator using LLM Agents. The user can ask a question and the system will use a chain · Go · Apache-2.0 · 2026-03
- [soruly/trace.moe](https://github.com/soruly/trace.moe) ★5.0k — Timestamp Retrieval for Anime Clips Everywhere · MIT · 2026-09
- [marqo-ai/marqo](https://github.com/marqo-ai/marqo) ★5.0k — Ecommerce Search and Discovery - marqo.ai · Python · Apache-2.0 · 2026-09
- [ssrajadh/sentrysearch](https://github.com/ssrajadh/sentrysearch) ★4.6k — Semantic search over videos using Gemini Embedding 2 or Qwen3-VL. · Python · Apache-2.0 · 2026-10
- [cboxdoerfer/fsearch](https://github.com/cboxdoerfer/fsearch) ★4.5k — A fast file search utility for Unix-like systems based on GTK3 · C · GPL-2.0 · 2026-10
- [apache/lucene-solr](https://github.com/apache/lucene-solr) ★4.4k — Apache Lucene and Solr open-source search software · Apache-2.0 · 2026-05
- [unum-cloud/USearch](https://github.com/unum-cloud/USearch) ★4.3k — Fast Open-Source Search & Clustering engine × for Vectors & Arbitrary Objects × in C++, C, Python, JavaScript, Rust, Java, Objective-C, Swif · C++ · Apache-2.0 · 2026-10
- [toshi-search/Toshi](https://github.com/toshi-search/Toshi) ★4.3k — A full-text search engine in rust · Rust · MIT · 2026-06
- [yacy/yacy_search_server](https://github.com/yacy/yacy_search_server) ★4.1k — Distributed Peer-to-Peer Web Search Engine and Intranet Search Appliance · Java · NOASSERTION · 2026-09
- [ravendb/ravendb](https://github.com/ravendb/ravendb) ★4.0k — ACID Document Database · C# · NOASSERTION · 2026-10
- [DO-SAY-GO/tdf](https://github.com/DO-SAY-GO/tdf) ★3.9k — 🌱 TDF - Tree Document Format - a universal file format for web collections · JavaScript · NOASSERTION · 2026-10
- [arpit-omprakash/100ProjectsOfCode](https://github.com/arpit-omprakash/100ProjectsOfCode) ★3.7k — A list of practical knowledge-building projects. · MIT · 2024-04
- [apache/lucene](https://github.com/apache/lucene) ★3.6k — Apache Lucene open-source search software · Java · Apache-2.0 · 2026-10
- [teamtnt/tntsearch](https://github.com/teamtnt/tntsearch) ★3.2k — A fully featured full text search engine written in PHP · PHP · MIT · 2026-08

### Text-to-speech (30)

- [RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) ★62.9k — 1 min voice data can also be used to train a good TTS model! (few shot voice cloning) · Python · MIT · 2026-10
- [coqui-ai/TTS](https://github.com/coqui-ai/TTS) ★46.1k — 🐸💬 - a deep learning toolkit for Text-to-Speech, battle-tested in research and production · Python · MPL-2.0 · 2024-08
- [OpenBMB/VoxCPM](https://github.com/OpenBMB/VoxCPM) ★39.4k — VoxCPM2: Tokenizer-Free TTS for Multilingual Speech Generation, Creative Voice Design, and True-to-Life Cloning · Python · Apache-2.0 · 2026-10
- [myshell-ai/OpenVoice](https://github.com/myshell-ai/OpenVoice) ★37.9k — Instant voice cloning by MIT and MyShell. Audio foundation model. · Python · MIT · 2025-04
- [babysor/MockingBird](https://github.com/babysor/MockingBird) ★36.9k — 🚀Clone a voice in 5 seconds to generate arbitrary speech in real-time · Python · NOASSERTION · 2026-03
- [index-tts/index-tts](https://github.com/index-tts/index-tts) ★24.5k — An Industrial-Level Controllable and Efficient Zero-Shot Text-To-Speech System · Python · NOASSERTION · 2026-09
- [jianchang512/pyvideotrans](https://github.com/jianchang512/pyvideotrans) ★19.4k — Translate the video from one language to another and embed dubbing & subtitles. · Python · GPL-3.0 · 2026-10
- [nari-labs/dia](https://github.com/nari-labs/dia) ★19.4k — A TTS model capable of generating ultra-realistic dialogue in one pass. · Python · Apache-2.0 · 2025-11
- [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) ★15.3k — Speech-to-text, text-to-speech, speaker diarization, speech enhancement, source separation, and VAD using next-gen Kaldi with onnxruntime wi · C++ · Apache-2.0 · 2026-10
- [supertone-oss-archive/supertonic](https://github.com/supertone-oss-archive/supertonic) ★13.8k — Lightning-Fast, On-Device, Multilingual TTS — running natively via ONNX. · Swift · MIT · 2026-09
- [rany2/edge-tts](https://github.com/rany2/edge-tts) ★12.3k — Use Microsoft Edge's online text-to-speech service from Python WITHOUT needing Microsoft Edge · Python · NOASSERTION · 2026-10
- [rhasspy/piper](https://github.com/rhasspy/piper) ★11.3k — A fast, local neural text to speech system · C++ · MIT · 2025-08
- [open-mmlab/Amphion](https://github.com/open-mmlab/Amphion) ★10.3k — Amphion (/æmˈfaɪən/) is a toolkit for Audio, Music, and Speech Generation. Its purpose is to support reproducible research and help junior r · Python · MIT · 2026-03
- [mozilla/TTS](https://github.com/mozilla/TTS) ★10.2k — :robot: :speech_balloon: Deep learning for Text to Speech  (Discussion forum: https://discourse.mozilla.org/c/tts) · Jupyter Notebook · MPL-2.0 · 2023-11
- [netease-youdao/EmotiVoice](https://github.com/netease-youdao/EmotiVoice) ★8.5k — EmotiVoice 😊: a Multi-Voice and Prompt-Controlled TTS Engine · Python · Apache-2.0 · 2026-09
- [Plachtaa/VALL-E-X](https://github.com/Plachtaa/VALL-E-X) ★7.9k — An open source implementation of Microsoft's VALL-E X zero-shot TTS model. Demo is available in https://plachtaa.github.io/vallex/ · Python · MIT · 2024-02
- [jaywalnut310/vits](https://github.com/jaywalnut310/vits) ★7.9k — VITS: Conditional Variational Autoencoder with Adversarial Learning for End-to-End Text-to-Speech · Python · MIT · 2023-12
- [myshell-ai/MeloTTS](https://github.com/myshell-ai/MeloTTS) ★7.7k — High-quality multi-lingual text-to-speech library by MyShell.ai. Support English, Spanish, French, Chinese, Japanese and Korean. · Python · MIT · 2024-12
- [espeak-ng/espeak-ng](https://github.com/espeak-ng/espeak-ng) ★7.0k — eSpeak NG is an open source speech synthesizer that supports more than hundred languages and accents. · C · GPL-3.0 · 2026-09
- [yl4579/StyleTTS2](https://github.com/yl4579/StyleTTS2) ★6.4k — StyleTTS 2: Towards Human-Level Text-to-Speech through Style Diffusion and Adversarial Training with Large Speech Language Models · Python · MIT · 2024-08
- [snakers4/silero-models](https://github.com/snakers4/silero-models) ★6.1k — Silero Models: pre-trained text-to-speech models made embarrassingly simple · Jupyter Notebook · NOASSERTION · 2026-10
- [denizsafak/abogen](https://github.com/denizsafak/abogen) ★6.1k — Generate audiobooks from EPUBs, PDFs and text with synchronized captions. · Python · MIT · 2026-10
- [liuzhao1225/YouDub-webui](https://github.com/liuzhao1225/YouDub-webui) ★5.7k — Open-source AI video localization and dubbing for YouTube/Bilibili: speech recognition, subtitle translation, voice cloning, audio mixing an · TypeScript · Apache-2.0 · 2026-10
- [remsky/Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) ★5.6k — Dockerized OpenAI-compatible wrapper for Kokoro-82M text-to-speech w/multiplatform CPU, AMD, NVIDIA GPU PyTorch; multi-speaker, clone-tuning · Python · Apache-2.0 · 2026-10
- [MoonInTheRiver/DiffSinger](https://github.com/MoonInTheRiver/DiffSinger) ★4.9k — DiffSinger: Singing Voice Synthesis via Shallow Diffusion Mechanism (SVS & TTS); AAAI 2022; Official code · Python · MIT · 2026-07
- [gradio-app/fastrtc](https://github.com/gradio-app/fastrtc) ★4.6k — The python library for real-time communication · JavaScript · MIT · 2026-01
- [OpenMOSS/MOSS-TTS-Nano](https://github.com/OpenMOSS/MOSS-TTS-Nano) ★4.5k — A 100M-parameter multilingual TTS model for real-time CPU inference, voice cloning, and 48 kHz stereo generation · Python · Apache-2.0 · 2026-09
- [collabora/WhisperLive](https://github.com/collabora/WhisperLive) ★4.3k — A nearly-live implementation of OpenAI's Whisper. · Python · MIT · 2026-10
- [OpenMOSS/MOSS-TTS](https://github.com/OpenMOSS/MOSS-TTS) ★4.2k — An open-source model family for long-form speech, dialogue synthesis, voice design, sound effects, and real-time streaming TTS · Python · Apache-2.0 · 2026-09
- [metavoiceio/metavoice-src](https://github.com/metavoiceio/metavoice-src) ★4.2k — Foundational model for human-like, expressive TTS · Python · Apache-2.0 · 2024-07

### OCR (30)

- [opendatalab/MinerU](https://github.com/opendatalab/MinerU) ★81.9k — Transforms complex documents like PDFs and Office docs into LLM-ready markdown/JSON for your Agentic workflows. · Python · NOASSERTION · 2026-10
- [tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract) ★77.0k — Tesseract Open Source OCR Engine (main repository) · C++ · Apache-2.0 · 2026-10
- [hiroi-sora/Umi-OCR](https://github.com/hiroi-sora/Umi-OCR) ★48.0k — OCR software, free and offline. 开源、免费的离线OCR软件。支持截屏/批量导入图片，PDF文档识别，排除水印/页眉页脚，扫描/生成二维码。内置多国语言库。 · Python · MIT · 2025-11
- [ShareX/ShareX](https://github.com/ShareX/ShareX) ★40.1k — ShareX is a free and open-source application that enables users to capture or record any area of their screen with a single keystroke. It al · C# · GPL-3.0 · 2026-10
- [naptha/tesseract.js](https://github.com/naptha/tesseract.js) ★38.8k — Pure Javascript OCR for more than 100 Languages 📖🎉🖥 · JavaScript · Apache-2.0 · 2026-05
- [ocrmypdf/OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) ★35.0k — OCRmyPDF adds an OCR text layer to scanned PDF files, allowing them to be searched · Python · MPL-2.0 · 2026-10
- [JaidedAI/EasyOCR](https://github.com/JaidedAI/EasyOCR) ★30.1k — Ready-to-use OCR with 80+ supported languages and all popular writing scripts including Latin, Chinese, Arabic, Devanagari, Cyrillic and etc · Python · Apache-2.0 · 2025-12
- [pot-app/pot-desktop](https://github.com/pot-app/pot-desktop) ★19.4k — 🌈一个跨平台的划词翻译和OCR软件 | A cross-platform software for text translation and recognition. · JavaScript · GPL-3.0 · 2026-07
- [lukas-blecher/LaTeX-OCR](https://github.com/lukas-blecher/LaTeX-OCR) ★16.6k — pix2tex: Using a ViT to convert images of equations into LaTeX code. · Python · MIT · 2025-01
- [Unstructured-IO/unstructured](https://github.com/Unstructured-IO/unstructured) ★15.6k — Convert documents to structured data effortlessly. Unstructured is open-source ETL solution for transforming complex documents into clean, s · HTML · Apache-2.0 · 2026-10
- [tisfeng/Easydict](https://github.com/tisfeng/Easydict) ★15.0k — 一个简洁优雅的词典翻译 macOS App。开箱即用，支持离线 OCR 识别，支持有道词典，🍎 苹果系统词典，🍎 苹果系统翻译，OpenAI，Gemini，DeepL，Google，Bing，腾讯，百度，阿里，小牛，彩云和火山翻译。A concise and elegant Di · Swift · GPL-3.0 · 2026-10
- [sml2h3/ddddocr](https://github.com/sml2h3/ddddocr) ★14.8k — 带带弟弟 通用验证码识别OCR pypi版 · Python · MIT · 2026-03
- [HIllya51/LunaTranslator](https://github.com/HIllya51/LunaTranslator) ★13.8k — 视觉小说翻译器 / Visual Novel Translator · C++ · GPL-3.0 · 2026-10
- [run-llama/liteparse](https://github.com/run-llama/liteparse) ★12.9k — A fast, helpful, and open-source document parser · Rust · Apache-2.0 · 2026-10
- [datalab-to/chandra](https://github.com/datalab-to/chandra) ★12.5k — OCR model that handles complex tables, forms, handwriting with full layout. · Python · Apache-2.0 · 2026-06
- [DayBreak-u/chineseocr_lite](https://github.com/DayBreak-u/chineseocr_lite) ★12.3k — 超轻量级中文ocr，支持竖排文字识别, 支持ncnn、mnn、tnn推理 ( dbnet(1.8M) + crnn(2.5M) + anglenet(378KB)) 总模型仅4.7M · C++ · GPL-2.0 · 2026-05
- [getomni-ai/zerox](https://github.com/getomni-ai/zerox) ★12.2k — OCR & Document Extraction using vision models · TypeScript · MIT · 2025-05
- [pymupdf/PyMuPDF](https://github.com/pymupdf/PyMuPDF) ★10.9k — PyMuPDF is a high performance Python library for data extraction, analysis, conversion & manipulation of PDF (and other) documents. · Python · AGPL-3.0 · 2026-10
- [CVHub520/X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling) ★10.7k — X-AnyLabeling: A lightweight, efficient, and unified cross-platform desktop application for annotating text, image, video, and multimodal da · Python · GPL-3.0 · 2026-10
- [zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator) ★10.5k — Translate manga/image 一键翻译各类图片内文字 https://cotrans.touhou.ai/ (no longer working) · Python · GPL-3.0 · 2026-10
- [ripperhe/Bob](https://github.com/ripperhe/Bob) ★9.8k — Bob 是一款 macOS 平台的翻译和 OCR 软件。 · NOASSERTION · 2025-12
- [YaoFANGUK/video-subtitle-extractor](https://github.com/YaoFANGUK/video-subtitle-extractor) ★9.6k — 视频硬字幕提取，生成srt文件。无需申请第三方API，本地实现文本识别。基于深度学习的视频字幕提取框架，包含字幕区域检测、字幕内容提取。A GUI tool for extracting hard-coded subtitle (hardsub) from videos and  · Python · Apache-2.0 · 2026-04
- [bytedance/Dolphin](https://github.com/bytedance/Dolphin) ★9.1k — The official repo for “Dolphin: Document Image Parsing via Heterogeneous Anchor Prompting”, ACL, 2025. · Python · NOASSERTION · 2026-03
- [STranslate/STranslate](https://github.com/STranslate/STranslate) ★8.3k — A ready-to-go translation ocr tool developed with WPF/WPF 开发的一款即用即走的翻译、OCR工具 · C# · MIT · 2026-09
- [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR) ★8.2k — 📄 Awesome OCR multiple programing languages toolkits based on ONNX Runtime, OpenVINO, MNN, PaddlePaddle, TensorRT and PyTorch. · Python · Apache-2.0 · 2026-10
- [adithya-s-k/omniparse](https://github.com/adithya-s-k/omniparse) ★7.9k — Ingest, parse, and optimize any data format ➡️ from documents to multimedia ➡️ for enhanced compatibility with GenAI frameworks · Python · GPL-3.0 · 2025-12
- [the-paperless-project/paperless](https://github.com/the-paperless-project/paperless) ★7.9k — Scan, index, and archive all of your paper documents · Python · GPL-3.0 · 2021-04
- [microsoft/ailab](https://github.com/microsoft/ailab) ★7.9k — Experience, Learn and Code the latest breakthrough innovations with Microsoft AI · C# · MIT · 2024-06
- [tesseract-ocr/tessdata](https://github.com/tesseract-ocr/tessdata) ★7.7k — Trained models with fast variant of the "best" LSTM models + legacy models · Apache-2.0 · 2024-03
- [zai-org/GLM-OCR](https://github.com/zai-org/GLM-OCR) ★7.5k — GLM-OCR: Accurate ×  Fast × Comprehensive · Python · Apache-2.0 · 2026-10

### PDF tooling (30)

- [microsoft/markitdown](https://github.com/microsoft/markitdown) ★190.5k — Python tool for converting files and office documents to Markdown. · Python · MIT · 2026-10
- [justjavac/free-programming-books-zh_CN](https://github.com/justjavac/free-programming-books-zh_CN) ★119.2k — :books: 免费的计算机编程类中文书籍，欢迎投稿 · GPL-3.0 · 2026-07
- [Stirling-Tools/Stirling-PDF](https://github.com/Stirling-Tools/Stirling-PDF) ★94.3k — #1 PDF Application on GitHub that lets you edit PDFs on any device anywhere · TypeScript · NOASSERTION · 2026-10
- [docling-project/docling](https://github.com/docling-project/docling) ★69.0k — Get your documents ready for gen AI · Python · MIT · 2026-10
- [hehonghui/awesome-english-ebooks](https://github.com/hehonghui/awesome-english-ebooks) ★38.1k — 经济学人(含音频)、纽约客、卫报、连线、大西洋月刊等英语杂志免费下载,支持epub、mobi、pdf格式, 每周更新 · CSS · NOASSERTION · 2026-10
- [koreader/koreader](https://github.com/koreader/koreader) ★30.3k — An ebook reader application supporting PDF, DjVu, EPUB, FB2 and many more formats, running on Cervantes, Kindle, Kobo, PocketBook and Androi · Lua · AGPL-3.0 · 2026-10
- [posquit0/Awesome-CV](https://github.com/posquit0/Awesome-CV) ★28.7k — :page_facing_up: Awesome CV is LaTeX template for your outstanding job application · TeX · LPPL-1.3c · 2026-09
- [koodo-reader/koodo-reader](https://github.com/koodo-reader/koodo-reader) ★28.5k — A modern ebook manager and reader with sync and backup capacities for Windows, macOS, Linux, Android, iOS and Web · JavaScript · AGPL-3.0 · 2026-10
- [forthespada/CS-Books](https://github.com/forthespada/CS-Books) ★27.5k — 🔥🔥超过1000本的计算机经典书籍、个人笔记资料以及本人在各平台发表文章中所涉及的资源等。书籍资源包括C/C++、Java、Python、Go语言、数据结构与算法、操作系统、后端架构、计算机系统知识、数据库、计算机网络、设计模式、前端、汇编以及校招社招各种面经~ · NOASSERTION · 2025-11
- [readest/readest](https://github.com/readest/readest) ★25.3k — Readest is a modern, feature-rich ebook reader designed for avid readers offering seamless cross-platform access, powerful tools, and an int · TypeScript · AGPL-3.0 · 2026-10
- [dream-num/univer](https://github.com/dream-num/univer) ★22.6k — The Office Harness for AI Agents — Spreadsheets, Docs, Slides, Canvas, Relational Tables, and PDF in one runtime. · TypeScript · Apache-2.0 · 2026-10
- [firecrawl/pdf-inspector](https://github.com/firecrawl/pdf-inspector) ★19.7k — Fast Rust library for PDF inspection, classification, and text extraction. Intelligently detects scanned vs text-based PDFs to enable smart  · Rust · MIT · 2026-10
- [docusealco/docuseal](https://github.com/docusealco/docuseal) ★18.7k — Open source DocuSign alternative. Create, fill, and sign digital documents ✍️ · Ruby · AGPL-3.0 · 2026-10
- [sumatrapdfreader/sumatrapdf](https://github.com/sumatrapdfreader/sumatrapdf) ★17.8k — SumatraPDF reader · C · GPL-3.0 · 2026-10
- [diegomura/react-pdf](https://github.com/diegomura/react-pdf) ★16.8k — 📄  Create PDF files using React · TypeScript · MIT · 2026-10
- [salomonelli/best-resume-ever](https://github.com/salomonelli/best-resume-ever) ★16.5k — :necktie: :briefcase: Build fast :rocket: and easy multiple beautiful resumes and create your best CV ever! Made with Vue and LESS. · Vue · MIT · 2024-06
- [iamgio/quarkdown](https://github.com/iamgio/quarkdown) ★16.3k — 🪐 Markdown with superpowers: from ideas to papers, presentations, websites, books, and knowledge bases. · Kotlin · GPL-3.0 · 2026-10
- [xournalpp/xournalpp](https://github.com/xournalpp/xournalpp) ★15.5k — Xournal++ is a handwriting notetaking software with PDF annotation support. Written in C++ with GTK3, supporting Linux (e.g. Ubuntu, Debian, · C++ · GPL-2.0 · 2026-10
- [documenso/documenso](https://github.com/documenso/documenso) ★15.4k — The Open Source DocuSign Alternative. · TypeScript · AGPL-3.0 · 2026-10
- [KAYOKG/BibliotecaDev](https://github.com/KAYOKG/BibliotecaDev) ★15.1k — 📚 Biblioteca de livros essenciais da área da programação. (Confira o meu novo projeto `SendScriptWhatsapp`) · MIT · 2026-05
- [T8RIN/ImageToolbox](https://github.com/T8RIN/ImageToolbox) ★15.0k — 🖼️ Image Toolbox is a powerful app for advanced image manipulation. It offers dozens of features, from basic tools like crop and draw to fil · Kotlin · Apache-2.0 · 2026-10
- [kekingcn/kkFileView](https://github.com/kekingcn/kkFileView) ★14.8k — Universal File Online Preview Project based on Spring-Boot · Java · NOASSERTION · 2026-10
- [storytold/pdfcraft](https://github.com/storytold/pdfcraft) ★14.7k — PdfCraft: An open-source PDF reader and editor written by scratch in pure Rust · Rust · Apache-2.0 · 2026-10
- [janishar/mit-deep-learning-book-pdf](https://github.com/janishar/mit-deep-learning-book-pdf) ★14.3k — MIT Deep Learning Book in PDF format (complete and parts) by Ian Goodfellow, Yoshua Bengio and Aaron Courville · Java · NOASSERTION · 2026-02
- [QuestPDF/QuestPDF](https://github.com/QuestPDF/QuestPDF) ★14.2k — QuestPDF is a modern library for PDF document generation. Its fluent C# API lets you design complex layouts with clean, readable code. Creat · C# · NOASSERTION · 2026-09
- [wmjordan/PDFPatcher](https://github.com/wmjordan/PDFPatcher) ★12.7k — PDF补丁丁——PDF工具箱，可以编辑书签、剪裁旋转页面、解除限制、提取或合并文档，探查文档结构，提取图片、转成图片等等 · C# · NOASSERTION · 2026-10
- [0voice/expert_readed_books](https://github.com/0voice/expert_readed_books) ★12.7k — 2021年最新总结，推荐工程师合适读本，计算机科学，软件技术，创业，思想类，数学类，人物传记书籍 · NOASSERTION · 2025-06
- [windingwind/zotero-pdf-translate](https://github.com/windingwind/zotero-pdf-translate) ★12.1k — Translate PDF, EPub, webpage, metadata, annotations, notes to the target language. Support 20+ translate services. · TypeScript · AGPL-3.0 · 2026-10
- [tw93/Kami](https://github.com/tw93/Kami) ★12.0k — 👩‍🚒 Good content deserves good paper. Layout rules and templates that let AI agents export PDF, PNG and editable PowerPoint. · HTML · MIT · 2026-10
- [Kareadita/Kavita](https://github.com/Kareadita/Kavita) ★11.9k — Kavita is a fast, feature rich, cross platform reading server. Built with the goal of being a full solution for all your reading needs. Setu · C# · GPL-3.0 · 2026-10

### Maps & geo (30)

- [Leaflet/Leaflet](https://github.com/Leaflet/Leaflet) ★45.8k — 🍃 JavaScript library for mobile-friendly interactive maps 🇺🇦 · JavaScript · BSD-2-Clause · 2026-10
- [react-native-maps/react-native-maps](https://github.com/react-native-maps/react-native-maps) ★16.0k — React Native Mapview component for iOS + Android · TypeScript · MIT · 2026-10
- [microg/GmsCore](https://github.com/microg/GmsCore) ★14.9k — Free implementation of Play Services · Java · Apache-2.0 · 2026-09
- [visgl/deck.gl](https://github.com/visgl/deck.gl) ★14.7k — WebGL2 powered visualization framework · TypeScript · MIT · 2026-10
- [marceloprates/prettymaps](https://github.com/marceloprates/prettymaps) ★14.3k — Draw pretty maps from OpenStreetMap data! Built with osmnx +matplotlib + shapely · Python · AGPL-3.0 · 2026-07
- [originalankur/maptoposter](https://github.com/originalankur/maptoposter) ★14.2k — Transform your favorite cities into beautiful, minimalist designs. MapToPoster lets you create and export visually striking map posters with · Python · MIT · 2026-08
- [openlayers/openlayers](https://github.com/openlayers/openlayers) ★12.6k — OpenLayers · JavaScript · BSD-2-Clause · 2026-10
- [mapbox/mapbox-gl-js](https://github.com/mapbox/mapbox-gl-js) ★12.4k — Interactive, thoroughly customizable maps in the browser, powered by vector tiles and WebGL · TypeScript · NOASSERTION · 2026-10
- [Freika/dawarich](https://github.com/Freika/dawarich) ★10.7k — Your favorite self-hostable alternative to Google Timeline (Google Location History) · Ruby · AGPL-3.0 · 2026-10
- [python-visualization/folium](https://github.com/python-visualization/folium) ★7.4k — Python Data. Leaflet.js Maps. · Python · NOASSERTION · 2026-10
- [GoogleMapReact/google-map-react](https://github.com/GoogleMapReact/google-map-react) ★6.5k — Google map library for react that allows rendering components as markers :tada: · JavaScript · MIT · 2026-02
- [hyperknot/openfreemap](https://github.com/hyperknot/openfreemap) ★6.2k — Free and open-source map hosting solution with custom styles for websites and apps, using OpenStreetMap data · Python · NOASSERTION · 2026-10
- [Live-Charts/Live-Charts](https://github.com/Live-Charts/Live-Charts) ★5.5k — Simple, flexible, interactive & powerful charts, maps and gauges for .Net · C# · MIT · 2023-03
- [wbkd/awesome-d3](https://github.com/wbkd/awesome-d3) ★5.3k — A list of D3 libraries, plugins and utilities · NOASSERTION · 2023-01
- [mark-when/markwhen](https://github.com/mark-when/markwhen) ★4.9k — Make a cascading timeline from markdown-like text. Supports simple American/European date styles, ISO8601, images, links, locations, and mor · HTML · MIT · 2023-12
- [maptalks/maptalks.js](https://github.com/maptalks/maptalks.js) ★4.5k — A light and plugable JavaScript library for integrated 2D/3D maps. · HTML · NOASSERTION · 2026-09
- [geoserver/geoserver](https://github.com/geoserver/geoserver) ★4.5k — Official GeoServer repository · Java · NOASSERTION · 2026-10
- [mapbox/mapbox-gl-native](https://github.com/mapbox/mapbox-gl-native) ★4.5k — Interactive, thoroughly customizable maps in native Android, iOS, macOS, Node.js, and Qt applications, powered by vector tiles and OpenGL · C++ · NOASSERTION · 2023-07
- [WebODM/WebODM](https://github.com/WebODM/WebODM) ★4.2k — User-friendly, commercial-grade software for processing aerial imagery. ✈️ Download it for free! · Python · AGPL-3.0 · 2026-10
- [yousifamanuel/terraink](https://github.com/yousifamanuel/terraink) ★4.2k — Terraink: The Cartographic Poster Engine that creates unique and customizable map posters · TypeScript · NOASSERTION · 2026-09
- [antvis/L7](https://github.com/antvis/L7) ★4.1k — 🌎 Large-scale WebGL-powered Geospatial Data Visualization analysis engine. · TypeScript · MIT · 2026-10
- [maplibre/martin](https://github.com/maplibre/martin) ★4.0k — Blazing fast and lightweight PostGIS, MBtiles and PMtiles tile server, tile generation, and mbtiles tooling. · Rust · Apache-2.0 · 2026-10
- [googlemaps/android-maps-utils](https://github.com/googlemaps/android-maps-utils) ★3.6k — Maps SDK for Android Utility Library · Kotlin · Apache-2.0 · 2026-10
- [alyssaxuu/mapus](https://github.com/alyssaxuu/mapus) ★3.5k — A map tool with real-time collaboration 🗺️ · JavaScript · MIT · 2022-07
- [zcreativelabs/react-simple-maps](https://github.com/zcreativelabs/react-simple-maps) ★3.4k — Composable SVG map charts for data visualization in React · TypeScript · MIT · 2026-09
- [openmaptiles/openmaptiles](https://github.com/openmaptiles/openmaptiles) ★3.2k — OpenMapTiles Vector Tile Schema Implementation · PLpgSQL · NOASSERTION · 2026-07
- [googlemaps/google-maps-services-js](https://github.com/googlemaps/google-maps-services-js) ★3.1k — Node.js client library for Google Maps API Web Services · TypeScript · Apache-2.0 · 2026-10
- [fleaflet/flutter_map](https://github.com/fleaflet/flutter_map) ★3.0k — Flutter's №1 non-commercially aimed map client: it's easy-to-use, versatile, vendor-free, fully cross-platform, and 100% pure-Flutter · Dart · BSD-3-Clause · 2026-09
- [headwaymaps/headway](https://github.com/headwaymaps/headway) ★3.0k — Self-hostable maps stack, powered by OpenStreetMap. · Rust · Apache-2.0 · 2026-10
- [kylecorry31/Trail-Sense](https://github.com/kylecorry31/Trail-Sense) ★2.9k — An Android app that uses your phone's sensors to assist with wilderness treks or survival situations. · Kotlin · MIT · 2026-10

### Data visualization (30)

- [d3/d3](https://github.com/d3/d3) ★113.8k — Bring data to life with SVG, Canvas and HTML. :bar_chart::chart_with_upwards_trend::tada: · Shell · ISC · 2026-05
- [apache/echarts](https://github.com/apache/echarts) ★67.5k — Apache ECharts is a powerful, interactive charting and data visualization library for browser · TypeScript · Apache-2.0 · 2026-10
- [metabase/metabase](https://github.com/metabase/metabase) ★49.7k — The easy-to-use open source Business Intelligence and Embedded Analytics tool that lets everyone work with data :bar_chart: · Clojure · NOASSERTION · 2026-10
- [algorithm-visualizer/algorithm-visualizer](https://github.com/algorithm-visualizer/algorithm-visualizer) ★48.9k — :fireworks:Interactive Online Platform that Visualizes Algorithms from Code · JavaScript · MIT · 2024-06
- [AykutSarac/jsoncrack.com](https://github.com/AykutSarac/jsoncrack.com) ★44.5k — ✨ Innovative and open-source visualization application that transforms various data formats, such as JSON, YAML, XML and CSV into interactiv · TypeScript · Apache-2.0 · 2026-09
- [getredash/redash](https://github.com/getredash/redash) ★28.8k — Make Your Company Data Driven. Connect to any data source, easily visualize, dashboard and share your data. · Python · BSD-2-Clause · 2026-10
- [chartdb/chartdb](https://github.com/chartdb/chartdb) ★23.0k — Database diagrams editor that allows you to visualize and design your DB with a single query. · TypeScript · AGPL-3.0 · 2026-09
- [thingsboard/thingsboard](https://github.com/thingsboard/thingsboard) ★22.6k — All-in-one IoT Platform - Device management, data collection, processing and visualization. · Java · NOASSERTION · 2026-10
- [airbnb/visx](https://github.com/airbnb/visx) ★21.1k — 🐯 visx | visualization components · TypeScript · MIT · 2026-06
- [bokeh/bokeh](https://github.com/bokeh/bokeh) ★20.5k — Interactive Data Visualization in the browser, from  Python · TypeScript · BSD-3-Clause · 2026-10
- [motion-canvas/motion-canvas](https://github.com/motion-canvas/motion-canvas) ★19.4k — Visualize Your Ideas With Code · TypeScript · MIT · 2026-07
- [plotly/plotly.py](https://github.com/plotly/plotly.py) ★18.8k — The interactive graphing library for Python :sparkles: · Python · MIT · 2026-10
- [plotly/plotly.js](https://github.com/plotly/plotly.js) ★18.4k — Open-source JavaScript charting library behind Plotly and Dash · JavaScript · MIT · 2026-10
- [Kanaries/pygwalker](https://github.com/Kanaries/pygwalker) ★16.0k — PyGWalker: Turn your dataframe into an interactive UI for visual analysis · Python · Apache-2.0 · 2026-09
- [apexcharts/apexcharts.js](https://github.com/apexcharts/apexcharts.js) ★15.2k — 📊 Interactive JavaScript Charts built on SVG · JavaScript · NOASSERTION · 2026-10
- [isl-org/Open3D](https://github.com/isl-org/Open3D) ★14.1k — Open3D: A Modern Library for 3D Data Processing · C++ · NOASSERTION · 2026-09
- [antvis/G2](https://github.com/antvis/G2) ★12.6k — 📊 The concise and progressive visualization grammar. · TypeScript · MIT · 2026-10
- [antvis/G6](https://github.com/antvis/G6) ★12.3k — ♾ A Graph Visualization Framework in JavaScript. · TypeScript · MIT · 2026-10
- [keplergl/kepler.gl](https://github.com/keplergl/kepler.gl) ★12.0k — Kepler.gl is a powerful open source geospatial analysis tool for large-scale data sets. · TypeScript · MIT · 2026-10
- [vega/vega](https://github.com/vega/vega) ★12.0k — A visualization grammar. · JavaScript · BSD-3-Clause · 2026-10
- [meshery/meshery](https://github.com/meshery/meshery) ★12.0k — Meshery, the cloud native manager · TypeScript · Apache-2.0 · 2026-10
- [didi/LogicFlow](https://github.com/didi/LogicFlow) ★11.7k — A flow chart editing framework focus on business customization.  专注于业务自定义的流程图编辑框架，支持实现脑图、ER图、UML、工作流等各种图编辑场景。 · TypeScript · Apache-2.0 · 2026-10
- [rerun-io/rerun](https://github.com/rerun-io/rerun) ★11.6k — Visualize, query, and stream to train on multimodal robotics data. · Rust · Apache-2.0 · 2026-10
- [cytoscape/cytoscape.js](https://github.com/cytoscape/cytoscape.js) ★11.2k — Graph theory (network) library for visualisation and analysis · JavaScript · MIT · 2026-10
- [projectstorm/react-diagrams](https://github.com/projectstorm/react-diagrams) ★9.4k — a super simple, no-nonsense diagramming library written in react that just works · TypeScript · MIT · 2025-04
- [poloclub/cnn-explainer](https://github.com/poloclub/cnn-explainer) ★9.1k — Learning Convolutional Neural Networks with Interactive Visualization. · JavaScript · MIT · 2023-10
- [rawgraphs/rawgraphs-app](https://github.com/rawgraphs/rawgraphs-app) ★9.0k — A web interface to create custom vector-based visualizations on top of RAWGraphs core · JavaScript · Apache-2.0 · 2026-10
- [poloclub/transformer-explainer](https://github.com/poloclub/transformer-explainer) ★9.0k — Transformer Explained Visually: Learn How LLM Transformer Models Work with Interactive Visualization · JavaScript · MIT · 2026-06
- [uber/react-vis](https://github.com/uber/react-vis) ★8.8k — Data Visualization Components · JavaScript · MIT · 2024-12
- [vaexio/vaex](https://github.com/vaexio/vaex) ★8.5k — Out-of-Core hybrid Apache Arrow/NumPy DataFrame for Python, ML, visualization and exploration of big tabular data at a billion rows per seco · Python · MIT · 2026-04

### Market data & trading (30)

- [ccxt/ccxt](https://github.com/ccxt/ccxt) ★44.4k — A unified trading API with more than 100 crypto exchanges and prediction markets in JavaScript / TypeScript / Python / C# / PHP / Go / Java  · Python · MIT · 2026-10
- [ranaroussi/yfinance](https://github.com/ranaroussi/yfinance) ★25.5k — Download market data from Yahoo! Finance's API · Python · Apache-2.0 · 2026-10
- [questdb/questdb](https://github.com/questdb/questdb) ★17.4k — QuestDB is a high performance, open-source, time-series database · Java · Apache-2.0 · 2026-10
- [simonlin1212/a-stock-data](https://github.com/simonlin1212/a-stock-data) ★10.9k — A股全栈数据工具包：行情K线·当日逐笔·研报·信号·资金面·新闻·财务·公告·打板·ETF期权·舆情·宏观利率·期货大宗(含大商所日K)·事件驱动·可转债 | 15层·87端点·34数据源·除iwencai外免Key | A-share data for AI agents: K · Python · Apache-2.0 · 2026-10
- [1nchaos/adata](https://github.com/1nchaos/adata) ★5.3k — 免费开源A股量化交易数据库； 专注A股，专注量化，向阳而生； 开放、纯净、持续、为Ai(爱)发电。为个人量化交易而生，保卫3000点，珍惜底部机会......【股票数据，股票行情数据，股票量化数据，股票交易数据，k线行情数据，股票概念数据，股票数据接口，行情数据接口，量化交易数据 · Python · Apache-2.0 · 2025-12
- [matplotlib/mplfinance](https://github.com/matplotlib/mplfinance) ★4.5k — Financial Markets Data Visualization using Matplotlib · Python · NOASSERTION · 2024-08
- [ctubio/Krypto-trading-bot](https://github.com/ctubio/Krypto-trading-bot) ★3.7k — Self-hosted crypto trading bot (automated high frequency market making) written in C++ · C++ · NOASSERTION · 2024-12
- [binance/binance-connector-python](https://github.com/binance/binance-connector-python) ★3.0k — Simple connector to Binance Public API · Python · MIT · 2026-10
- [bmoscon/cryptofeed](https://github.com/bmoscon/cryptofeed) ★2.9k — Cryptocurrency Exchange Websocket Data Feed Handler · Python · NOASSERTION · 2026-10
- [binance/binance-public-data](https://github.com/binance/binance-public-data) ★2.5k — Details on how to get Binance public data · Python · NOASSERTION · 2026-09
- [gloom-sh/gloomberb](https://github.com/gloom-sh/gloomberb) ★2.4k — Finance terminal, in your terminal. · TypeScript · NOASSERTION · 2026-10
- [pmxt-dev/pmxt](https://github.com/pmxt-dev/pmxt) ★2.2k — CCXT for prediction markets. PMXT is a unified API for trading on Polymarket, Kalshi, and more. · TypeScript · MIT · 2026-09
- [cuemacro/findatapy](https://github.com/cuemacro/findatapy) ★2.1k — Python library to download market data via Bloomberg, Eikon, Quandl, Yahoo etc. · Python · Apache-2.0 · 2026-07
- [alpacahq/alpaca-trade-api-python](https://github.com/alpacahq/alpaca-trade-api-python) ★1.9k — Python client for Alpaca's trade API · Python · Apache-2.0 · 2024-12
- [simonlin1212/global-stock-data](https://github.com/simonlin1212/global-stock-data) ★1.7k — 美股与全球市场数据工具包（给 AI 编程助手用）：官方源优先、零鉴权、标注合规级别 | US & global market data for AI coding assistants — zero-auth, official sources. CBOE options + 0 · Apache-2.0 · 2026-10
- [binance/binance-api-postman](https://github.com/binance/binance-api-postman) ★1.6k — Postman collection for Binance Public API, including spot, margin, futures, etc. · MIT · 2026-10
- [alpacahq/alpaca-py](https://github.com/alpacahq/alpaca-py) ★1.6k — The Official Python SDK for Alpaca API · Python · Apache-2.0 · 2026-10
- [binance/binance-futures-connector-python](https://github.com/binance/binance-futures-connector-python) ★1.2k — Simple python connector to Binance Futures API · Python · MIT · 2025-07
- [visualHFT/VisualHFT](https://github.com/visualHFT/VisualHFT) ★1.2k — VisualHFT Terminal: open-source observability and decision terminal for electronic trading desks. Live Level 2 order books, microstructure a · C# · Apache-2.0 · 2026-10
- [TreborNamor/TradingView-Machine-Learning-GUI](https://github.com/TreborNamor/TradingView-Machine-Learning-GUI) ★1.0k — HyperView is a terminal-first TradingView strategy lab for downloading market data, backtesting Python strategies with Pine-like behavior, a · Python · MIT · 2026-08
- [tradecatlabs/tradecat-public](https://github.com/tradecatlabs/tradecat-public) ★959 — 交易猫数据系统 · Python · MIT · 2026-09
- [BitcoinExchangeFH/BitcoinExchangeFH](https://github.com/BitcoinExchangeFH/BitcoinExchangeFH) ★949 — Cryptocurrency exchange market data feed handler · Python · NOASSERTION · 2023-11
- [Leo4815162342/dukascopy-node](https://github.com/Leo4815162342/dukascopy-node) ★930 — ✨ Download historical and real-time price tick data for Crypto, Stocks, ETFs, CFDs, Forex via CLI and Node.js ✨ · TypeScript · MIT · 2026-07
- [dpguthrie/yahooquery](https://github.com/dpguthrie/yahooquery) ★919 — Python wrapper for an unofficial Yahoo Finance API · Python · MIT · 2025-05
- [komako-workshop/digital-oracle](https://github.com/komako-workshop/digital-oracle) ★896 — AI agent skill that answers macro questions — housing, gold, BTC, geopolitics — with probability estimates mined from 13 financial data sour · Python · MIT · 2026-07
- [greyblake/ta-rs](https://github.com/greyblake/ta-rs) ★870 — Technical analysis library for Rust language · Rust · MIT · 2024-07
- [TickDB/tickdb-unified-realtime-marketdata-api](https://github.com/TickDB/tickdb-unified-realtime-marketdata-api) ★867 — TickDB: AI-native real time stock API and market data API for US/HK/CN stocks, forex, futures, crypto, indices and commodities. Skill, CLI,  · Python · MIT · 2026-10
- [alpacahq/example-scalping](https://github.com/alpacahq/example-scalping) ★851 — A working example algorithm for scalping strategy trading multiple stocks concurrently using python asyncio · Python · NOASSERTION · 2023-10
- [guanquann/Stocksera](https://github.com/guanquann/Stocksera) ★782 — Finance application that provides more than 60 different alternative data to retail investors · JavaScript · MIT · 2024-08
- [defeat-beta/defeatbeta-api](https://github.com/defeat-beta/defeatbeta-api) ★782 — An open-source alternative to Yahoo Finance's market data APIs with higher reliability. · Python · Apache-2.0 · 2026-10

### Awesome lists (meta) (30)

- [sindresorhus/awesome](https://github.com/sindresorhus/awesome) ★519.7k — 😎 Awesome lists about all kinds of interesting topics [NOTE: Pull requests are temporarily disabled until I have a chance to catch up with t · CC0-1.0 · 2026-09
- [vinta/awesome-python](https://github.com/vinta/awesome-python) ★327.8k — The definitive list that answers "I want to do X in Python, which tool should I use?" · Python · NOASSERTION · 2026-10
- [avelino/awesome-go](https://github.com/avelino/awesome-go) ★188.7k — A curated list of awesome Go frameworks, libraries and software · Go · MIT · 2026-10
- [Hack-with-Github/Awesome-Hacking](https://github.com/Hack-with-Github/Awesome-Hacking) ★122.7k — A collection of various awesome lists for hackers, pentesters and security researchers · CC0-1.0 · 2026-07
- [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md) ★121.7k — A collection of DESIGN.md files analysis by popular brand design systems. Drop one into your project and let coding agents generate a matchi · MIT · 2026-10
- [MunGell/awesome-for-beginners](https://github.com/MunGell/awesome-for-beginners) ★90.3k — A list of awesome beginners-friendly projects. · NOASSERTION · 2026-10
- [DopplerHQ/awesome-interview-questions](https://github.com/DopplerHQ/awesome-interview-questions) ★85.0k — :octocat: A curated awesome list of lists of interview questions. Feel free to contribute! :mortar_board: · NOASSERTION · 2024-07
- [awesomedata/awesome-public-datasets](https://github.com/awesomedata/awesome-public-datasets) ★79.5k — A topic-centric list of HQ open datasets. · MIT · 2026-10
- [FortAwesome/Font-Awesome](https://github.com/FortAwesome/Font-Awesome) ★77.0k — The iconic SVG, font, and CSS toolkit · JavaScript · NOASSERTION · 2026-07
- [enaqx/awesome-react](https://github.com/enaqx/awesome-react) ★74.9k — A collection of awesome things regarding React ecosystem · NOASSERTION · 2026-09
- [binhnguyennus/awesome-scalability](https://github.com/binhnguyennus/awesome-scalability) ★74.8k — The Patterns of Scalable, Reliable, and Performant Large-Scale Systems · MIT · 2026-01
- [josephmisiti/awesome-machine-learning](https://github.com/josephmisiti/awesome-machine-learning) ★74.6k — A curated list of awesome Machine Learning frameworks, libraries and software. · Python · NOASSERTION · 2026-10
- [fffaraz/awesome-cpp](https://github.com/fffaraz/awesome-cpp) ★73.8k — A curated list of awesome C++ (or C) frameworks, libraries, resources, and shiny things. Inspired by awesome-... stuff. · MIT · 2026-10
- [vuejs/awesome-vue](https://github.com/vuejs/awesome-vue) ★73.5k — 🎉 A curated list of awesome things related to Vue.js · MIT · 2026-10
- [prakhar1989/awesome-courses](https://github.com/prakhar1989/awesome-courses) ★71.9k — :books: List of awesome university courses for learning Computer Science! · NOASSERTION · 2023-05
- [sindresorhus/awesome-nodejs](https://github.com/sindresorhus/awesome-nodejs) ★67.1k — :zap: Delightful Node.js packages and resources [BECAUSE OF TOO MUCH SPAM AND LOW-QUALITY SUBMISSIONS, SUBMISSIONS ARE PAUSED TEMPORARILY] · CC0-1.0 · 2026-09
- [PlexPt/awesome-chatgpt-prompts-zh](https://github.com/PlexPt/awesome-chatgpt-prompts-zh) ★63.6k — ChatGPT 中文调教指南。各种场景使用指南。学习怎么让它听你的话。 · MIT · 2026-04
- [Solido/awesome-flutter](https://github.com/Solido/awesome-flutter) ★61.5k — An awesome list that curates the best Flutter libraries, tools, tutorials, articles and more. · Dart · NOASSERTION · 2026-09
- [xingshaocheng/architect-awesome](https://github.com/xingshaocheng/architect-awesome) ★60.8k — 后端架构师技术图谱 · NOASSERTION · 2024-04
- [rust-unofficial/awesome-rust](https://github.com/rust-unofficial/awesome-rust) ★59.9k — A curated list of Rust code and resources. · Rust · CC0-1.0 · 2026-10
- [wasabeef/awesome-android-ui](https://github.com/wasabeef/awesome-android-ui) ★58.0k — A curated list of awesome Android UI/UX libraries · MIT · 2026-06
- [vsouza/awesome-ios](https://github.com/vsouza/awesome-ios) ★53.6k — A curated list of awesome iOS ecosystem, including Objective-C and Swift Projects · Swift · MIT · 2026-08
- [VoltAgent/awesome-openclaw-skills](https://github.com/VoltAgent/awesome-openclaw-skills) ★53.2k — The awesome collection of OpenClaw skills. 5,400+ skills filtered and categorized from the official OpenClaw Skills Registry.🦞 · MIT · 2026-10
- [lukasz-madon/awesome-remote-job](https://github.com/lukasz-madon/awesome-remote-job) ★49.5k — A curated list of awesome remote jobs and resources. Inspired by https://github.com/vinta/awesome-python · NOASSERTION · 2026-09
- [DovAmir/awesome-design-patterns](https://github.com/DovAmir/awesome-design-patterns) ★49.4k — A curated list of software and architecture related design patterns. · NOASSERTION · 2024-10
- [akullpp/awesome-java](https://github.com/akullpp/awesome-java) ★49.3k — A curated list of awesome frameworks, libraries and software for the Java programming language. · CC-BY-SA-4.0 · 2026-09
- [brillout/awesome-react-components](https://github.com/brillout/awesome-react-components) ★48.6k — Curated List of React Components & Libraries. · CC0-1.0 · 2026-01
- [LeCoupa/awesome-cheatsheets](https://github.com/LeCoupa/awesome-cheatsheets) ★46.6k — 👩‍💻👨‍💻 Awesome cheatsheets for popular programming languages, frameworks and development tools. They include everything you should know in o · JavaScript · MIT · 2026-04
- [docker/awesome-compose](https://github.com/docker/awesome-compose) ★46.5k — Awesome Docker Compose samples · HTML · CC0-1.0 · 2026-10
- [ashishps1/awesome-system-design-resources](https://github.com/ashishps1/awesome-system-design-resources) ★42.3k — Learn System Design concepts and prepare for interviews using free resources. · Java · GPL-3.0 · 2026-02

### Agentic AI (2026 wave) (30)

- [vectorize-io/hindsight](https://github.com/vectorize-io/hindsight) ★50.2k — Hindsight: Agent Memory That Learns · Python · MIT · 2026-10
- [huggingface/agents-course](https://github.com/huggingface/agents-course) ★33.6k — This repository contains the Hugging Face Agents Course. · MDX · Apache-2.0 · 2026-10
- [charmbracelet/crush](https://github.com/charmbracelet/crush) ★28.7k — Glamourous agentic coding for all 💘 · Go · NOASSERTION · 2026-10
- [keploy/keploy](https://github.com/keploy/keploy) ★18.6k — Open-source platform for creating safe, isolated production sandboxes for API, integration, and E2E testing. · Go · Apache-2.0 · 2026-10
- [kubeflow/kubeflow](https://github.com/kubeflow/kubeflow) ★15.9k — The Cloud Native AI Platform · Apache-2.0 · 2026-09
- [The-Pocket/PocketFlow](https://github.com/The-Pocket/PocketFlow) ★11.2k — Pocket Flow: 100-line LLM framework. Let Agents build Agents! · Python · MIT · 2026-07
- [ValueCell-ai/valuecell](https://github.com/ValueCell-ai/valuecell) ★11.0k — ValueCell is a community-driven, multi-agent platform for financial applications. · Python · Apache-2.0 · 2026-03
- [kedro-org/kedro](https://github.com/kedro-org/kedro) ★11.0k — Kedro is a toolbox for production-ready data science. It uses software engineering best practices to help you create data engineering and da · Python · NOASSERTION · 2026-10
- [yzhao062/pyod](https://github.com/yzhao062/pyod) ★10.0k — A Python library for anomaly detection across tabular, time series, graph, text, image, and audio data. 60+ detectors, benchmark-backed ADEn · Python · BSD-2-Clause · 2026-10
- [alvinunreal/oh-my-opencode-slim](https://github.com/alvinunreal/oh-my-opencode-slim) ★9.6k — Lean, fine tuned Opencode multi agent suite · Mix any models · Auto delegate tasks · TypeScript · MIT · 2026-10
- [oumi-ai/oumi](https://github.com/oumi-ai/oumi) ★9.4k — Easily fine-tune (SFT/RL), evaluate, and deploy Qwen, Gemma, or any open agentic LLM/VLM! · Python · Apache-2.0 · 2026-10
- [SWE-agent/mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) ★8.6k — The 100 line AI agent that solves GitHub issues or helps you in your command line. Radically simple, no huge configs, no giant monorepo—but  · Python · MIT · 2026-10
- [idosal/git-mcp](https://github.com/idosal/git-mcp) ★8.5k — Put an end to code hallucinations! GitMCP is a free, open-source, remote MCP server for any GitHub project · TypeScript · Apache-2.0 · 2026-05
- [GetStream/Vision-Agents](https://github.com/GetStream/Vision-Agents) ★8.2k — Open Vision Agents by Stream. Build voice and vision agents quickly with any model or video provider. Uses Stream's edge network for ultra-l · Python · Apache-2.0 · 2026-10
- [ValueCell-ai/ClawX](https://github.com/ValueCell-ai/ClawX) ★7.6k — ClawX is a desktop app that provides a graphical interface for OpenClaw AI agents. It turns CLI-based AI orchestration into a desktop experi · TypeScript · MIT · 2026-10
- [ParthJadhav/app-store-screenshots](https://github.com/ParthJadhav/app-store-screenshots) ★7.3k — end to end app store screenshot creation using AI · TypeScript · MIT · 2026-10
- [zai-org/GLM-5](https://github.com/zai-org/GLM-5) ★7.3k — GLM-5: From Vibe Coding to Agentic Engineering · Apache-2.0 · 2026-10
- [grab/cursor-talk-to-figma-mcp](https://github.com/grab/cursor-talk-to-figma-mcp) ★7.1k — TalkToFigma: MCP integration between AI Agent (Cursor, Claude Code, Codex) and Figma, allowing Agentic AI to communicate with Figma for read · JavaScript · MIT · 2026-07
- [MrLesk/Backlog.md](https://github.com/MrLesk/Backlog.md) ★7.0k — Backlog.md - A tool for managing project collaboration between humans and AI Agents in a git ecosystem · TypeScript · MIT · 2026-10
- [Tencent/AI-Infra-Guard](https://github.com/Tencent/AI-Infra-Guard) ★6.9k — A full-stack AI Red Teaming platform securing AI ecosystems via Agent Scan, Skills Scan, MCP scan, AI Infra scan and LLM jailbreak evaluatio · Python · Apache-2.0 · 2026-10
- [j3ssie/osmedeus](https://github.com/j3ssie/osmedeus) ★6.6k — A Modern Orchestration Engine for Security · Go · MIT · 2026-10
- [jeinlee1991/chinese-llm-benchmark](https://github.com/jeinlee1991/chinese-llm-benchmark) ★6.5k — 非线智能 NoneLinear - ReLE评测：中文AI大模型能力评测（持续更新）：目前已囊括374个大模型，覆盖chatgpt、gpt-5.4、谷歌gemini-3.1-pro、Claude-4.6、文心ERNIE-X1.1、ERNIE-5.0、qwen3.6-max、qwe · NOASSERTION · 2026-10
- [truefoundry/trueforge](https://github.com/truefoundry/trueforge) ★6.2k — The open-source agent harness - the runtime layer that turns an LLM into a working agent. · TypeScript · MIT · 2026-10
- [datawhalechina/vibe-vibe](https://github.com/datawhalechina/vibe-vibe) ★6.2k — AI for All: The First Systematic Vibe Coding Tutorial | From Zero to Full-Stack, Bring Your Ideas to Life | Live at: www.vibevibe.cn   ；全民AI · Dockerfile · NOASSERTION · 2026-04
- [ModelEngine-Group/nexent](https://github.com/ModelEngine-Group/nexent) ★6.0k — Nexent is a zero-code platform for auto-generating production-grade AI agents using Harness Engineering principles — unified tools, skills,  · Python · MIT · 2026-10
- [samchon/typia](https://github.com/samchon/typia) ★5.9k — Super-fast/easy runtime validators and serializers via transformation · TypeScript · MIT · 2026-10
- [Anil-matcha/open-dots](https://github.com/Anil-matcha/open-dots) ★5.8k — Open-source, self-hosted AI agent workspace and alternative to OpenAI Dots, Meta Muse, Grok Bot, Instinct, Manus Cue, Claude Cowork, and Cha · Python · NOASSERTION · 2026-10
- [RLinf/RLinf](https://github.com/RLinf/RLinf) ★5.4k — RLinf: Reinforcement Learning Infrastructure for Embodied and Agentic AI · Python · Apache-2.0 · 2026-10
- [beclab/Olares](https://github.com/beclab/Olares) ★5.3k — Open-Source Personal Cloud OS for Always-On Agents · Go · AGPL-3.0 · 2026-10
- [katanaml/sparrow](https://github.com/katanaml/sparrow) ★5.2k — Structured data extraction, instruction calling and agentic workflows with ML, LLM and Vision LLM · Python · GPL-3.0 · 2026-10

### Claude Code ecosystem (30)

- [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) ★220.2k — A single CLAUDE.md file to improve Claude Code behavior, derived from Andrej Karpathy's observations on LLM coding pitfalls. · NOASSERTION · 2026-04
- [anthropics/claude-code](https://github.com/anthropics/claude-code) ★151.2k — Claude Code is an agentic coding tool that lives in your terminal, understands your codebase, and helps you code faster by executing routine · TypeScript · NOASSERTION · 2026-10
- [x1xhlol/system-prompts-and-models-of-ai-tools](https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools) ★144.1k — FULL Augment Code, Claude Code, Cluely, CodeBuddy, Comet, Cursor, Devin AI, Junie, Kiro, Leap.new, Lovable, Manus, NotionAI, Orchids.app, Pe · GPL-3.0 · 2026-10
- [garrytan/gstack](https://github.com/garrytan/gstack) ★136.6k — Use Garry Tan's exact Claude Code setup: 23 opinionated tools that serve as CEO, Designer, Eng Manager, Release Manager, Doc Engineer, and Q · TypeScript · MIT · 2026-10
- [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph) ★74.2k — Pre-indexed code knowledge graph, auto syncs on code changes, for Claude Code, Codex, Gemini, Cursor, OpenCode, AntiGravity, Kiro, CoPilot,  · C · MIT · 2026-10
- [gsd-build/get-shit-done](https://github.com/gsd-build/get-shit-done) ★64.3k — A light-weight and powerful meta-prompting, context engineering and spec-driven development system for Claude Code by TÂCHES. · JavaScript · MIT · 2026-05
- [Alishahryar1/free-claude-code](https://github.com/Alishahryar1/free-claude-code) ★60.9k — Use Claude Code, Codex, VSCode, Pi, and OpenCode (and 6 other harnesses) for free (1.3B+ free tokens) from your terminal, app, IDE, or phone · Python · NOASSERTION · 2026-10
- [cathrynlavery/diagram-design](https://github.com/cathrynlavery/diagram-design) ★56.1k — Editorial diagram design for Claude Code, Codex, GitHub Copilot, Cursor, Factory Droid, and Pi. 44 diagram types. Self-contained HTML + SVG. · HTML · MIT · 2026-10
- [router-for-me/CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) ★55.4k — Wrap Antigravity, ChatGPT Codex, Claude Code, Grok Build, Muse Code, Devin as an OpenAI/Gemini/Claude/Codex compatible API service, allowing · Go · MIT · 2026-10
- [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) ★51.0k — Turn any AI agent into an AI Scientist. The #1 Agent Skills library for science, used by 250,000+ scientists worldwide. 177 ready-to-use val · Python · MIT · 2026-10
- [zhaoxuya520/reverse-skill](https://github.com/zhaoxuya520/reverse-skill) ★42.2k — Reverse Engineering / Authorized Penetration Testing / Security Research Skill Router Pack AI-powered routing + On-demand toolchain bootstra · PowerShell · MIT · 2026-09
- [luongnv89/claude-howto](https://github.com/luongnv89/claude-howto) ★41.9k — A visual, example-driven guide to Claude Code — from basic concepts to advanced agents, with copy-paste templates that bring immediate value · Python · MIT · 2026-10
- [musistudio/claude-code-router](https://github.com/musistudio/claude-code-router) ★37.7k — One local control plane for every AI agent: route across models, fuse new capabilities, orchestrate tools, and stay fully in control. · TypeScript · MIT · 2026-10
- [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) ★34.3k — Use Codex from Claude Code to review code or delegate tasks. · JavaScript · Apache-2.0 · 2026-07
- [davila7/claude-code-templates](https://github.com/davila7/claude-code-templates) ★32.7k — CLI tool for configuring and monitoring Claude Code · Python · MIT · 2026-10
- [Nutlope/hallmark](https://github.com/Nutlope/hallmark) ★30.2k — Anti-AI-slop design skill for Claude Code, Cursor, and Codex. · CSS · MIT · 2026-08
- [EveryInc/compound-engineering-plugin](https://github.com/EveryInc/compound-engineering-plugin) ★25.5k — Official Compound Engineering plugin for Claude Code, Codex, Cursor, and more · TypeScript · MIT · 2026-10
- [alchaincyf/huashu-design](https://github.com/alchaincyf/huashu-design) ★25.0k — Huashu Design · HTML-native design skill for Claude Code · Claude Code 里 HTML 原生的设计 skill · 高保真原型 / 幻灯片 / 动画 + 20 设计哲学 + 5 维评审 + MP4 导出 · Ag · HTML · MIT · 2026-10
- [SuperClaude-Org/SuperClaude_Framework](https://github.com/SuperClaude-Org/SuperClaude_Framework) ★23.9k — A configuration framework that enhances Claude Code with specialized commands, cognitive personas, and development methodologies. · Python · MIT · 2026-09
- [claude-code-best/claude-code](https://github.com/claude-code-best/claude-code) ★22.9k — 原汁原昧 Claude Code 可运行,可构建, 可调试版; 生产级工程化, 企业级可靠性; 安全无毒, 内存泄露修复 · TypeScript · NOASSERTION · 2026-08
- [steipete/CodexBar](https://github.com/steipete/CodexBar) ★22.6k — Show usage stats for OpenAI Codex and Claude Code, without having to login. · Swift · MIT · 2026-10
- [winfunc/opcode](https://github.com/winfunc/opcode) ★22.4k — A powerful GUI app and Toolkit for Claude Code - Create custom agents, manage interactive Claude Code sessions, run secure background agents · TypeScript · AGPL-3.0 · 2026-09
- [op7418/Humanizer-zh](https://github.com/op7418/Humanizer-zh) ★19.8k — Humanizer 的汉化版本，Claude Code Skills，旨在消除文本中 AI 生成的痕迹。 · Python · MIT · 2026-09
- [teng-lin/notebooklm-py](https://github.com/teng-lin/notebooklm-py) ★19.8k — Unofficial Python API and agentic skill for Google Gemini Notebook. Full programmatic access to Gemini Notebook's features—including capabil · Python · MIT · 2026-10
- [AgriciDaniel/claude-seo](https://github.com/AgriciDaniel/claude-seo) ★19.0k — Universal SEO skill for Claude Code. 26 sub-skills + 19 sub-agents covering technical SEO, E-E-A-T, schema, GEO/AEO, agent readiness (Lighth · Python · MIT · 2026-10
- [wasp-lang/open-saas](https://github.com/wasp-lang/open-saas) ★16.1k — A 100% free modern JS SaaS boilerplate (React, NodeJS, Prisma). Full-featured: Auth (email, google, github, slack, MS), Email sending, Backg · MDX · MIT · 2026-10
- [chenhg5/cc-connect](https://github.com/chenhg5/cc-connect) ★16.0k — Bridge local AI coding agents (Claude Code, Cursor, Gemini CLI, Codex) to messaging platforms (Feishu/Lark, DingTalk, Slack, Telegram, Disco · Go · NOASSERTION · 2026-10
- [YishenTu/claudian](https://github.com/YishenTu/claudian) ★15.7k — An Obsidian plugin that embeds Claude Code/Codex as an AI collaborator in your vault · TypeScript · MIT · 2026-10
- [travisvn/awesome-claude-skills](https://github.com/travisvn/awesome-claude-skills) ★15.4k — A curated list of awesome Claude Skills, resources, and tools for customizing Claude AI workflows — particularly Claude Code · NOASSERTION · 2026-04
- [siteboon/claudecodeui](https://github.com/siteboon/claudecodeui) ★14.1k — Use Claude Code, OpenCode, Cursor CLI, and Codex on mobile and web with CloudCLI (aka Claude Code UI). CloudCLI is a free open source webui/ · TypeScript · AGPL-3.0 · 2026-10

### opencode ecosystem (30)

- [anomalyco/opencode](https://github.com/anomalyco/opencode) ★214.1k — The open source coding agent. · TypeScript · MIT · 2026-10
- [different-ai/openwork](https://github.com/different-ai/openwork) ★24.1k — The open-source alternative to Claude Cowork (powered by opencode) · TypeScript · NOASSERTION · 2026-10
- [opencode-ai/opencode](https://github.com/opencode-ai/opencode) ★13.8k — A powerful AI coding agent. Built for the terminal. · Go · MIT · 2025-09
- [openchamber/openchamber](https://github.com/openchamber/openchamber) ★11.7k — Agentic Development Environment based on OpenCode AI agent · TypeScript · MIT · 2026-10
- [NoeFabris/opencode-antigravity-auth](https://github.com/NoeFabris/opencode-antigravity-auth) ★10.9k — Enable Opencode to authenticate against Antigravity (Google's IDE) via OAuth so you can use Antigravity rate limits and access models like g · TypeScript · MIT · 2026-08
- [awesome-opencode/awesome-opencode](https://github.com/awesome-opencode/awesome-opencode) ★10.6k — A curated list of awesome plugins, themes, agents, projects, and resources for https://opencode.ai · JavaScript · CC0-1.0 · 2026-07
- [smtg-ai/claude-squad](https://github.com/smtg-ai/claude-squad) ★8.6k — Manage multiple AI terminal agents like Claude Code, Codex, OpenCode, and Amp. · Go · AGPL-3.0 · 2026-08
- [logancyang/obsidian-copilot](https://github.com/logancyang/obsidian-copilot) ★7.8k — Run agents in Obsidian - OpenCode, Codex, Claude Code etc. · TypeScript · AGPL-3.0 · 2026-10
- [zenstory-ai/oh-story-claudecode](https://github.com/zenstory-ai/oh-story-claudecode) ★7.7k — Claude Code / Codex / OpenCode agent skills for writing Chinese web novels (网文): 扫榜、拆文、写作、去AI味、封面全流程，长篇短篇都支持 | 13 skills for novel writing a · Python · MIT · 2026-10
- [Devin-AXIS/iPolloWork](https://github.com/Devin-AXIS/iPolloWork) ★7.0k — Enterprise-grade, local-first Agent Workbench for people and agent teams. A unified multi-engine workspace for Codex Harness, DeepSeek Harne · TypeScript · NOASSERTION · 2026-10
- [ghuntley/how-to-build-a-coding-agent](https://github.com/ghuntley/how-to-build-a-coding-agent) ★5.9k — A workshop that teaches you how to build your own coding agent. Similar to Roo code, Cline, Amp, Cursor, Windsurf or OpenCode. · Go · NOASSERTION · 2026-10
- [Galaxy-Dawn/claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar) ★5.8k — Semi-automated research assistant for academic research and software development. Supports Claude Code, Codex CLI, Kimi Code CLI, and OpenCo · Python · MIT · 2026-09
- [hey-api/hey-api](https://github.com/hey-api/hey-api) ★5.5k — 👨‍🚀 Turn API specifications into production-ready SDKs, validators, mocks, and more. 20+ plugins. Millions of weekly npm downloads. Used by  · TypeScript · MIT · 2026-09
- [tiann/hapi](https://github.com/tiann/hapi) ★5.3k — App for Codex / Claude Code / Pi / OpenCode / Kimi Code / Grok Build, vibe coding anytime, anywhere · TypeScript · AGPL-3.0 · 2026-10
- [nguyenphutrong/quotio](https://github.com/nguyenphutrong/quotio) ★4.9k — Stop juggling AI accounts. Quotio is a beautiful native macOS menu bar app that unifies your Claude, Gemini, OpenAI, Qwen, and Antigravity s · Rust · MIT · 2026-10
- [Tarquinen/opencode-dynamic-context-pruning](https://github.com/Tarquinen/opencode-dynamic-context-pruning) ★4.4k — Dynamic context pruning plugin for OpenCode - intelligently manages conversation context to optimize token usage · TypeScript · AGPL-3.0 · 2026-09
- [crafter-station/petdex](https://github.com/crafter-station/petdex) ★4.2k — A public gallery of animated pets for Codex, Claude Code, DeepSeek Harness, Hermes, OpenCode, Gemini CLI, and more. · TypeScript · MIT · 2026-10
- [spacering-net/codeg](https://github.com/spacering-net/codeg) ★4.0k — Collaborative multi-agent AI coding workspace: aggregate sessions from Claude Code, Codex, OpenCode, Pi, Grok Build, etc. Desktop app, self- · Rust · Apache-2.0 · 2026-10
- [nickjvandyke/opencode.nvim](https://github.com/nickjvandyke/opencode.nvim) ★3.9k — Neovim 🤝 OpenCode in the flow that you already know. · Lua · MIT · 2026-10
- [gotalab/cc-sdd](https://github.com/gotalab/cc-sdd) ★3.7k — Turn approved specs into long-running autonomous implementation. A minimal, adaptable SDD harness with Agent Skills for Claude Code, Codex,  · TypeScript · MIT · 2026-10
- [agent-of-empires/agent-of-empires](https://github.com/agent-of-empires/agent-of-empires) ★3.4k — Manage multiple Claude Code, OpenCode agents from either TUI or Web for easy access on mobile. Also supports Mistral Vibe, Codex CLI, Gemini · Rust · MIT · 2026-10
- [Soju06/codex-lb](https://github.com/Soju06/codex-lb) ★3.3k — Codex/ChatGPT multiple account load balancer & proxy with usage tracking, dashboard, and OpenCode-compatible endpoints · Python · MIT · 2026-10
- [liaohch3/claude-tap](https://github.com/liaohch3/claude-tap) ★3.3k — Intercept and inspect Coding Agent API traffic from Claude Code, Codex CLI, Gemini CLI, Cursor CLI, OpenCode, Kimi/Kimi Code, Pi, and Hermes · Python · MIT · 2026-10
- [Oldcircle/geo-sleuth](https://github.com/Oldcircle/geo-sleuth) ★3.0k — An agent skill that finds where a photo was taken — OpenStreetMap geometry, elevation skylines, satellite imagery and street view — and show · Python · MIT · 2026-10
- [michaelshimeles/ralphy](https://github.com/michaelshimeles/ralphy) ★3.0k — My Ralph Wiggum setup, an autonomous bash script that runs Claude Code, Codex, OpenCode, Cursor agent, Qwen & Droid in a loop until your PRD · TypeScript · NOASSERTION · 2026-02
- [stellarlinkco/myclaude](https://github.com/stellarlinkco/myclaude) ★2.8k — Multi-agent orchestration workflow (Claude Code  Codex Gemini OpenCode) · Go · AGPL-3.0 · 2026-05
- [cytostack/openwolf](https://github.com/cytostack/openwolf) ★2.4k — Portable project memory across Claude Code, Codex and OpenCode, plus token accounting measured from harness transcripts. Local file I/O, no  · TypeScript · AGPL-3.0 · 2026-09
- [codejunkie99/agentic-stack](https://github.com/codejunkie99/agentic-stack) ★2.3k — One brain, many harnesses. Portable .agent/ folder (memory + skills + protocols) that plugs into Claude Code, Cursor, Windsurf, OpenCode, Op · Python · Apache-2.0 · 2026-10
- [numman-ali/opencode-openai-codex-auth](https://github.com/numman-ali/opencode-openai-codex-auth) ★2.2k — OAuth authentication plugin for personal coding assistance with ChatGPT Plus/Pro subscriptions - uses OpenAI's official authentication metho · TypeScript · NOASSERTION · 2026-01
- [OpenCoder-llm/OpenCoder-llm](https://github.com/OpenCoder-llm/OpenCoder-llm) ★2.1k — The Open Cookbook for Top-Tier Code Large Language Model · Python · MIT · 2024-12

### MCP registries (27)

- [creativetimofficial/ui](https://github.com/creativetimofficial/ui) ★12.1k — Open-source components, blocks, and AI agents designed to speed up your workflow. Import them seamlessly into your favorite tools through Re · TypeScript · MIT · 2026-03
- [modelcontextprotocol/registry](https://github.com/modelcontextprotocol/registry) ★7.4k — A community driven registry service for Model Context Protocol (MCP) servers. · Go · NOASSERTION · 2026-10
- [Observal/Observal](https://github.com/Observal/Observal) ★4.5k — Observal is self-hosted registry for your coding agent extensions with a built in insight engine.  Setup Observal, define the scope and shar · Python · Apache-2.0 · 2026-10
- [vybenetwork/solana-mcp-vybe](https://github.com/vybenetwork/solana-mcp-vybe) ★1.9k — Public Solana MCP registry metadata for Vybe Solana API · NOASSERTION · 2026-09
- [pathintegral-institute/mcpm.sh](https://github.com/pathintegral-institute/mcpm.sh) ★1.0k — CLI MCP package manager & registry for all platforms and all clients. Search & configure MCP servers. Advanced Router & Profile features. · Python · MIT · 2026-10
- [agentic-community/mcp-gateway-registry](https://github.com/agentic-community/mcp-gateway-registry) ★985 — Enterprise-ready MCP Gateway & Registry that centralizes AI development tools with secure OAuth authentication, dynamic tool discovery, and  · Python · Apache-2.0 · 2026-10
- [DevnorsAI/devnors-data-python](https://github.com/DevnorsAI/devnors-data-python) ★614 — Devnors Data - Python SDK: 接口,数据API,裁判文书,Legal Case,法律法规,法条,Law Article,企业工商,Company Registry,企业年报,Annual Report,税号开票,Tax Invoice,失信核查,Disho · Python · MIT · 2026-09
- [docker/mcp-registry](https://github.com/docker/mcp-registry) ★572 — Official Docker MCP registry · Go · MIT · 2026-10
- [DevnorsAI/devnors-data-mcp](https://github.com/DevnorsAI/devnors-data-mcp) ★545 — Devnors Data - MCP Server: MCP,Model Context Protocol,Claude,Cursor,WorkBuddy,接口,数据API,裁判文书,Legal Case,法律法规,法条,Law Article,企业工商,Company Regi · Python · MIT · 2026-09
- [marvkr/better-design](https://github.com/marvkr/better-design) ★440 — 🎨 Open-source design MCP server + shadcn/ui registry — AI design systems for Claude Code, Cursor, Codex, GitHub Copilot & any MCP client. 31 · TypeScript · MIT · 2026-09
- [JSONbored/awesome-claude](https://github.com/JSONbored/awesome-claude) ★300 — HeyClaude is a curated registry and distribution surface for Claude and AI-workflow assets: agents, MCP servers, skills, commands, hooks, ru · MDX · MIT · 2026-08
- [toolsdk-ai/toolsdk-mcp-registry](https://github.com/toolsdk-ai/toolsdk-mcp-registry) ★198 — MCPSDK.dev(ToolSDK.ai)'s Awesome MCP Servers and Packages Registry and Database with Structured JSON configurations. Supports OAuth2.1, DCR. · TypeScript · MIT · 2026-10
- [thrashr888/terraform-mcp-server](https://github.com/thrashr888/terraform-mcp-server) ★120 — Terraform Registry MCP Server · TypeScript · MIT · 2025-05
- [opentofu/opentofu-mcp-server](https://github.com/opentofu/opentofu-mcp-server) ★111 — OpenTofu MCP Server for accessing the OpenTofu Registry · TypeScript · NOASSERTION · 2026-09
- [yinghongzhen/RedNb.Nacos](https://github.com/yinghongzhen/RedNb.Nacos) ★99 — 面向 Nacos 3.2.4 的 .NET 8/10 SDK，提供配置中心、服务注册与发现、ASP.NET Core 集成及 AI Registry（MCP、A2A、Prompt、Skill、AgentSpec）。 · C# · Apache-2.0 · 2026-09
- [pouyahasanamreji/continuum](https://github.com/pouyahasanamreji/continuum) ★98 — Shared memory + orchestration for your coding agents — one MCP server, persistent vector memory, agent registry · TypeScript · NOASSERTION · 2026-05
- [aarora79/mcp-gateway](https://github.com/aarora79/mcp-gateway) ★80 — MCP Gateway and Registry · Python · MIT-0 · 2025-10
- [mcp-get/community-servers](https://github.com/mcp-get/community-servers) ★68 — Archived: the mcp-get community server registry is no longer maintained. · JavaScript · MIT · 2026-06
- [aicanvas-me/aicanvas](https://github.com/aicanvas-me/aicanvas) ★68 — Open-core registry of animated React components, blocks, design systems, and templates. Real, editable code: install with one shadcn CLI com · TypeScript · MIT · 2026-10
- [Oaklight/ToolRegistry](https://github.com/Oaklight/ToolRegistry) ★65 — ToolRegistry: A Protocol-Agnostic Tool Management Library for Function-Calling LLMs (OpenAI, Anthropic, Gemini, LangChain, MCP) · Python · MIT · 2026-10
- [opentools/cli](https://github.com/opentools/cli) ★65 — Retired. Publish MCP servers to the official MCP Registry (registry.modelcontextprotocol.io). The opentools name is retained by the OpenTool · TypeScript · NOASSERTION · 2026-07
- [jsonresume/mcp](https://github.com/jsonresume/mcp) ★63 — The registry mcp server updates your resume while you code · TypeScript · Unlicense · 2026-06
- [neuronto/agentic-resource-discovery](https://github.com/neuronto/agentic-resource-discovery) ★60 — Neuronto Agentic Resource Discovery (ARD) Index. Federated search across every public ARD registry, plus a verified tool index read from eac · Python · Apache-2.0 · 2026-10
- [qianniuspace/mcp-security-audit](https://github.com/qianniuspace/mcp-security-audit) ★57 — A powerful MCP (Model Context Protocol) Server that audits npm package dependencies for security vulnerabilities. Built with remote npm regi · TypeScript · MIT · 2025-07
- [ruvnet/dynamo-mcp](https://github.com/ruvnet/dynamo-mcp) ★54 — A dyamic MCP Registry using Cookiecutter templates · Python · MIT · 2026-09
- [terravidhal/logoforge](https://github.com/terravidhal/logoforge) ★52 — 971 brand logos for developers: SVG files, typed React components, shadcn registry (official directory), MCP server. African brands included · TypeScript · NOASSERTION · 2026-10
- [aiagenta2z/onekey-gateway](https://github.com/aiagenta2z/onekey-gateway) ★52 — OneKey Agent Gateway access to Commercial APIs, Skills, MCPs Build once and Ship 10× faster. For devs & builders, A unified API registry to  · Python · NOASSERTION · 2026-04

### Self-hosted apps (30)

- [immich-app/immich](https://github.com/immich-app/immich) ★116.4k — High performance self-hosted photo and video management solution. · TypeScript · AGPL-3.0 · 2026-10
- [usememos/memos](https://github.com/usememos/memos) ★63.8k — A personal timeline for quick notes. Write short memos, find them later by search, tag, or date. Open source and self-hosted. · Go · MIT · 2026-10
- [coollabsio/coolify](https://github.com/coollabsio/coolify) ★63.0k — An open-source, self-hostable PaaS alternative to Vercel, Heroku & Netlify that lets you easily deploy static sites, databases, full-stack a · PHP · Apache-2.0 · 2026-10
- [go-gitea/gitea](https://github.com/go-gitea/gitea) ★58.5k — Git with a cup of tea! Painless self-hosted all-in-one software development service, including Git hosting, code review, team collaboration, · Go · MIT · 2026-10
- [appwrite/appwrite](https://github.com/appwrite/appwrite) ★57.7k — The open-source cloud for agents & devs. Including Auth, Databases, Storage, Functions, Messaging, Hosting, Realtime, WAF and more · TypeScript · BSD-3-Clause · 2026-10
- [ClickHouse/ClickHouse](https://github.com/ClickHouse/ClickHouse) ★50.4k — ClickHouse® is a real-time analytics database management system · C++ · Apache-2.0 · 2026-10
- [gogs/gogs](https://github.com/gogs/gogs) ★47.9k — The painless way to host your own Git service · Go · MIT · 2026-09
- [photoprism/photoprism](https://github.com/photoprism/photoprism) ★40.3k — AI-Powered Photos App 🌈💎✨ · Go · NOASSERTION · 2026-10
- [Dokploy/dokploy](https://github.com/Dokploy/dokploy) ★37.8k — Open Source Alternative to Vercel, Netlify and Heroku. · TypeScript · NOASSERTION · 2026-10
- [IceWhaleTech/CasaOS](https://github.com/IceWhaleTech/CasaOS) ★37.3k — CasaOS - A simple, easy-to-use, elegant open-source Personal Cloud system. · Go · Apache-2.0 · 2026-09
- [filebrowser/filebrowser](https://github.com/filebrowser/filebrowser) ★35.9k — File Browser provides a file managing interface within a specified directory and it can be used to upload, delete, preview and edit your fil · Go · Apache-2.0 · 2026-07
- [gethomepage/homepage](https://github.com/gethomepage/homepage) ★33.2k — A highly customizable homepage (or startpage / application dashboard) with Docker and service API integrations. · JavaScript · GPL-3.0 · 2026-10
- [dokku/dokku](https://github.com/dokku/dokku) ★32.2k — A docker-powered PaaS that helps you build and manage the lifecycle of applications · Go · MIT · 2026-10
- [community-scripts/ProxmoxVE](https://github.com/community-scripts/ProxmoxVE) ★29.8k — Proxmox VE Helper-Scripts (Community Edition) · Shell · MIT · 2026-10
- [karakeep-app/karakeep](https://github.com/karakeep-app/karakeep) ★29.7k — A self-hostable bookmark-everything app (links, notes and images) with AI-based automatic tagging and full text search · TypeScript · AGPL-3.0 · 2026-10
- [lissy93/dashy](https://github.com/lissy93/dashy) ★26.7k — 🚀 A self-hostable personal dashboard built for you. Includes status-checking, widgets, themes, icon packs, a UI editor and tons more! · Vue · MIT · 2026-10
- [louislam/dockge](https://github.com/louislam/dockge) ★24.6k — A fancy, easy-to-use and reactive self-hosted docker compose.yaml stack-oriented manager · TypeScript · MIT · 2026-04
- [navidrome/navidrome](https://github.com/navidrome/navidrome) ★24.2k — 🎧 Your Personal Streaming Service · Go · GPL-3.0 · 2026-10
- [knadh/listmonk](https://github.com/knadh/listmonk) ★23.8k — High performance, self-hosted, newsletter and mailing list manager with a modern dashboard. Single binary app. · Go · AGPL-3.0 · 2026-10
- [fosrl/pangolin](https://github.com/fosrl/pangolin) ★23.1k — Modern networking and security platform providing secure access and connectivity to apps, infrastructure, and AI workloads. Connect and prot · TypeScript · NOASSERTION · 2026-10
- [chaitin/SafeLine](https://github.com/chaitin/SafeLine) ★22.8k — SafeLine is a self-hosted WAF(Web Application Firewall) / reverse proxy to protect your web apps from attacks and exploits. · Go · GPL-3.0 · 2026-09
- [m1k1o/neko](https://github.com/m1k1o/neko) ★22.5k — A self hosted virtual browser that runs in docker and uses WebRTC. · Go · Apache-2.0 · 2026-10
- [airbytehq/airbyte](https://github.com/airbytehq/airbyte) ★22.2k — Open-source data movement for ELT pipelines and AI agents — from APIs, databases & files to warehouses, lakes, and AI applications. Both sel · Python · NOASSERTION · 2026-10
- [linkwarden/linkwarden](https://github.com/linkwarden/linkwarden) ★20.1k — ⚡️⚡️⚡️ Self-hosted collaborative bookmark manager to collect, read, annotate, and fully preserve what matters, all in one place. · TypeScript · AGPL-3.0 · 2026-10
- [C4illin/ConvertX](https://github.com/C4illin/ConvertX) ★19.1k — 💾 Self-hosted online file converter. Supports 1000+ formats ⚙️ · TypeScript · AGPL-3.0 · 2026-10
- [suitenumerique/docs](https://github.com/suitenumerique/docs) ★16.9k — Docs is an open-source text editor: web-native, made for real-time collaboration, cleanly structured documents and sub-documents with full o · Python · MIT · 2026-10
- [rmyndharis/OpenWA](https://github.com/rmyndharis/OpenWA) ★15.5k — Free, Open Source, Self-Hosted WhatsApp API Gateway · TypeScript · MIT · 2026-10
- [theonedev/onedev](https://github.com/theonedev/onedev) ★15.3k — The Unified and Autonomous Development Platform · Java · MIT · 2026-10
- [n8n-io/self-hosted-ai-starter-kit](https://github.com/n8n-io/self-hosted-ai-starter-kit) ★15.3k — The Self-hosted AI Starter Kit is an open-source template that quickly sets up a local AI environment. Curated by n8n, it provides essential · Apache-2.0 · 2026-10
- [cachethq/cachet](https://github.com/cachethq/cachet) ★15.3k — 🚦 Cachet, the open source, self-hosted status page system. · PHP · NOASSERTION · 2026-10

### Structured output & extraction (30)

- [mangiucugna/json_repair](https://github.com/mangiucugna/json_repair) ★5.1k — Repair malformed JSON from LLMs, APIs, logs, and user input in Python. · Python · MIT · 2026-10
- [shcherbak-ai/contextgem](https://github.com/shcherbak-ai/contextgem) ★2.0k — Extract structured data and insights from documents using LLMs and decision models · Python · Apache-2.0 · 2026-10
- [vamplabAI/sgr-agent-core](https://github.com/vamplabAI/sgr-agent-core) ★1.1k — Schema-Guided Reasoning (SGR) has agentic system design created by neuraldeep community · Python · MIT · 2026-09
- [suzuran0y/CCTV-Smartphone-AI-Monitoring](https://github.com/suzuran0y/CCTV-Smartphone-AI-Monitoring) ★821 — 本地监控 + AI 视觉 — LAN-based smartphone-powered AI monitoring framework with structured event output for data acquisition and analysis. · Python · MIT · 2026-10
- [madroidmaq/mlx-omni-server](https://github.com/madroidmaq/mlx-omni-server) ★745 — MLX Omni Server is a local inference server powered by Apple's MLX framework, specifically designed for Apple Silicon (M-series) chips. It i · Python · MIT · 2026-05
- [teilomillet/gollm](https://github.com/teilomillet/gollm) ★676 — Unified Go interface for Language Model (LLM) providers. Simplifies LLM integration with flexible prompt management and common task function · Go · Apache-2.0 · 2026-03
- [AbdelStark/awesome-typesafe-jev](https://github.com/AbdelStark/awesome-typesafe-jev) ★593 — Awesome Jev: a source-backed field guide to TypeSafe's System One model, with SDKs, live demos, agent tools, and independent evaluations. · HTML · MIT · 2026-10
- [jbexta/AgentPilot](https://github.com/jbexta/AgentPilot) ★569 — A versatile workflow automation platform to create, organize, and execute AI workflows, from a single LLM to complex AI-driven workflows. · Python · AGPL-3.0 · 2026-04
- [cobanov/awesome-jev](https://github.com/cobanov/awesome-jev) ★558 — A curated, source-backed list of projects built with Jev, TypeSafe AI's System One model for typed decisions. · CC0-1.0 · 2026-10
- [hassancs91/SimplerLLM](https://github.com/hassancs91/SimplerLLM) ★226 — Python library for building with LLMs. One interface across 11 providers (OpenAI, Anthropic, Gemini, DeepSeek, Ollama and more), automatic f · Python · MIT · 2026-08
- [Buffalo2024/Rulora](https://github.com/Buffalo2024/Rulora) ★145 — Pluggable controls for reliable AI agents: validated outputs, bounded loops and frozen collective decisions. · JavaScript · Apache-2.0 · 2026-10
- [msoedov/validex](https://github.com/msoedov/validex) ★144 — Simplifies the retrieval, extraction, and training of structured data from various unstructured sources. · Python · MIT · 2025-10
- [aaddrick/building-with-typesafe-jev](https://github.com/aaddrick/building-with-typesafe-jev) ★142 — Unofficial skill that teaches coding agents to build with TypeSafe AI's Jev: typed decisions, calibrated confidence, and prior art from 150+ · Python · MIT · 2026-10
- [ItzCrazyKns/Epoch](https://github.com/ItzCrazyKns/Epoch) ★140 — Where conversations become interfaces. · TypeScript · MIT · 2025-11
- [Dave-London/Pare](https://github.com/Dave-London/Pare) ★139 — Dev tools, optimized for agents. Structured, token-efficient MCP servers for git, test runners, npm, Docker, and more. · TypeScript · MIT · 2026-10
- [damionrashford/RivalSearchMCP](https://github.com/damionrashford/RivalSearchMCP) ★132 — Deterministic research MCP server on FastMCP 3 — 5-engine web search, 9-platform social search, 6 academic DBs, news aggregation, entity pro · Python · MIT · 2026-10
- [samchon/openapi](https://github.com/samchon/openapi) ★126 — OpenAPI definitions, converters and LLM function calling schema composer. · TypeScript · MIT · 2026-03
- [supernovae-st/nika](https://github.com/supernovae-st/nika) ★94 — Intent as Code | the workflow language for AI. One file, 4 verbs, one Rust binary. Local-first, any model, AGPL-3.0. 🦋 · Rust · AGPL-3.0 · 2026-10
- [MaximeRivest/functai](https://github.com/MaximeRivest/functai) ★88 — Typed functions whose body a language model writes: run them on tables, measure how often they're right, make them better. Python, TypeScrip · Python · MIT · 2026-10
- [tomnio/rubric](https://github.com/tomnio/rubric) ★86 — Schema-first structured extraction from LLMs — validated JSON from one call or a 150-page document. · TypeScript · MIT · 2026-09
- [yzfly/awesome-jev-zh](https://github.com/yzfly/awesome-jev-zh) ★82 — Jev / TypeSafe System One 中文精选列表：官方资料、SDK、爆款应用、Agent 工具、开源复现与独立评测，附中文上手指南，每日自动收录 GitHub 热门项目。 · HTML · CC0-1.0 · 2026-10
- [petrukha-ivan/mlx-swift-structured](https://github.com/petrukha-ivan/mlx-swift-structured) ★77 — Structured output generation in Swift · Swift · Apache-2.0 · 2026-07
- [kikoncuo/jevfire](https://github.com/kikoncuo/jevfire) ★75 — JEV-inspired parallel decisions for CUDA LLMs. One context, many decisions. vLLM API, game-agent examples, and reproducible benchmarks. · JavaScript · MIT · 2026-09
- [parsehawk/parsehawk](https://github.com/parsehawk/parsehawk) ★69 — Turn documents into structured JSON with local-first document AI. Run 100% locally by default, with API, CLI, and Web UI. · Python · Apache-2.0 · 2026-09
- [ikermoel/open-alternative-jev](https://github.com/ikermoel/open-alternative-jev) ★68 — Open-source alternative to TypeSafe's Jev: a System One style model layer that gives typed, calibrated decisions from any open-weights LLM i · Python · Apache-2.0 · 2026-09
- [call518/LogSentinelAI](https://github.com/call518/LogSentinelAI) ★66 — LLM-powered security log analyzer: detect threats & anomalies with zero regex — just declare a Pydantic schema. Real-time Telegram alerts, S · Python · MIT · 2026-10
- [longtail-labs/cigs](https://github.com/longtail-labs/cigs) ★64 — 🚬 cigs are chainable Ai functions for typescript. Call functions with natural language and get a response back in a specified structure. Use · TypeScript · MIT · 2024-08
- [LeeFly-cn/TripStar-Java](https://github.com/LeeFly-cn/TripStar-Java) ★62 — TripStar multi-agent travel planner powered by Spring Boot 4, Spring AI Alibaba, StateGraph, multimodal note understanding and AMap · JavaScript · GPL-2.0 · 2026-07
- [Emmimal/control-layer](https://github.com/Emmimal/control-layer) ★62 — A production-grade control layer that sits between your application logic and any LLM — input validation, schema enforcement, circuit breaki · Python · MIT · 2026-05
- [bonnard-data/bonnard-cli](https://github.com/bonnard-data/bonnard-cli) ★50 — Archived. Earlier Bonnard product. Current: bonnard.dev / @bonnard/mcp-charts · TypeScript · MIT · 2026-07

