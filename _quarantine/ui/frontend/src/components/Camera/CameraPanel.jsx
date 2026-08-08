import { useRef, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Camera, CameraOff } from 'lucide-react'
import { useVoiceStore } from '../../stores/voiceStore'
import { startCam, stopCam } from '../../services/voice'

export default function CameraPanel() {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const camActive = useVoiceStore((s) => s.camActive)
  const setCamActive = useVoiceStore((s) => s.setCamActive)
  const [fps, setFps] = useState('--')
  const [resolution, setResolution] = useState('--')
  const frameCountRef = useRef(0)
  const fpsTimerRef = useRef(null)

  useEffect(() => {
    if (camActive) {
      startCam().then((stream) => {
        if (stream && videoRef.current) {
          streamRef.current = stream
          videoRef.current.srcObject = stream
          videoRef.current.onloadedmetadata = () => {
            setResolution(`${videoRef.current.videoWidth}x${videoRef.current.videoHeight}`)
          }
          frameCountRef.current = 0
          fpsTimerRef.current = setInterval(() => {
            setFps(frameCountRef.current)
            frameCountRef.current = 0
          }, 1000)
          const countFrames = () => { frameCountRef.current++; requestAnimationFrame(countFrames) }
          requestAnimationFrame(countFrames)
        }
      })
    } else {
      stopCam(streamRef.current)
      streamRef.current = null
      if (videoRef.current) videoRef.current.srcObject = null
      setFps('--')
      setResolution('--')
      if (fpsTimerRef.current) { clearInterval(fpsTimerRef.current); fpsTimerRef.current = null }
    }
  }, [camActive])

  return (
    <motion.div
      className="camera-panel"
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {camActive ? <Camera size={12} /> : <CameraOff size={12} />}
        VISION <span className="panel-subtitle">{fps} FPS</span>
      </div>
      <div className="video-container">
        <video ref={videoRef} autoPlay muted playsInline className="video-feed" />
        {!camActive && <div className="video-placeholder">CAMERA OFFLINE</div>}
      </div>
      <div className="video-meta">
        <span>RES: {resolution}</span>
        <span>{camActive ? 'ACTIVE' : 'STANDBY'}</span>
      </div>
    </motion.div>
  )
}
