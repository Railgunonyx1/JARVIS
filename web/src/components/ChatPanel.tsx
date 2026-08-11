import { useEffect, useRef, useState } from 'react'
import { useConnectionStore } from '../store/connection'
import { useTaskStore } from '../store/task'

interface Message {
  role: 'user' | 'assistant'
  text: string
  error?: boolean
}

export function ChatPanel() {
  const client = useConnectionStore((s) => s.client)
  const connected = useConnectionStore((s) => s.status === 'connected')
  const phase = useTaskStore((s) => s.phase)
  const startRun = useTaskStore((s) => s.startRun)
  const handleEvent = useTaskStore((s) => s.handleEvent)
  const finishRun = useTaskStore((s) => s.finishRun)
  const failRun = useTaskStore((s) => s.failRun)
  const cancelRun = useTaskStore((s) => s.cancelRun)

  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  const running = phase === 'queued' || phase === 'running'

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])

  function send() {
    const goal = input.trim()
    if (!goal || !connected) return
    setMessages((m) => [...m, { role: 'user', text: goal }])
    setInput('')
    startRun('', goal)
    client.run(goal, {
      onEvent: (event) => {
        handleEvent(event.name, event.payload)
      },
      onResult: (result) => {
        finishRun(result)
        setMessages((m) => [
          ...m,
          {
            role: 'assistant',
            text:
              result.success
                ? 'Task completed.'
                : `Task failed: ${result.error ?? 'unknown error'}`,
            error: !result.success,
          },
        ])
      },
      onError: (error) => {
        failRun(error)
        setMessages((m) => [...m, { role: 'assistant', text: error.message, error: true }])
      },
    })
  }

  function cancel() {
    cancelRun()
    client.cancel()
  }

  return (
    <div className="flex h-[calc(100vh-5rem)] flex-col rounded-lg border border-zinc-800 bg-zinc-900/40">
      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto p-4 text-sm"
      >
        {messages.length === 0 && (
          <p className="text-center text-zinc-500">
            Ask JARVIS something. {connected ? '' : 'Connect to the daemon first.'}
          </p>
        )}
        {messages.map((message, i) => (
          <div
            key={i}
            className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 ${
              message.role === 'user'
                ? 'ml-auto bg-emerald-600/20 text-emerald-100'
                : message.error
                  ? 'bg-red-900/30 text-red-200'
                  : 'bg-zinc-800 text-zinc-200'
            }`}
          >
            {message.text}
          </div>
        ))}
        {running && (
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-400" />
            Working…
          </div>
        )}
      </div>
      <div className="flex items-center gap-2 border-t border-zinc-800 p-3">
        <input
          className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
          placeholder={connected ? 'Describe a task…' : 'Connect to the daemon to chat'}
          value={input}
          disabled={!connected || running}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && connected && !running) send()
          }}
        />
        {running ? (
          <button
            className="rounded bg-red-800 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
            onClick={cancel}
          >
            Cancel
          </button>
        ) : (
          <button
            className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
            disabled={!connected || !input.trim()}
            onClick={send}
          >
            Send
          </button>
        )}
      </div>
    </div>
  )
}
