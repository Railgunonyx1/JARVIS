import { authHeaders, API_BASE } from './api'

let activeController = null
let activeAudio = null

export function abortStream() {
  if (activeController) { activeController.abort(); activeController = null }
}

export function stopAudio() {
  if (activeAudio) { activeAudio.pause(); activeAudio = null }
}

export function sendChatStream(text, callbacks) {
  abortStream()

  const controller = new AbortController()
  activeController = controller

  callbacks?.onStart?.()

  fetch(`${API_BASE}/api/chat/stream`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ text }),
    signal: controller.signal,
  }).then(async (response) => {
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    function read() {
      reader.read().then(({ done, value }) => {
        if (done) { callbacks?.onDone?.(); return }
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const msg = JSON.parse(line.slice(6))
            if (msg.type === 'text' && msg.token) {
              callbacks?.onToken?.(msg.token)
            } else if (msg.type === 'tts_chunk' && msg.audio) {
              callbacks?.onAudio?.(msg.audio)
            } else if (msg.type === 'timing' && msg.timing) {
              callbacks?.onTiming?.(msg.timing)
            } else if (msg.type === 'error') {
              callbacks?.onError?.(msg.error)
            } else if (msg.type === 'done') {
              callbacks?.onDone?.()
            }
          } catch { /* ignore */ }
        }
        read()
      })
    }
    read()
  }).catch((e) => {
    if (e.name === 'AbortError') {
      callbacks?.onError?.('cancelled')
    } else {
      callbacks?.onError?.(e.message)
    }
  })
}

export function escapeHtml(str) {
  const div = document.createElement('div')
  div.appendChild(document.createTextNode(str))
  return div.innerHTML
}

export function speakText(text) {
  stopAudio()

  fetch(`${API_BASE}/api/tts/stream`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ text }),
  }).then(async (response) => {
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let queue = []
    let playing = false

    function playNext() {
      if (queue.length === 0) { playing = false; return }
      playing = true
      const b64 = queue.shift()
      try {
        const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0))
        const blob = new Blob([bytes], { type: 'audio/wav' })
        const url = URL.createObjectURL(blob)
        const audio = new Audio(url)
        audio.onended = () => { URL.revokeObjectURL(url); playNext() }
        audio.onerror = () => { URL.revokeObjectURL(url); playNext() }
        activeAudio = audio
        audio.play().catch(() => playNext())
      } catch { playNext() }
    }

    function read() {
      reader.read().then(({ done, value }) => {
        if (done) return
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const msg = JSON.parse(line.slice(6))
            if (msg.type === 'tts_chunk' && msg.audio) {
              queue.push(msg.audio)
              if (!playing) playNext()
            } else if (msg.type === 'tts_done' && !playing && msg.audio) {
              const bytes = Uint8Array.from(atob(msg.audio), c => c.charCodeAt(0))
              const blob = new Blob([bytes], { type: 'audio/wav' })
              const url = URL.createObjectURL(blob)
              activeAudio = new Audio(url)
              activeAudio.onended = () => { URL.revokeObjectURL(url); activeAudio = null }
              activeAudio.play().catch(() => {})
            }
          } catch { /* ignore */ }
        }
        read()
      })
    }
    read()
  }).catch(() => {
    fetch(`${API_BASE}/api/tts`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ text }),
    }).then(r => r.blob()).then(blob => {
      const url = URL.createObjectURL(blob)
      activeAudio = new Audio(url)
      activeAudio.onended = () => { URL.revokeObjectURL(url); activeAudio = null }
      activeAudio.play().catch(() => {})
    }).catch(() => {})
  })
}

