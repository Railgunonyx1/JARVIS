/**
 * JARVIS Orbit — Electron Main Process
 *
 * A custom Chromium browser with native JARVIS intelligence.
 * NOT an extension — a standalone browser built on Electron (Chromium).
 */

const { app, BrowserWindow, ipcMain, session, protocol } = require("electron");
const path = require("path");
const WebSocket = require("ws");

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

// ── State ─────────────────────────────────────────────────────────
let mainWindow = null;
let jarvisWs = null;
let jarvisStatus = { ok: false, kernel: "offline" };

// ── Tab Management ────────────────────────────────────────────────
const tabs = new Map();
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

  // Notify renderer
  mainWindow?.webContents.send("tab-created", tabs.get(id));
  return id;
}

function closeTab(id) {
  tabs.delete(id);
  mainWindow?.webContents.send("tab-closed", id);
}

function setActiveTab(id) {
  activeTabId = id;
  const tab = tabs.get(id);
  if (tab) {
    mainWindow?.webContents.send("tab-activated", tab);
  }
}

// ── JARVIS WebSocket Connection ───────────────────────────────────
function connectJarvis() {
  if (jarvisWs?.readyState === WebSocket.OPEN) return;

  try {
    jarvisWs = new WebSocket(CONFIG.JARVIS_WS_URL);

    jarvisWs.on("open", () => {
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
      // Reconnect after 3 seconds
      setTimeout(connectJarvis, 3000);
    });

    jarvisWs.on("error", (err) => {
      console.error("[JARVIS] Error:", err.message);
    });
  } catch (e) {
    console.error("[JARVIS] Connection failed:", e.message);
    setTimeout(connectJarvis, 3000);
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

// ── IPC Handlers ──────────────────────────────────────────────────
function setupIPC() {
  // Tab management
  ipcMain.handle("tab:create", (_, url) => createTab(url));
  ipcMain.handle("tab:close", (_, id) => closeTab(id));
  ipcMain.handle("tab:activate", (_, id) => setActiveTab(id));
  ipcMain.handle("tab:list", () => Array.from(tabs.values()));

  // JARVIS communication
  ipcMain.handle("jarvis:status", () => jarvisStatus);
  ipcMain.handle("jarvis:send", (_, msg) => sendToJarvis(msg));
  ipcMain.handle("jarvis:chat", (_, text, sessionId) => {
    sendToJarvis({
      type: "chat_request",
      payload: { text, sessionId },
    });
  });

  // Navigation
  ipcMain.handle("navigate", (_, url) => {
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
    titleBarOverlay: {
      color: "#000000",
      symbolColor: "#999999",
      height: 40,
    },
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      webviewTag: true,
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

  // Connect to JARVIS
  connectJarvis();

  // Create initial tab
  createTab("orbit://newtab");

  mainWindow.on("closed", () => {
    mainWindow = null;
    jarvisWs?.close();
  });
}

// ── App Lifecycle ─────────────────────────────────────────────────
app.whenReady().then(() => {
  setupIPC();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  jarvisWs?.close();
  if (process.platform !== "darwin") {
    app.quit();
  }
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
  protocol.handle("orbit", (request) => {
    const url = request.url.replace("orbit://", "");
    // Route internal pages
    const pages = {
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
    const file = pages[url] || "src/newtab.html";
    return new Response(
      require("fs").readFileSync(path.join(__dirname, file)),
      {
        headers: { "Content-Type": "text/html" },
      }
    );
  });
});
