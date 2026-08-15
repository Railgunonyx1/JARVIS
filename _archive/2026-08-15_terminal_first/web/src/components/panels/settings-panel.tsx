import { useState } from "react"
import { Cpu, Plug, Settings2, Zap } from "lucide-react"
import { useJarvis } from "@/store/jarvis"
import { PanelShell, Label, StatusDot, Chip } from "@/components/ui/primitives"
import { fmtNum, fmtUsd } from "@/lib/format"
import { cn } from "@/lib/utils"

export function SettingsPanel() {
  const providers = useJarvis((s) => s.providers)
  const activeProvider = useJarvis((s) => s.activeProvider)
  const activeModel = useJarvis((s) => s.activeModel)
  const selectModel = useJarvis((s) => s.selectModel)
  const connection = useJarvis((s) => s.connection)
  const daemon = useJarvis((s) => s.daemon)
  const reconnect = useJarvis((s) => s.reconnect)
  const toggleSim = useJarvis((s) => s.toggleSim)

  const [url, setUrl] = useState(connection.url)

  return (
    <PanelShell
      toolbar={
        <>
          <Settings2 className="h-3.5 w-3.5 text-accent" />
          <Label>settings</Label>
        </>
      }
    >
      <div className="scroll-thin h-full overflow-y-auto p-3">
        <section className="mb-4">
          <div className="mb-2 flex items-center gap-1.5">
            <Plug className="h-3.5 w-3.5 text-muted-foreground" />
            <Label>daemon connection</Label>
          </div>
          <div className="rounded-md border border-border bg-elevated/40 p-2.5">
            <div className="flex items-center gap-2">
              <StatusDot status={connection.state === "online" ? "online" : connection.state === "sim" ? "sim" : "warn"} pulse={connection.state === "connecting" || connection.state === "reconnecting"} />
              <span className="text-xs text-foreground">{connection.state}</span>
              {connection.usingSim ? <Chip tone="info">simulator</Chip> : null}
              {daemon ? <span className="ml-auto text-2xs text-muted-foreground">{daemon.name} v{daemon.version}</span> : null}
            </div>
            <div className="mt-2 flex items-center gap-1.5">
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                spellCheck={false}
                className="h-7 flex-1 rounded-sm border border-border bg-input px-2 font-mono text-2xs text-foreground outline-none focus:border-accent-muted"
              />
              <button
                onClick={() => reconnect(url)}
                className="h-7 rounded-sm bg-accent px-2.5 text-2xs uppercase tracking-wider text-accent-foreground"
              >
                connect
              </button>
            </div>
            <div className="mt-2 flex items-center justify-between">
              <span className="text-2xs text-muted-foreground">
                {connection.usingSim
                  ? "Running the in-browser simulator (no daemon reachable)."
                  : "Point this at your JARVIS daemon WebSocket endpoint."}
              </span>
              <button onClick={toggleSim} className="text-2xs uppercase tracking-wider text-accent hover:underline">
                {connection.usingSim ? "use real" : "use sim"}
              </button>
            </div>
          </div>
        </section>

        <section>
          <div className="mb-2 flex items-center gap-1.5">
            <Cpu className="h-3.5 w-3.5 text-muted-foreground" />
            <Label>providers &amp; models</Label>
          </div>
          <div className="flex flex-col gap-2">
            {providers.length === 0 ? (
              <p className="text-2xs text-muted-foreground">No providers reported by the daemon.</p>
            ) : (
              providers.map((p) => (
                <div key={p.id} className="rounded-md border border-border bg-elevated/40 p-2.5">
                  <div className="mb-1.5 flex items-center gap-2">
                    <StatusDot status={p.status} pulse={p.status === "online" && p.id === activeProvider} />
                    <span className="text-xs font-medium text-foreground">{p.label}</span>
                    <Chip
                      tone={p.status === "online" ? "online" : p.status === "degraded" ? "warn" : "error"}
                      className="ml-auto"
                    >
                      {p.status}
                    </Chip>
                  </div>
                  <div className="flex flex-col gap-1">
                    {p.models.map((m) => {
                      const active = p.id === activeProvider && m.id === activeModel
                      return (
                        <button
                          key={m.id}
                          onClick={() => selectModel(p.id, m.id)}
                          disabled={p.status === "offline"}
                          className={cn(
                            "flex items-center gap-2 rounded-sm border px-2 py-1.5 text-left transition-colors disabled:opacity-40",
                            active
                              ? "border-accent-muted bg-accent/10"
                              : "border-transparent hover:border-border hover:bg-background/50",
                          )}
                        >
                          {active ? <Zap className="h-3 w-3 shrink-0 text-accent" /> : <span className="w-3 shrink-0" />}
                          <span className={cn("truncate font-mono text-2xs", active ? "text-accent" : "text-foreground")}>
                            {m.label}
                          </span>
                          <span className="ml-auto shrink-0 font-mono text-2xs tabular text-muted-foreground/60">
                            {fmtNum(m.context / 1000)}k · {fmtUsd(m.input)}/{fmtUsd(m.output)}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </PanelShell>
  )
}
