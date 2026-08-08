import { create } from 'zustand'

const MAX_MESSAGES = 100

export const useChatStore = create((set, get) => ({
  messages: [],
  streaming: false,
  streamText: '',
  timing: null,

  addMessage: (role, text, opts = {}) => {
    const { messages } = get()
    const msg = { id: Date.now() + Math.random(), role, text, ...opts }
    const next = messages.length >= MAX_MESSAGES
      ? [...messages.slice(1), msg]
      : [...messages, msg]
    set({ messages: next })
  },

  startStream: () => set({ streaming: true, streamText: '', timing: null }),
  appendStream: (token) => set((s) => ({ streamText: s.streamText + token })),
  endStream: () => set({ streaming: false }),
  setTiming: (timing) => set({ timing }),
}))
