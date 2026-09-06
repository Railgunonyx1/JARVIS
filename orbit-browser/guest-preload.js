/**
 * JARVIS Orbit — guest (webview) preload.
 *
 * Runs in every <webview> guest frame, isolated from the page when
 * contextIsolation is enforced (see will-attach-webview in main.js). Ships no
 * node power to the site; only a tiny inert flag so the renderer/bridge can
 * confirm a hardened guest. Fingerprint farbling and anti-automation hooks
 * land here in Phase D.
 */
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("__ORBIT_GUEST__", Object.freeze({
  hardened: true,
  name: "JARVIS Orbit",
}));