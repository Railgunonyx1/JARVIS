import { useCallback } from "react"
import { DockviewReact, type DockviewReadyEvent, type IDockviewPanelProps } from "dockview-react"
import { ChatPanel } from "@/components/panels/chat-panel"
import { TimelinePanel } from "@/components/panels/timeline-panel"
import { TelemetryPanel } from "@/components/panels/telemetry-panel"
import { LogsPanel } from "@/components/panels/logs-panel"
import { TasksPanel } from "@/components/panels/tasks-panel"
import { MemoryPanel } from "@/components/panels/memory-panel"
import { FilesPanel } from "@/components/panels/files-panel"
import { SettingsPanel } from "@/components/panels/settings-panel"
import { workspaceApi } from "@/lib/workspace-api"

const components = {
  chat: (_: IDockviewPanelProps) => <ChatPanel />,
  timeline: (_: IDockviewPanelProps) => <TimelinePanel />,
  telemetry: (_: IDockviewPanelProps) => <TelemetryPanel />,
  logs: (_: IDockviewPanelProps) => <LogsPanel />,
  tasks: (_: IDockviewPanelProps) => <TasksPanel />,
  memory: (_: IDockviewPanelProps) => <MemoryPanel />,
  files: (_: IDockviewPanelProps) => <FilesPanel />,
  settings: (_: IDockviewPanelProps) => <SettingsPanel />,
}

const STORAGE_KEY = "jarvis.layout.v1"

export function Workspace() {
  const onReady = useCallback((event: DockviewReadyEvent) => {
    const api = event.api
    workspaceApi.attach(api)

    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      try {
        api.fromJSON(JSON.parse(saved))
        return
      } catch {
        localStorage.removeItem(STORAGE_KEY)
      }
    }

    buildDefaultLayout(api)

    api.onDidLayoutChange(() => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(api.toJSON()))
      } catch {
        /* ignore quota */
      }
    })
  }, [])

  return (
    <DockviewReact
      className="dockview-theme-jarvis h-full w-full"
      components={components}
      onReady={onReady}
    />
  )
}

function buildDefaultLayout(api: DockviewReadyEvent["api"]) {
  const chat = api.addPanel({ id: "chat", component: "chat", title: "chat" })

  const timeline = api.addPanel({
    id: "timeline",
    component: "timeline",
    title: "timeline",
    position: { referencePanel: chat.id, direction: "right" },
  })

  api.addPanel({
    id: "telemetry",
    component: "telemetry",
    title: "telemetry",
    position: { referencePanel: timeline.id, direction: "right" },
  })

  const logs = api.addPanel({
    id: "logs",
    component: "logs",
    title: "logs",
    position: { referencePanel: timeline.id, direction: "below" },
  })

  api.addPanel({ id: "tasks", component: "tasks", title: "tasks", position: { referencePanel: logs.id, direction: "within" } })

  api.addPanel({
    id: "memory",
    component: "memory",
    title: "memory",
    position: { referencePanel: "telemetry", direction: "below" },
  })

  api.addPanel({ id: "files", component: "files", title: "files", position: { referencePanel: "chat", direction: "below" } })
  api.addPanel({ id: "settings", component: "settings", title: "settings", position: { referencePanel: "files", direction: "within" } })

  const chatPanel = api.getPanel("chat")
  chatPanel?.api.setActive()
}
