import { useEffect } from 'react'
import { useConnectionStore } from './store/connection'
import { ConnectionBar } from './components/ConnectionBar'
import { ChatPanel } from './components/ChatPanel'
import { TimelinePanel } from './components/TimelinePanel'

function readUrlConfig(): { ws?: string; bootstrap?: string } {
  const params = new URLSearchParams(window.location.search)
  const ws = params.get('ws') ?? undefined
  const bootstrap = params.get('bootstrap') ?? undefined
  if (ws || !bootstrap) {
    return { ws, bootstrap }
  }
  const wsPort = params.get('ws_port')
  if (wsPort) {
    return { ws: `ws://127.0.0.1:${wsPort}/`, bootstrap }
  }
  return { ws, bootstrap }
}

export default function App() {
  const connect = useConnectionStore((s) => s.connect)
  const setBootstrapUrl = useConnectionStore((s) => s.setBootstrapUrl)

  useEffect(() => {
    const { ws, bootstrap } = readUrlConfig()
    if (ws && bootstrap) {
      setBootstrapUrl(bootstrap)
      connect(ws, { bootstrap })
    }
  }, [connect, setBootstrapUrl])

  return (
    <div className="min-h-screen bg-zinc-950 font-sans text-zinc-100">
      <ConnectionBar />
      <main className="mx-auto grid max-w-6xl grid-cols-1 gap-4 p-4 md:grid-cols-2">
        <ChatPanel />
        <TimelinePanel />
      </main>
    </div>
  )
}
