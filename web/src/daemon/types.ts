/** Shared domain types for the daemon WebSocket protocol. */

export type ConnectionStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'error'

export interface PongPayload {
  pid: number
  project: string
  project_id: string
  mode: string
  port: number
  ws_port: number
  started_at: number
  uptime: number
}

export interface ConnStateEvent {
  event: 'opened' | 'closed'
  peer: string
  clients: number
}

export interface RunResult {
  success: boolean
  cancelled?: boolean
  goal?: string
  error?: string
  trace_id?: string
  state?: Record<string, unknown>
  observation?: Record<string, unknown>
}

export interface StreamEvent {
  name: string
  payload: Record<string, unknown>
}

export type TaskPhase = 'idle' | 'queued' | 'running' | 'done' | 'cancelled' | 'failed'

export interface TimelineStep {
  index: number
  tool: string
  status: 'running' | 'ok' | 'error' | 'denied'
  duration_ms?: number
  error?: string
}

export interface TaskModel {
  phase: TaskPhase
  goal: string
  runId: string
  steps: TimelineStep[]
  errors: string[]
  result?: RunResult
}
