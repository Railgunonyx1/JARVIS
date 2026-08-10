/** Wire protocol constants mirrored from runtime/transport/protocol.py. */

export const PROTOCOL_VERSION = 1

export const MSG_AUTH = 'auth'
export const MSG_PING = 'ping'
export const MSG_STATUS = 'status'
export const MSG_RUN = 'run'
export const MSG_SET_MODE = 'set_mode'
export const MSG_MEMORY_SEARCH = 'memory_search'
export const MSG_MEMORY_ADD = 'memory_add'
export const MSG_MODELS = 'models'
export const MSG_HISTORY = 'history'
export const MSG_SHUTDOWN = 'shutdown'
export const MSG_CANCEL = 'cancel'
export const MSG_BOOTSTRAP = 'issue_bootstrap'

export const MSG_PONG = 'pong'
export const MSG_OK = 'ok'
export const MSG_RESULT = 'result'
export const MSG_EVENT = 'stream.event'
export const MSG_RUN_RESULT = 'stream.result'
export const MSG_CONN_STATE = 'stream.conn'
export const MSG_ERROR = 'error'
export const MSG_BUSY = 'busy'

/** id used by the daemon for broadcast frames (peer connection-state). */
export const BROADCAST_ID = '__broadcast__'

export interface Envelope {
  version: number
  id: string
  type: string
  timestamp: number
  payload: Record<string, unknown>
}

export function makeEnvelope(
  type: string,
  payload: Record<string, unknown> = {},
  id: string = '',
): Envelope {
  return {
    version: PROTOCOL_VERSION,
    id: id || randomId(),
    type,
    timestamp: Date.now() / 1000,
    payload,
  }
}

export function randomId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID().replace(/-/g, '')
  }
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}
