import { useState, useEffect, useRef, useCallback } from 'react'
import { fetchAuthToken, getAuthToken } from '../services/api'

const WS_URL = 'ws://localhost:8766'

export function useWebSocket() {
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState([])
  const [systemStatus, setSystemStatus] = useState({
    status: 'offline',
    uptime: 0,
    memory: { rss_mb: 0 },
  })
  const wsRef = useRef(null)
  const maxEvents = 100

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    const open = () => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) return
      setConnected(true)
      wsRef.current.send(JSON.stringify({ type: 'auth', token: getAuthToken() }))
      wsRef.current.send(JSON.stringify({ type: 'subscribe', channels: ['status', 'voice', 'llm', 'memory'] }))
    }
    const onReady = async () => {
      if (!getAuthToken()) await fetchAuthToken()
      const ws = new WebSocket(WS_URL)
      ws.onopen = open
      ws.onclose = () => {
        setConnected(false)
        setTimeout(connect, 2000)
      }
      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data)
          if (data.type === 'status') {
            setSystemStatus(data.payload)
          } else {
            setEvents((prev) => {
              const next = [{ ...data, id: Date.now() }, ...prev]
              return next.slice(0, maxEvents)
            })
          }
        } catch { /* ignore parse errors */ }
      }
      ws.onerror = () => ws.close()
      wsRef.current = ws
    }
    onReady()
  }, [])

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  useEffect(() => {
    connect()
    return () => wsRef.current?.close()
  }, [connect])

  return { connected, events, systemStatus, send }
}
