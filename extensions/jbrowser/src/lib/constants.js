export const BRIDGE = Object.freeze({
  host: "127.0.0.1",
  port: 8170,
  base: "http://127.0.0.1:8170",
  endpoints: Object.freeze({
    status: "/status",
    chat: "/v1/chat",
    agent: "/v1/agent",
    cdp: "/v1/cdp",
  }),
  connectTimeoutMs: 2500,
});

export const Msg = Object.freeze({
  // worker -> contexts
  PAGE_CONTEXT: "jb:page-context",
  SELECTION: "jb:selection",
  STREAM_DELTA: "jb:stream-delta",
  CHAT_REPLY: "jb:chat-reply",
  CHAT_DONE: "jb:chat-done",
  CHAT_ERROR: "jb:chat-error",
  STATUS_UPDATE: "jb:status-update",
  CAPTURE_PAGE: "jb:capture-page",
  STREAM_START: "jb:stream-start",
  // sidebar <-> service worker
  CHAT_REQUEST: "jb:chat-request",
  ABORT_REQUEST: "jb:abort-request",
  STATUS_REQUEST: "jb:status-request",
  CLEAR_SESSION: "jb:clear-session",
  TOGGLE: "jb:toggle",
});

export const STORAGE = Object.freeze({
  sessionId: "jb:sessionId",
  conversations: "jb:conversations",
  settings: "jb:settings",
  installState: "jb:installed",
  bridgeToken: "jb:bridgeToken",
});
