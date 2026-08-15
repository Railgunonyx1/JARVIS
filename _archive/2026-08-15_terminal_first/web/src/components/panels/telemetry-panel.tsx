import { Activity } from "lucide-react"
import { useJarvis } from "@/store/jarvis"
import { PanelShell, Label, EmptyState } from "@/components/ui/primitives"
import { Sparkline } from "@/components/ui/sparkline"
import { palette } from "@/lib/colors"
import { fmtNum } from "@/lib/format"
import { cn } from "@/lib/utils"

type Metric = {
  key: string
  label: string
  unit: string
  color: string
  max?: number
  pick: (s: { cpu: number; mem: number; gpu: number; netIn: number; netOut: number; tokensPerSec: number; latencyMs: number }) => number
  digits?: number
}

const METRICS: Metric[] = [
  { key: "cpu", label: "CPU", unit: "%", color: palette.accent, max: 100, pick: (s) => s.cpu },
  { key: "mem", label: "Memory", unit: "%", color: palette.info, max: 100, pick: (s) => s.mem },
  { key: "gpu", label: "GPU", unit: "%", color: palette.online, max: 100, pick: (s) => s.gpu },
  { key: "tok", label: "Tokens/s", unit: "t/s", color: palette.warn, pick: (s) => s.tokensPerSec, digits: 0 },
  { key: "lat", label: "Latency", unit: "ms", color: palette.error, pick: (s) => s.latencyMs, digits: 0 },
  { key: "net", label: "Net In", unit: "KB/s", color: palette.info, pick: (s) => s.netIn, digits: 0 },
]

export function TelemetryPanel() {
  const history = useJarvis((s) => s.telemetryHistory)
  const current = useJarvis((s) => s.telemetry)

  return (
    <PanelShell
      toolbar={
        <>
          <Activity className="h-3.5 w-3.5 text-accent" />
          <Label>system telemetry</Label>
          {current ? (
            <span className="ml-auto font-mono text-2xs text-muted-foreground">
              {current.activeRuns} active · {fmtNum(current.tokensPerSec)} t/s
            </span>
          ) : null}
        </>
      }
    >
      {!current ? (
        <EmptyState>Waiting for telemetry stream…</EmptyState>
      ) : (
        <div className="scroll-thin h-full overflow-y-auto p-2.5">
          <div className="grid grid-cols-2 gap-2">
            {METRICS.map((m) => {
              const series = history.map((h) => m.pick(h))
              const value = m.pick(current)
              return (
                <div key={m.key} className="rounded-md border border-border bg-elevated/40 p-2.5">
                  <div className="flex items-baseline justify-between">
                    <Label>{m.label}</Label>
                    <span className="font-mono text-sm tabular text-foreground" style={{ color: m.color }}>
                      {fmtNum(value, m.digits ?? 0)}
                      <span className="ml-0.5 text-2xs text-muted-foreground">{m.unit}</span>
                    </span>
                  </div>
                  <Sparkline data={series} color={m.color} max={m.max} height={38} className="mt-1.5" />
                </div>
              )
            })}
          </div>

          <div className="mt-2 rounded-md border border-border bg-elevated/40 p-2.5">
            <div className="mb-2 flex items-center justify-between">
              <Label>resource load</Label>
              <span className="text-2xs text-muted-foreground">live</span>
            </div>
            <div className="flex flex-col gap-2">
              <Bar label="CPU" value={current.cpu} color={palette.accent} />
              <Bar label="MEM" value={current.mem} color={palette.info} />
              <Bar label="GPU" value={current.gpu} color={palette.online} />
            </div>
          </div>
        </div>
      )}
    </PanelShell>
  )
}

function Bar({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.max(0, Math.min(100, value))
  return (
    <div className="flex items-center gap-2">
      <span className="w-8 shrink-0 font-mono text-2xs text-muted-foreground">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-background">
        <div
          className={cn("h-full rounded-full transition-[width] duration-300")}
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="w-9 shrink-0 text-right font-mono text-2xs tabular text-foreground">{pct.toFixed(0)}%</span>
    </div>
  )
}
