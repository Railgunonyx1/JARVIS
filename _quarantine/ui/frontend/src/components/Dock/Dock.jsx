import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Mic, Camera, HeartPulse, Brain, Power } from 'lucide-react'
import { useVoiceStore } from '../../stores/voiceStore'
import { useChatStore } from '../../stores/chatStore'
import { authHeaders, API_BASE } from '../../services/api'
import { startMic, stopMic, fetchHealth } from '../../services/voice'
import { escapeHtml } from '../../services/chat'

export default function Dock() {
  const setMicActive = useVoiceStore((s) => s.setMicActive)
  const setCamActive = useVoiceStore((s) => s.setCamActive)
  const camActive = useVoiceStore((s) => s.camActive)
  const addMessage = useChatStore((s) => s.addMessage)
  const [healthVisible, setHealthVisible] = useState(false)
  const [healthContent, setHealthContent] = useState('')
  const [shutdownVisible, setShutdownVisible] = useState(false)

  const handleMic = async () => {
    const active = useVoiceStore.getState().micActive
    if (active) {
      const data = await stopMic()
      setMicActive(false)
      if (data?.ok && data.text) {
        window.dispatchEvent(new CustomEvent('jarvis:mic-result', { detail: data }))
      }
    } else {
      const ok = await startMic()
      if (ok) setMicActive(true)
    }
  }

  const handleCam = () => {
    setCamActive(!useVoiceStore.getState().camActive)
  }

  const handleHealth = async () => {
    setHealthVisible(true)
    setHealthContent('<div class="health-loading">Loading health data...</div>')
    const data = await fetchHealth()
    if (data?.report) {
      setHealthContent(`<pre class="health-report">${escapeHtml(data.report)}</pre>`)
    } else if (data?.checks) {
      setHealthContent(data.checks.map((c) => {
        const icon = c.ok ? '<span class="health-ok">OK</span>' : '<span class="health-fail">FAIL</span>'
        return `<div class="health-row"><span>${escapeHtml(c.name)}</span><span>${icon} ${escapeHtml(c.message || '')}</span></div>`
      }).join(''))
    } else {
      setHealthContent('<div class="health-loading">Health check unavailable</div>')
    }
  }

  const handleMemory = () => {
    fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ text: '/memory status' }),
    }).then(r => r.json()).then(data => {
      if (data.ok && data.response) addMessage('ai', data.response)
    }).catch(() => {})
    window.dispatchEvent(new CustomEvent('jarvis:log', { detail: { tag: 'CMD', text: '/memory status' } }))
  }

  const handleShutdown = () => {
    setShutdownVisible(false)
    fetch(`${API_BASE}/api/shutdown`, { method: 'POST', headers: authHeaders() }).catch(() => {})
    window.dispatchEvent(new CustomEvent('jarvis:log', { detail: { tag: 'SYS', text: 'Shutdown initiated' } }))
    addMessage('system', 'JARVIS shutting down...')
  }

  const btnClass = (active) =>
    `dock-btn ${active ? 'active' : ''}`

  return (
    <>
      <motion.div
        className="dock"
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      >
        <motion.button
          className={btnClass(false)}
          onClick={handleMic}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <Mic size={16} />MIC
        </motion.button>
        <motion.button
          className={btnClass(camActive)}
          onClick={handleCam}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <Camera size={16} />CAM
        </motion.button>
        <motion.button
          className="dock-btn"
          onClick={handleHealth}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <HeartPulse size={16} />HEALTH
        </motion.button>
        <motion.button
          className="dock-btn"
          onClick={handleMemory}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <Brain size={16} />MEMORY
        </motion.button>
        <motion.button
          className="dock-btn shutdown"
          onClick={() => setShutdownVisible(true)}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <Power size={16} />SHUTDOWN
        </motion.button>
      </motion.div>

      <AnimatePresence>
        {healthVisible && (
          <motion.div
            className="modal-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={(e) => { if (e.target === e.currentTarget) setHealthVisible(false) }}
          >
            <motion.div
              className="modal-content"
              initial={{ scale: 0.9, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.9, y: 20 }}
              transition={{ type: 'spring', stiffness: 300, damping: 25 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="modal-header">
                <span className="modal-title">SYSTEM HEALTH</span>
                <button className="modal-close" onClick={() => setHealthVisible(false)}>&times;</button>
              </div>
              <div className="modal-body" dangerouslySetInnerHTML={{ __html: healthContent }} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {shutdownVisible && (
          <motion.div
            className="modal-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={(e) => { if (e.target === e.currentTarget) setShutdownVisible(false) }}
          >
            <motion.div
              className="modal-content shutdown-modal"
              initial={{ scale: 0.9, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.9, y: 20 }}
              transition={{ type: 'spring', stiffness: 300, damping: 25 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="modal-header">
                <span className="modal-title shutdown-title">SHUTDOWN CONFIRM</span>
                <button className="modal-close" onClick={() => setShutdownVisible(false)}>&times;</button>
              </div>
              <p className="shutdown-text">This will shut down JARVIS and all connected services. Are you sure?</p>
              <div className="shutdown-actions">
                <button className="btn-danger" onClick={handleShutdown}>CONFIRM</button>
                <button className="btn-cancel" onClick={() => setShutdownVisible(false)}>CANCEL</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
