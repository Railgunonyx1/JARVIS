import type { ClientCommand, ConnectionState, ServerEvent } from "./protocol"
import { PROTOCOL_VERSION } from "./protocol"
import { Simulator } from "./simulator"

export type EventListener = (e: ServerEvent) => void
export type StateListener = (state: ConnectionState, meta: { attempts: number; usingSim: boolean; url: string }) => void

const DEFAULT_URL =
  (typeof window !== "undefined" && (window as { __JARVIS_WS__?: string }).__JARVIS_WS__) || "ws://127.0.0.1:8787/ws"

// After this many failed connection attempts we transparently engage the local
// in-browser daemon simulator so the console stays fully interactive. The real
// socket keeps its protocol; the sim just speaks the same ServerEvent shape.
const AUTO_SIM_AFTER = 2
const CONNECT_TIMEOUT = 2500
const HEARTBEAT_INTERVAL = 10_000

/**
 * The single client seam. Everything above (stores, UI) talks only to this.
 * Everything below (WebSocket now, Tauri IPC later, sim fallback) is hidden.
 */
export class JarvisClient {
  state: ConnectionState = "idle"
  url: string = DEFAULT_URL

  private ws: WebSocket | null = null
  private sim: Simulator | null = null
  private usingSim = false
  private attempts = 0
  private lastSeq = 0
  private manualClose = false
  private queue: ClientCommand[] = []

  private eventListeners = new Set<EventListener>()
  private stateListeners = new Set<StateListener>()

  private heartbeat: ReturnType<typeof setInterval> | null = null
  private connectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null

  on(fn: EventListener): () => void {
    this.eventListeners.add(fn)
    return () => this.eventListeners.delete(fn)
  }

  onState(fn: StateListener): () => void {
    this.stateListeners.add(fn)
    fn(this.state, { attempts: this.attempts, usingSim: this.usingSim, url: this.url })
    return () => this.stateListeners.delete(fn)
  }

  connect(url?: string) {
    if (url) this.url = url
    this.manualClose = false
    this.usingSim = false
    this.teardownSim()
    this.openSocket()
  }

  /** Explicitly run against the local simulator (used by the "SIM" toggle). */
  useSimulator() {
    this.manualClose = true
    this.closeSocket()
    this.startSim()
  }

  reconnect() {
    this.attempts = 0
    this.connect(this.url)
  }

  disconnect() {
    this.manualClose = true
    this.closeSocket()
    this.teardownSim()
    this.setState("offline")
  }

  send(cmd: ClientCommand) {
    if (this.usingSim && this.sim) {
      this.sim.handle(cmd)
      return
    }
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(cmd))
    } else {
      // Buffer until the socket is back; replayed in order on open.
      this.queue.push(cmd)
    }
  }

  // ---- internals ---------------------------------------------------------

  private openSocket() {
    this.setState(this.attempts === 0 ? "connecting" : "reconnecting")
    let ws: WebSocket
    try {
      ws = new WebSocket(this.url)
    } catch {
      this.handleFailure()
      return
    }
    this.ws = ws

    this.connectTimer = setTimeout(() => {
      if (ws.readyState !== WebSocket.OPEN) {
        try {
          ws.close()
        } catch {
          /* noop */
        }
      }
    }, CONNECT_TIMEOUT)

    ws.onopen = () => {
      this.clearConnectTimer()
      this.attempts = 0
      this.setState("online")
      this.rawSend({ type: "hello", payload: { client: `jarvis-ui/${PROTOCOL_VERSION}`, lastSeq: this.lastSeq } })
      this.flushQueue()
      this.startHeartbeat()
    }

    ws.onmessage = (ev) => {
      let msg: ServerEvent
      try {
        msg = JSON.parse(ev.data as string)
      } catch {
        return
      }
      if (typeof msg.seq === "number") this.lastSeq = msg.seq
      this.emit(msg)
    }

    ws.onerror = () => {
      /* onclose will follow */
    }

    ws.onclose = () => {
      this.clearConnectTimer()
      this.stopHeartbeat()
      this.ws = null
      if (this.manualClose) return
      this.handleFailure()
    }
  }

  private handleFailure() {
    this.attempts++
    if (this.attempts >= AUTO_SIM_AFTER) {
      this.startSim()
      return
    }
    this.setState("reconnecting")
    const delay = Math.min(1000 * 2 ** this.attempts, 8000)
    this.reconnectTimer = setTimeout(() => this.openSocket(), delay)
  }

  private rawSend(cmd: ClientCommand) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(cmd))
  }

  private flushQueue() {
    const pending = this.queue
    this.queue = []
    for (const cmd of pending) this.rawSend(cmd)
  }

  private startHeartbeat() {
    this.stopHeartbeat()
    this.heartbeat = setInterval(() => {
      this.rawSend({ type: "ping", payload: { t: Date.now() } })
    }, HEARTBEAT_INTERVAL)
  }

  private stopHeartbeat() {
    if (this.heartbeat) clearInterval(this.heartbeat)
    this.heartbeat = null
  }

  private clearConnectTimer() {
    if (this.connectTimer) clearTimeout(this.connectTimer)
    this.connectTimer = null
  }

  private closeSocket() {
    this.clearConnectTimer()
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    this.stopHeartbeat()
    if (this.ws) {
      try {
        this.ws.close()
      } catch {
        /* noop */
      }
      this.ws = null
    }
  }

  private startSim() {
    this.closeSocket()
    this.usingSim = true
    if (!this.sim) {
      this.sim = new Simulator((e) => this.emit(e))
    }
    this.sim.start()
    this.setState("sim")
  }

  private teardownSim() {
    if (this.sim) {
      this.sim.stop()
      this.sim = null
    }
    this.usingSim = false
  }

  private emit(e: ServerEvent) {
    for (const fn of this.eventListeners) fn(e)
  }

  private setState(s: ConnectionState) {
    this.state = s
    for (const fn of this.stateListeners) {
      fn(s, { attempts: this.attempts, usingSim: this.usingSim, url: this.url })
    }
  }
}

// App-wide singleton.
export const client = new JarvisClient()
