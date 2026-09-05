import { Msg, STORAGE } from "../lib/constants.js";
import { sendMessage, onMessage } from "../lib/messaging.js";

const thread = document.getElementById("jb-thread");
const input = document.getElementById("jb-input");
const sendBtn = document.getElementById("jb-send");
const statusDot = document.getElementById("jb-status-dot");
const statusLabel = document.getElementById("jb-status-label");
const pageTitleEl = document.getElementById("jb-page-title");
const pageUrlEl = document.getElementById("jb-page-url");
const listenToggle = document.getElementById("jb-listen");
const clearBtn = document.getElementById("jb-clear");
const settingsEl = document.getElementById("jb-settings");
const settingsBtn = document.getElementById("jb-toggle-control");
const settingsClose = document.getElementById("jb-settings-close");
const settingsSave = document.getElementById("jb-settings-save");
const bridgeTokenInput = document.getElementById("jb-bridge-token");

let sessionId = null;
let messages = [];
let listening = true;
let live = { session: null, text: "", elapsed: 0 };
let lastContext = null;
let activeTab = null;

async function hydrate() {
  const { [STORAGE.sessionId]: sid } = await chrome.storage.local.get(STORAGE.sessionId);
  sessionId = sid || crypto.randomUUID();
  if (!sid) await chrome.storage.local.set({ [STORAGE.sessionId]: sessionId });
  const { [STORAGE.conversations]: all } = await chrome.storage.local.get(STORAGE.conversations);
  messages = (all && all[sessionId]) || [];
  render();
}

function roleLabel(role) {
  return role === "user" ? "You" : "JARVIS";
}

function render() {
  thread.innerHTML = "";
  if (messages.length === 0) {
    const empty = document.createElement("div");
    empty.className = "jb-msg jarvis empty";
    empty.textContent = "I'm JARVIS. Ask me about this page, or give me a task.";
    thread.appendChild(empty);
  }
  for (const m of messages) {
    appendMessage(m.role, m.content, m.kind === "error");
  }
  thread.scrollTop = thread.scrollHeight;
}

function appendMessage(role, content, isError = false) {
  const el = document.createElement("div");
  el.className = `jb-msg ${role}${isError ? " error" : ""}`;
  const r = document.createElement("span");
  r.className = "jb-role";
  r.textContent = roleLabel(role);
  el.appendChild(r);
  const body = document.createElement("span");
  body.textContent = content;
  el.appendChild(body);
  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
  return el;
}

function appendDelta(role, content) {
  const el = document.createElement("div");
  el.className = `jb-msg ${role}`;
  const r = document.createElement("span");
  r.className = "jb-role";
  r.textContent = roleLabel(role);
  el.appendChild(r);
  const body = document.createElement("span");
  body.textContent = content;
  el.appendChild(body);
  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
  return el;
}

async function currentPageContext() {
  if (!listening) {
    return { url: activeTab?.url || "", title: activeTab?.title || "", text: "", selection: "" };
  }
  try {
    const res = await sendMessage({ type: Msg.CAPTURE_PAGE });
    if (res && res.ok) {
      lastContext = res.result;
      return res.result;
    }
  } catch (_) {}
  if (lastContext) return lastContext;
  return { url: activeTab?.url || "", title: activeTab?.title || "", text: "", selection: "" };
}

async function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  autoGrow();
  listening = false;
  listenToggle.checked = false;

  messages.push({ role: "user", content: text, at: Date.now() });
  messages.push({ role: "unsent", content: "", at: Date.now() });
  await save();
  render();

  const page = await currentPageContext();
  const requestId = crypto.randomUUID();

  live = { session: sessionId, requestId, text: "" };
  const liveEl = appendDelta("jarvis", "");

  sendMessage({
    type: Msg.CHAT_REQUEST,
    sessionId,
    text,
    page,
    streamVia: Msg.CHAT_REPLY,
    requestId,
  });

  onMessage((message) => {
    if (message?.type !== Msg.CHAT_REPLY || message.requestId !== requestId) return;
    const p = message.payload || {};
    if (p.kind === "start") {
      sendBtn.disabled = true;
    } else if (p.kind === "delta") {
      live.text += p.text || "";
      liveEl.querySelector("span:last-child").textContent = live.text;
      thread.scrollTop = thread.scrollHeight;
    } else if (p.kind === "done") {
      finish(p);
    } else if (p.kind === "error") {
      finish({ error: true, message: p.error?.message || "JARVIS error" });
    }
    return undefined;
  });
}

function finish({ error = false, message = "" } = {}) {
  if (live.text || error) {
    const content = error ? message : live.text;
    messages.pop();
    messages.push({ role: "jarvis", content, at: Date.now(), kind: error ? "error" : undefined });
  }
  live = { session: null, requestId: null, text: "" };
  sendBtn.disabled = false;
  if (!error) {
    listening = true;
    listenToggle.checked = true;
  }
  save().then(render);
}

async function save() {
  const { [STORAGE.conversations]: all } = await chrome.storage.local.get(STORAGE.conversations);
  const next = { ...(all || {}), [sessionId]: messages };
  await chrome.storage.local.set({ [STORAGE.conversations]: next });
}

function autoGrow() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 120) + "px";
}

async function refreshPageBar() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) return;
  activeTab = tab;
  pageTitleEl.textContent = tab.title || "New tab";
  pageUrlEl.textContent = tab.url || "";
}

function updateStatus(status) {
  if (!status) return;
  const online = status.ok === true && status.kernel === "online";
  statusDot.className = "jb-dot " + (online ? "online" : "offline");
  statusLabel.textContent = online ? "JARVIS online" : "JARVIS offline";
}

async function loadSettings() {
  const { [STORAGE.bridgeToken]: token } = await chrome.storage.local.get(STORAGE.bridgeToken);
  bridgeTokenInput.value = typeof token === "string" ? token : "";
}

function storeSettings() {
  return sendMessage({ type: "jb:settings", bridgeToken: bridgeTokenInput.value }).catch(
    () => {}
  );
}

sendBtn.addEventListener("click", send);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    send();
  }
  autoGrow();
});
input.addEventListener("input", autoGrow);
listenToggle.addEventListener("change", () => {
  listening = listenToggle.checked;
});
clearBtn.addEventListener("click", async () => {
  messages = [];
  await save();
  render();
  sendMessage({ type: Msg.CLEAR_SESSION }).catch(() => {});
});

settingsBtn.addEventListener("click", () => {
  settingsEl.hidden = !settingsEl.hidden;
});
settingsClose.addEventListener("click", () => {
  settingsEl.hidden = true;
});
settingsSave.addEventListener("click", async () => {
  await storeSettings();
  settingsEl.hidden = true;
});

chrome.tabs.onActivated.addListener(refreshPageBar);
chrome.tabs.onUpdated.addListener((_id, info) => {
  if (info.status === "complete") refreshPageBar();
});

onMessage((message) => {
  if (message?.type === Msg.STATUS_UPDATE) {
    updateStatus(message.payload);
  }
  return undefined;
});

input.focus();
hydrate().then(() => {
  refreshPageBar();
  sendMessage({ type: Msg.STATUS_REQUEST }).then((res) => updateStatus(res));
  loadSettings();
});
