import { create } from 'zustand'
import { DaemonClient } from '../daemon/client'
import type { AuthCredentials } from '../daemon/client'
import type { ConnStateEvent, ConnectionStatus } from '../daemon/types'

interface ConnectionStore {
  status: ConnectionStatus
  detail: string
  peerCount: number
  bootstrapUrl: string
  url: string
  client: DaemonClient
  connect: (url: string, auth: AuthCredentials) => void
  disconnect: () => void
  setBootstrapUrl: (url: string) => void
}

const client = new DaemonClient()

export const useConnectionStore = create<ConnectionStore>((set) => ({
  status: 'idle',
  detail: '',
  peerCount: 0,
  bootstrapUrl: '',
  url: '',
  client,

  connect: (url, auth) => {
    set({ url })
    client.onStatus((status, detail) => set({ status, detail }))
    client.onConnState((event: ConnStateEvent) => {
      if (event.event === 'opened') {
        set({ peerCount: event.clients })
      }
    })
    client.connect(url, auth)
  },

  disconnect: () => {
    client.disconnect()
    set({ status: 'idle', detail: '', peerCount: 0 })
  },

  setBootstrapUrl: (url) => set({ bootstrapUrl: url }),
}))
