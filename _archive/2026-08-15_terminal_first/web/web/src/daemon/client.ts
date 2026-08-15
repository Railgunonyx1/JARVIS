/** Message types shared between daemon and web frontend. */

export type MessageId = string

/** Base envelope for all daemon ↔ web communication. */
export interface MessageEnvelope {
  type: string
  id: MessageId
  timestamp: number
}

/** Request envelope — client → daemon. */
export interface RequestEnvelope extends MessageEnvelope {
  type: 'REQUEST'
  payload: Record<string, unknown>
}

/** Response envelope — daemon → client (one-shot). */
export interface ResponseEnvelope extends MessageEnvelope {
  type: 'RESPONSE'
  success: boolean
  error?: string
  payload?: Record<string, unknown>
}

/** Event envelope — daemon → client (push, never re-request). */
export interface EventEnvelope extends MessageEnvelope {
  type: 'EVENT'
  event: string
  payload: Record<string, unknown>
}

/** Bootstrap envelope — sent on connect. */
export interface BootstrapEnvelope extends MessageEnvelope {
  type: 'BOOTSTRAP'
  token: string
  project: string
  mode: string
  provider: string
  model: string
}

/* ── Telemetry ────────────────────────────────────────────── */

export interface TelemetrySample {
  cpu_percent: number
  ram_percent: number
  disk_percent: number
  gpu_percent: number | null
  uptime: number
  timestamp: number
}

export interface TelemetrySubscribeResult {
  subscribed: true
}

export interface TelemetryUnsubscribeResult {
  subscribed: false
}

/* ── MCP ──────────────────────────────────────────────────── */

export interface McpServer {
  name: string
  status: 'ONLINE' | 'OFFLINE' | 'ERROR'
  tools: number
  version?: string
}

export interface McpListResult {
  servers: McpServer[]
}

/* ── Agent/Task events ──────────────────────────────────── */

export interface TraceSummary {
  task_id: string
  goal: string
  status: 'idle' | 'queued' | 'running' | 'done' | 'cancelled' | 'failed'
  started_at: number
  completed_at: number | null
  duration_ms: number | null
  iterations: number
}

export interface RecentTraces {
  traces: TraceSummary[]
}

export interface TaskEvent {
  task_id: string
  event: 'run.queued' | 'task.started' | 'step.started' | 'step.completed' | 'step.failed' | 'permission.observed' | 'task.finished' | 'task.cancelled'
  payload: Record<string, unknown>
}

/* ── Model / Provider ─────────────────────────────────────── */

export interface ModelInfo {
  name: string
  provider: string
  status: 'ONLINE' | 'OFFLINE'
  latency_ms?: number
}

/* ── Memory ───────────────────────────────────────────────── */

export interface MemorySearchResult {
  id: string
  type: 'fact' | 'episode' | 'procedure' | 'entity' | 'relationship'
  content: string
  score: number
  metadata?: Record<string, unknown>
}

/* ── Sidebar / System ─────────────────────────────────────── */

export interface SystemStatus {
  running: boolean
  mode: string
  provider: string
  model: string
  uptime: number
}

export interface McpStatus {
  online: number
  total: number
  servers: McpServer[]
}