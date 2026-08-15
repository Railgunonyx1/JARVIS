import type { DockviewApi } from "dockview-react"

export type PanelId = "chat" | "timeline" | "telemetry" | "logs" | "tasks" | "memory" | "files" | "settings"

export const PANELS: { id: PanelId; title: string }[] = [
  { id: "chat", title: "Chat" },
  { id: "timeline", title: "Agent Timeline" },
  { id: "telemetry", title: "Telemetry" },
  { id: "logs", title: "Logs" },
  { id: "tasks", title: "Tasks" },
  { id: "memory", title: "Memory" },
  { id: "files", title: "Files" },
  { id: "settings", title: "Settings" },
]

const STORAGE_KEY = "jarvis.layout.v1"

/**
 * Thin imperative handle over the Dockview API. The command palette, title bar,
 * and status bar drive panel focus/creation/reset through this without props
 * drilling the dockview instance across the tree.
 */
class WorkspaceApi {
  private api: DockviewApi | null = null

  attach(api: DockviewApi) {
    this.api = api
  }

  /** Focus a panel, re-creating it if the user had closed it. */
  focus(id: PanelId) {
    if (!this.api) return
    const existing = this.api.getPanel(id)
    if (existing) {
      existing.api.setActive()
      return
    }
    const meta = PANELS.find((p) => p.id === id)
    this.api.addPanel({ id, component: id, title: meta ? meta.title.toLowerCase() : id })
  }

  resetLayout() {
    if (!this.api) return
    localStorage.removeItem(STORAGE_KEY)
    this.api.clear()
    // reload rebuilds the default layout deterministically
    window.location.reload()
  }
}

export const workspaceApi = new WorkspaceApi()
