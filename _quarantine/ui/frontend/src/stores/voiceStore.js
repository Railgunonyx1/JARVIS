import { create } from 'zustand'

export const useVoiceStore = create((set) => ({
  micActive: false,
  camActive: false,
  waveformVisible: false,

  setMicActive: (active) => set({ micActive: active, waveformVisible: active }),
  setCamActive: (active) => set({ camActive: active }),
}))
