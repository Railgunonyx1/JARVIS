import { create } from 'zustand'
import {
  PERMISSION_OBSERVED,
  RUN_QUEUED,
  STEP_COMPLETED,
  STEP_FAILED,
  STEP_STARTED,
  TASK_CANCELLED,
  TASK_STARTED,
} from '../daemon/events'
import type { RunResult, TaskPhase, TimelineStep } from '../daemon/types'

interface TaskStore {
  phase: TaskPhase
  goal: string
  runId: string
  steps: TimelineStep[]
  errors: string[]
  result?: RunResult
  startRun: (runId: string, goal: string) => void
  handleEvent: (name: string, payload: Record<string, unknown>) => void
  finishRun: (result: RunResult) => void
  failRun: (error: Error) => void
  cancelRun: () => void
  reset: () => void
}

export const useTaskStore = create<TaskStore>((set) => ({
  phase: 'idle',
  goal: '',
  runId: '',
  steps: [],
  errors: [],
  result: undefined,

  startRun: (runId, goal) =>
    set({ phase: 'queued', runId, goal, steps: [], errors: [], result: undefined }),

  handleEvent: (name, payload) => {
    if (name === RUN_QUEUED || name === TASK_STARTED) {
      const goal = payload.goal ? String(payload.goal) : undefined
      set((s) => ({
        phase: 'running',
        ...(goal ? { goal } : {}),
        ...(name === TASK_STARTED && payload.run_id
          ? { runId: String(payload.run_id) }
          : {}),
      }))
      return
    }
    if (name === STEP_STARTED) {
      const index = Number(payload.step ?? s.steps.length)
      set((s) => ({
        steps: [
          ...s.steps,
          {
            index,
            tool: String(payload.tool ?? 'tool'),
            status: 'running',
            duration_ms: undefined,
          },
        ],
      }))
      return
    }
    if (name === STEP_COMPLETED) {
      const index = Number(payload.step)
      set((s) => ({
        steps: s.steps.map((step) =>
          step.index === index
            ? {
                ...step,
                status:
                  payload.status === 'error'
                    ? 'error'
                    : payload.status === 'denied'
                      ? 'denied'
                      : 'ok',
                duration_ms: Number(payload.duration_ms ?? step.duration_ms ?? 0),
                error: payload.error ? String(payload.error) : undefined,
              }
            : step,
        ),
        ...(payload.status === 'error' && payload.error
          ? { errors: [...s.errors, String(payload.error)] }
          : {}),
      }))
      return
    }
    if (name === STEP_FAILED) {
      const message = payload.error ? String(payload.error) : 'step failed'
      set((s) => ({
        steps: s.steps.map((step, i) =>
          i === s.steps.length - 1 && step.status === 'running'
            ? { ...step, status: 'error' as const, error: message }
            : step,
        ),
        errors: [...s.errors, message],
      }))
      return
    }
    if (name === PERMISSION_OBSERVED && payload.allowed === false) {
      const tool = String(payload.tool ?? '')
      set((s) => ({
        steps: s.steps.map((step) =>
          step.tool === tool && step.status === 'running'
            ? { ...step, status: 'denied' as const }
            : step,
        ),
      }))
    }
    if (name === TASK_CANCELLED) {
      set({ phase: 'cancelled' })
    }
  },

  finishRun: (result) =>
    set({
      phase: result.success ? 'done' : 'failed',
      result,
      ...(result.error ? { errors: [result.error] } : {}),
    }),

  failRun: (error) =>
    set((s) => ({ phase: 'failed', errors: [...s.errors, error.message] })),

  cancelRun: () => set({ phase: 'cancelled' }),

  reset: () => set({ phase: 'idle', goal: '', steps: [], errors: [], result: undefined }),
}))
