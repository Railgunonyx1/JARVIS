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

/** Daemon client namespace — provides typed methods for WebSocket communication. */
export namespace daemon {
  let ws: WebSocket | null = null
  const pending = new Map<string, ((result: any) => void)>()
  const eventListeners = new Map<string, ((event: any) => void)>()

  export function connect(url: string) {
    ws = new WebSocket(url)
    ws.onopen = () => sendBootstrap()
    ws.onmessage = (msg: MessageEvent) => handleMessage(msg)
    ws.onclose = () => scheduleReconnect()
    ws.onerror = () => {}
  }

  function sendBootstrap() {
    if (!ws?.readyState === WebSocket.OPEN) return
    const msg: BootstrapEnvelope = {
      type: 'BOOTSTRAP',
      id: `bootstrap-${Date.now()}`,
      timestamp: Date.now(),
      payload: {
        token: 'dev-token',
        project: 'JARVIS MK-X',
        mode: 'SMART',
        provider: 'Groq',
        model: 'phi3',
      },
    }
    ws.send(JSON.stringify(msg))
  }

  function handleMessage(msg: MessageEvent) {
    const data = JSON.parse(msg.data) as MessageEnvelope
    switch (data.type) {
      case 'RESPONSE': {
        const handler = pending.get(data.id)
        if (handler) handler(data.payload)
        pending.delete(data.id)
        break
      }
      case 'EVENT': {
        const listeners = eventListeners.get(data.event) || []
        for (const h of listeners) h(data.payload)
        break
      }
    }
  }

  function scheduleReconnect() {
    setTimeout(() => connect('ws://localhost:8765'), 3000)
  }

  export function request<T = unknown>(type: string, payload: Record<string, unknown>): Promise<T> {
    return new Promise<T>((resolve) => {
      const id = `req-${Date.now()}-${Math.random().toString(36).slice(2)}`
      pending.set(id, resolve)
      if (!ws?.readyState === WebSocket.OPEN) return
      const envelope: RequestEnvelope = {
        type: 'REQUEST',
        id,
        timestamp: Date.now(),
        payload,
      }
      ws.send(JSON.stringify(envelope))
    })
  }

  export function on(event: string, handler: (event: any) => void) {
    if (!eventListeners.has(event)) eventListeners.set(event, [] as any)
    ;(eventListeners.get(event) as any[]).push(handler as any)
    return () => {
      const listeners = eventListeners.get(event) || []
      ;(eventListeners.get(event) as any[]).splice(
        listeners.findIndex((h) => h === handler),
        1,
      )
    }
  }

  export function mcpList(): Promise<McpListResult> {
    return new Promise<McpListResult>((resolve) => {
      resolve({
        servers: [
          { name: 'memory', status: 'ONLINE', tools: 12 },
          { name: 'file', status: 'ONLINE', tools: 8 },
        ],
      })
    })
  }

  export function cancel(): Promise<{ cancelled: boolean }> {
    return new Promise<{ cancelled: boolean }>((resolve) => {
      if (!ws?.readyState === WebSocket.OPEN) return resolve({ cancelled: false })
      ws.send(JSON.stringify({ type: 'CANCEL', timestamp: Date.now() }))
      resolve({ cancelled: true })
    })
  }
}