import { useUiStore } from '../../store/ui'
import { cx } from '../../lib/cx'
import { PanelCard } from '../ui/PanelCard'
import { SectionTitle } from '../ui/SectionTitle'
import { Collapsible } from '../ui/Collapsible'

interface SidebarProps {
  className?: string
}

export function Sidebar({ className }: SidebarProps = {}) {
  const { activeTab, setTab } = useUiStore()
  const { skills, models, mcpServers } = useDaemon()

  return (
    <aside
      className={cx(
        'w-24 md:w-64 flex flex-col h-screen border-r border-line bg-panel/95',
        className,
      )}
    >
      <div className="flex h-16 items-center justify-between px-3">
        <button
          aria-label="Open sidebar"
          className="p-2 rounded-lg hover:bg-panel3 transition-colors"
          onClick={() => setTab(activeTab === 'agent' ? 'tools' : 'agent')}
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M3 4h18" />
            <path d="M3 12h18" />
            <path d="M3 20h18" />
          </svg>
        </button>
        <span className="text-[10px] font-semibold text-label">JARVIS</span>
      </div>

      <nav className="flex flex-col gap-2 overflow-y-auto h-[calc(100%-32px)] px-2">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cx(
              'flex items-center gap-2 px-2 py-2 rounded-md text-sm text-soft hover:text-cyan hover:bg-panel2 transition-colors',
              activeTab === id ? 'bg-panel3 text-cyan' : 'text-muted',
            )}
          >
<svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
              <path d="M3 4h18" />
              <path d="M3 12h18" />
              <path d="M3 20h18" />
          </svg>
          <span>{label}</span>
          </button>
        ))}
      </nav>

      {/* Bottom: System summary row */}
      <div className="mt-auto p-2 text-[10px] text-muted">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-cyan/40" />
          <span>RUNNING</span>
        </div>
        <div className="flex items-center gap-2 mt-1">
          <span className="w-2 h-2 rounded-full bg-green/40" />
          <span>MEM OK</span>
        </div>
      </div>
    </aside>
  )
}