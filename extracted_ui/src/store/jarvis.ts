import { create } from "zustand"
import { nanoid } from "nanoid"
import { client } from "@/lib/ipc/client"
import type {
  AgentEvent,
  ChatMessage,
  ConnectionState,
  FsNode,
  LogLevel,
  LogLine,
  MemoryEntry,
  Notification,
  Provider,
  ServerEvent,
  Task,
  TelemetrySample,
  ToolEvent,
} from "@/lib/ipc/protocol"

const LOG_CAP = 500
const TELEMETRY_CAP = 120
const EVENT_CAP = 400

export type ConnectionInfo = {
  state: ConnectionState
  attempts: number
  usingSim: boolean
  url: string
}

type JarvisState = {
  connection: ConnectionInfo
  daemon: { name: string; version: string; capabilities: string[] } | null

  providers: Provider[]
  activeProvider: string
  activeModel: string

  sessionId: string
  messages: ChatMessage[]

  agentEvents: AgentEvent[]
  toolEvents: ToolEvent[]
  tasks: Record<string, Task>
  memory: Record<string, MemoryEntry>
  logs: LogLine[]

  telemetry: TelemetrySample | null
  telemetryHistory: TelemetrySample[]

  notifications: Notification[]
  fsTree: FsNode | null

  logFilter: LogLevel | "all"

  // actions
  ingest: (e: ServerEvent) => void
  sendChat: (text: string) => void
  cancelRun: (runId: string) => void
  createTask: (title: string) => void
  cancelTask: (id: string) => void
  selectModel: (provider: string, model: string) => void
  reconnect: (url?: string) => void
  toggleSim: () => void
  markNotificationsRead: () => void
  dismissNotification: (id: string) => void
  clearLogs: () => void
  setLogFilter: (f: LogLevel | "all") => void
}

const initialTelemetry = (): TelemetrySample[] => []

export const useJarvis = create<JarvisState>((set, get) => ({
  connection: { state: "idle", attempts: 0, usingSim: false, url: client.url },
  daemon: null,

  providers: [],
  activeProvider: "",
  activeModel: "",

  sessionId: nanoid(10),
  messages: [],

  agentEvents: [],
  toolEvents: [],
  tasks: {},
  memory: {},
  logs: [],

  telemetry: null,
  telemetryHistory: initialTelemetry(),

  notifications: [],
  fsTree: null,

  logFilter: "all",

  ingest: (e) => {
    switch (e.type) {
      case "hello": {
        set({
          daemon: { name: e.payload.daemon, version: e.payload.version, capabilities: e.payload.capabilities },
          providers: e.payload.providers,
          activeProvider: e.payload.activeProvider,
          activeModel: e.payload.activeModel,
        })
        break
      }
      case "provider.status":
        set({ providers: e.payload.providers })
        break
      case "chat.message": {
        const msg = e.payload.message
        set((s) => {
          const exists = s.messages.some((m) => m.id === msg.id)
          return { messages: exists ? s.messages.map((m) => (m.id === msg.id ? msg : m)) : [...s.messages, msg] }
        })
        break
      }
      case "chat.delta": {
        const { messageId, delta } = e.payload
        set((s) => ({
          messages: s.messages.map((m) => (m.id === messageId ? { ...m, content: m.content + delta } : m)),
        }))
        break
      }
      case "chat.done": {
        const { messageId, usage } = e.payload
        set((s) => ({
          messages: s.messages.map((m) => (m.id === messageId ? { ...m, streaming: false, usage } : m)),
        }))
        break
      }
      case "agent.event":
        set((s) => ({ agentEvents: cap([...s.agentEvents, e.payload], EVENT_CAP) }))
        break
      case "tool.call":
      case "tool.result": {
        const t = e.payload
        set((s) => {
          const idx = s.toolEvents.findIndex((x) => x.id === t.id)
          if (idx === -1) return { toolEvents: cap([...s.toolEvents, t], EVENT_CAP) }
          const next = s.toolEvents.slice()
          next[idx] = { ...next[idx], ...t }
          return { toolEvents: next }
        })
        break
      }
      case "task.update":
        set((s) => ({ tasks: { ...s.tasks, [e.payload.task.id]: e.payload.task } }))
        break
      case "memory.update": {
        const { op, entry } = e.payload
        set((s) => {
          const memory = { ...s.memory }
          if (op === "remove") delete memory[entry.id]
          else memory[entry.id] = entry
          return { memory }
        })
        break
      }
      case "log":
        set((s) => ({ logs: cap([...s.logs, e.payload], LOG_CAP) }))
        break
      case "telemetry":
        set((s) => ({
          telemetry: e.payload,
          telemetryHistory: cap([...s.telemetryHistory, e.payload], TELEMETRY_CAP),
        }))
        break
      case "notification":
        set((s) => ({ notifications: cap([e.payload, ...s.notifications], 50) }))
        break
      case "fs.tree":
        set({ fsTree: e.payload.root })
        break
      case "error":
        set((s) => ({
          logs: cap(
            [...s.logs, { id: nanoid(8), level: "error", source: "daemon", message: e.payload.message, ts: e.ts }],
            LOG_CAP,
          ),
        }))
        break
    }
  },

  sendChat: (text) => {
    const trimmed = text.trim()
    if (!trimmed) return
    const { sessionId } = get()
    const msg: ChatMessage = {
      id: nanoid(10),
      sessionId,
      role: "user",
      content: trimmed,
      ts: Date.now(),
    }
    set((s) => ({ messages: [...s.messages, msg] }))
    client.send({ type: "chat.send", payload: { sessionId, text: trimmed } })
  },

  cancelRun: (runId) => client.send({ type: "chat.cancel", payload: { runId } }),

  createTask: (title) => {
    if (!title.trim()) return
    client.send({ type: "task.create", payload: { title: title.trim() } })
  },

  cancelTask: (id) => client.send({ type: "task.cancel", payload: { id } }),

  selectModel: (provider, model) => {
    set({ activeProvider: provider, activeModel: model })
    client.send({ type: "provider.select", payload: { provider, model } })
  },

  reconnect: (url) => client.connect(url),
  toggleSim: () => {
    if (get().connection.usingSim) client.reconnect()
    else client.useSimulator()
  },

  markNotificationsRead: () => set((s) => ({ notifications: s.notifications.map((n) => ({ ...n, read: true })) })),
  dismissNotification: (id) => set((s) => ({ notifications: s.notifications.filter((n) => n.id !== id) })),
  clearLogs: () => set({ logs: [] }),
  setLogFilter: (f) => set({ logFilter: f }),
}))

function cap<T>(arr: T[], max: number): T[] {
  return arr.length > max ? arr.slice(arr.length - max) : arr
}

// ---- wire the client into the store (once) --------------------------------

let wired = false
export function initJarvis() {
  if (wired) return
  wired = true
  client.on((e) => useJarvis.getState().ingest(e))
  client.onState((state, meta) =>
    useJarvis.setState({ connection: { state, attempts: meta.attempts, usingSim: meta.usingSim, url: meta.url } }),
  )
  client.connect()
}

// ---- derived selectors -----------------------------------------------------

export const selectRunTimeline = (runId: string) => (s: JarvisState) => ({
  agent: s.agentEvents.filter((e) => e.runId === runId),
  tools: s.toolEvents.filter((e) => e.runId === runId),
})
