import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import './App.css'
import { useKernelStore } from './stores/kernelStore'
import { useTelemetryStore } from './stores/telemetryStore'
import { useChatStore } from './stores/chatStore'
import { fetchAuthToken } from './services/api'
import { connectTelemetry, disconnectTelemetry } from './services/telemetry'
import { speakText } from './services/chat'
import { useWebSocket } from './hooks/useWebSocket'

import StatusBar from './components/Status/StatusBar'
import ArcReactor from './components/Reactor/ArcReactor'
import SystemMonitor from './components/Monitor/SystemMonitor'
import ChatPanel from './components/Chat/ChatPanel'
import CameraPanel from './components/Camera/CameraPanel'
import VoiceControls from './components/Voice/VoiceControls'
import SystemPanel from './components/System/SystemPanel'
import Dock from './components/Dock/Dock'

export default function App() {
  const setConnected = useKernelStore((s) => s.setConnected)
  const setStatus = useKernelStore((s) => s.setStatus)
  const setPerformanceMode = useKernelStore((s) => s.setPerformanceMode)
  const updateTelemetry = useTelemetryStore((s) => s.update)
  const addMessage = useChatStore((s) => s.addMessage)
  const startStream = useChatStore((s) => s.startStream)
  const appendStream = useChatStore((s) => s.appendStream)
  const endStream = useChatStore((s) => s.endStream)
  const setTiming = useChatStore((s) => s.setTiming)

  const firstTokenRef = useRef(false)
  const { connected: wsConnected, events } = useWebSocket()

  useEffect(() => {
    setConnected(wsConnected)
    if (wsConnected) setStatus('running')
  }, [wsConnected, setConnected, setStatus])

  useEffect(() => {
    for (const ev of events) {
      if (ev.type === 'status') {
        const p = ev.payload
        if (p.cpu !== undefined) updateTelemetry(p)
        if (p.performance_mode) setPerformanceMode(p.performance_mode)
        if (p.state) setStatus(p.state)
      } else if (ev.type === 'voice') {
        if (ev.payload?.state === 'listening') {
          addMessage('user', ev.payload?.text || '...')
        }
      } else if (ev.type === 'llm') {
        if (ev.payload?.token) {
          if (!firstTokenRef.current) {
            firstTokenRef.current = true
            startStream()
          }
          appendStream(ev.payload.token)
        }
        if (ev.payload?.timing) setTiming(ev.payload.timing)
        if (ev.payload?.done) {
          endStream()
          firstTokenRef.current = false
        }
        if (ev.payload?.response) {
          addMessage('ai', ev.payload.response)
          speakText(ev.payload.response)
        }
      }
    }
  }, [events, updateTelemetry, setPerformanceMode, setStatus, addMessage, startStream, appendStream, endStream, setTiming])

  useEffect(() => {
    fetchAuthToken()
    connectTelemetry(
      (data) => {
        updateTelemetry(data)
        if (data.performance_mode) setPerformanceMode(data.performance_mode)
      },
      (connected) => {
        setConnected(connected)
        if (connected) setStatus('running')
      }
    )
    const startTime = Date.now()
    const uptimeInterval = setInterval(() => {
      useKernelStore.getState().setUptime(Math.floor((Date.now() - startTime) / 1000))
    }, 1000)
    return () => {
      disconnectTelemetry()
      clearInterval(uptimeInterval)
    }
  }, [updateTelemetry, setPerformanceMode, setConnected, setStatus])

  useEffect(() => {
    const handler = (e) => {
      const data = e.detail
      if (data.text && data.text !== '(no speech detected)' && data.text !== '(no audio captured)') {
        addMessage('user', data.text)
      }
      if (data.response) {
        addMessage('ai', data.response)
        speakText(data.response)
      }
    }
    window.addEventListener('jarvis:mic-result', handler)
    return () => window.removeEventListener('jarvis:mic-result', handler)
  }, [addMessage])

  return (
    <motion.div
      className="hud"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
    >
      <StatusBar />
      <main className="main-grid">
        <div className="left-column">
          <CameraPanel />
          <SystemPanel />
        </div>
        <div className="center-column">
          <ArcReactor />
          <ChatPanel />
        </div>
        <div className="right-column">
          <SystemMonitor />
        </div>
      </main>
      <footer className="bottom-bar">
        <div className="input-area">
          <VoiceControls />
        </div>
        <Dock />
      </footer>
    </motion.div>
  )
}
