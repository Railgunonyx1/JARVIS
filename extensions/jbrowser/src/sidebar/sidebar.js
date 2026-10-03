import { Msg, STORAGE } from "../lib/constants.js";
import { sendMessage, onMessage } from "../lib/messaging.js";

/* ── DOM refs (all existing IDs preserved) ──────────────────────── */
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
const matrixEl = document.getElementById("sb-matrix");
const navEl = document.getElementById("sb-nav");
const offlineBanner = document.getElementById("jb-offline-banner");
const retryBtn = document.getElementById("jb-retry");

/* ── 7×7 glyph matrix ──────────────────────────────────────────── */
function initMatrix(el) {
  if (!el || el.childElementCount) return;
  el.innerHTML = Array.from({ length: 49 }, () => "<i></i>").join("");
}
initMatrix(matrixEl);

const STATE_LABELS = {
  idle: "IDLE", thinking: "THINK", planning: "PLAN",
  running: "RUN", ask: "ASK", done: "DONE", fail: "FAIL",
  offline: "OFF", link: "LINK",
};

function setMatrix(state) {
  if (!matrixEl) return;
  matrixEl.dataset.state = state === "thinking" ? "thinking" : state;
}

/* ── Quick actions ──────────────────────────────────────────────── */
const QUICK_ACTIONS = [
  { label: "Summarize", prompt: "Summarize the current page I have open.", icon: "✎" },
  { label: "Explain", prompt: "Explain what the current page is about, simply.", icon: "❔" },
  { label: "Research", prompt: "Research this topic across the web and summarize findings: ", icon: "◎" },
  { label: "Extract", prompt: "Extract the key facts from the current page into a list.", icon: "▤" },
  { label: "Remember", prompt: "Save what's important on this page to memory.", icon: "✦" },
];

/* ── State ──────────────────────────────────────────────────────── */
let sessionId = null;
let messages = [];
let listening = true;
let live = { session: null, text: "", elapsed: 0 };
let lastContext = null;
let activeTab = null;
let activePanel = "jarvis";

/* ── Panels ─────────────────────────────────────────────────────── */
const panels = {
  jarvis: null, // always render from messages
  agents() {
    return `<div class="sb-cards">
      <div class="sb-card"><div class="sb-card-top"><div class="sb-matrix" data-state="idle"></div><h3>Main agent</h3><span class="sb-chip" style="color:var(--jb-mute);border-color:var(--jb-border-subtle)">IDLE</span></div><p>No active task.</p></div>
    </div>`;
  },
  activity() {
    return `<div class="sb-tools">
      <div class="sb-tool"><summary style="display:flex"><span>No activity yet</span></summary></div>
    </div>`;
  },
  memory() {
    return `<div class="sb-card"><h3>Memory</h3><p style="margin-top:4px">Saved sentences and facts appear here.</p></div>`;
  },
};

function renderPanel(name) {
  activePanel = name;
  if (name === "jarvis") {
    render();
    return;
  }
  const html = (panels[name] || panels.jarvis)();
  thread.innerHTML = html;
  thread.querySelectorAll(".sb-matrix").forEach(initMatrix);
  navEl.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.panel === name));
}

navEl.addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (b && b.dataset.panel) renderPanel(b.dataset.panel);
});

/* ── Hydrate ────────────────────────────────────────────────────── */
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

/* ── Render ─────────────────────────────────────────────────────── */
function render() {
  if (activePanel !== "jarvis") return; // don't override agents/activity/memory
  thread.innerHTML = "";
  if (messages.length === 0) {
    thread.appendChild(buildEmptyState());
  } else {
    for (const m of messages) {
      appendMessage(m.role, m.content, m.kind === "error");
    }
  }
  thread.scrollTop = thread.scrollHeight;
  navEl.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.panel === "jarvis"));
}

function buildEmptyState() {
  const wrap = document.createElement("div");
  wrap.className = "sb-empty";

  const title = document.createElement("div");
  title.className = "sb-empty-display";
  title.textContent = "READY";
  wrap.appendChild(title);

  const sub = document.createElement("div");
  sub.className = "sb-empty-sub";
  sub.textContent = "The page stays primary. Invoke JARVIS when you need it.";
  wrap.appendChild(sub);

  for (const a of QUICK_ACTIONS) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "sb-chip";
    chip.textContent = a.label;
    chip.addEventListener("click", () => {
      input.value = a.prompt;
      input.focus();
      autoGrow();
      send();
    });
    wrap.appendChild(chip);
  }

  if (messages.length > 0) {
    const recent = document.createElement("div");
    recent.className = "sb-recent";
    recent.innerHTML = `<div class="sb-recent-title">Recent</div>`;
    const last = messages[messages.length - 1];
    if (last) {
      const row = document.createElement("div");
      row.style.cssText = "border:1px solid var(--jb-border);border-radius:var(--jb-radius-md);background:var(--jb-bg);padding:10px 12px;font-size:var(--jb-text-sm);color:var(--jb-text-secondary)";
      row.textContent = (last.content || "").slice(0, 80);
      recent.appendChild(row);
    }
    wrap.appendChild(recent);
  }

  return wrap;
}

/* ── Agent state strip ──────────────────────────────────────────── */
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

/* ── Messages ───────────────────────────────────────────────────── */
function appendMessage(role, content, isError = false) {
  const el = document.createElement("div");
  el.className = `sb-msg ${role}${isError ? " error" : ""}`;
  const who = document.createElement("div");
  who.className = "who";
  who.textContent = roleLabel(role);
  el.appendChild(who);
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content;
  el.appendChild(bubble);
  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
  return el;
}

function appendDelta(role, content) {
  return appendMessage(role, content);
}

/* ── Page context ───────────────────────────────────────────────── */
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

/* ── Send ───────────────────────────────────────────────────────── */
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
  setMatrix("thinking");

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
      setMatrix("running");
    } else if (p.kind === "delta") {
      live.text += p.text || "";
      liveEl.querySelector(".bubble").textContent = live.text;
      thread.scrollTop = thread.scrollHeight;
    } else if (p.kind === "done") {
      setMatrix("done");
      setTimeout(() => setMatrix("idle"), 2000);
      finish(p);
    } else if (p.kind === "error") {
      setMatrix("fail");
      setTimeout(() => setMatrix("idle"), 2000);
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

/* ── Page bar ───────────────────────────────────────────────────── */
async function refreshPageBar() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) return;
  activeTab = tab;
  pageTitleEl.textContent = tab.title || "New tab";
  pageUrlEl.textContent = tab.url || "";
}

/* ── Status ─────────────────────────────────────────────────────── */
function updateStatus(status) {
  if (!status) return;
  const online = status.ok === true && status.kernel === "online";
  statusDot.className = "sb-dot " + (online ? "online" : "offline");
  statusLabel.textContent = online ? "JARVIS online" : "JARVIS offline";
  offlineBanner.hidden = online;

  if (!online) {
    setMatrix("offline");
  }

  const agent = status.agent;
  if (agent && typeof agent === "object") {
    if (agent.state === "waiting_browser") {
      setAgentState("waiting_browser", "Waiting for the browser to come back…", "Retry");
      setMatrix("link");
    } else if (agent.state === "approval") {
      setAgentState("approval", "JARVIS needs approval for the next step.", "Review");
      setMatrix("ask");
    } else if (agent.state === "error") {
      setAgentState("error", agent.text || "JARVIS hit an error.", "Retry");
      setMatrix("fail");
    } else {
      setAgentState("");
      if (online) setMatrix("idle");
    }
  } else if (!online) {
    setAgentState("error", "Bridge offline — browsing keeps working, JARVIS is paused.", "Retry");
  } else {
    setAgentState("");
    setMatrix("idle");
  }
}

/* ── Settings ───────────────────────────────────────────────────── */
async function loadSettings() {
  const { [STORAGE.bridgeToken]: token } = await chrome.storage.local.get(STORAGE.bridgeToken);
  bridgeTokenInput.value = typeof token === "string" ? token : "";
}
function storeSettings() {
  return sendMessage({ type: "jb:settings", bridgeToken: bridgeTokenInput.value }).catch(() => {});
}

/* ── Events ─────────────────────────────────────────────────────── */
stateAction.addEventListener("click", () => {
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
listenToggle.addEventListener("change", () => { listening = listenToggle.checked; });

clearBtn.addEventListener("click", async () => {
  messages = [];
  await save();
  render();
  sendMessage({ type: Msg.CLEAR_SESSION }).catch(() => {});
});

settingsBtn.addEventListener("click", () => { settingsEl.hidden = !settingsEl.hidden; });
settingsClose.addEventListener("click", () => { settingsEl.hidden = true; });
settingsSave.addEventListener("click", async () => {
  await storeSettings();
  settingsEl.hidden = true;
});

retryBtn?.addEventListener("click", () => {
  sendMessage({ type: Msg.STATUS_REQUEST }).then((res) => updateStatus(res));
});

// Quick action chips from page context
document.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-quick]");
  if (!chip) return;
  const action = chip.dataset.quick;
  const qa = QUICK_ACTIONS.find(a => a.label.toLowerCase() === action);
  if (qa) {
    input.value = qa.prompt;
    input.focus();
    autoGrow();
    send();
  }
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

/* ── Init ───────────────────────────────────────────────────────── */
input.focus();
hydrate().then(() => {
  refreshPageBar();
  sendMessage({ type: Msg.STATUS_REQUEST }).then((res) => updateStatus(res));
  loadSettings();
});
