import { API_BASE } from './api'

let eventSource = null
let listeners = []
let connected = false

export function connectTelemetry(onData, onConnection) {
  if (eventSource) eventSource.close()

  eventSource = new EventSource(`${API_BASE}/api/telemetry/stream`)

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (!connected) {
        connected = true
        onConnection?.(true)
      }
      onData?.(data)
    } catch { /* ignore */ }
  }

  eventSource.onerror = () => {
    if (connected) {
      connected = false
      onConnection?.(false)
    }
  }
}

export function disconnectTelemetry() {
  if (eventSource) { eventSource.close(); eventSource = null }
  connected = false
}
