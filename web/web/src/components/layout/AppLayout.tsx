import { useEffect } from 'react'
import { useAgentEvents } from '../../hooks/useAgentEvents'
import { useUiStore } from '../../store/ui'
import { useTelemetryStore } from '../../store/telemetry'
import { useMcpStore } from '../../store/tools'
import { useAgentStore } from '../../store/agent'
import { useMemoryStore } from '../../store/memory'
import { cx } from '../../lib/cx'
import { TopBar } from './TopBar'
import { Sidebar } from './Sidebar'
import { FooterBar } from './FooterBar'

interface AppLayoutProps {
  className?: string
}

export default function AppLayout({ className }: AppLayoutProps = {}) {
  const { activeTab, setTab } = useUiStore()
  const { latest, isSubscribed, subscribe } = useTelemetryStore()
  const { servers, load: loadMcp, error: mcpError } = useMcpStore()
  const { plan, connect: agentConnect, submit, cancel } = useAgentStore()
  const { searchResults, setQuery, performSearch, clearResults } = useMemoryStore()

  useEffect(() => {
    const unsubscribe = useAgentEvents()
    agentConnect(url)
    loadMcp()
    return () => {
      unsubscribe()
      // Event listeners managed inside useAgentStore
    }
  }, [])

  useEffect(() => {
    if (!isSubscribed) {
      subscribe()
    }
  }, [isSubscribed])

  return (
    <div className={cx('min-h-screen bg-[var(--color-bg)]', className)}>
      <TopBar setTab={setTab} />
      <div className="flex min-h-[calc(100vh-138px)]">
        <Sidebar setTab={setTab} />
        <main className="flex flex-col min-0 flex-1 w-full md:w-[calc(100%-260px)]">
          <div className="flex-1 overflow-auto p-4">
            <div className="space-y-2">
              {/* Agent workspace center */}
              <div className="space-y-2">
                {plan.phase !== 'idle' && (
                  <PanelCard title="AGENT PLAN">
                    <div className="text-[10px] text-muted mb-2">
                      Goal: {plan.plan.goal}
                    </div>
                    <div className="flex items-center gap-2 text-[10px]">
                      <span className={cx('px-2 py-1 rounded', plan.plan.phase === 'running' ? 'bg-cyan/10 text-cyan' : 'bg-panel3 text-muted')}>
                        {plan.plan.phase}
                      </span>
                      <span className="text-[10px] text-cyan/60">⏱ {plan.plan.durationMs ? `${plan.plan.durationMs}ms` : '—'}</span>
                    </div>
                    <div className="space-y-1">
                      {plan.plan.steps.map((step, i) => (
                        <div
                          key={i}
                          className={cx(
                            'flex items-center gap-2 px-2 py-1 rounded-md text-[10px] tracking-[.05em]',
                            step.status === 'pending' ? 'text-soft bg-transparent' : '',
                            step.status === 'running' ? 'bg-cyan/10 text-cyan' : '',
                            step.status === 'completed' ? 'bg-green/10 text-green' : '',
                            step.status === 'failed' ? 'bg-red/10 text-red' : '',
                          )}
                        >
                          <span
                            className={cx(
                              'w-1.5 h-1.5 rounded-full',
                              step.status === 'running' ? 'bg-cyan' : step.status === 'completed' ? 'bg-green' : step.status === 'failed' ? 'bg-red' : 'bg-soft',
                            )}
/>
                          <span className="min-w-0 flex-1 truncate">{step.title}</span>
                        </div>
                      ))}
                    </div>
                  </PanelCard>
                )}

                {/* Activity stream */}
                <PanelCard title="ACTIVITY">
                  <div className="h-[150px] overflow-auto text-[10px] text-muted">
                    {plan.plan.errors.map((err, i) => (
                      <div key={i} className="mb-1">
                        <span className="text-red/60">✗</span> {err}
                      </div>
                    ))}
                  </div>
                </PanelCard>

                {/* Output pane */}
                <PanelCard title="OUTPUT" className="h-[120px]">
                  <div className="h-full text-[10px] text-body overflow-auto">{plan.plan.output || '—'}</div>
                </PanelCard>
              </div>

              {/* Composer at bottom */}
              <Composer onSubmit={submit} onCancel={cancel} />
            </div>
          </div>
        </main>
      </div>

      {/* Inspector / right panel */}
      <div className="md:w-64 border-l border-line bg-panel/95 flex flex-col h-screen">
        <SectionTitle>SYSTEM</SectionTitle>
        <div className="flex-1 p-2">
          {/* Telemetry rings */}
          {latest && (
            <div className="flex items-center gap-4 mb-4">
              <div className="w-8 h-8 rounded-full bg-cyan/20 flex items-center justify-center">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                </svg>
              </div>
              <div>
                <span className="text-[10px] text-cyan">CPU</span>
                <span className="text-[10px]">{latest?.cpu_percent}%</span>
              </div>
            </div>
          )}

          {/* MCP panel */}
          <PanelCard>
            <SectionTitle>MCP SERVERS</SectionTitle>
            <div className="text-[10px]">
              {mcpError && <span className="text-red/60">Error: {mcpError}</span>}
              {servers.length === 0 && <span className="text-soft">No MCP servers configured</span>}
              {servers.map((s) => (
                <div key={s.name} className="flex items-center gap-2 my-1">
                  <span className={cx('w-2 h-2 rounded-full', s.status === 'ONLINE' ? 'bg-green' : s.status === 'OFFLINE' ? 'bg-red' : 'bg-gray')}></span>
                  <span>{s.name}</span>
                  <span className="text-[10px] text-soft">{s.tools} tools</span>
                </div>
              ))}
            </div>
          </PanelCard>

          {/* Memory search */}
          <PanelCard>
            <SectionTitle>MEMORY SEARCH</SectionTitle>
            <div className="mt-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search memory..."
                className="w-full bg-panel3 border border-line rounded px-2 py-1 text-[10px] placeholder:[#536d7d] focus:outline-none focus:ring-2 focus:ring-cyan/30"
              />
              <button
                onClick={() => performSearch(searchQuery)}
                className="mt-1 w-full bg-cyan text-white text-[10px] py-1 rounded hover:bg-cyan/90"
              >
                Search
              </button>
              {searchResults.length > 0 && (
                <div className="mt-2 text-[10px]">
                  {searchResults.map((r) => (
                    <div key={r.id} className="mb-1">
                      <span className="text-cyan truncate">{r.content.substring(0, 50)}...</span>
                      <span className="text-soft">{r.type}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </PanelCard>
        </div>
      </div>
    </div>
  )
}