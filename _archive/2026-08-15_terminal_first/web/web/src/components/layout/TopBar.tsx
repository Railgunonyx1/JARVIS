import { useUiStore } from '../../store/ui'
import { Tab } from '../../store/ui'
import { cx } from '../../lib/cx'
import { PanelCard } from '../ui/PanelCard'
import { SectionTitle } from '../ui/SectionTitle'
import { Collapsible } from '../ui/Collapsible'
import { Sparkline } from '../ui/Sparkline'

interface TopBarProps {
  className?: string
}

export function TopBar({ className }: TopBarProps = {}) {
  const { activeTab, setTab } = useUiStore()

  return (
    <header
      className={cx(
        'flex h-[68px] items-center justify-between px-4 border-b border-line bg-panel/95 backdrop-filter blur-sm',
        className,
      )}
    >
      {/* Left: Brand + Mode */}
      <div className="flex items-center gap-3">
        <button
          aria-label="Open menu"
          className="p-2 rounded-lg hover:bg-panel3 transition-colors"
        >
          <svg
            width="28"
            height="28"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="3" y1="3" x2="21" y2="21" />
            <line x1="21" y1="3" x2="3" y2="21" />
          </svg>
        </button>
        <span className="text-[20px] font-semibold truncate">JARVIS MK-X</span>
        <span className="text-sm text-muted">Web/Desktop Integration</span>
      </div>

      {/* Center: Nav tabs */}
      <div className="hidden md:flex items-center gap-2 overflow-x-auto">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cx(
              'px-4 py-2 text-sm text-label [&_span]:text-soft [&_span]:font-medium',
              'rounded-lg transition-colors hover:bg-panel2',
              activeTab === id ? 'bg-panel3 text-cyan' : 'text-muted',
              'data-[state=active]:bg-cyan/10 [&_span]:font-medium',
            )}
          >
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* Right: Mode selector + Clock */}
      <div className="flex items-center gap-4">
        {/* Mode selector */}
        <div className="relative">
          <select
            onChange={(e) => setTab(e.target.value as Tab)}
            className="pl-2 pr-8 text-[10px] py-1 rounded-md bg-panel3 border border-line focus:outline-none focus:ring-2 focus:ring-cyan/30"
          >
            <option value="agent">SMART</option>
            <option value="tools">AGENT</option>
            <option value="memory">CONTROLLED</option>
            <option value="repo">PLAN</option>
          </select>
          <svg
            width="8"
            height="4"
            viewBox="0 0 8 4"
            fill="none"
            className="absolute right-2 top-1/2 -translate-y-1 text-muted"
          >
            <path d="M2 0L4 4L6 0" fill="none" stroke="current" stroke-width="1.5"/>
          </svg>
        </div>

        {/* Clock */}
        <span
          id="topbar-clock"
          className="text-[10px] text-muted"
        >00:00</span>

        {/* Notifications/Toasts indicator */}
        <button
          aria-label="Notifications"
          className="relative p-2 rounded-lg hover:bg-panel3 transition-colors"
        >
          <span className="absolute -top-1 -right-1 rounded-full bg-red-500 text-xs text-white p-0.5">!</span>
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4l2 2" />
          </svg>
        </button>
      </div>
    </header>
  )
}