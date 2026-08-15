import { useMemo, useState } from "react"
import { ListChecks, Plus, X } from "lucide-react"
import { useJarvis } from "@/store/jarvis"
import { PanelShell, Label, StatusDot, EmptyState } from "@/components/ui/primitives"
import { fmtAgo } from "@/lib/format"
import type { Task, TaskStatus } from "@/lib/ipc/protocol"

const COLUMNS: { status: TaskStatus; label: string }[] = [
  { status: "queued", label: "queued" },
  { status: "running", label: "running" },
  { status: "blocked", label: "blocked" },
  { status: "done", label: "done" },
  { status: "failed", label: "failed" },
]

export function TasksPanel() {
  const tasksMap = useJarvis((s) => s.tasks)
  const createTask = useJarvis((s) => s.createTask)
  const cancelTask = useJarvis((s) => s.cancelTask)
  const [draft, setDraft] = useState("")

  const tasks = useMemo(() => Object.values(tasksMap).sort((a, b) => b.updatedAt - a.updatedAt), [tasksMap])
  const byStatus = (st: TaskStatus) => tasks.filter((t) => t.status === st)

  function add() {
    if (!draft.trim()) return
    createTask(draft)
    setDraft("")
  }

  return (
    <PanelShell
      toolbar={
        <>
          <ListChecks className="h-3.5 w-3.5 text-accent" />
          <Label>tasks</Label>
          <span className="text-2xs text-muted-foreground">{tasks.length} total</span>
          <div className="ml-auto flex items-center gap-1.5">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.nativeEvent.isComposing) add()
              }}
              placeholder="new task…"
              className="h-6 w-36 rounded-sm border border-border bg-input px-1.5 text-2xs text-foreground outline-none focus:border-accent-muted"
            />
            <button onClick={add} className="text-muted-foreground hover:text-accent" title="Add task">
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>
        </>
      }
    >
      {tasks.length === 0 ? (
        <EmptyState>No tasks yet. Queue one above or let the agent spawn tasks as it works.</EmptyState>
      ) : (
        <div className="scroll-thin h-full overflow-y-auto p-2">
          <div className="flex flex-col gap-2.5">
            {COLUMNS.map((col) => {
              const items = byStatus(col.status)
              if (items.length === 0) return null
              return (
                <div key={col.status}>
                  <div className="mb-1 flex items-center gap-1.5 px-1">
                    <StatusDot status={col.status} pulse={col.status === "running"} />
                    <Label>{col.label}</Label>
                    <span className="text-2xs text-muted-foreground/60">{items.length}</span>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    {items.map((t) => (
                      <TaskCard key={t.id} t={t} onCancel={() => cancelTask(t.id)} />
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </PanelShell>
  )
}

function TaskCard({ t, onCancel }: { t: Task; onCancel: () => void }) {
  const active = t.status === "running" || t.status === "queued"
  return (
    <div className="group rounded-md border border-border bg-elevated/40 px-2.5 py-2">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs text-foreground">{t.title}</p>
          {t.detail ? <p className="mt-0.5 truncate text-2xs text-muted-foreground">{t.detail}</p> : null}
        </div>
        <span className="shrink-0 font-mono text-2xs text-muted-foreground/50">{fmtAgo(t.updatedAt)}</span>
        {active ? (
          <button
            onClick={onCancel}
            className="shrink-0 text-muted-foreground opacity-0 transition-opacity hover:text-error group-hover:opacity-100"
            title="Cancel task"
          >
            <X className="h-3 w-3" />
          </button>
        ) : null}
      </div>
      {t.status === "running" ? (
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-background">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-300"
            style={{ width: `${Math.round(t.progress * 100)}%` }}
          />
        </div>
      ) : null}
    </div>
  )
}
