import { create } from 'zustand'

export const useKernelStore = create((set) => ({
  status: 'offline',
  connected: false,
  uptime: 0,
  performanceMode: 'balanced',
  startTime: Date.now(),

  setStatus: (status) => set({ status }),
  setConnected: (connected) => set({ connected }),
  setUptime: (uptime) => set({ uptime }),
  setPerformanceMode: (mode) => set({ performanceMode: mode }),
}))
