import { create } from 'zustand'
import { daemon } from '../daemon'

interface StepStatus {
  index: number
  title: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  startedAt: number | null
  completedAt: number | null
  durationMs: number | null
}

interface ToolCard {
  id: string
  title: string
  command: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  startedAt: number | null
  durationMs: number | null
  output?: string
}

interface AgentPlan {
  goal: string
  phase: 'idle' | 'queued' | 'running' | 'done' | 'cancelled' | 'failed'
  runId: string | null
  steps: StepStatus[]
  tools: ToolCard[]
  output: string
  errors: string[]
  isRunning: boolean
  completedAt: number | null
}

interface AgentState {
  plan: AgentPlan
  connect: (url: string) => void | (() => void)
  submit: (goal: string) => void
  cancel: () => void
  setStepStatus: (index: number, status: StepStatus['status'], startedAt?: number) => void
  addTool: (tool: Omit<ToolCard, 'id'>) => void
  updateTool: (id: string, updates: Partial<ToolCard>) => void
  setOutput: (output: string) => void
  addError: (error: string) => void
  clearErrors: () => void
}

export const useAgentStore = create<AgentState>((set) => ({
  plan: {
    goal: '',
    phase: 'idle',
    runId: null,
    steps: [],
    tools: [],
    output: '',
    errors: [],
    isRunning: false,
    completedAt: null,
    // Limited to last 200 live entries; older entries from history on demand
    liveActivityLimit: 200,
  },

  connect: (url: string) => {
    daemon.connect(url)
    // Listen for agent events and return cleanup function
    daemon.on('run.queued', (payload: any) => {
      set((s) => ({
        plan: {
          ...s.plan,
          phase: 'queued',
          runId: payload.run_id,
        },
      }))
    })

    daemon.on('task.started', (payload: any) => {
      set((s) => ({
        plan: {
          ...s.plan,
          phase: 'running',
        },
      }))
    })

    daemon.on('step.started', (payload: any) => {
      set((s) => ({
        plan: {
          ...s.plan,
          steps: s.plan.steps.map((step, i) =>
            i === payload.step_index ? { ...step, status: 'running', startedAt: Date.now() } : step
          ),
        },
      }))
    })

    daemon.on('step.completed', (payload: any) => {
      const duration = Date.now() - (payload.started_at || Date.now())
      set((s) => ({
        plan: {
          ...s.plan,
          steps: s.plan.steps.map((step, i) =>
            i === payload.step_index
              ? { ...step, status: 'completed', completedAt: Date.now(), durationMs: duration }
              : step
          ),
          output: s.plan.output + (s.plan.output ? '\n' : '') + payload.output,
        },
      }))
    })

    daemon.on('step.failed', (payload: any) => {
      set((s) => ({
        plan: {
          ...s.plan,
          steps: s.plan.steps.map((step, i) =>
            i === payload.step_index ? { ...step, status: 'failed' } : step
          ),
          errors: [...s.plan.errors, payload.error],
        },
      }))
    })

    daemon.on('task.finished', (payload: any) => {
      set((s) => ({
        plan: {
          ...s.plan,
          phase: 'done',
          isRunning: false,
          completedAt: Date.now(),
        },
      }))
    })

    daemon.on('task.cancelled', () => {
      set((s) => ({
        plan: {
          ...s.plan,
          phase: 'cancelled',
          isRunning: false,
        },
      }))
    })

    // Return cleanup function
    return () => {
      // Note: daemon.on doesn't have off in this simplified version
      // In production, would track subscriptions and clean up
    }
  },

  submit: (goal: string) => {
    daemon.request('run', { goal }).then(() => {
      set((s) => ({
        plan: {
          ...s.plan,
          goal,
          phase: 'queued',
        },
      }))
    })
  },

  cancel: () => {
    daemon.cancel().then(() => {
      set((s) => ({
        plan: {
          ...s.plan,
          phase: 'cancelled',
        },
      }))
    })
  },

  setStepStatus: (index: number, status: StepStatus['status'], startedAt?: number) =>
    set((s) => ({
      plan: {
        ...s.plan,
        steps: s.plan.steps.map((step, i) =>
          i === index ? { ...step, status, startedAt } : step
        ),
      },
    })),

  addTool: (tool: Omit<ToolCard, 'id'>) =>
    set((s) => ({
      plan: {
        ...s.plan,
        tools: [...s.plan.tools, { id: Date.now().toString(), ...tool }],
      },
    })),

  updateTool: (id: string, updates: Partial<ToolCard>) =>
    set((s) => ({
      plan: {
        ...s.plan,
        tools: s.plan.tools.map((t) => (t.id === id ? { ...t, ...updates } : t)),
      },
    })),

  setOutput: (output: string) =>
    set((s) => ({
      plan: {
        ...s.plan,
        output,
      },
    })),

  addError: (error: string) =>
    set((s) => ({
      plan: {
        ...s.plan,
        errors: [...s.plan.errors, error],
      },
    })),

  clearErrors: () =>
    set((s) => ({
      plan: {
        ...s.plan,
        errors: [],
      },
    })),
}))