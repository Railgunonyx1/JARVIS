/**
 * JARVIS wire protocol (v1).
 *
 * This is the stable contract between the JARVIS daemon and this UI. It is
 * transport-agnostic: today it rides a WebSocket, but the same envelopes can be
 * forwarded over Tauri IPC (window.__TAURI__) without touching the UI layer.
 *
 * Design rules:
 *  - Every server frame is a `ServerEvent` with a monotonic `seq` for resume.
 *  - Every client frame is a `ClientCommand`.
 *  - Payloads are additive-only; unknown fields are ignored by the UI.
 */

export const PROTOCOL_VERSION = 1

export type Provider = {
  id: string
  label: string
  status: "online" | "degraded" | "offline"
  models: ModelInfo[]
}

export type ModelInfo = {
  id: string
  label: string
  context: number
  input: number // $ / 1M tokens
  output: number // $ / 1M tokens
}

export type ChatRole = "user" | "assistant" | "system"

export type ChatMessage = {
  id: string
  sessionId: string
  role: ChatRole
  content: string
  ts: number
  model?: string
  streaming?: boolean
  usage?: TokenUsage
  runId?: string
}

export type TokenUsage = {
  input: number
  output: number
  totalCostUsd?: number
}

export type AgentPhase = "start" | "think" | "plan" | "act" | "observe" | "done" | "error"

export type AgentEvent = {
  id: string
  runId: string
  phase: AgentPhase
  label: string
  detail?: string
  ts: number
}

export type ToolStatus = "pending" | "running" | "ok" | "error"

export type ToolEvent = {
  id: string // callId
  runId: string
  tool: string
  args?: Record<string, unknown>
  status: ToolStatus
  result?: unknown
  error?: string
  ts: number
  durationMs?: number
}

export type TaskStatus = "queued" | "running" | "blocked" | "done" | "failed"

export type Task = {
  id: string
  title: string
  status: TaskStatus
  progress: number // 0..1
  createdAt: number
  updatedAt: number
  runId?: string
  detail?: string
}

export type MemoryKind = "fact" | "preference" | "entity" | "episode"

export type MemoryEntry = {
  id: string
  kind: MemoryKind
  key: string
  value: string
  score: number // salience 0..1
  ts: number
  refs?: string[] // linked memory ids (for the graph)
}

export type LogLevel = "trace" | "debug" | "info" | "warn" | "error"

export type LogLine = {
  id: string
  level: LogLevel
  source: string
  message: string
  ts: number
}

export type TelemetrySample = {
  ts: number
  cpu: number // 0..100
  mem: number // 0..100
  gpu: number // 0..100
  netIn: number // KB/s
  netOut: number // KB/s
  tokensPerSec: number
  latencyMs: number // last round-trip / inference latency
  activeRuns: number
}

export type Notification = {
  id: string
  level: "info" | "success" | "warn" | "error"
  title: string
  body?: string
  ts: number
  read?: boolean
}

export type FsNode = {
  name: string
  path: string
  type: "dir" | "file"
  size?: number
  ext?: string
  children?: FsNode[]
}

export type ConnectionState = "idle" | "connecting" | "online" | "reconnecting" | "offline" | "sim"

// ---- Server -> Client -----------------------------------------------------

export type ServerEvent =
  | { seq: number; ts: number; type: "hello"; payload: HelloPayload }
  | { seq: number; ts: number; type: "pong"; payload: { t: number } }
  | { seq: number; ts: number; type: "chat.delta"; payload: { messageId: string; sessionId: string; delta: string } }
  | { seq: number; ts: number; type: "chat.message"; payload: { message: ChatMessage } }
  | { seq: number; ts: number; type: "chat.done"; payload: { messageId: string; usage: TokenUsage } }
  | { seq: number; ts: number; type: "agent.event"; payload: AgentEvent }
  | { seq: number; ts: number; type: "tool.call"; payload: ToolEvent }
  | { seq: number; ts: number; type: "tool.result"; payload: ToolEvent }
  | { seq: number; ts: number; type: "task.update"; payload: { task: Task } }
  | { seq: number; ts: number; type: "memory.update"; payload: { op: "add" | "update" | "remove"; entry: MemoryEntry } }
  | { seq: number; ts: number; type: "log"; payload: LogLine }
  | { seq: number; ts: number; type: "telemetry"; payload: TelemetrySample }
  | { seq: number; ts: number; type: "notification"; payload: Notification }
  | { seq: number; ts: number; type: "provider.status"; payload: { providers: Provider[] } }
  | { seq: number; ts: number; type: "fs.tree"; payload: { root: FsNode } }
  | { seq: number; ts: number; type: "error"; payload: { code: string; message: string } }

export type HelloPayload = {
  daemon: string
  version: string
  capabilities: string[]
  providers: Provider[]
  activeProvider: string
  activeModel: string
}

export type ServerEventType = ServerEvent["type"]

// ---- Client -> Server -----------------------------------------------------

export type ClientCommand =
  | { type: "hello"; payload: { client: string; lastSeq?: number } }
  | { type: "ping"; payload: { t: number } }
  | { type: "chat.send"; payload: { sessionId: string; text: string } }
  | { type: "chat.cancel"; payload: { runId: string } }
  | { type: "task.create"; payload: { title: string } }
  | { type: "task.cancel"; payload: { id: string } }
  | { type: "provider.select"; payload: { provider: string; model: string } }
  | { type: "mode.set"; payload: { mode: "smart" | "agent" | "controlled" | "plan" } }
  | { type: "fs.read"; payload: { path: string } }
  | { type: "subscribe"; payload: { channels: string[] } }
