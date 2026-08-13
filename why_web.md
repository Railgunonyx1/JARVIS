# Why JARVIS MK-X is a Web Application

## Architecture Decision

JARVIS MK-X uses a **React + Vite + Tauri** architecture rather than a traditional Python TUI for several strategic reasons:

### 1. **Browser-First, Tauri 2 Later**
The project explicitly chose **browser-first development** with Tauri 2 as the final desktop shell. This means:
- UI is developed and tested in the browser first
- Later, Tauri 2 packages the React app into a native desktop window
- No need to maintain separate Python + HTML codebases
- Single source of truth for the UI

### 2. **Modern Stack Advantages**
| Advantage | Python TUI | React Web |
|-----------|------------|-----------|
| **Visual fidelity** | Limited to terminal chars | Rich UI, gradients, animations, overlays |
| **Responsive layout** | Complex, custom coding | Tailwind CSS, flexible grid |
| **Component reuse** | Low | High (PanelCard, Collapsible, etc.) |
| **State management** | Custom | Zustand (centralized) |
| **Event-driven** | Polling or signals | WebSocket, SSE, event streams |
| **Telemetry display** | Difficult rings | SVG graphs, sparklines, real-time updates |
| **MCP panels** | Text list | Interactive servers, tool counts, versions |
| **Memory search** | Command line | Debounced search, results with scores |

### 3. **Daemon as Source of Truth**
The UI is an **event-driven client** of the JARVIS daemon:
```
JARVIS Daemon (Python)
       │
   WebSocket/IPC
       │
JARVIS React UI (observes, never implements)
       │
   Browser / Tauri 2
```

This separation means:
- The daemon handles: agent execution, tool execution, providers, memory, security, events
- The UI handles: display, user interaction, visualization
- No duplicate state, no fake telemetry

### 4. **600-Repository Research Backlog**
The web architecture allows JARVIS to leverage the 600+ GitHub repositories for:
- MCP tool ecosystem integration
- Memory system implementations (sqlite-vec, Graphiti, Letta, Mem0)
- Agent frameworks (LangGraph, AutoGen, CrewAI)
- LLM inference (vLLM, Ollama, llama.cpp)
- Voice/STT/TTS (Whisper, Piper, Vosk)
- Computer vision (OpenCV, SAM2, GroundingDINO)
- And 20+ other categories

These would be much harder to integrate into a pure Python TUI.

### 5. **Tauri 2 Desktop Shell**
The final delivery is a native desktop app:
```
React + Vite + Tauri 2 → native Windows/Linux/macOS app
```
- Web assets (`dist/`) are embedded in the Tauri Rust backend
- Native window, system tray, global shortcuts
- WebSocket transport unchanged (same daemon connection)
- No browser dependency for the end user

### 6. **Development Velocity**
- Fast refresh (`vite dev`) during development
- TypeScript catches errors early
- Tailwind CSS v4 utility-first styling
- Zustand state management is predictable and testable
- Ecosystem of 600+ repositories can be consumed via APIs, not direct code dependencies

### 7. **The Exception: Python TUI is Still Available**
The Python TUI is **not deleted** — it's in a separate branch/research track:
- `jarvis_memory/` contains the Python daemon + memory system
- The TUI is "superseded by the React UI" per the frozen architecture decisions
- Can be revived later if needed for lightweight terminals or offline use

---

## The Critical Path Decision

> **The critical path is: finish UI P0 while keeping CAD and the 600-repo research track parallel and non-blocking.**

The web app is the **current P0** because it:
- ✅ Matches the prototype visual language exactly
- ✅ Connects to the daemon via WebSocket events
- ✅ No mock data presented as real telemetry
- ✅ All frozen P0 decisions are maintained
- ✅ Can be packaged as Tauri 2 desktop app
- ✅ Leverages the 600-repository research ecosystem

The Python TUI remains a **valid research track** but does not block the web P0.

---

## Port Conflict Resolution

If port 5173 is already in use (from a previous Vite session):

1. **Kill the existing process:**
   ```cmd
   taskkill /f /im node.exe
   ```
   Or find the PID and kill it.

2. **Or change the port in `vite.config.ts`:**
   ```js
   export default defineConfig({
     server: {
       port: 5174, // or 5175, 5180, etc.
     },
     // ...
   })
   ```

3. **Or use the `--host` flag:**
   ```cmd
   npx vite --host
   ```

---

## Summary

**JARVIS MK-X is a web application** because:
- ✅ Rich UI matches the prototype's cyberpunk aesthetic
- ✅ Event-driven daemon integration via WebSocket
- ✅ Leverages 600+ GitHub repositories for MCP, memory, agents, etc.
- ✅ Tauri 2 packaging for native desktop delivery
- ✅ Faster development velocity with modern web tools
- ✅ Daemon remains the source of truth (UI observes only)
- ✅ P0 critical path is verified and complete

The Python TUI and 600-repository research are **parallel tracks** that do not block the web P0.