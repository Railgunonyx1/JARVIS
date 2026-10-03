/**
 * JARVIS Orbit — Preload Script
 *
 * Exposes a safe, contextIsolated API to the renderer process.
 * No Node.js access in renderer — all communication via IPC.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("orbit", {
  // A-01: per-launch bridge token (set by the launcher's env). One-time
  // sync read at boot; the value never leaves the preload boundary.
  getBridgeToken: () => ipcRenderer.sendSync("orbit:get-bridge-token"),
  // ── Tab Management ──────────────────────────────────────────────
  tabs: {
    create: (url) => ipcRenderer.invoke("tab:create", url),
    close: (id) => ipcRenderer.invoke("tab:close", id),
    activate: (id) => ipcRenderer.invoke("tab:activate", id),
    list: () => ipcRenderer.invoke("tab:list"),
    attach: (id, url, wcId) => ipcRenderer.invoke("tab:attach", id, url, wcId),
  },

  // ── JARVIS Communication ────────────────────────────────────────
  jarvis: {
    status: () => ipcRenderer.invoke("jarvis:status"),
    send: (msg) => ipcRenderer.invoke("jarvis:send", msg),
    chat: (text, sessionId) => ipcRenderer.invoke("jarvis:chat", text, sessionId),

    // Companion management
    startTask: (payload) => ipcRenderer.invoke("companion:task", payload),
    stopTask: (payload) => ipcRenderer.invoke("companion:stop", payload),

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

  // ── Performance / Lightweight Module ────────────────────────
  perf: {
    stats: () => ipcRenderer.invoke("perf:stats"),
    domOptimize: (data) => ipcRenderer.invoke("perf:dom-optimize", data),
    gc: () => ipcRenderer.invoke("perf:gc"),
    memoryReport: () => ipcRenderer.invoke("perf:memory-report"),
    errorLog: () => ipcRenderer.invoke("main:error-log"),
    clearErrorLog: () => ipcRenderer.invoke("main:error-log-clear"),
  },

  // ── Window Controls ─────────────────────────────────────────────
  window: {
    minimize: () => ipcRenderer.send("win-minimize"),
    maximize: () => ipcRenderer.send("win-maximize"),
    close: () => ipcRenderer.send("win-close"),
    create: () => ipcRenderer.invoke("window:create"),
    createPrivate: () => ipcRenderer.invoke("window:create-private"),
    // Private tab PIN protection (Safari-style)
    checkPin: (pin) => ipcRenderer.invoke("private:check-pin", pin),
    setPin: (pin) => ipcRenderer.invoke("private:set-pin", pin),
    clearPin: () => ipcRenderer.invoke("private:clear-pin"),
    isLocked: () => ipcRenderer.invoke("private:is-locked"),
    fullscreen: () => ipcRenderer.invoke("window:fullscreen"),
  },

  // ── Webview partition for this window (persist:orbit or in-memory) ──
  partition: (() => {
    const arg = process.argv.find((a) => a.startsWith("--orbit-partition="));
    return arg ? arg.split("=")[1] : null;
  })(),

  // ── Navigation ──────────────────────────────────────────────────
  navigation: {
    to: (url) => ipcRenderer.invoke("navigate", url),
  },

  // ── Browser Info / window-level browser actions ────────────────
  browser: {
    info: () => ipcRenderer.invoke("browser:info"),
    popoutVideo: () => ipcRenderer.invoke("tab:popout"),
  },

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
    // REMOVED: agent-read / agent-click / agent-type. These answered tool
    // round-trips from the quarantined Electron agent loop. Browser actions
    // now execute in the JARVIS kernel, which drives Chromium over CDP
    // (jbrowser/BrowserController) instead of driving the renderer.
    tabSleep: (callback) => {
      ipcRenderer.on("tab-sleep", (_, id) => callback(id));
    },
    tabWake: (callback) => {
      ipcRenderer.on("tab-wake", (_, id) => callback(id));
    },
    spaceChanged: (callback) => {
      ipcRenderer.on("space-changed", (_, payload) => callback(payload));
    },
  },

  // ── Headless Agent Loop ────────────────────────────────────────
  // REMOVED: the legacy `agent` surface. main.js answers agent:start with
  // "disabled" and registers no agent-state / agent-tool / agent-*-result
  // senders, so this advertised a second execution authority that could not
  // run. Agent work goes through the JARVIS kernel via orbit.jarvis.*
  // (dshNative -> POST /v1/agent -> ToolExecutionService).

  // ── Chrome Import ──────────────────────────────────────────────
  chrome: {
    detect: () => ipcRenderer.invoke("chrome:detect"),
    import: (profilePath) => ipcRenderer.invoke("chrome:import", profilePath),
    applyBookmarks: (bookmarks) => ipcRenderer.invoke("chrome:apply-bookmarks", bookmarks),
    applyHistory: (history) => ipcRenderer.invoke("chrome:apply-history", history),
  },

  // ── Extension Store ────────────────────────────────────────────
  extensions: {
    list: () => ipcRenderer.invoke("extensions:list"),
    vpn: () => ipcRenderer.invoke("extensions:vpn"),
    adblockers: () => ipcRenderer.invoke("extensions:adblockers"),
    install: (key) => ipcRenderer.invoke("extensions:install", key),
    toggle: (extensionId) => ipcRenderer.invoke("extensions:toggle", extensionId),
    remove: (extensionId) => ipcRenderer.invoke("extensions:remove", extensionId),
    markInstalled: (extensionId) => ipcRenderer.invoke("extensions:mark-installed", extensionId),
  },

  // ── Permissions ────────────────────────────────────────────────
  // Canonical location. It used to also be reachable as system.permissions;
  // two names for one capability means the renderer, the security review and
  // the permission engine can silently drift apart. One name, one path.
  permissions: {
    allow: (origin, permission) => ipcRenderer.invoke("permissions:allow", origin, permission),
    revoke: (origin, permission) => ipcRenderer.invoke("permissions:revoke", origin, permission),
    list: () => ipcRenderer.invoke("permissions:list"),
  },

  // ── Downloads ──────────────────────────────────────────────────
  // Canonical location (was also exposed as system.downloads).
  downloads: {
    list: () => ipcRenderer.invoke("downloads:list"),
    clear: () => ipcRenderer.invoke("downloads:clear"),
    cancel: (id) => ipcRenderer.invoke("downloads:cancel", id),
    show: (id) => ipcRenderer.invoke("downloads:show", id),
    onUpdated: (cb) => ipcRenderer.on("downloads-updated", (_e, list) => cb(list)),
  },

  // ── Spaces ─────────────────────────────────────────────────────
  spaces: {
    list: () => ipcRenderer.invoke("spaces:list"),
    switch: (id) => ipcRenderer.invoke("spaces:switch", id),
  },

  // ── Session ────────────────────────────────────────────────────
  session: {
    clearSiteData: (origin) => ipcRenderer.invoke("session:clear-site-data", origin),
  },

  // ── System (Shields / Performance) ─────────────────────────────
  system: {
    security: {
      status: () => ipcRenderer.invoke("security:status"),
      shields: (enabled) => ipcRenderer.invoke("security:shields", !!enabled),
      config: (cfg) => ipcRenderer.invoke("security:config", cfg),
      network: (cfg) => ipcRenderer.invoke("security:network", cfg),
      clearBrowsingData: (opts) => ipcRenderer.invoke("browsing-data:clear", opts || {}),
    },
    performance: {
      status: () => ipcRenderer.invoke("performance:status"),
      efficiency: (enabled) => ipcRenderer.invoke("performance:efficiency", !!enabled),
    },
  },
});
