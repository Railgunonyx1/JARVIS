import { authHeaders, API_BASE } from './api'

export async function startMic() {
  try {
    const r = await fetch(`${API_BASE}/api/mic/start`, { method: 'POST', headers: authHeaders() })
    const data = await r.json()
    return data.ok
  } catch { return false }
}

export async function stopMic() {
  try {
    const r = await fetch(`${API_BASE}/api/mic/stop`, { method: 'POST', headers: authHeaders() })
    const data = await r.json()
    return data
  } catch { return null }
}

export async function startCam() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } })
    return stream
  } catch { return null }
}

export function stopCam(stream) {
  if (stream) {
    stream.getTracks().forEach(t => t.stop())
  }
}

export async function fetchHealth() {
  try {
    const r = await fetch(`${API_BASE}/api/health`)
    return await r.json()
  } catch { return null }
}
