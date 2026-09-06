/**
 * JARVIS Orbit — Electron Main Process
 *
 * A custom Chromium browser with native JARVIS intelligence.
 * NOT an extension — a standalone browser built on Electron (Chromium).
 */

const { app, BrowserWindow, ipcMain, session, protocol, net } = require("electron");
const path = require("path");
const { pathToFileURL } = require("url");
const WebSocket = require("ws");
const Store = require("electron-store");

// Research-pipeline optimizer modules (src/*.js — Brave Shields, Edge
// sleeping-tabs, Arc Spaces patterns).
const { SecurityModule } = require("./src/security.js");
const { PerformanceModule } = require("./src/performance.js");
const { SpacesModule } = require("./src/spaces.js");

// ── Chromium performance flags ────────────────────────────────────
// Mirrors the researched, evidence-backed launch profile codified in
// jbrowser/optimization.py, restricted to the flags that help a user-facing
// daily-driver browser (rendering/GPU offload, QUIC, lean background waste,
// live active tab). Browser-hostile switches (mute-audio, hide-scrollbars)
// and agent-only switches (disable-extensions/...) are intentionally omitted.
function applyChromiumFlags() {
  const flags = {
    "enable-gpu-rasterization": "",
    "num-raster-threads": "2",
    "enable-quic": "",
    "disable-features":
      "PreloadMediaEngagementData,MediaEngagementBypassAutoplayPolicies",
    "disable-background-timer-throttling": "",
    "disable-backgrounding-occluded-windows": "",
    "disable-renderer-backgrounding": "",
    "no-first-run": "",
    "no-default-browser-check": "",
    "disable-default-apps": "",
    "disable-domain-reliability": "",
    "disable-background-networking": "",
    "freeze-background-tabs": "",
  };
  for (const [name, value] of Object.entries(flags)) {
    app.commandLine.appendSwitch(name, value);
  }
}
applyChromiumFlags();

// ── Configuration ─────────────────────────────────────────────────
const CONFIG = {
  JARVIS_WS_URL: "ws://127.0.0.1:8171",
  DEFAULT_WIDTH: 1440,
  DEFAULT_HEIGHT: 900,
  MIN_WIDTH: 800,
  MIN_HEIGHT: 600,
  USER_AGENT:
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) JARVIS-Orbit/0.1.0 Chrome/120.0.0.0 Safari/537.36",
};

// ── Internal pages (orbit://<host>) ───────────────────────────────
const PAGES = {
  newtab: "src/newtab.html",
  settings: "src/settings.html",
  downloads: "src/downloads.html",
  history: "src/history.html",
  bookmarks: "src/bookmarks.html",
  tasks: "src/tasks.html",
  permissions: "src/permissions.html",
  memory: "src/memory.html",
  extensions: "src/extensions.html",
  diagnostics: "src/diagnostics.html",
};

// ── State ─────────────────────────────────────────────────────────
let mainWindow = null;
let jarvisWs = null;
let jarvisStatus = { ok: false, kernel: "offline" };
let jarvisReconnectAttempts = 0;
const JARVIS_MAX_RECONNECT = 10;
const JARVIS_BASE_DELAY = 1000; // 1s base, doubles each attempt

// ── Optimizer module instances ────────────────────────────────────
const security = new SecurityModule();
const performance = new PerformanceModule();
const spaces = new SpacesModule();
let store = null;           // electron-store: settings + site permissions
let browserSession = null;  // session.fromPartition("persist:orbit")

// ── Session & Security (Shields) ──────────────────────────────────
const SESSION_PARTITION = "persist:orbit";
const GUEST_PRELOAD = path.join(__dirname, "guest-preload.js");
const PERMISSION_ALLOWLIST = []; // { origin, permissions: [] }

// Network governance (Brave-style aggressive defaults, persisted in store).
const networkConfig = {
  blockPrivateNetwork: true,        // no page subresource may probe local nets
  fastBlockThirdPartyCookies: true, // cross-site responses drop Set-Cookie
  blockCrossSiteCookies: false,     // opt-in: also strip Cookie on cross-site calls
};

// Canvas readback grain — Brave-Shields-style fingerprint farbling, injected
// into the guest main world on load. Deterministic per page, bounded cost,
// skips huge canvases. Full farbling suite (WebGL, UA hints) lands in Phase D.
const GRAIN_JS = `
(function(){
  try {
    if (HTMLCanvasElement.prototype.__orbitGrain) return;
    Object.defineProperty(HTMLCanvasElement.prototype, "__orbitGrain", { value: true });
    var proto = HTMLCanvasElement.prototype;
    var td = proto.toDataURL;
    var gi = CanvasRenderingContext2D.prototype.getImageData;
    var host = (location && location.hostname) || "";
    var seed = 17;
    for (var i = 0; i < host.length; i++) seed = (seed * 131 + host.charCodeAt(i)) | 0;
    proto.toDataURL = function () {
      var out = td.apply(this, arguments);
      try {
        var w = this.width, h = this.height;
        if (!w || !h || w * h > 400000) return out;
        var ctx = this.getContext("2d");
        if (!ctx) return out;
        var d = gi.call(ctx, 0, 0, w, h).data;
        var n = Math.min(28, Math.floor(d.length / 3072) + 4);
        var mask = d.length - 8;
        for (var k = 0; k < n; k++) {
          var p = (seed + k * 977) & mask;
          var ch = (seed >>> 3 + k) & 3;
          d[p + ch] ^= 1 + ((seed + k) & 1);
        }
        ctx.putImageData(new ImageData(d, w, h), 0, 0);
      } catch (e) {}
      return out;
    };
  } catch (e) {}
})();
`;

function getBrowserSession() {
  if (!browserSession) {
    browserSession = session.fromPartition(SESSION_PARTITION);
  }
  return browserSession;
}

function urlFor(hostname) {
  try {
    return new URL(hostname);
  } catch (_) {
    return null;
  }
}

function isPrivateOrLocalHost(hostname) {
  const h = String(hostname || "").toLowerCase().replace(/\.$/, "");
  if (!h) return false;
  if (h === "localhost" || h.endsWith(".local") || h.endsWith(".localhost")) return true;
  if (h.includes(":") && h.split(":")[0] === "localhost") return true;
  const ipv4 = h.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (ipv4) {
    const [a, b, c, d] = ipv4.slice(1).map(Number);
    if (a === 127) return true;
    if (a === 10) return true;
    if (a === 192 && b === 168) return true;
    if (a === 172 && b >= 16 && b <= 31) return true;
    if (a === 169 && b === 254) return true;
    if (a === 0 || a >= 224) return true;
  }
  return false;
}

function isPrivateNetworkHost(hostname) {
  const h = String(hostname || "").replace(/^\[|\]$/g, "").toLowerCase();
  if (isPrivateOrLocalHost(h)) return true;
  if (h === "::1" || h === "::") return true;
  if (/^fe[89ab]?:/i.test(h)) return true;      // link-local fe80::/10
  if (/^f[cd]:/i.test(h)) return true;          // ULA fc00::/7
  return false;
}

function siteOriginOf(url) {
  try {
    return new URL(url).origin;
  } catch (_) {
    return null;
  }
}

function isAllowedPermission(origin, permission) {
  return PERMISSION_ALLOWLIST.some(
    (e) =>
      e.origin === origin &&
      (e.permissions.includes("*") || e.permissions.includes(permission))
  );
}

function installSecurity(ses) {
  // Ad/tracker blocking + HTTPS upgrade (Brave-Shields-lite). Private and
  // loopback destinations are left untouched so local dev servers keep
  // working while the daily browser is hardened.
  ses.webRequest.onBeforeRequest({ urls: ["*://*/*"] }, (details, callback) => {
    if (security.shouldBlock(details.url)) return callback({ cancel: true });
    if (networkConfig.blockPrivateNetwork && details.resourceType !== "mainFrame") {
      const parsed = urlFor(details.url);
      if (parsed && isPrivateNetworkHost(parsed.hostname)) {
        return callback({ cancel: true });
      }
    }
    if (details.url.startsWith("http://")) {
      const parsed = urlFor(details.url);
      if (parsed && !isPrivateOrLocalHost(parsed.hostname)) {
        const upgraded = security.upgradeToHttps(details.url);
        if (upgraded !== details.url) return callback({ redirectURL: upgraded });
      }
    }
    callback({});
  });

  // DNT header (referrer trust is baked into Chromium's default
  // strict-origin-when-cross-origin policy — no header surgery needed).
  ses.webRequest.onBeforeSendHeaders({ urls: ["*://*/*"] }, (details, callback) => {
    const headers = { ...(details.requestHeaders || {}) };
    if (security.config.doNotTrack) headers["DNT"] = "1";
    // Aggressive posture: strip Cookie on cross-site requests too.
    if (networkConfig.blockCrossSiteCookies && details.resourceType !== "mainFrame") {
      const top = siteOriginOf(details.topURL || "");
      const req = siteOriginOf(details.url);
      if (top && req && top !== req) delete headers["cookie"];
    }
    callback({ requestHeaders: headers });
  });

  // Cross-site responses never set cookies (third-party set-cookie block).
  ses.webRequest.onHeadersReceived({ urls: ["*://*/*"] }, (details, callback) => {
    const headers = details.responseHeaders || {};
    if (networkConfig.fastBlockThirdPartyCookies && details.resourceType !== "mainFrame") {
      const top = siteOriginOf(details.topURL || "");
      const req = siteOriginOf(details.url);
      if (top && req && top !== req) delete headers["set-cookie"];
    }
    callback({ responseHeaders: headers });
  });

  // Permissions: default-deny, allowlist wins (aggressive posture).
  ses.setPermissionCheckHandler((_wc, permission, origin, _details) =>
    isAllowedPermission(String(origin || ""), permission)
  );
  ses.setPermissionRequestHandler((wc, permission, callback, details) => {
    let origin = "";
    try {
      origin = new URL(details.requestingUrl).origin;
    } catch (_) {
      origin = wc.getURL();
    }
    callback(isAllowedPermission(origin, permission));
  });
}

function initStore() {
  store = new Store({
    name: "orbit-settings",
    defaults: {
      shields: {
        adBlocking: true,
        trackerBlocking: true,
        fingerprintProtection: true,
        httpsUpgrade: true,
      },
      network: { ...networkConfig },
      permissions: [],
    },
  });
  Object.assign(security.config, store.get("shields"));
  Object.assign(networkConfig, store.get("network"));
  const storedPermissions = store.get("permissions", []);
  if (Array.isArray(storedPermissions)) {
    PERMISSION_ALLOWLIST.length = 0;
    storedPermissions.forEach((entry) => PERMISSION_ALLOWLIST.push(entry));
  }
  return store;
}

// ── Tab Management ────────────────────────────────────────────────
const tabs = new Map();
const webContentsIds = new Map(); // tabId -> guest webContents.id
const frozenTabs = new Set();     // tabId currently frozen (sleeping)
let activeTabId = null;

function createTab(url = "orbit://newtab") {
  const id = `tab-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  tabs.set(id, {
    id,
    url,
    title: "New tab",
    favicon: null,
    loading: false,
    agentOwned: false,
  });

  performance.registerTab(id, url);

  // Notify renderer
  mainWindow?.webContents.send("tab-created", tabs.get(id));
  return id;
}

function closeTab(id) {
  performance.unregisterTab(id);
  webContentsIds.delete(id);
  frozenTabs.delete(id);
  tabs.delete(id);
  mainWindow?.webContents.send("tab-closed", id);
}

function setActiveTab(id) {
  activeTabId = id;
  performance.markActive(id);
  wakeTab(id);
  const tab = tabs.get(id);
  if (tab) {
    mainWindow?.webContents.send("tab-activated", tab);
  }
}

// ── Sleeping tabs (real freeze, Chrome-sleeping-tabs style) ───────
// The renderer marks sleeping state visually; this is the process lever.
// A hidden guest is put into the Chromium 'frozen' lifecycle state so its
// process can be swapped out. Tabs owned by an agent are never touched.

function guestFor(id) {
  const wcId = webContentsIds.get(id);
  return wcId ? webContents.fromId(wcId) : null;
}

async function freezeTab(id) {
  if (frozenTabs.has(id)) return;
  if (id === activeTabId) return;
  const wc = guestFor(id);
  if (!wc || wc.isDestroyed()) return;
  // The renderer pools webviews across tabs; never freeze the guest that is
  // currently backing the active tab, even if our id->wcId map is stale.
  if (webContentsIds.get(activeTabId) === wc.id) return;
  let attached = false;
  try {
    if (!wc.debugger.isAttached()) {
      wc.debugger.attach("1.3");
      attached = true;
      await wc.debugger.sendCommand("Page.setWebLifecycleState", { state: "frozen" });
      frozenTabs.add(id);
      mainWindow?.webContents.send("tab-sleep", id);
    }
  } catch (_) {
    // WebViews may refuse lifecycle control; cosmetic sleep still applies.
  } finally {
    if (attached) {
      try { wc.debugger.detach(); } catch (_) {}
    }
  }
}

async function wakeTab(id) {
  if (!frozenTabs.has(id)) return;
  frozenTabs.delete(id);
  mainWindow?.webContents.send("tab-wake", id);
  const wc = guestFor(id);
  if (!wc || wc.isDestroyed()) return;
  let attached = false;
  try {
    if (!wc.debugger.isAttached()) {
      wc.debugger.attach("1.3");
      attached = true;
      await wc.debugger.sendCommand("Page.setWebLifecycleState", { state: "active" });
    }
  } catch (_) {
  } finally {
    if (attached) {
      try { wc.debugger.detach(); } catch (_) {}
    }
  }
}

function runSleepCheck() {
  for (const [id, tab] of tabs) {
    if (tab.agentOwned) continue;
    if (performance.shouldSleep(id)) freezeTab(id);
  }
}

// ── JARVIS WebSocket Connection ───────────────────────────────────
function connectJarvis() {
  if (jarvisWs?.readyState === WebSocket.OPEN) return;
  if (jarvisReconnectAttempts >= JARVIS_MAX_RECONNECT) {
    console.warn("[JARVIS] Max reconnect attempts reached. Manual retry required.");
    jarvisStatus = { ok: false, kernel: "offline", reason: "max_retries" };
    mainWindow?.webContents.send("jarvis-status", jarvisStatus);
    return;
  }

  try {
    jarvisWs = new WebSocket(CONFIG.JARVIS_WS_URL);

    jarvisWs.on("open", () => {
      jarvisReconnectAttempts = 0; // Reset on successful connection
      jarvisStatus = { ok: true, kernel: "online" };
      mainWindow?.webContents.send("jarvis-status", jarvisStatus);
      console.log("[JARVIS] Connected");
    });

    jarvisWs.on("message", (data) => {
      try {
        const msg = JSON.parse(data.toString());
        handleJarvisMessage(msg);
      } catch (e) {
        console.error("[JARVIS] Parse error:", e);
      }
    });

    jarvisWs.on("close", () => {
      jarvisStatus = { ok: false, kernel: "offline" };
      mainWindow?.webContents.send("jarvis-status", jarvisStatus);
      console.log("[JARVIS] Disconnected");
      // Exponential backoff: 1s, 2s, 4s, 8s... capped at 30s
      const delay = Math.min(JARVIS_BASE_DELAY * Math.pow(2, jarvisReconnectAttempts), 30000);
      jarvisReconnectAttempts++;
      console.log(`[JARVIS] Reconnecting in ${delay}ms (attempt ${jarvisReconnectAttempts}/${JARVIS_MAX_RECONNECT})`);
      setTimeout(connectJarvis, delay);
    });

    jarvisWs.on("error", (err) => {
      console.error("[JARVIS] Error:", err.message);
    });
  } catch (e) {
    console.error("[JARVIS] Connection failed:", e.message);
    jarvisReconnectAttempts++;
    const delay = Math.min(JARVIS_BASE_DELAY * Math.pow(2, jarvisReconnectAttempts), 30000);
    setTimeout(connectJarvis, delay);
  }
}

function handleJarvisMessage(msg) {
  switch (msg.type) {
    case "status":
      jarvisStatus = msg.payload;
      mainWindow?.webContents.send("jarvis-status", jarvisStatus);
      break;
    case "chat_reply":
      mainWindow?.webContents.send("jarvis-chat", msg.payload);
      break;
    case "agent_event":
      mainWindow?.webContents.send("jarvis-agent-event", msg.payload);
      break;
    case "approval_request":
      mainWindow?.webContents.send("jarvis-approval", msg.payload);
      break;
    default:
      mainWindow?.webContents.send("jarvis-message", msg);
  }
}

function sendToJarvis(msg) {
  if (jarvisWs?.readyState === WebSocket.OPEN) {
    jarvisWs.send(JSON.stringify(msg));
  }
}

// ── Input Validation ──────────────────────────────────────────────
function validateString(val, name, maxLen = 2048) {
  if (typeof val !== "string") throw new TypeError(`${name} must be a string`);
  if (val.length > maxLen) throw new RangeError(`${name} exceeds max length ${maxLen}`);
  return val;
}

function validateUrl(val, name) {
  validateString(val, name);
  if (!/^(https?|orbit|about|data|blob):/i.test(val)) {
    throw new TypeError(`${name} must be a valid URL (http/https/orbit scheme)`);
  }
  return val;
}

function validateObject(val, name) {
  if (val === null || typeof val !== "object" || Array.isArray(val)) {
    throw new TypeError(`${name} must be a plain object`);
  }
  return val;
}

// ── Offline Message Queue ─────────────────────────────────────────
const offlineQueue = [];
const MAX_OFFLINE_QUEUE = 100;

function queueOrSend(msg) {
  if (jarvisWs?.readyState === WebSocket.OPEN) {
    jarvisWs.send(JSON.stringify(msg));
  } else if (offlineQueue.length < MAX_OFFLINE_QUEUE) {
    offlineQueue.push(msg);
    console.log(`[JARVIS] Message queued (offline) — queue size: ${offlineQueue.length}`);
  }
}

function flushOfflineQueue() {
  while (offlineQueue.length > 0 && jarvisWs?.readyState === WebSocket.OPEN) {
    const msg = offlineQueue.shift();
    jarvisWs.send(JSON.stringify(msg));
  }
}

// ── IPC Handlers ──────────────────────────────────────────────────
function setupIPC() {
  // Tab management
  ipcMain.handle("tab:create", (_, url) => createTab(url ? validateUrl(url, "tab url") : "orbit://newtab"));
  ipcMain.handle("tab:close", (_, id) => closeTab(validateString(id, "tab id", 128)));
  ipcMain.handle("tab:activate", (_, id) => setActiveTab(validateString(id, "tab id", 128)));
  ipcMain.handle("tab:list", () => Array.from(tabs.values()));
  // Renderer-born tabs register their guests here so the sleeping engine can
  // map tabId -> webContents.id (real freeze/wake); unknown ids are picked up
  // into the shared registry (e.g. window.open-created tabs).
  ipcMain.handle("tab:attach", (_e, id, url, wcId) => {
    const safeId = validateString(id, "tab id", 128);
    const safeUrl = url ? validateUrl(url, "tab url", 8192) : "orbit://newtab";
    if (!tabs.has(safeId)) {
      tabs.set(safeId, {
        id: safeId,
        url: safeUrl,
        title: "New tab",
        favicon: null,
        loading: false,
        agentOwned: false,
      });
      performance.registerTab(safeId, safeUrl);
    } else {
      tabs.get(safeId).url = safeUrl;
    }
    if (Number.isInteger(wcId) && wcId > 0) webContentsIds.set(safeId, wcId);
    return true;
  });

  // JARVIS communication
  ipcMain.handle("jarvis:status", () => jarvisStatus);
  ipcMain.handle("jarvis:send", (_, msg) => {
    validateObject(msg, "jarvis message");
    validateString(msg.type || "", "message type", 64);
    queueOrSend(msg);
  });
  ipcMain.handle("jarvis:chat", (_, text, sessionId) => {
    validateString(text, "chat text", 10000);
    const sid = sessionId ? validateString(sessionId, "session id", 128) : "default";
    queueOrSend({
      type: "chat_request",
      payload: { text, sessionId: sid },
    });
  });

  // Navigation
  ipcMain.handle("navigate", (_, url) => {
    validateUrl(url, "navigation url");
    mainWindow?.webContents.send("navigate-to", url);
  });

  // Browser info
  ipcMain.handle("browser:info", () => ({
    name: "JARVIS Orbit",
    version: app.getVersion(),
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
  }));

  // Security (Shields)
  ipcMain.handle("security:status", () => security.getStatus());
  ipcMain.handle("security:shields", (_e, enabled) => {
    security.toggleShields(!!enabled);
    store?.set("shields", { ...security.config });
    return security.getStatus();
  });
  ipcMain.handle("security:config", (_e, cfg) => {
    const safe = validateObject(cfg || {}, "security config");
    const allowed = ["adBlocking", "trackerBlocking", "fingerprintProtection", "httpsUpgrade", "doNotTrack"];
    for (const key of Object.keys(safe)) {
      if (allowed.includes(key)) security.config[key] = safe[key];
    }
    store?.set("shields", { ...security.config });
    return security.getStatus();
  });
  ipcMain.handle("security:network", (_e, cfg) => {
    const safe = validateObject(cfg || {}, "network config");
    const allowed = ["blockPrivateNetwork", "fastBlockThirdPartyCookies", "blockCrossSiteCookies"];
    for (const key of Object.keys(safe)) {
      if (allowed.includes(key)) networkConfig[key] = safe[key];
    }
    store?.set("network", { ...networkConfig });
    return { ...networkConfig };
  });

  // Site permissions (default-deny allowlist)
  ipcMain.handle("permissions:allow", (_e, origin, permission) => {
    const safeOrigin = validateString(origin, "origin", 2048);
    const safePerm = validateString(permission, "permission", 128);
    const entry = PERMISSION_ALLOWLIST.find((e) => e.origin === safeOrigin);
    if (entry) entry.permissions.push(safePerm);
    else PERMISSION_ALLOWLIST.push({ origin: safeOrigin, permissions: [safePerm] });
    store?.set("permissions", PERMISSION_ALLOWLIST);
    return true;
  });
  ipcMain.handle("permissions:revoke", (_e, origin, permission) => {
    const safeOrigin = validateString(origin, "origin", 2048);
    const safePerm = permission ? validateString(permission, "permission", 128) : null;
    const entry = PERMISSION_ALLOWLIST.find((e) => e.origin === safeOrigin);
    if (entry && safePerm) {
      entry.permissions = entry.permissions.filter((p) => p !== safePerm);
      if (!entry.permissions.length) {
        PERMISSION_ALLOWLIST.splice(PERMISSION_ALLOWLIST.indexOf(entry), 1);
      }
    } else if (entry) {
      PERMISSION_ALLOWLIST.splice(PERMISSION_ALLOWLIST.indexOf(entry), 1);
    }
    store?.set("permissions", PERMISSION_ALLOWLIST);
    return true;
  });
  ipcMain.handle("permissions:list", () =>
    PERMISSION_ALLOWLIST.map((e) => ({ ...e, permissions: [...e.permissions] }))
  );

  // Performance (sleeping tabs with real freeze; frozen count reported live)
  ipcMain.handle("performance:status", () => ({
    ...performance.getStatus(),
    frozen: frozenTabs.size,
  }));
  ipcMain.handle("performance:efficiency", (_e, enabled) =>
    performance.toggleEfficiencyMode(!!enabled)
  );

  // Spaces (active space reporting; partition-isolated tabs land in Phase B)
  ipcMain.handle("spaces:list", () => spaces.getStatus());
  ipcMain.handle("spaces:switch", (_e, id) => {
    spaces.switchTo(validateString(id, "space id", 64));
    return spaces.getStatus();
  });

  // Session persistence
  ipcMain.handle("session:save", () => {
    const tabData = Array.from(tabs.values());
    store?.set("lastSession", tabData);
    return { saved: tabData.length };
  });
  ipcMain.handle("session:restore", () => {
    return store?.get("lastSession", []) || [];
  });
}

// ── Window Creation ───────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: CONFIG.DEFAULT_WIDTH,
    height: CONFIG.DEFAULT_HEIGHT,
    minWidth: CONFIG.MIN_WIDTH,
    minHeight: CONFIG.MIN_HEIGHT,
    title: "JARVIS Orbit",
    icon: path.join(__dirname, "src/icons/icon.png"),
    titleBarStyle: "hidden",
    frame: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webviewTag: true,
      spellcheck: false,
    },
    backgroundColor: "#000000",
    show: false,
  });

  // Load the browser UI
  mainWindow.loadFile(path.join(__dirname, "src/index.html"));

  // Show when ready
  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  // Set CSP headers on the main window
  mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [
          "default-src 'self'; " +
          "script-src 'self' 'unsafe-inline'; " +
          "style-src 'self' 'unsafe-inline'; " +
          "img-src 'self' data: https:; " +
          "font-src 'self' data:; " +
          "connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:* wss://127.0.0.1:* https:; " +
          "frame-src 'self' https:; " +
          "object-src 'none'; " +
          "base-uri 'self'; " +
          "form-action 'self'; "
        ],
      },
    });
  });

  // Connect to JARVIS
  connectJarvis();

  // Restore previous session or create new tab
  const lastSession = store?.get("lastSession", []) || [];
  if (lastSession.length > 0 && lastSession.some(t => t.url && !t.url.startsWith("orbit://"))) {
    // Restore non-internal tabs from last session
    for (const tab of lastSession.filter(t => t.url && !t.url.startsWith("orbit://"))) {
      createTab(tab.url);
    }
  } else {
    createTab("orbit://newtab");
  }

  mainWindow.on("closed", () => {
    // Save session before closing
    const tabData = Array.from(tabs.values());
    store?.set("lastSession", tabData);
    // Cleanup
    mainWindow = null;
    jarvisWs?.close();
    performance.stopSleepCheck?.();
  });

  // ── Window Controls (frameless window) ────────────────────────
  ipcMain.on("win-minimize", () => mainWindow?.minimize());
  ipcMain.on("win-maximize", () => {
    if (mainWindow?.isMaximized()) mainWindow.unmaximize();
    else mainWindow?.maximize();
  });
  ipcMain.on("win-close", () => mainWindow?.close());
}

// ── App Lifecycle ─────────────────────────────────────────────────
app.whenReady().then(() => {
  initStore();
  installSecurity(getBrowserSession());
  // Spellcheck off at the session boundary (webContents-level API is gone in
  // modern Electron; dictionary loading is a RAM/CPU cost we don't need).
  for (const s of [session.defaultSession, getBrowserSession()]) {
    try {
      if (typeof s.setSpellCheckerEnabled === "function") s.setSpellCheckerEnabled(false);
    } catch (_) {}
  }
  setupIPC();
  createWindow();
  // Compact interval keeps tab-discard state fresh without busy work and
  // drives the real freeze/wake sleeping engine for hidden webviews.
  setInterval(runSleepCheck, 60000);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// ── Error Boundaries ──────────────────────────────────────────────
process.on("uncaughtException", (err) => {
  console.error("[FATAL] Uncaught exception:", err);
  // Don't crash the whole browser for renderer errors
});

process.on("unhandledRejection", (reason) => {
  console.error("[FATAL] Unhandled rejection:", reason);
});

app.on("window-all-closed", () => {
  jarvisWs?.close();
  performance.stopSleepCheck?.();
  if (process.platform !== "darwin") {
    app.quit();
  }
});

// ── Webview (guest) hardening ─────────────────────────────────────
// Every webContents at birth: spellcheck off (dict load is wasted RAM/CPU).
// The webContents-level setter was removed in modern Electron — prefer the
// session-level switch and guard the legacy call for safety.
app.on("web-contents-created", (_event, contents) => {
  try {
    if (typeof contents.setSpellCheckerEnabled === "function") {
      contents.setSpellCheckerEnabled(false);
    }
  } catch (_) {}

  // Guest navigation policy: window.open lands in the active tab (no popup
  // windows); only web-safe schemes may navigate a guest frame.
  if (contents.getType() === "webview") {
    contents.setWindowOpenHandler(({ url }) => {
      if (url && /^(https?):\/\//i.test(url)) {
        mainWindow?.webContents.send("navigate-to", url);
      }
      return { action: "deny" };
    });
    contents.on("will-navigate", (event, url) => {
      if (!/^(https?|about|data|blob):/i.test(url)) {
        event.preventDefault();
      }
    });
    // Canvas fingerprint grain (Brave-Shields style), gated on the Shield.
    contents.on("dom-ready", () => {
      if (security.config.fingerprintProtection) {
        contents.executeJavaScript(GRAIN_JS).catch(() => {});
      }
    });
  }
});

// Hard-fail any webview attach: strip foreign preloads and force the secure
// guest profile, regardless of what the embedder HTML tried to set
// (e.g. index.html's legacy disablewebsecurity / contextIsolation=no).
app.on("will-attach-webview", (_event, webPreferences, _params) => {
  if (webPreferences.preload && webPreferences.preload !== GUEST_PRELOAD) {
    delete webPreferences.preload; // block injected preloads
  }
  if (!webPreferences.preload) webPreferences.preload = GUEST_PRELOAD;
  webPreferences.nodeIntegration = false;
  webPreferences.nodeIntegrationInSubFrames = false;
  webPreferences.contextIsolation = true;
  webPreferences.sandbox = true;
  webPreferences.webSecurity = true;
  webPreferences.spellcheck = false;
});

// ── Custom Protocol (orbit://) ────────────────────────────────────
protocol.registerSchemesAsPrivileged([
  {
    scheme: "orbit",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
    },
  },
]);

app.whenReady().then(() => {
  protocol.handle("orbit", async (request) => {
    // Stream the page from disk over Electron's async net.fetch: the handler
    // never blocks the main process (no sync fs.read) and sets the correct
    // Content-Type per file extension for free.
    let host = "newtab";
    try {
      host = new URL(request.url).hostname || "newtab";
    } catch (_) {
      host = "newtab";
    }
    const file = PAGES[host] || "src/newtab.html";
    try {
      return await net.fetch(
        pathToFileURL(path.join(__dirname, file)).toString()
      );
    } catch (_) {
      return new Response("Not Found", { status: 404 });
    }
  });
});
