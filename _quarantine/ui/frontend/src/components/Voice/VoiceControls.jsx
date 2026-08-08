import { motion } from 'framer-motion'
import { Mic, Square } from 'lucide-react'
import { useVoiceStore } from '../../stores/voiceStore'
import { startMic, stopMic } from '../../services/voice'

export default function VoiceControls() {
  const micActive = useVoiceStore((s) => s.micActive)
  const waveformVisible = useVoiceStore((s) => s.waveformVisible)
  const setMicActive = useVoiceStore((s) => s.setMicActive)

  const handleToggleMic = async () => {
    if (micActive) {
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

  return (
    <div className="voice-controls">
      <motion.button
        className={`mic-btn ${micActive ? 'mic-active' : ''}`}
        onClick={handleToggleMic}
        title="Toggle Microphone"
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.9 }}
        animate={micActive ? { scale: [1, 1.08, 1], transition: { repeat: Infinity, duration: 1.5 } } : {}}
      >
        {micActive ? <Square size={16} /> : <Mic size={16} />}
      </motion.button>
      {waveformVisible && (
        <motion.div
          className="waveform"
          initial={{ opacity: 0, width: 0 }}
          animate={{ opacity: 1, width: 'auto' }}
        >
          {[12, 18, 10, 22, 14, 20, 8, 16].map((h, i) => (
            <motion.div
              key={i}
              className="waveform-bar"
              style={{ height: h }}
              animate={{ height: [h, h + 8, h], transition: { repeat: Infinity, duration: 0.6 + i * 0.08, delay: i * 0.1 } }}
            />
          ))}
        </motion.div>
      )}
    </div>
  )
}
