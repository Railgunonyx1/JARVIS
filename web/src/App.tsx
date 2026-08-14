import { useEffect, useState } from "react"
import { initJarvis, useJarvis } from "@/store/jarvis"
import { workspaceApi } from "@/lib/workspace-api"
import { Workspace } from "@/components/workspace"
import { client } from "@/lib/ipc/client"
import { cn } from "@/lib/utils"

/** Preserve the URL-config connect contract (ws / bootstrap / ws_port). */
function applyUrlConfig(): string {
  const params = new URLSearchParams(window.location.search)
  const ws = params.get("ws")
  const wsPort = params.get("ws_port")
  const url = ws ?? (wsPort ? `ws://127.0.0.1:${wsPort}/ws` : undefined)
  if (url) {
    ;(window as { __JARVIS_WS__?: string }).__JARVIS_WS__ = url
  }
  return url ?? ""
}

const MODES = ["SMART", "AGENT", "CONTROLLED", "PLAN"] as const
type Mode = (typeof MODES)[number]

export function App() {
  useEffect(() => {
    applyUrlConfig()
    initJarvis()
  }, [])

  const connection = useJarvis((s) => s.connection)
  const telemetry = useJarvis((s) => s.telemetry)
  const [mode, setMode] = useState<Mode>("SMART")

  const connLabel =
    connection.state === "sim"
      ? "SIMULATOR"
      : connection.state === "online"
        ? "DAEMON ONLINE"
        : connection.state === "offline"
          ? "OFFLINE"
          : connection.state.toUpperCase()

  return (
    <div className="app-frame" data-mode={mode.toLowerCase()}>
      <header className="app-topbar">
        <div className="app-brand">
          <div className="app-logo">J</div>
          <div className="app-brand-meta">
            <span>JARVIS MK-X</span>
            <small>COMMAND CENTER · v0.4.1-final</small>
          </div>
        </div>

        <div className="app-topmeta">
          <span className="app-pill">
            <span className={cn("mode-dot", (connection.state === "online" || connection.state === "sim") ? "" : "opacity-50")} />
            {connLabel}
          </span>
          <span className="app-pill" title="Tokens per second">
            {telemetry ? `${Math.round(telemetry.tokensPerSec)} t/s` : "TOKENS 0 · 0%"}
          </span>
          <select
            className="mode-select"
            value={mode}
            onChange={(e) => {
              const next = e.target.value as Mode
              setMode(next)
              client.send({ type: "mode.set", payload: { mode: next.toLowerCase() as "smart" | "agent" | "controlled" | "plan" } })
            }}
            title="Agent mode"
          >
            {MODES.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
          <button
            className="iconbtn"
            title="Command palette (⌘K)"
            onClick={() => workspaceApi.focus("chat")}
          >
            ⌘
          </button>
          <button className="iconbtn" title="Settings" onClick={() => workspaceApi.focus("settings")}>
            ⚙
          </button>
        </div>
      </header>

      <div className="app-workspace">
        <Workspace />
      </div>
    </div>
  )
}
