/**
 * JARVIS Orbit — Preload Script
 *
 * Exposes a safe, contextIsolated API to the renderer process.
 * No Node.js access in renderer — all communication via IPC.
 *
 * Every event subscription (jarvis.on*, on.*, downloads.onUpdated) returns a
 * disposer that removes exactly its own wrapped listener, so repeated mounts
 * cannot accumulate duplicate callbacks.
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
      const listener = (_, status) => callback(status);
      ipcRenderer.on("jarvis-status", listener);
      return () => ipcRenderer.removeListener("jarvis-status", listener);
    },
    onChat: (callback) => {
      const listener = (_, payload) => callback(payload);
      ipcRenderer.on("jarvis-chat", listener);
      return () => ipcRenderer.removeListener("jarvis-chat", listener);
    },
    onAgentEvent: (callback) => {
      const listener = (_, event) => callback(event);
      ipcRenderer.on("jarvis-agent-event", listener);
      return () => ipcRenderer.removeListener("jarvis-agent-event", listener);
    },
    onApproval: (callback) => {
      const listener = (_, request) => callback(request);
      ipcRenderer.on("jarvis-approval", listener);
      return () => ipcRenderer.removeListener("jarvis-approval", listener);
    },
    onMessage: (callback) => {
      const listener = (_, msg) => callback(msg);
      ipcRenderer.on("jarvis-message", listener);
      return () => ipcRenderer.removeListener("jarvis-message", listener);
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

  // Absolute path to the guest (<webview>) preload, handed over by main.js.
  // It cannot be spelled relatively: relative webview preloads resolve against
  // the embedder document (src/index.html), so "./guest-preload.js" pointed at
  // a file that does not exist and every guest ran with no preload at all.
  guestPreload: (() => {
    const arg = process.argv.find((a) => a.startsWith("--orbit-guest-preload="));
    return arg ? arg.slice("--orbit-guest-preload=".length) : null;
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
      const listener = (_, tab) => callback(tab);
      ipcRenderer.on("tab-created", listener);
      return () => ipcRenderer.removeListener("tab-created", listener);
    },
    tabClosed: (callback) => {
      const listener = (_, id) => callback(id);
      ipcRenderer.on("tab-closed", listener);
      return () => ipcRenderer.removeListener("tab-closed", listener);
    },
    tabActivated: (callback) => {
      const listener = (_, tab) => callback(tab);
      ipcRenderer.on("tab-activated", listener);
      return () => ipcRenderer.removeListener("tab-activated", listener);
    },
    navigateTo: (callback) => {
      const listener = (_, url) => callback(url);
      ipcRenderer.on("navigate-to", listener);
      return () => ipcRenderer.removeListener("navigate-to", listener);
    },
    // REMOVED: agent-read / agent-click / agent-type. These answered tool
    // round-trips from the quarantined Electron agent loop. Browser actions
    // now execute in the JARVIS kernel, which drives Chromium over CDP
    // (jbrowser/BrowserController) instead of driving the renderer.
    tabSleep: (callback) => {
      const listener = (_, id) => callback(id);
      ipcRenderer.on("tab-sleep", listener);
      return () => ipcRenderer.removeListener("tab-sleep", listener);
    },
    tabWake: (callback) => {
      const listener = (_, id) => callback(id);
      ipcRenderer.on("tab-wake", listener);
      return () => ipcRenderer.removeListener("tab-wake", listener);
    },
    spaceChanged: (callback) => {
      const listener = (_, payload) => callback(payload);
      ipcRenderer.on("space-changed", listener);
      return () => ipcRenderer.removeListener("space-changed", listener);
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
    onUpdated: (cb) => {
      const listener = (_e, list) => cb(list);
      ipcRenderer.on("downloads-updated", listener);
      return () => ipcRenderer.removeListener("downloads-updated", listener);
    },
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
