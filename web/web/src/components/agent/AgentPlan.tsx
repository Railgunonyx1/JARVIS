import { cx } from '../../lib/cx'
import { PanelCard } from '../ui/PanelCard'
import { useUiStore } from '../../store/ui'

interface PlanRowProps {
  stepIndex: number
  title: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  onComplete?: () => void
  onFail?: () => void
}

export function PlanRow({ stepIndex, title, status, onComplete, onFail }: PlanRowProps) {
  const classes = cx(
    'flex items-center gap-2 px-2 py-1 rounded-md text-[10px] tracking-[.05em] transition-colors',
    'border-b border-line last:border-0',
    status === 'pending' ? 'text-soft bg-transparent' : '',
    status === 'running' ? 'bg-cyan/10 text-cyan' : '',
    status === 'completed' ? 'bg-green/10 text-green' : '',
    status === 'failed' ? 'bg-red/10 text-red' : '',
  )

  const statusClasses = cx(
    'w-1.5 h-1.5 rounded-full',
    status === 'pending' ? 'bg-soft' : status === 'running' ? 'bg-cyan' : status === 'completed' ? 'bg-green' : 'bg-red',
  )

  return (
    <div className={classes}>
      <div className={statusClasses} />
      <span className="min-w-0 flex-1 truncate">{title}</span>
      {status === 'running' && <span className="text-[10px] text-cyan/80">▶</span>}
      {status === 'completed' && <span className="text-[10px] text-green/60">✓</span>}
      {status === 'failed' && <span className="text-[10px] text-red/60">✗</span>}
    </div>
  )
}

interface AgentPlanProps {
  plan: Array<{ index: number; title: string; status?: 'pending' | 'running' | 'completed' | 'failed' }>
}

export function AgentPlan({ plan }: AgentPlanProps) {
  return (
    <PanelCard title="AGENT PLAN">
      {plan.map((step, i) => (
        <PlanRow
          key={i}
          stepIndex={step.index}
          title={step.title}
          status={step.status ?? 'pending'}
        />
      ))}
    </PanelCard>
  )
}