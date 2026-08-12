import { create } from 'zustand'

/** Top-bar navigation tabs (prototype `.nav`). */
export type Tab = 'agent' | 'tools' | 'memory' | 'repo' | 'mcp' | 'audit' | 'settings'

export const TABS: ReadonlyArray<{ id: Tab; label: string }> = [
  { id: 'agent', label: 'AGENT' },
  { id: 'tools', label: 'TOOLS' },
  { id: 'memory', label: 'MEMORY' },
  { id: 'repo', label: 'REPO' },
  { id: 'mcp', label: 'MCP' },
  { id: 'audit', label: 'AUDIT' },
  { id: 'settings', label: 'SETTINGS' },
]

export interface Toast {
  id: string
  message: string
}

const TOAST_MS = 1800
let toastSeq = 0

interface UiStore {
  activeTab: Tab
  focusMode: boolean
  /** Expanded state keyed by component id (tool cards, collapsibles...). */
  expanded: Record<string, boolean>
  toasts: Toast[]
  setTab: (tab: Tab) => void
  toggleFocus: () => void
  setExpanded: (id: string, open: boolean) => void
  toggleExpanded: (id: string) => void
  toast: (message: string) => void
  dismissToast: (id: string) => void
}

export const useUiStore = create<UiStore>((set) => ({
  activeTab: 'agent',
  focusMode: false,
  expanded: {},
  toasts: [],

  setTab: (tab) => set({ activeTab: tab }),

  toggleFocus: () => set((s) => ({ focusMode: !s.focusMode })),

  setExpanded: (id, open) => set((s) => ({ expanded: { ...s.expanded, [id]: open } })),
  toggleExpanded: (id) =>
    set((s) => ({ expanded: { ...s.expanded, [id]: !s.expanded[id] } })),

  toast: (message) => {
    const id = `t-${Date.now()}-${toastSeq++}`
    set((s) => ({ toasts: [...s.toasts, { id, message }] }))
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
    }, TOAST_MS)
  },

  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))
