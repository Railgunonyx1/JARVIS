import { useEffect, useMemo, useRef, useState } from "react"
import { Brain, ChevronRight, ListTree, Wrench, Zap } from "lucide-react"
import { useJarvis } from "@/store/jarvis"
import { PanelShell, Label, StatusDot, Chip, EmptyState } from "@/components/ui/primitives"
import { fmtTime, fmtDuration } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { AgentEvent, AgentPhase, ToolEvent } from "@/lib/ipc/protocol"

type Row =
  | { kind: "agent"; ts: number; data: AgentEvent }
  | { kind: "tool"; ts: number; data: ToolEvent }

const PHASE_COLOR: Record<AgentPhase, string> = {
  start: "text-info",
  think: "text-accent",
  plan: "text-accent",
  act: "text-warn",
  observe: "text-info",
  done: "text-online",
  error: "text-error",
}

export function TimelinePanel() {
  const agentEvents = useJarvis((s) => s.agentEvents)
  const toolEvents = useJarvis((s) => s.toolEvents)
  const [autoscroll, setAutoscroll] = useState(true)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  const runs = useMemo(() => {
    const map = new Map<string, Row[]>()
    for (const e of agentEvents) {
      if (!map.has(e.runId)) map.set(e.runId, [])
      map.get(e.runId)!.push({ kind: "agent", ts: e.ts, data: e })
    }
    for (const t of toolEvents) {
      if (!map.has(t.runId)) map.set(t.runId, [])
      map.get(t.runId)!.push({ kind: "tool", ts: t.ts, data: t })
    }
    const arr = [...map.entries()].map(([runId, rows]) => ({
      runId,
      rows: rows.sort((a, b) => a.ts - b.ts),
    }))
    arr.sort((a, b) => (a.rows[0]?.ts ?? 0) - (b.rows[0]?.ts ?? 0))
    return arr
  }, [agentEvents, toolEvents])

  useEffect(() => {
    if (!autoscroll) return
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [runs, autoscroll])

  return (
    <PanelShell
      toolbar={
        <>
          <ListTree className="h-3.5 w-3.5 text-accent" />
          <Label>agent timeline</Label>
          <span className="text-2xs text-muted-foreground">{runs.length} runs</span>
          <button
            onClick={() => setAutoscroll((v) => !v)}
            className={cn(
              "ml-auto text-2xs uppercase tracking-wider transition-colors",
              autoscroll ? "text-accent" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {autoscroll ? "following" : "paused"}
          </button>
        </>
      }
    >
      {runs.length === 0 ? (
        <EmptyState>No agent activity yet. Send a message and reasoning phases, tool calls, and results appear here as they stream.</EmptyState>
      ) : (
        <div
          ref={scrollRef}
          onWheel={() => setAutoscroll(false)}
          className="scroll-thin h-full overflow-y-auto px-2 py-2"
        >
          <div className="flex flex-col gap-3">
            {runs.map((run) => (
              <RunGroup key={run.runId} runId={run.runId} rows={run.rows} />
            ))}
          </div>
        </div>
      )}
    </PanelShell>
  )
}

function RunGroup({ runId, rows }: { runId: string; rows: Row[] }) {
  const done = rows.some((r) => r.kind === "agent" && (r.data as AgentEvent).phase === "done")
  const failed = rows.some((r) => r.kind === "agent" && (r.data as AgentEvent).phase === "error")
  const toolCount = rows.filter((r) => r.kind === "tool").length
  const status = failed ? "error" : done ? "done" : "running"

  return (
    <div className="rounded-md border border-border bg-elevated/40">
      <div className="flex items-center gap-2 border-b border-border px-2.5 py-1.5">
        <StatusDot status={status} pulse={status === "running"} />
        <span className="font-mono text-2xs text-muted-foreground">run/{runId.slice(0, 8)}</span>
        <Chip tone="neutral" className="ml-auto">
          <Wrench className="h-2.5 w-2.5" /> {toolCount}
        </Chip>
        <Chip tone={status === "error" ? "error" : status === "done" ? "online" : "accent"}>{status}</Chip>
      </div>
      <div className="flex flex-col py-1">
        {rows.map((r, i) =>
          r.kind === "agent" ? (
            <AgentRow key={`a-${r.data.id}-${i}`} e={r.data} />
          ) : (
            <ToolRow key={`t-${r.data.id}-${i}`} t={r.data} />
          ),
        )}
      </div>
    </div>
  )
}

function AgentRow({ e }: { e: AgentEvent }) {
  return (
    <div className="flex items-start gap-2 px-2.5 py-1">
      <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center">
        {e.phase === "think" || e.phase === "plan" ? (
          <Brain className={cn("h-3 w-3", PHASE_COLOR[e.phase])} />
        ) : (
          <Zap className={cn("h-3 w-3", PHASE_COLOR[e.phase])} />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className={cn("text-2xs uppercase tracking-wider", PHASE_COLOR[e.phase])}>{e.phase}</span>
          <span className="truncate text-xs text-foreground">{e.label}</span>
          <span className="ml-auto shrink-0 font-mono text-2xs text-muted-foreground/50">{fmtTime(e.ts)}</span>
        </div>
        {e.detail ? <p className="text-pretty text-2xs leading-relaxed text-muted-foreground">{e.detail}</p> : null}
      </div>
    </div>
  )
}

function ToolRow({ t }: { t: ToolEvent }) {
  const [open, setOpen] = useState(false)
  const tone = t.status === "error" ? "error" : t.status === "ok" ? "online" : "accent"
  return (
    <div className="mx-2 my-0.5 rounded-sm border border-border/60 bg-background/40">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-2 py-1 text-left"
      >
        <ChevronRight className={cn("h-3 w-3 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} />
        <Wrench className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="truncate font-mono text-xs text-foreground">{t.tool}</span>
        <StatusDot status={t.status} pulse={t.status === "running" || t.status === "pending"} />
        {t.durationMs != null ? (
          <span className="shrink-0 font-mono text-2xs text-muted-foreground/60">{fmtDuration(t.durationMs)}</span>
        ) : null}
        <Chip tone={tone} className="ml-auto shrink-0">
          {t.status}
        </Chip>
      </button>
      {open ? (
        <div className="border-t border-border/60 px-2 py-1.5">
          {t.args ? (
            <div className="mb-1.5">
              <Label>args</Label>
              <pre className="scroll-thin mt-0.5 max-h-40 overflow-auto rounded-sm bg-background p-1.5 text-2xs leading-relaxed text-muted-foreground">
                {JSON.stringify(t.args, null, 2)}
              </pre>
            </div>
          ) : null}
          {t.error ? (
            <p className="text-2xs leading-relaxed text-error">{t.error}</p>
          ) : t.result !== undefined ? (
            <div>
              <Label>result</Label>
              <pre className="scroll-thin mt-0.5 max-h-40 overflow-auto rounded-sm bg-background p-1.5 text-2xs leading-relaxed text-muted-foreground">
                {typeof t.result === "string" ? t.result : JSON.stringify(t.result, null, 2)}
              </pre>
            </div>
          ) : (
            <span className="text-2xs text-muted-foreground/60">awaiting result…</span>
          )}
        </div>
      ) : null}
    </div>
  )
}
