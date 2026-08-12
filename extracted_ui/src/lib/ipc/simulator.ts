import { nanoid } from "nanoid"
import type {
  ClientCommand,
  MemoryEntry,
  Provider,
  ServerEvent,
  Task,
  TelemetrySample,
  ToolEvent,
} from "./protocol"

type Emit = (e: ServerEvent) => void

const PROVIDERS: Provider[] = [
  {
    id: "anthropic",
    label: "Anthropic",
    status: "online",
    models: [
      { id: "claude-sonnet-4.5", label: "Claude Sonnet 4.5", context: 200_000, input: 3, output: 15 },
      { id: "claude-opus-4.1", label: "Claude Opus 4.1", context: 200_000, input: 15, output: 75 },
      { id: "claude-haiku-4", label: "Claude Haiku 4", context: 200_000, input: 0.8, output: 4 },
    ],
  },
  {
    id: "openai",
    label: "OpenAI",
    status: "online",
    models: [
      { id: "gpt-5.1", label: "GPT-5.1", context: 400_000, input: 2.5, output: 10 },
      { id: "gpt-5.1-mini", label: "GPT-5.1 Mini", context: 400_000, input: 0.4, output: 1.6 },
    ],
  },
  {
    id: "google",
    label: "Google",
    status: "degraded",
    models: [{ id: "gemini-3-pro", label: "Gemini 3 Pro", context: 1_000_000, input: 1.25, output: 5 }],
  },
  {
    id: "local",
    label: "Local (Ollama)",
    status: "online",
    models: [
      { id: "llama-3.3-70b", label: "Llama 3.3 70B", context: 128_000, input: 0, output: 0 },
      { id: "qwen-2.5-coder", label: "Qwen 2.5 Coder", context: 32_000, input: 0, output: 0 },
    ],
  },
]

const TOOLS = ["web.search", "fs.read", "shell.exec", "memory.query", "http.fetch", "code.edit", "vector.search"]

const LOG_SOURCES = ["daemon", "agent", "router", "tools", "memory", "provider", "telemetry"]

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}
function rand(min: number, max: number) {
  return min + Math.random() * (max - min)
}

/**
 * A believable local stand-in for the JARVIS daemon. It emits the exact same
 * ServerEvent frames the real daemon would, so the UI cannot tell the
 * difference — the only signal is the connection state showing "SIM".
 */
export class Simulator {
  private emit: Emit
  private seq = 0
  private running = false
  private timers = new Set<ReturnType<typeof setTimeout>>()
  private intervals = new Set<ReturnType<typeof setInterval>>()

  private activeRuns = 0
  private telemetry: TelemetrySample = {
    ts: Date.now(),
    cpu: 14,
    mem: 41,
    gpu: 6,
    netIn: 12,
    netOut: 4,
    tokensPerSec: 0,
    latencyMs: 42,
    activeRuns: 0,
  }

  constructor(emit: Emit) {
    this.emit = emit
  }

  start() {
    if (this.running) return
    this.running = true

    this.frame("hello", {
      daemon: "jarvisd",
      version: "2.4.1",
      capabilities: ["chat", "agent", "tools", "memory", "tasks", "telemetry", "fs"],
      providers: PROVIDERS,
      activeProvider: "anthropic",
      activeModel: "claude-sonnet-4.5",
    })
    this.frame("provider.status", { providers: PROVIDERS })
    this.frame("fs.tree", { root: this.buildTree() })
    this.seedMemory()
    this.seedTasks()
    this.log("info", "daemon", "jarvisd 2.4.1 online — 7 tools registered, 4 providers")
    this.log("info", "memory", "loaded 128 episodic + 42 semantic entries")

    // Telemetry heartbeat (1 Hz keeps React updates cheap; charts interpolate).
    this.every(1000, () => this.tick())
    // Ambient log chatter.
    this.every(3200, () => this.ambientLog())
    // Occasional autonomous activity so the console feels alive.
    this.every(15_000, () => {
      if (Math.random() < 0.6) this.autonomousRun()
    })
    this.after(1400, () => this.autonomousRun())
  }

  stop() {
    this.running = false
    for (const t of this.timers) clearTimeout(t)
    for (const i of this.intervals) clearInterval(i)
    this.timers.clear()
    this.intervals.clear()
  }

  handle(cmd: ClientCommand) {
    switch (cmd.type) {
      case "chat.send":
        this.runAgent(cmd.payload.sessionId, cmd.payload.text)
        break
      case "provider.select":
        this.log("info", "router", `provider set → ${cmd.payload.provider}/${cmd.payload.model}`)
        this.frame("notification", {
          id: nanoid(6),
          level: "info",
          title: "Model switched",
          body: `${cmd.payload.provider} · ${cmd.payload.model}`,
          ts: Date.now(),
        })
        break
      case "task.create": {
        const task = this.mkTask(cmd.payload.title, "queued", 0)
        this.frame("task.update", { task })
        this.after(900, () => this.frame("task.update", { task: { ...task, status: "running", updatedAt: Date.now() } }))
        break
      }
      case "task.cancel":
        this.log("warn", "agent", `task ${cmd.payload.id} cancelled by operator`)
        break
      case "fs.read":
        this.log("debug", "tools", `fs.read ${cmd.payload.path}`)
        break
      case "ping":
        this.frame("pong", { t: cmd.payload.t })
        break
      default:
        break
    }
  }

  // ---- orchestration -----------------------------------------------------

  private runAgent(sessionId: string, text: string) {
    const runId = nanoid(8)
    const messageId = nanoid(10)
    this.activeRuns++
    this.telemetry.tokensPerSec = rand(60, 140)

    this.agent(runId, "start", "run started", `session ${sessionId.slice(0, 6)}`)
    this.log("info", "agent", `run ${runId} started`)

    let t = 250
    this.after(t, () => this.agent(runId, "think", "interpreting request", text.slice(0, 80)))
    t += 500

    // Decide on a tool plan from the prompt.
    const plan = this.planFor(text)
    this.after(t, () => this.agent(runId, "plan", `plan: ${plan.map((p) => p.tool).join(" → ") || "direct answer"}`))
    t += 500

    for (const step of plan) {
      const callId = nanoid(8)
      const start = t
      this.after(start, () => {
        this.agent(runId, "act", `calling ${step.tool}`)
        this.frame("tool.call", {
          id: callId,
          runId,
          tool: step.tool,
          args: step.args,
          status: "running",
          ts: Date.now(),
        } as ToolEvent)
        this.log("debug", "tools", `→ ${step.tool}(${JSON.stringify(step.args).slice(0, 60)})`)
      })
      const dur = Math.round(rand(400, 1400))
      this.after(start + dur, () => {
        this.frame("tool.result", {
          id: callId,
          runId,
          tool: step.tool,
          status: "ok",
          result: step.result,
          durationMs: dur,
          ts: Date.now(),
        } as ToolEvent)
        this.agent(runId, "observe", `${step.tool} → ${step.summary}`, undefined)
        this.log("debug", "tools", `← ${step.tool} ok ${dur}ms`)
      })
      t = start + dur + 250
    }

    // Stream the answer.
    this.after(t, () => {
      const reply = this.replyFor(text, plan)
      this.frame("chat.message", {
        message: {
          id: messageId,
          sessionId,
          role: "assistant",
          content: "",
          ts: Date.now(),
          model: "claude-sonnet-4.5",
          streaming: true,
          runId,
        },
      })
      this.streamTokens(sessionId, messageId, reply, () => {
        const usage = { input: Math.round(rand(400, 1200)), output: Math.round(rand(120, 600)) }
        this.frame("chat.done", { messageId, usage })
        this.agent(runId, "done", "run complete")
        this.log("info", "agent", `run ${runId} complete`)
        this.activeRuns = Math.max(0, this.activeRuns - 1)
        this.telemetry.tokensPerSec = this.activeRuns > 0 ? rand(60, 140) : 0
        if (Math.random() < 0.5) this.rememberFrom(text)
      })
    })
  }

  private streamTokens(sessionId: string, messageId: string, text: string, done: () => void) {
    const chunks = text.match(/\S+\s*/g) ?? [text]
    let i = 0
    const step = () => {
      if (!this.running) return
      if (i >= chunks.length) {
        done()
        return
      }
      // Emit 1-3 words per frame for a snappy-but-natural cadence.
      const n = 1 + Math.floor(Math.random() * 3)
      const delta = chunks.slice(i, i + n).join("")
      i += n
      this.frame("chat.delta", { messageId, sessionId, delta })
      this.after(rand(14, 46), step)
    }
    step()
  }

  private autonomousRun() {
    const runId = nanoid(8)
    const tool = pick(["memory.query", "vector.search", "http.fetch", "telemetry.scan"])
    this.agent(runId, "think", "background maintenance", tool)
    const callId = nanoid(8)
    this.frame("tool.call", { id: callId, runId, tool, status: "running", ts: Date.now() } as ToolEvent)
    const dur = Math.round(rand(300, 900))
    this.after(dur, () => {
      this.frame("tool.result", { id: callId, runId, tool, status: "ok", durationMs: dur, ts: Date.now() } as ToolEvent)
      this.agent(runId, "done", `${tool} refreshed`)
    })
  }

  // ---- planning + canned replies ----------------------------------------

  private planFor(text: string): { tool: string; args: Record<string, unknown>; result: unknown; summary: string }[] {
    const q = text.toLowerCase()
    const steps: { tool: string; args: Record<string, unknown>; result: unknown; summary: string }[] = []
    if (/search|find|look up|latest|news|who|what|when/.test(q)) {
      steps.push({ tool: "web.search", args: { q: text.slice(0, 40) }, result: { hits: 8 }, summary: "8 sources" })
    }
    if (/file|read|code|repo|function|bug|error/.test(q)) {
      steps.push({ tool: "fs.read", args: { path: "src/agent/loop.ts" }, result: { lines: 412 }, summary: "412 lines" })
      steps.push({ tool: "vector.search", args: { k: 6 }, result: { matches: 6 }, summary: "6 matches" })
    }
    if (/run|execute|deploy|build|test|install/.test(q)) {
      steps.push({ tool: "shell.exec", args: { cmd: "pnpm test" }, result: { code: 0 }, summary: "exit 0" })
    }
    if (/remember|recall|prefer|memory|earlier|last time/.test(q)) {
      steps.push({ tool: "memory.query", args: { k: 5 }, result: { entries: 5 }, summary: "5 memories" })
    }
    if (steps.length === 0 && Math.random() < 0.6) {
      steps.push({ tool: "memory.query", args: { k: 3 }, result: { entries: 3 }, summary: "3 memories" })
    }
    return steps
  }

  private replyFor(text: string, plan: { tool: string }[]): string {
    const used = plan.map((p) => p.tool)
    const lead = used.length
      ? `I ran ${used.length} tool${used.length > 1 ? "s" : ""} (${used.join(", ")}) and here's what I found. `
      : ""
    const q = text.trim()
    return (
      lead +
      `Regarding "${q.slice(0, 60)}${q.length > 60 ? "…" : ""}": the request is scoped and actionable. ` +
      `I've cross-referenced current context against memory and the relevant sources, then synthesized a plan. ` +
      `Next I can execute the steps directly, or hand you a diff for review — your call. ` +
      `Everything above the fold streamed in real time over the daemon socket.`
    )
  }

  // ---- seeds -------------------------------------------------------------

  private seedMemory() {
    const seeds: Omit<MemoryEntry, "id" | "ts">[] = [
      { kind: "preference", key: "code.style", value: "TypeScript strict, no default exports", score: 0.92 },
      { kind: "preference", key: "ui.theme", value: "dark terminal, monospace, clay accent", score: 0.88 },
      { kind: "fact", key: "stack", value: "Tauri + React + WebSocket daemon", score: 0.81 },
      { kind: "entity", key: "operator", value: "primary user — high autonomy granted", score: 0.95 },
      { kind: "episode", key: "session.boot", value: "console reconnected after cold start", score: 0.4 },
      { kind: "fact", key: "daemon.host", value: "127.0.0.1:8787", score: 0.6 },
    ]
    seeds.forEach((s, idx) => {
      const entry: MemoryEntry = {
        ...s,
        id: nanoid(8),
        ts: Date.now() - idx * 60_000,
        refs: idx > 0 && Math.random() < 0.5 ? [] : undefined,
      }
      this.frame("memory.update", { op: "add", entry })
    })
  }

  private rememberFrom(text: string) {
    const entry: MemoryEntry = {
      id: nanoid(8),
      kind: "episode",
      key: `episode.${Date.now().toString(36)}`,
      value: text.slice(0, 70),
      score: rand(0.3, 0.7),
      ts: Date.now(),
    }
    this.frame("memory.update", { op: "add", entry })
    this.log("debug", "memory", `+episode "${entry.value.slice(0, 32)}"`)
  }

  private seedTasks() {
    const specs: [string, Task["status"], number][] = [
      ["Index /src for semantic recall", "done", 1],
      ["Watch daemon socket & auto-reconnect", "running", 0.62],
      ["Summarize overnight logs", "queued", 0],
      ["Refactor tool router timeouts", "blocked", 0.25],
    ]
    specs.forEach(([title, status, progress], i) => {
      const task = this.mkTask(title, status, progress)
      task.createdAt = Date.now() - (i + 1) * 120_000
      this.frame("task.update", { task })
    })
  }

  private mkTask(title: string, status: Task["status"], progress: number): Task {
    return {
      id: nanoid(8),
      title,
      status,
      progress,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    }
  }

  private buildTree() {
    const file = (name: string, path: string, size: number) => ({
      name,
      path,
      type: "file" as const,
      ext: name.split(".").pop(),
      size,
    })
    return {
      name: "jarvis",
      path: "/",
      type: "dir" as const,
      children: [
        {
          name: "src",
          path: "/src",
          type: "dir" as const,
          children: [
            {
              name: "agent",
              path: "/src/agent",
              type: "dir" as const,
              children: [
                file("loop.ts", "/src/agent/loop.ts", 11800),
                file("router.ts", "/src/agent/router.ts", 6400),
                file("tools.ts", "/src/agent/tools.ts", 9200),
              ],
            },
            {
              name: "memory",
              path: "/src/memory",
              type: "dir" as const,
              children: [file("store.ts", "/src/memory/store.ts", 5100), file("vector.ts", "/src/memory/vector.ts", 4300)],
            },
            file("daemon.ts", "/src/daemon.ts", 8700),
            file("protocol.ts", "/src/protocol.ts", 3900),
          ],
        },
        {
          name: "config",
          path: "/config",
          type: "dir" as const,
          children: [file("jarvis.toml", "/config/jarvis.toml", 1200), file("providers.toml", "/config/providers.toml", 800)],
        },
        file("README.md", "/README.md", 2400),
        file("Cargo.toml", "/Cargo.toml", 640),
      ],
    }
  }

  // ---- telemetry + logs --------------------------------------------------

  private tick() {
    const t = this.telemetry
    const load = this.activeRuns > 0 ? 1 : 0
    t.ts = Date.now()
    t.cpu = clamp(walk(t.cpu, 6) + load * 4, 3, 98)
    t.mem = clamp(walk(t.mem, 2), 30, 92)
    t.gpu = clamp(walk(t.gpu, 8) + load * 20, 1, 99)
    t.netIn = clamp(walk(t.netIn, 10) + load * 30, 0, 900)
    t.netOut = clamp(walk(t.netOut, 6) + load * 12, 0, 400)
    t.latencyMs = clamp(walk(t.latencyMs, 8), 18, 260)
    t.activeRuns = this.activeRuns
    t.tokensPerSec = this.activeRuns > 0 ? clamp(walk(t.tokensPerSec || 90, 20), 20, 220) : 0
    this.frame("telemetry", { ...t })
  }

  private ambientLog() {
    const level = Math.random() < 0.08 ? "warn" : Math.random() < 0.03 ? "error" : Math.random() < 0.4 ? "info" : "debug"
    const source = pick(LOG_SOURCES)
    const messages = [
      "heartbeat ok",
      "gc: reclaimed 2.4MB",
      "vector index compacted",
      "router: 3 providers healthy, 1 degraded",
      "context window 42% utilized",
      "tool registry hot-reloaded",
      "socket backpressure nominal",
      "cache hit ratio 0.87",
    ]
    if (level === "warn") this.log("warn", source, "provider latency spike detected (gemini-3-pro)")
    else if (level === "error") this.log("error", source, "tool http.fetch timed out after 8s — retrying")
    else this.log(level as "info" | "debug", source, pick(messages))
  }

  private log(level: "trace" | "debug" | "info" | "warn" | "error", source: string, message: string) {
    this.frame("log", { id: nanoid(8), level, source, message, ts: Date.now() })
  }

  // ---- helpers -----------------------------------------------------------

  private agent(runId: string, phase: Parameters<typeof buildAgent>[1], label: string, detail?: string) {
    this.frame("agent.event", buildAgent(runId, phase, label, detail))
  }

  private frame<T extends ServerEvent["type"]>(type: T, payload: Extract<ServerEvent, { type: T }>["payload"]) {
    if (!this.running && type !== "hello") return
    this.emit({ seq: ++this.seq, ts: Date.now(), type, payload } as ServerEvent)
  }

  private after(ms: number, fn: () => void) {
    const id = setTimeout(() => {
      this.timers.delete(id)
      if (this.running) fn()
    }, ms)
    this.timers.add(id)
  }

  private every(ms: number, fn: () => void) {
    const id = setInterval(() => {
      if (this.running) fn()
    }, ms)
    this.intervals.add(id)
  }
}

function buildAgent(
  runId: string,
  phase: "start" | "think" | "plan" | "act" | "observe" | "done" | "error",
  label: string,
  detail?: string,
) {
  return { id: nanoid(8), runId, phase, label, detail, ts: Date.now() }
}

function walk(v: number, step: number) {
  return v + rand(-step, step)
}
function clamp(n: number, min: number, max: number) {
  return Math.min(max, Math.max(min, n))
}
