/**
 * JARVIS Orbit — Preload Script
 *
 * Exposes a safe, contextIsolated API to the renderer process.
 * No Node.js access in renderer — all communication via IPC.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("orbit", {
  // ── Tab Management ──────────────────────────────────────────────
  tabs: {
    create: (url) => ipcRenderer.invoke("tab:create", url),
    close: (id) => ipcRenderer.invoke("tab:close", id),
    activate: (id) => ipcRenderer.invoke("tab:activate", id),
    list: () => ipcRenderer.invoke("tab:list"),
  },

  // ── JARVIS Communication ────────────────────────────────────────
  jarvis: {
    status: () => ipcRenderer.invoke("jarvis:status"),
    send: (msg) => ipcRenderer.invoke("jarvis:send", msg),
    chat: (text, sessionId) => ipcRenderer.invoke("jarvis:chat", text, sessionId),

    // Event listeners
    onStatus: (callback) => {
      ipcRenderer.on("jarvis-status", (_, status) => callback(status));
    },
    onChat: (callback) => {
      ipcRenderer.on("jarvis-chat", (_, payload) => callback(payload));
    },
    onAgentEvent: (callback) => {
      ipcRenderer.on("jarvis-agent-event", (_, event) => callback(event));
    },
    onApproval: (callback) => {
      ipcRenderer.on("jarvis-approval", (_, request) => callback(request));
    },
    onMessage: (callback) => {
      ipcRenderer.on("jarvis-message", (_, msg) => callback(msg));
    },
  },

  // ── Navigation ──────────────────────────────────────────────────
  navigate: (url) => ipcRenderer.invoke("navigate", url),

  // ── Browser Info ────────────────────────────────────────────────
  info: () => ipcRenderer.invoke("browser:info"),

  // ── Window Events ───────────────────────────────────────────────
  on: {
    tabCreated: (callback) => {
      ipcRenderer.on("tab-created", (_, tab) => callback(tab));
    },
    tabClosed: (callback) => {
      ipcRenderer.on("tab-closed", (_, id) => callback(id));
    },
    tabActivated: (callback) => {
      ipcRenderer.on("tab-activated", (_, tab) => callback(tab));
    },
    navigateTo: (callback) => {
      ipcRenderer.on("navigate-to", (_, url) => callback(url));
    },
  },

  // ── System (Shields / Permissions / Performance / Spaces) ───────
  system: {
    security: {
      status: () => ipcRenderer.invoke("security:status"),
      shields: (enabled) => ipcRenderer.invoke("security:shields", !!enabled),
      config: (cfg) => ipcRenderer.invoke("security:config", cfg),
    },
    permissions: {
      allow: (origin, permission) => ipcRenderer.invoke("permissions:allow", origin, permission),
      revoke: (origin, permission) => ipcRenderer.invoke("permissions:revoke", origin, permission),
      list: () => ipcRenderer.invoke("permissions:list"),
    },
    performance: {
      status: () => ipcRenderer.invoke("performance:status"),
      efficiency: (enabled) => ipcRenderer.invoke("performance:efficiency", !!enabled),
    },
    spaces: {
      list: () => ipcRenderer.invoke("spaces:list"),
      switch: (id) => ipcRenderer.invoke("spaces:switch", id),
    },
  },
});
