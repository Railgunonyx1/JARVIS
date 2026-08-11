/** Browser WebSocket client for the JARVIS daemon (mirrors daemon/client.py).
 *
 * Responsibilities:
 *  - envelope-framed JSON over a native WebSocket
 *  - authenticated handshake (permanent token or short-lived bootstrap)
 *  - request/response correlation by id
 *  - run streaming (stream.event frames -> onEvent, stream.result -> result)
 *  - cancellation via MSG_CANCEL using the current run id
 *  - bounded-backoff reconnect that resends an in-flight run with the SAME id,
 *    so the daemon's run-id dedupe resumes the kernel task instead of running
 *    it twice
 *  - app-level heartbeat (ping every ~15s) with a stale-frame watchdog
 */

import { Backoff } from './reconnect'
import {
  MSG_AUTH,
  MSG_CANCEL,
  MSG_CONN_STATE,
  MSG_EVENT,
  MSG_ERROR,
  MSG_OK,
  MSG_PING,
  MSG_PONG,
  MSG_RESULT,
  MSG_RUN,
  MSG_RUN_RESULT,
  makeEnvelope,
  randomId,
} from './protocol'
import type { Envelope } from './protocol'
import type { ConnectionStatus, ConnStateEvent, RunResult, StreamEvent } from './types'

export type AuthCredentials = { token: string } | { bootstrap: string }

export interface RunHandlers {
  onEvent(event: StreamEvent): void
  onResult(result: RunResult): void
  onError(error: Error): void
}

interface PendingRequest {
  resolve(payload: Record<string, unknown>): void
  reject(error: Error): void
  timer: number
}

interface RunHandle {
  handlers: RunHandlers
  settled: boolean
}

export const HEARTBEAT_MS = 15_000
export const STALE_FRAME_MS = 40_000

export class DaemonClient {
  private ws: WebSocket | null = null
  private url = ''
  private auth: AuthCredentials = { token: '' }
  private status: ConnectionStatus = 'idle'
  private pending = new Map<string, PendingRequest>()
  private runs = new Map<string, RunHandle>()
  private runId: string | null = null
  private connStateListeners = new Set<(event: ConnStateEvent) => void>()
  private statusListeners = new Set<(status: ConnectionStatus, detail: string) => void>()
  private backoff = new Backoff()
  private manualClose = false
  private heartbeatTimer: number | null = null
  private staleTimer: number | null = null
  private lastFrameAt = 0

  // ── observers ──────────────────────────────────────────────────────────

  onStatus(fn: (status: ConnectionStatus, detail: string) => void): () => void {
    this.statusListeners.add(fn)
    return () => this.statusListeners.delete(fn)
  }

  onConnState(fn: (event: ConnStateEvent) => void): () => void {
    this.connStateListeners.add(fn)
    return () => this.connStateListeners.delete(fn)
  }

  get currentStatus(): ConnectionStatus {
    return this.status
  }

  // ── lifecycle ──────────────────────────────────────────────────────────

  connect(url: string, auth: AuthCredentials): void {
    this.url = url
    this.auth = auth
    this.manualClose = false
    this.backoff.reset()
    this.open()
  }

  disconnect(): void {
    this.manualClose = true
    this.runs.clear()
    this.runId = null
    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
    if (this.staleTimer !== null) {
      window.clearInterval(this.staleTimer)
      this.staleTimer = null
    }
    this.ws?.close()
    this.ws = null
    this.setStatus('idle')
  }

  private open(): void {
    this.setStatus('connecting')
    let socket: WebSocket
    try {
      socket = new WebSocket(this.url)
    } catch (err) {
      this.handleOpenFailure(err)
      return
    }
    this.ws = socket
    socket.onopen = () => {
      this.lastFrameAt = Date.now()
      this.send(makeEnvelope(MSG_AUTH, this.auth as Record<string, unknown>, randomId()))
    }
    socket.onmessage = (event: MessageEvent) => {
      this.lastFrameAt = Date.now()
      this.handleMessage(event.data)
    }
    socket.onclose = () => this.handleClose()
    socket.onerror = () => {
      /* onclose follows; surface a readable detail if no close arrives */
    }
  }

  private handleOpenFailure(err: unknown): void {
    const message = err instanceof Error ? err.message : String(err)
    this.setStatus('error', `connection failed: ${message}`)
    this.ws = null
    this.scheduleReconnect()
  }

  private handleClose(): void {
    this.ws = null
    if (this.manualClose) {
      return
    }
    if (this.runs.size > 0 || this.runId !== null) {
      this.setStatus('reconnecting', 'connection lost; resuming task')
    } else {
      this.setStatus('reconnecting')
    }
    this.scheduleReconnect()
  }

  private scheduleReconnect(): void {
    const delay = this.backoff.next()
    if (delay === null) {
      this.setStatus('error', 'reconnect attempts exhausted')
      this.failInFlight('reconnect attempts exhausted')
      return
    }
    window.setTimeout(() => {
      if (!this.manualClose) {
        this.open()
      }
    }, delay)
  }

  private setStatus(status: ConnectionStatus, detail = ''): void {
    this.status = status
    for (const fn of this.statusListeners) {
      fn(status, detail)
    }
  }

  // ── wire handling ──────────────────────────────────────────────────────

  private handleMessage(raw: unknown): void {
    let frame: Envelope
    try {
      const data = typeof raw === 'string' ? JSON.parse(raw) : raw
      frame = data as Envelope
    } catch {
      return // malformed frame; the daemon closes dead peers at the transport
    }
    if (frame.type === MSG_CONN_STATE) {
      const event = frame.payload as unknown as ConnStateEvent
      for (const fn of this.connStateListeners) {
        fn(event)
      }
      return
    }
    if (frame.type === MSG_EVENT) {
      const run = this.runs.get(frame.id)
      if (run && !run.settled) {
        const data = frame.payload as { name?: string; payload?: unknown }
        run.handlers.onEvent({
          name: data.name ?? '',
          payload: (data.payload ?? {}) as Record<string, unknown>,
        })
      }
      return
    }
    if (frame.type === MSG_RUN_RESULT) {
      const run = this.runs.get(frame.id)
      if (run && !run.settled) {
        run.settled = true
        const result = (frame.payload as { result?: RunResult }).result ?? ({} as RunResult)
        run.handlers.onResult(result)
      }
      if (frame.id === this.runId) {
        this.runId = null
      }
      this.runs.delete(frame.id)
      return
    }
    if (frame.type === MSG_ERROR) {
      const run = this.runs.get(frame.id)
      if (run && !run.settled) {
        run.settled = true
        const message = (frame.payload as { message?: string }).message ?? 'run failed'
        run.handlers.onError(new Error(message))
      }
      if (frame.id === this.runId) {
        this.runId = null
      }
      this.runs.delete(frame.id)
      return
    }
    const pending = this.pending.get(frame.id)
    if (!pending) {
      return
    }
    this.pending.delete(frame.id)
    window.clearTimeout(pending.timer)
    if (frame.type === MSG_ERROR) {
      const message = (frame.payload as { message?: string }).message ?? 'request failed'
      pending.reject(new Error(message))
    } else if (frame.type === MSG_OK || frame.type === MSG_RESULT || frame.type === MSG_PONG) {
      pending.resolve(frame.payload)
    }
  }

  private send(frame: Envelope): void {
    const ws = this.ws
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      throw new Error('not connected')
    }
    ws.send(JSON.stringify(frame))
  }

  request(type: string, payload: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    return new Promise((resolve, reject) => {
      const id = randomId()
      let timer = 0
      timer = window.setTimeout(() => {
        this.pending.delete(id)
        reject(new Error('request timed out'))
      }, 30_000)
      this.pending.set(id, { resolve, reject, timer })
      try {
        this.send(makeEnvelope(type, payload, id))
      } catch (err) {
        this.pending.delete(id)
        window.clearTimeout(timer)
        reject(err)
      }
    })
  }

  async ping(): Promise<Record<string, unknown>> {
    return this.request(MSG_PING)
  }

  // ── runs ───────────────────────────────────────────────────────────────

  run(goal: string, handlers: RunHandlers): void {
    const id = this.runId ?? randomId()
    this.runId = id
    const handle: RunHandle = { handlers, settled: false }
    this.runs.set(id, handle)
    this.issueRun(id, goal)
    this.startTimers()
  }

  private issueRun(id: string, goal: string): void {
    try {
      this.send(makeEnvelope(MSG_RUN, { goal }, id))
    } catch {
      // Not connected: reconnect resends the run with the same id.
    }
  }

  cancel(): void {
    if (!this.runId) {
      return
    }
    try {
      this.send(makeEnvelope(MSG_CANCEL, { task_id: this.runId }, randomId()))
    } catch {
      /* no-op */
    }
  }

  private failInFlight(reason: string): void {
    for (const [id, run] of this.runs) {
      if (!run.settled) {
        run.settled = true
        run.handlers.onError(new Error(reason))
      }
      this.runs.delete(id)
    }
    if (this.runId !== null) {
      this.runs.delete(this.runId)
      this.runId = null
    }
  }

  // ── heartbeat / staleness ──────────────────────────────────────────────

  private startTimers(): void {
    if (this.heartbeatTimer !== null || this.staleTimer !== null) {
      return
    }
    this.heartbeatTimer = window.setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        try {
          this.send(makeEnvelope(MSG_PING, {}, randomId()))
        } catch {
          /* closed underneath us */
        }
      }
    }, HEARTBEAT_MS)
    this.staleTimer = window.setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        if (Date.now() - this.lastFrameAt > STALE_FRAME_MS) {
          this.ws.close()
        }
      }
    }, HEARTBEAT_MS)
  }
}
