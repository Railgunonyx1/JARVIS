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
const stateEl = document.getElementById("jb-state");
const stateText = document.getElementById("jb-state-text");
const stateAction = document.getElementById("jb-state-action");

// Quick actions shown in the empty state — one-click task starters.
const QUICK_ACTIONS = [
  { label: "Summarize", prompt: "Summarize the current page I have open.", icon: "✎" },
  { label: "Explain", prompt: "Explain what the current page is about, simply.", icon: "❔" },
  { label: "Research", prompt: "Research this topic across the web and summarize findings: ", icon: "◎" },
  { label: "Extract", prompt: "Extract the key facts from the current page into a list.", icon: "▤" },
  { label: "Remember", prompt: "Save what's important on this page to memory.", icon: "✦" },
];

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
    thread.appendChild(buildEmptyState());
  }
  for (const m of messages) {
    appendMessage(m.role, m.content, m.kind === "error");
  }
  thread.scrollTop = thread.scrollHeight;
}

function buildEmptyState() {
  const wrap = document.createElement("div");
  wrap.className = "jb-msg jarvis empty";

  const title = document.createElement("div");
  title.className = "jb-empty-title";
  title.textContent = "I'm JARVIS.";
  wrap.appendChild(title);

  const sub = document.createElement("div");
  sub.className = "jb-empty-sub";
  sub.textContent = "Ask me about this page, research a topic, or hand me a task — I'll keep you in control of anything consequential.";
  wrap.appendChild(sub);

  const chips = document.createElement("div");
  chips.className = "jb-quick";
  for (const a of QUICK_ACTIONS) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "jb-quick-chip";
    chip.innerHTML = `<span class="jb-quick-icon" aria-hidden="true">${a.icon}</span><span>${a.label}</span>`;
    chip.addEventListener("click", () => {
      input.value = a.prompt;
      input.focus();
      autoGrow();
      send();
    });
    chips.appendChild(chip);
  }
  wrap.appendChild(chips);
  return wrap;
}

function setAgentState(state, text, actionLabel = "") {
  if (!state) {
    stateEl.hidden = true;
    return;
  }
  stateEl.hidden = false;
  stateEl.dataset.state = state;
  stateText.textContent = text;
  stateAction.hidden = !actionLabel;
  if (actionLabel) {
    stateAction.textContent = actionLabel;
    stateAction.dataset.action = state;
  }
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

  // Agent-layer states ride along on STATUS_UPDATE when the bridge/kernel
  // reports them (waiting_browser / approval / error). Absent, the strip
  // simply stays hidden and the UI keeps the conversation model.
  const agent = status.agent;
  if (agent && typeof agent === "object") {
    if (agent.state === "waiting_browser") {
      setAgentState("waiting_browser", "Waiting for the browser to come back…", "Retry");
    } else if (agent.state === "approval") {
      setAgentState("approval", "JARVIS needs approval for the next step.", "Review");
    } else if (agent.state === "error") {
      setAgentState("error", agent.text || "JARVIS hit an error.", "Retry");
    } else {
      setAgentState("");
    }
  } else if (!online) {
    setAgentState("error", "Bridge offline — browsing keeps working, JARVIS is paused.", "Retry");
  } else {
    setAgentState("");
  }
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

stateAction.addEventListener("click", () => {
  // Retry / review re-probes bridge + kernel status and refreshes the pill.
  setAgentState("");
  sendMessage({ type: Msg.STATUS_REQUEST }).then((res) => updateStatus(res));
});

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
