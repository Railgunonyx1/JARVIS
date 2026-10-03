/**
 * JARVIS Orbit — guest (webview) preload.
 *
 * Runs in every <webview> guest frame, isolated from the page when
 * contextIsolation is enforced (see will-attach-webview in main.js). Ships no
 * node power to the site; only a tiny inert flag so the renderer/bridge can
 * confirm a hardened guest. Fingerprint farbling and anti-automation hooks
 * land here in Phase D.
 *
 * First-party orbit:// pages (Import helper, Extension Store) additionally get
 * a narrow IPC bridge (chrome + extensions surfaces) so those utilities work
 * inside a hardened guest. The gate on location.protocol keeps third-party
 * sites from reaching any IPC.
 */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("__ORBIT_GUEST__", Object.freeze({
  hardened: true,
  name: "JARVIS Orbit",
}));

const firstParty = typeof location !== "undefined" && location.protocol === "orbit:";

if (firstParty) {
  contextBridge.exposeInMainWorld("orbit", Object.freeze({
    chrome: Object.freeze({
      detect: () => ipcRenderer.invoke("chrome:detect"),
      import: (profilePath) => ipcRenderer.invoke("chrome:import", profilePath),
      applyBookmarks: (bookmarks) => ipcRenderer.invoke("chrome:apply-bookmarks", bookmarks),
      applyHistory: (history) => ipcRenderer.invoke("chrome:apply-history", history),
    }),
    extensions: Object.freeze({
      list: () => ipcRenderer.invoke("extensions:list"),
      vpn: () => ipcRenderer.invoke("extensions:vpn"),
      adblockers: () => ipcRenderer.invoke("extensions:adblockers"),
      install: (key) => ipcRenderer.invoke("extensions:install", key),
      toggle: (extensionId) => ipcRenderer.invoke("extensions:toggle", extensionId),
      remove: (extensionId) => ipcRenderer.invoke("extensions:remove", extensionId),
      markInstalled: (extensionId) => ipcRenderer.invoke("extensions:mark-installed", extensionId),
    }),
  }));
}