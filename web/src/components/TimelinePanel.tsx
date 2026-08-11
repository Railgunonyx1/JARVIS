import { useTaskStore } from '../store/task'
import type { TimelineStep } from '../daemon/types'

const STEP_DOT: Record<TimelineStep['status'], string> = {
  running: 'bg-amber-400 animate-pulse',
  ok: 'bg-emerald-400',
  error: 'bg-red-500',
  denied: 'bg-orange-400',
}

function formatDuration(ms?: number): string {
  if (ms === undefined) return ''
  if (ms < 1000) return `${ms.toFixed(0)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function TimelinePanel() {
  const phase = useTaskStore((s) => s.phase)
  const goal = useTaskStore((s) => s.goal)
  const steps = useTaskStore((s) => s.steps)
  const errors = useTaskStore((s) => s.errors)
  const result = useTaskStore((s) => s.result)

  return (
    <div className="flex h-[calc(100vh-5rem)] flex-col rounded-lg border border-zinc-800 bg-zinc-900/40">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
          Timeline
        </h2>
        <span className="text-xs text-zinc-500">{phase}</span>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {goal && (
          <div className="rounded-lg bg-zinc-800 px-3 py-2 text-xs text-zinc-300">
            <span className="text-zinc-500">goal · </span>
            {goal}
          </div>
        )}

        {steps.length === 0 && !goal && (
          <p className="text-center text-xs text-zinc-600">No activity yet.</p>
        )}

        <ol className="relative space-y-2">
          {steps.map((step, i) => (
            <li key={i} className="flex items-start gap-2 text-xs">
              <span
                className={`mt-1 inline-block h-2 w-2 shrink-0 rounded-full ${STEP_DOT[step.status]}`}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate font-mono text-zinc-200">{step.tool}</span>
                  <span className="shrink-0 text-zinc-500">{formatDuration(step.duration_ms)}</span>
                </div>
                {step.error && <p className="text-red-400">{step.error}</p>}
              </div>
            </li>
          ))}
        </ol>

        {errors.length > 0 && (
          <div className="rounded-lg border border-red-900/50 bg-red-900/10 p-3">
            <p className="mb-1 text-xs font-semibold text-red-300">Errors</p>
            <ul className="list-inside list-disc space-y-1 text-xs text-red-200/80">
              {errors.map((error, i) => (
                <li key={i}>{error}</li>
              ))}
            </ul>
          </div>
        )}

        {result && (
          <div
            className={`rounded-lg border px-3 py-2 text-xs ${
              result.success
                ? 'border-emerald-900/50 bg-emerald-900/10 text-emerald-200'
                : 'border-red-900/50 bg-red-900/10 text-red-200'
            }`}
          >
            {result.success ? 'Completed' : 'Failed'} · trace {result.trace_id ?? '—'}
            {result.cancelled && ' · cancelled'}
          </div>
        )}
      </div>
    </div>
  )
}
