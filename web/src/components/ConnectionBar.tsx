import { useState } from 'react'
import { useConnectionStore } from '../store/connection'
import type { ConnectionStatus } from '../daemon/types'

const DOT: Record<ConnectionStatus, string> = {
  idle: 'bg-zinc-500',
  connecting: 'bg-amber-400 animate-pulse',
  connected: 'bg-emerald-400',
  reconnecting: 'bg-amber-400 animate-pulse',
  error: 'bg-red-500',
}

const LABEL: Record<ConnectionStatus, string> = {
  idle: 'disconnected',
  connecting: 'connecting',
  connected: 'connected',
  reconnecting: 'reconnecting',
  error: 'error',
}

export function ConnectionBar() {
  const status = useConnectionStore((s) => s.status)
  const detail = useConnectionStore((s) => s.detail)
  const peerCount = useConnectionStore((s) => s.peerCount)
  const bootstrapUrl = useConnectionStore((s) => s.bootstrapUrl)
  const connect = useConnectionStore((s) => s.connect)
  const disconnect = useConnectionStore((s) => s.disconnect)
  const [url, setUrl] = useState('')

  const connected = status === 'connected'

  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-zinc-800 bg-zinc-900 px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="text-lg">🗣</span>
        <h1 className="text-sm font-semibold tracking-wide text-zinc-100">JARVIS</h1>
        <span className={`inline-block h-2 w-2 rounded-full ${DOT[status]}`} />
        <span className="text-xs text-zinc-400">{LABEL[status]}</span>
        {peerCount > 0 && (
          <span className="text-xs text-zinc-500">· {peerCount} client{peerCount !== 1 ? 's' : ''}</span>
        )}
        {detail && <span className="text-xs text-amber-400">{detail}</span>}
      </div>

      <input
        className="min-w-52 flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-zinc-500"
        placeholder="ws://127.0.0.1:5174/"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />

      {bootstrapUrl && (
        <div className="hidden items-center gap-1 text-xs text-zinc-500 md:flex">
          <span className="text-zinc-600">bootstrap:</span>
          <code className="truncate">{bootstrapUrl}</code>
        </div>
      )}

      {connected ? (
        <button
          className="rounded border border-zinc-600 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
          onClick={disconnect}
        >
          Disconnect
        </button>
      ) : (
        <button
          className="rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
          disabled={!url.trim()}
          onClick={() => connect(url.trim(), { bootstrap: bootstrapUrl })}
        >
          Connect
        </button>
      )}
    </header>
  )
}
