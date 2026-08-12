import { useEffect, useMemo, useRef, useState } from "react"
import { Terminal, Trash2 } from "lucide-react"
import { useJarvis } from "@/store/jarvis"
import { PanelShell, Label, EmptyState } from "@/components/ui/primitives"
import { fmtTime } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { LogLevel } from "@/lib/ipc/protocol"

const LEVELS: (LogLevel | "all")[] = ["all", "trace", "debug", "info", "warn", "error"]

const LEVEL_COLOR: Record<LogLevel, string> = {
  trace: "text-muted-foreground/60",
  debug: "text-muted-foreground",
  info: "text-info",
  warn: "text-warn",
  error: "text-error",
}

export function LogsPanel() {
  const logs = useJarvis((s) => s.logs)
  const filter = useJarvis((s) => s.logFilter)
  const setFilter = useJarvis((s) => s.setLogFilter)
  const clearLogs = useJarvis((s) => s.clearLogs)
  const [query, setQuery] = useState("")
  const [follow, setFollow] = useState(true)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  const filtered = useMemo(() => {
    const q = query.toLowerCase()
    return logs.filter((l) => {
      if (filter !== "all" && l.level !== filter) return false
      if (q && !(`${l.source} ${l.message}`.toLowerCase().includes(q))) return false
      return true
    })
  }, [logs, filter, query])

  useEffect(() => {
    if (!follow) return
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [filtered, follow])

  return (
    <PanelShell
      toolbar={
        <>
          <Terminal className="h-3.5 w-3.5 text-accent" />
          <Label>logs</Label>
          <div className="flex items-center gap-0.5">
            {LEVELS.map((lv) => (
              <button
                key={lv}
                onClick={() => setFilter(lv)}
                className={cn(
                  "rounded-sm px-1.5 py-0.5 text-2xs uppercase tracking-wider transition-colors",
                  filter === lv ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {lv}
              </button>
            ))}
          </div>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="filter…"
            className="ml-auto h-6 w-28 rounded-sm border border-border bg-input px-1.5 text-2xs text-foreground outline-none focus:border-accent-muted"
          />
          <button
            onClick={() => setFollow((v) => !v)}
            className={cn("text-2xs uppercase tracking-wider", follow ? "text-accent" : "text-muted-foreground")}
          >
            tail
          </button>
          <button onClick={clearLogs} title="Clear logs" className="text-muted-foreground hover:text-error">
            <Trash2 className="h-3 w-3" />
          </button>
        </>
      }
    >
      {filtered.length === 0 ? (
        <EmptyState>No log lines match the current filter.</EmptyState>
      ) : (
        <div ref={scrollRef} onWheel={() => setFollow(false)} className="scroll-thin h-full overflow-y-auto px-2 py-1">
          {filtered.map((l) => (
            <div key={l.id} className="flex gap-2 px-1 py-0.5 font-mono text-2xs leading-relaxed hover:bg-elevated/50">
              <span className="shrink-0 text-muted-foreground/50">{fmtTime(l.ts)}</span>
              <span className={cn("w-10 shrink-0 uppercase", LEVEL_COLOR[l.level])}>{l.level}</span>
              <span className="w-24 shrink-0 truncate text-muted-foreground">{l.source}</span>
              <span className="min-w-0 flex-1 whitespace-pre-wrap break-words text-foreground/90">{l.message}</span>
            </div>
          ))}
        </div>
      )}
    </PanelShell>
  )
}
