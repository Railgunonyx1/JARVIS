import { create } from 'zustand'

export const useTelemetryStore = create((set) => ({
  cpu: 0,
  ram: 0,
  gpu: 0,
  disk: 0,
  vram: 0,
  network: 0,
  temperature: null,

  update: (data) => set({
    cpu: data.cpu ?? 0,
    ram: data.ram ?? 0,
    gpu: data.gpu ?? 0,
    disk: data.disk ?? 0,
    vram: data.vram ?? 0,
    network: data.network ?? 0,
    temperature: data.temperature ?? null,
  }),
}))
