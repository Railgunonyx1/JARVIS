import { BridgeClient } from "../bridge/bridge-client.js";
import { Msg, STORAGE, BRIDGE } from "../lib/constants.js";
import { onMessage, broadcastType } from "../lib/messaging.js";

async function getBridgeToken() {
  const { [STORAGE.bridgeToken]: token } = await chrome.storage.local.get(STORAGE.bridgeToken);
  return typeof token === "string" && token.trim() ? token.trim() : undefined;
}

async function setBridgeToken(token) {
  const value = typeof token === "string" && token.trim() ? token.trim() : "";
  await chrome.storage.local.set({ [STORAGE.bridgeToken]: value });
  return value || undefined;
}

const bridge = new BridgeClient({ tokenProvider: getBridgeToken });
const liveChats = new Set();
let statusTask = null;
let statusCached = { ok: false, kernel: "offline", checkedAt: 0 };

async function ensureSession() {
  const { [STORAGE.sessionId]: id } = await chrome.storage.local.get(STORAGE.sessionId);
  if (id) return id;
  const next = crypto.randomUUID();
  await chrome.storage.local.set({ [STORAGE.sessionId]: next });
  return next;
}

async function getConversation(sessionId) {
  const { [STORAGE.conversations]: all } = await chrome.storage.local.get(STORAGE.conversations);
  return (all && all[sessionId]) || [];
}

async function saveConversation(sessionId, messages) {
  const { [STORAGE.conversations]: all } = await chrome.storage.local.get(STORAGE.conversations);
  const next = { ...(all || {}), [sessionId]: messages };
  await chrome.storage.local.set({ [STORAGE.conversations]: next });
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab;
}

async function captureActiveTabContext() {
  const tab = await activeTab();
  if (!tab) return { url: "", title: "No active tab", text: "", selection: "" };
  if (tab.url && /^(chrome|edge|chrome-extension|devtools):/i.test(tab.url)) {
    return { url: tab.url, title: tab.title || "Browser page", text: "", selection: "" };
  }
  try {
    const res = await chrome.tabs.sendMessage(tab.id, { type: Msg.CAPTURE_PAGE });
    if (res && res.ok && res.context) return res.context;
  } catch (_) {}
  return { url: tab.url || "", title: tab.title || tab.url || "Page", text: "", selection: "" };
}

async function refreshStatus(force = false) {
  const now = Date.now();
  if (!force && now - statusCached.checkedAt < 3000) return statusCached;
  const s = await bridge.status();
  statusCached = { ...s, checkedAt: now };
  broadcastType(Msg.STATUS_UPDATE, statusCached);
  return statusCached;
}

function startStatusLoop() {
  if (statusTask) return;
  statusTask = setInterval(() => refreshStatus().catch(() => {}), 15000);
}

async function handleChat({ sessionId, messages, page, streamVia, requestId }) {
  if (liveChats.has(sessionId)) {
    return { ok: false, error: "A JARVIS request is already running for this tab." };
  }
  liveChats.add(sessionId);

  const send = (obj) => {
    try {
      chrome.runtime.sendMessage({ type: streamVia || Msg.CHAT_REPLY, payload: obj, requestId, sessionId });
    } catch (_) {}
  };

  send({ kind: "start", requestId, sessionId });

  await bridge.chat({
    sessionId,
    messages,
    page,
    onStart: (p) => send({ kind: "start", ...p }),
    onDelta: (text) => send({ kind: "delta", text }),
    onDone: (p) => send({ kind: "done", ...p }),
    onError: (e) => send({ kind: "error", error: e }),
  });

  liveChats.delete(sessionId);
  return { ok: true };
}

onMessage(async (message) => {
  switch (message?.type) {
    case Msg.TOGGLE: {
      await chrome.sidePanel.open({ windowId: (await chrome.windows.getLastFocused()).id });
      return "opened";
    }
    case Msg.STATUS_REQUEST:
      return refreshStatus(true);
    case Msg.CLEAR_SESSION: {
      const sessionId = await ensureSession();
      await saveConversation(sessionId, []);
      return { ok: true };
    }
    case Msg.CHAT_REQUEST: {
      const sessionId = message.sessionId || (await ensureSession());
      const past = await getConversation(sessionId);
      const userMsg = { role: "user", content: message.text || "", at: Date.now() };
      const next = [...past, userMsg];
      await saveConversation(sessionId, next);

      const context = message.page
        ? message.page
        : await captureActiveTabContext();

      const streamVia = message.streamVia || Msg.CHAT_REPLY;
      handleChat({
        sessionId,
        messages: next,
        page: context,
        streamVia,
        requestId: message.requestId,
      }).catch((e) => {
        try {
          chrome.runtime.sendMessage({
            type: streamVia,
            payload: { kind: "error", error: { message: e?.message || "internal error" } },
            requestId: message.requestId,
            sessionId,
          });
        } catch (_) {}
      });
      return { ok: true, sessionId };
    }
    case Msg.ABORT_REQUEST: {
      bridge.abort(message.sessionId);
      return { ok: true };
    }
    case Msg.CAPTURE_PAGE:
      return captureActiveTabContext();
    case "jb:settings": {
      const token = await setBridgeToken(message.bridgeToken);
      return { ok: true, bridgeToken: token };
    }
    default:
      return undefined;
  }
});

async function ensureContextMenu() {
  try {
    await chrome.contextMenus.removeAll();
    chrome.contextMenus.create({
      id: "jb-ask-selection",
      title: "Ask JARVIS about “%s”",
      contexts: ["selection"],
    });
    chrome.contextMenus.create({
      id: "jb-ask-page",
      title: "Ask JARVIS about this page",
      contexts: ["page"],
    });
  } catch (_) {}
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({ [STORAGE.installState]: true });
  ensureContextMenu();
});

chrome.runtime.onStartup.addListener(() => {
  refreshStatus(true).catch(() => {});
  startStatusLoop();
  ensureContextMenu();
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  try {
    const win = await chrome.windows.getCurrent();
    await chrome.sidePanel.open({ windowId: win.id });
  } catch (_) {}
  const sessionId = await ensureSession();
  const page = await captureActiveTabContext();
  if (info.menuItemId === "jb-ask-selection") {
    page.selection = info.selectionText || page.selection;
  }
  broadcastType(Msg.CAPTURE_PAGE, { sessionId, context: page, prompt: "Ask about the current page" });
});

chrome.action.onClicked.addListener(async () => {
  try {
    const win = await chrome.windows.getCurrent();
    await chrome.sidePanel.open({ windowId: win.id });
  } catch (_) {}
});

chrome.commands.onCommand.addListener(async (command) => {
  if (command === "toggle-sidebar") {
    try {
      const win = await chrome.windows.getCurrent();
      await chrome.sidePanel.open({ windowId: win.id });
    } catch (_) {}
  } else if (command === "listen-to-page") {
    const win = await chrome.windows.getCurrent();
    await chrome.sidePanel.open({ windowId: win.id });
    try {
      const ctx = await captureActiveTabContext();
      if (ctx.selection) {
        broadcastType(Msg.SELECTION, { sessionId: await ensureSession(), text: ctx.selection });
      } else {
        broadcastType(Msg.CAPTURE_PAGE, { sessionId: await ensureSession(), context: ctx });
      }
    } catch (_) {}
  }
});

refreshStatus(true).catch(() => {});
startStatusLoop();

void BRIDGE;
