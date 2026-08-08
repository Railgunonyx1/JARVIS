import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { useKernelStore } from '../../stores/kernelStore'
import { useVoiceStore } from '../../stores/voiceStore'

export default function StatusBar() {
  const connected = useKernelStore((s) => s.connected)
  const performanceMode = useKernelStore((s) => s.performanceMode)
  const micActive = useVoiceStore((s) => s.micActive)
  const camActive = useVoiceStore((s) => s.camActive)
  const [clock, setClock] = useState('')

  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setClock(now.toLocaleTimeString('en-US', { hour12: false }))
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <motion.header
      className="status-bar"
      initial={{ y: -30, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
    >
      <div className="status-bar-left">
        <motion.span
          className={`status-dot ${connected ? 'on' : 'off'}`}
          animate={connected ? { scale: [1, 1.3, 1], transition: { repeat: Infinity, duration: 2 } } : {}}
        />
        <h1 className="status-title">JARVIS MK-X</h1>
        <span className="status-subtitle">COMMAND CENTER</span>
      </div>
      <div className="status-bar-right">
        <span className="status-indicator">
          <span className="status-dot-sm" style={{ background: connected ? '#00d4ff' : '#333' }} />
          {connected ? 'ONLINE' : 'OFFLINE'}
        </span>
        <span className="status-indicator">{performanceMode.toUpperCase()}</span>
        <span className="status-indicator" style={{ color: micActive ? '#ff6b35' : undefined }}>MIC {micActive ? 'ON' : 'OFF'}</span>
        <span className="status-indicator" style={{ color: camActive ? '#ff6b35' : undefined }}>CAM {camActive ? 'ON' : 'OFF'}</span>
        <span className="status-clock">{clock}</span>
      </div>
    </motion.header>
  )
}
