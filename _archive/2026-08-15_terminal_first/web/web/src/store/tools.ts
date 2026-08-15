import { create } from 'zustand'
import { daemon } from '../daemon'

interface McpServer {
  name: string
  status: 'ONLINE' | 'OFFLINE' | 'ERROR'
  tools: number
  version?: string
}

interface McpState {
  servers: McpServer[]
  isLoading: boolean
  error: string | null
  load: () => void
}

export const useMcpStore = create<McpState>((set) => ({
  servers: [],
  isLoading: false,
  error: null,

  load: async () => {
    set({ isLoading: true, error: null })
    try {
      const result = await daemon.mcpList()
      set({ servers: result.servers, isLoading: false })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Unknown MCP error', isLoading: false })
    }
  },
}))