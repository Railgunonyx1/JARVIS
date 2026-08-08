import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { Activity, Cpu, HardDrive } from 'lucide-react'
import { useKernelStore } from '../../stores/kernelStore'
import { useTelemetryStore } from '../../stores/telemetryStore'

export default function SystemPanel() {
  const startTime = useKernelStore((s) => s.startTime)
  const cpu = useTelemetryStore((s) => s.cpu)
  const ram = useTelemetryStore((s) => s.ram)
  const [uptime, setUptime] = useState('00:00:00')
  const [logs, setLogs] = useState([{ tag: 'SYS', text: 'HUD initialized' }])
  const logRef = useRef(null)

  useEffect(() => {
    const tick = () => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000)
      const h = String(Math.floor(elapsed / 3600)).padStart(2, '0')
      const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0')
      const s = String(elapsed % 60).padStart(2, '0')
      setUptime(`${h}:${m}:${s}`)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [startTime])

  useEffect(() => {
    const handler = (e) => {
      const { tag, text } = e.detail
      setLogs((prev) => {
        const next = [{ tag, text }, ...prev]
        return next.slice(0, 60)
      })
    }
    window.addEventListener('jarvis:log', handler)
    return () => window.removeEventListener('jarvis:log', handler)
  }, [])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = 0
  }, [logs])

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5, delay: 0.1 }}
    >
      <div className="quick-stats">
        <div className="panel-title"><Activity size={10} /> QUICK STATS</div>
        <div className="stats-grid">
          <div className="stat-row"><span><Cpu size={10} /> UPTIME</span><span className="stat-value">{uptime}</span></div>
          <div className="stat-row"><span><Cpu size={10} /> CPU</span><span className="stat-value">{Math.round(cpu)}%</span></div>
          <div className="stat-row"><span><HardDrive size={10} /> RAM</span><span className="stat-value">{Math.round(ram)}%</span></div>
        </div>
      </div>

      <div className="process-panel">
        <div className="panel-title">ACTIVE PROCESSES</div>
        {['jarvis-core', 'stt-engine', 'tts-engine', 'vision-proc', 'llm-backend'].map((p) => (
          <div key={p} className="process-row">
            <span>{p}</span>
            <span className="stat-value">OK</span>
          </div>
        ))}
      </div>

      <div className="log-panel">
        <div className="panel-title">RECENT LOGS</div>
        <div ref={logRef} className="log-list">
          {logs.map((l, i) => (
            <motion.div
              key={i}
              className="log-entry"
              initial={{ opacity: 0, x: -5 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2 }}
            >
              [<span className="log-tag">{l.tag}</span>] {l.text}
            </motion.div>
          ))}
        </div>
      </div>
    </motion.div>
  )
}
