import { create } from 'zustand'

interface TelemetrySample {
  cpu_percent: number
  ram_percent: number
  disk_percent: number
  gpu_percent: number | null
  uptime: number
  timestamp: number
}

interface TelemetryState {
  latest: TelemetrySample | null
  cpuHistory: number[]
  ramHistory: number[]
  diskHistory: number[]
  gpuHistory: number[] | null
  isSubscribed: boolean
  subscribe: () => void
  unsubscribe: () => void
}

export const useTelemetryStore = create<TelemetryState>((set, get) => ({
  latest: null,
  cpuHistory: [],
  ramHistory: [],
  diskHistory: [],
  gpuHistory: null,
  isSubscribed: false,

  subscribe: () => set((s) => {
    if (s.isSubscribed) return s
    // Subscribe to daemon telemetry stream - cx is available globally via Tailwind
    const unsubscribe = (_sample: TelemetrySample) => {
      const { cpuHistory, ramHistory, diskHistory, gpuHistory } = get()
      set({
        latest: _sample,
        cpuHistory: [...cpuHistory, _sample.cpu_percent].slice(-60),
        ramHistory: [...ramHistory, _sample.ram_percent].slice(-60),
        diskHistory: [...diskHistory, _sample.disk_percent].slice(-60),
        gpuHistory: gpuHistory ? [...gpuHistory, _sample.gpu_percent!].slice(-60) : [_sample.gpu_percent!].slice(-60),
      })
    }
    set({ latest: undefined })
    return { ...s, isSubscribed: true, subscribe: () => {}, unsubscribe }
  }),

  unsubscribe: () => set({ isSubscribed: false }),
}))