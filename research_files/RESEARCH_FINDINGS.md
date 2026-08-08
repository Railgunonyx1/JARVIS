# JARVIS MK-X — external research findings & recommended skills

Scope: broad sweep across (a) other open-source JARVIS/Iron-Man-style assistants for
architecture ideas, and (b) specific libraries that address gaps already identified in
your own `02_hotspots.md` / `04_architecture_recommendations.md`. Everything below is
something I actually found and can point to — nothing here is invented.

---

## 1. Comparable open-source projects (architecture ideas, not code to copy wholesale)

| Project | What's worth stealing |
|---|---|
| **eadmin2/jarvis_ai** (github.com/eadmin2/jarvis_ai) | Built on top of an existing agent framework (Hermes) rather than hand-rolling the agent loop. Ships "80+ skills" as a plugin bundle, a `hud_display` plugin that can pop holographic panels on command, a live CPU/GPU "machines panel," and — notably — a **privacy filter that redacts secret-shaped strings before any text reaches cloud TTS**. That last one is a concrete gap: your `voice.toml` sends text to Edge-TTS (cloud) with no redaction step. Worth adding regardless of what else you do. |
| **rezaulhreza/jarvis** (github.com/rezaulhreza/jarvis) | "Strong identity system: stays in character regardless of underlying model" — i.e. personality/identity is enforced at the prompt-assembly layer, not hoped for from the model. Also auto-detects a `JARVIS.md`/`CLAUDE.md` project-context file — a pattern you could reuse for per-project context injection. |
| **cam-hm/jarvis** | Small, readable reference for a FastAPI + WebSocket + Piper TTS pipeline if you ever want to compare your `web/server.py` structure against a minimal working example. |

None of these are "install this instead of MK-X" — MK-X is already more architecturally complete than most of what's out there (dialogue state machine, resource governor, vector memory, personality layer). The useful part is specific patterns, not whole-codebase replacement.

---

## 2. Concrete fixes tied to your own hotspot docs

### 2a. Vector store — `sqlite-vec` (directly answers `04_architecture_recommendations.md` §1)

Your own docs flag the vector store as the top hotspot: O(n) full scan, `json.loads()` per row, won't scale past ~1000 memories. The doc suggests FAISS — but FAISS is a heavy, separate dependency (C++ build, its own index files to manage). **`sqlite-vec`** (github.com/asg017/sqlite-vec, MIT license, by Alex Garcia) gets you the same O(log n)-ish KNN search *inside the SQLite file you already have*, via a `vec0` virtual table — no new database, no FAISS build step, minimal-dependency Python bindings (`pip install sqlite-vec`).

I built a drop-in replacement below (`vector_store_sqlitevec.py`) — same public API as your existing `VectorMemoryStore`, so it's a swap, not a rewrite.

### 2b. MCP client — turns "add an integration" into "connect a server"

Not in your hotspot docs, but directly relevant to "skills": **Model Context Protocol (MCP)** is now the standard tool-calling protocol (adopted by Anthropic, OpenAI, Google, Microsoft; under the Linux Foundation as of 2026). The official Python SDK (`pip install "mcp<2"` — stick to the stable v1.x line, v2 is still pre-release) lets a Python app act as an MCP *client* and call tools exposed by any MCP *server*.

Why this matters for you specifically: your `plugin_loader.py` is a solid pattern for hand-written plugins, but every new integration (Gmail, Google Calendar, Notion, Slack, home automation) means writing a new plugin from scratch. There are already hundreds of community MCP servers for exactly these services. Adding an **MCP client plugin** to `plugin_loader.py` means JARVIS can call any of those servers as tools *without you writing an integration for each one* — you configure a server, JARVIS gets its tools.

I built a starting version below (`mcp_client_plugin.py`) that registers as a `jarvis_plugin` and exposes "list available MCP tools" / "call an MCP tool" as actions the planner can use.

### 2c. Face ID — `DeepFace.represent`/`analyze` numpy-array claim was likely false

Confirmed via DeepFace's own documentation: `img_path` "expects exact image paths as inputs. Passing numpy or base64 encoded images is also welcome." The earlier "critical bug" claim that these calls require a file path and reject numpy arrays doesn't match the library's documented behavior. Don't apply that fix without reproducing the actual error first — same lesson as the other three false claims from that list.

### 2d. `planner.py` — tool name mismatch (found this session, not from GitHub research)

Worth repeating here since it's the direct cause of the "screen hallucination" bug: `PLANNER_PROMPT`'s rules text says `Use screen for screenshots`, but the only registered tool is `screen_analyzer`. One-line fix, in the file itself — not a library issue.

---

## 3. Things I looked at and are *not* worth adopting right now

- **Porcupine (Picovoice)** for wake word — your own `voice.toml` already standardizes on `openWakeWord`, which is still the right call: openWakeWord is free/offline/no-account, while Porcupine requires a commercial key. No reason to switch.
- **InsightFace** as a DeepFace replacement — real performance gains are GPU-throughput-focused (batch face-swap/verification pipelines). For a single local webcam doing periodic identity checks, DeepFace's overhead isn't your bottleneck; not worth the migration cost right now.
- **Full alternative assistant frameworks** (LibreChat, AnythingLLM, Jan.ai) — these are chat-interface-first products, not personal-assistant-with-HUD frameworks. Nothing there fits your architecture better than what you already have.

---

## 4. Suggested priority order

1. Fix `planner.py` tool name mismatch (5 min, directly fixes the hallucination bug)
2. Swap in `sqlite-vec` vector store (addresses your own documented #1 hotspot)
3. Add MCP client plugin (opens the door to calendar/email/Slack/etc. without hand-written integrations)
4. Add TTS text redaction before cloud calls (privacy gap, borrowed from eadmin2/jarvis_ai)
5. Everything else in your `03_quick_wins.md` — that list was already solid before this research pass.
