import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, Square } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { sendChatStream, abortStream, speakText } from '../../services/chat'

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export default function ChatPanel() {
  const messages = useChatStore((s) => s.messages)
  const streaming = useChatStore((s) => s.streaming)
  const streamText = useChatStore((s) => s.streamText)
  const timing = useChatStore((s) => s.timing)
  const addMessage = useChatStore((s) => s.addMessage)
  const startStream = useChatStore((s) => s.startStream)
  const appendStream = useChatStore((s) => s.appendStream)
  const endStream = useChatStore((s) => s.endStream)
  const setTiming = useChatStore((s) => s.setTiming)

  const [input, setInput] = useState('')
  const listRef = useRef(null)
  const firstTokenRef = useRef(false)

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, streamText])

  const handleSend = useCallback(() => {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')
    addMessage('user', text)
    startStream()
    firstTokenRef.current = false
    window.dispatchEvent(new CustomEvent('jarvis:log', { detail: { tag: 'CMD', text } }))
    let fullResponse = ''
    sendChatStream(text, {
      onToken: (token) => {
        if (!firstTokenRef.current) firstTokenRef.current = true
        fullResponse += token
        appendStream(token)
      },
      onAudio: (b64) => {
        try {
          const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0))
          const blob = new Blob([bytes], { type: 'audio/wav' })
          const url = URL.createObjectURL(blob)
          const audio = new Audio(url)
          audio.onended = () => URL.revokeObjectURL(url)
          audio.play().catch(() => {})
        } catch {}
      },
      onTiming: (t) => setTiming(t),
      onError: (err) => {
        if (err === 'cancelled') addMessage('system', 'Stream cancelled')
        else addMessage('system', `Error: ${err}`)
        endStream()
      },
      onDone: () => {
        addMessage('ai', fullResponse)
        speakText(fullResponse)
        endStream()
      },
    })
  }, [input, streaming, addMessage, startStream, appendStream, endStream, setTiming])

  return (
    <motion.div
      className="chat-panel"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className="panel-title">AI RESPONSE <span className="panel-subtitle">{messages.length} messages</span></div>
      <div ref={listRef} className="chat-list">
        {messages.length === 0 && !streaming && (
          <div className="chat-placeholder">Awaiting input...</div>
        )}
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              className={`chat-message chat-${msg.role}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
            >
              {msg.role === 'user' && <div className="chat-label user-label">YOU</div>}
              {msg.role === 'ai' && <div className="chat-label ai-label">JARVIS</div>}
              <div className="chat-text">{escapeHtml(msg.text)}</div>
            </motion.div>
          ))}
        </AnimatePresence>
        {streaming && (
          <motion.div
            className="chat-message chat-ai streaming"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            <div className="chat-label ai-label">JARVIS</div>
            <div className="chat-text">
              {streamText || (!firstTokenRef.current ? (
                <span className="thinking-indicator">
                  <span className="thinking-dot" /><span className="thinking-dot" /><span className="thinking-dot" />
                </span>
              ) : null)}
              {firstTokenRef.current && <span className="cursor-blink" />}
            </div>
            {timing && (
              <div className="timing-bar visible">
                {[
                  timing.intent_ms && `Intent: ${timing.intent_ms}ms`,
                  timing.ttft_ms && `TTFT: ${timing.ttft_ms}ms`,
                  timing.tokens_per_sec && `${timing.tokens_per_sec} tok/s`,
                  timing.total_ms && `Total: ${timing.total_ms}ms`,
                  timing.provider,
                ].filter(Boolean).join(' | ')}
              </div>
            )}
          </motion.div>
        )}
      </div>
      <div className="chat-input-wrapper" style={{ marginTop: 8 }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
          placeholder="Enter command..."
          className="chat-input"
          disabled={streaming}
        />
        <motion.button
          className="send-btn"
          onClick={handleSend}
          disabled={streaming || !input.trim()}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          {streaming ? <Square size={14} onClick={abortStream} /> : <Send size={14} />}
        </motion.button>
      </div>
    </motion.div>
  )
}
