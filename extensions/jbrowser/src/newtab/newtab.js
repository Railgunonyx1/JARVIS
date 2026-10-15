import { STORAGE } from "../lib/constants.js";
import { sendMessage, onMessage } from "../lib/messaging.js";

/* ── DOM refs (all existing IDs preserved) ──────────────────────── */
const input = document.getElementById("nt-input");
const btn = document.getElementById("nt-btn");
const dot = document.getElementById("nt-dot");
const statusEl = document.getElementById("nt-status");
const thread = document.getElementById("nt-thread");
const quickEl = document.getElementById("nt-quick");
const chipsEl = document.getElementById("nt-chips");

const AGENT_ACTIONS = [
  { label: "Summarize the current tab", prompt: "Summarize the current page I have open." },
  { label: "Explain a topic", prompt: "Explain this topic clearly, with examples: " },
  { label: "Research across the web", prompt: "Research this and return a short briefing with sources: " },
  { label: "Remember for later", prompt: "Save what's important on the current page to my memory." },
  { label: "Run an autonomous agent", prompt: "Start an autonomous agent session to carry out a task. I'll approve consequential actions as it goes." },
];

let sessionId = null;
let conversations = {};

/* ── Greeting ───────────────────────────────────────────────────── */
function hourGreeting() {
  const h = new Date().getHours();
  if (h < 5) return "Working late?";
  if (h < 12) return "Good morning.";
  if (h < 18) return "Good afternoon.";
  return "Good evening.";
}

/* ── Messages ───────────────────────────────────────────────────── */
function appendMsg(role, content, isError = false) {
  const el = document.createElement("div");
  el.className = `nt-msg ${role}${isError ? " error" : ""}`;
  el.textContent = content;
  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
  return el;
}

/* ── Session ────────────────────────────────────────────────────── */
async function ensureSession() {
  const { [STORAGE.sessionId]: sid } = await chrome.storage.local.get(STORAGE.sessionId);
  sessionId = sid || crypto.randomUUID();
  if (!sid) await chrome.storage.local.set({ [STORAGE.sessionId]: sessionId });
  const { [STORAGE.conversations]: all } = await chrome.storage.local.get(STORAGE.conversations);
  conversations = all || {};
}

/* ── Send ───────────────────────────────────────────────────────── */
function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";

  const messages = (conversations[sessionId] || []).concat({
    role: "user",
    content: text,
    at: Date.now(),
  });

  appendMsg("user", text);
  const live = appendMsg("jarvis", "");
  let acc = "";
  const requestId = crypto.randomUUID();

  sendMessage({ type: "CHAT_REQUEST", sessionId, text, streamVia: "CHAT_REPLY", requestId });

  onMessage((message) => {
    if (message?.type !== "CHAT_REPLY" || message.requestId !== requestId) return;
    const p = message.payload || {};
    if (p.kind === "delta") {
      acc += p.text || "";
      live.textContent = acc;
    } else if (p.kind === "done") {
      conversations[sessionId] = [...messages, { role: "jarvis", content: acc || "", at: Date.now() }];
      chrome.storage.local.set({ [STORAGE.conversations]: conversations });
    } else if (p.kind === "error") {
      live.textContent = p.error?.message || "JARVIS error";
      live.classList.add("error");
    }
    return undefined;
  });
}

/* ── Status ─────────────────────────────────────────────────────── */
async function refreshStatus() {
  try {
    const res = await sendMessage({ type: "STATUS_REQUEST" });
    const online = res && res.ok === true && res.kernel === "online";
    dot.className = "nt-dot " + (online ? "online" : "offline");
    statusEl.textContent = online ? "JARVIS online" : "JARVIS offline";
  } catch (_) {
    dot.className = "nt-dot offline";
    statusEl.textContent = "JARVIS offline";
  }
}

/* ── Agent chips ────────────────────────────────────────────────── */
function buildChips() {
  for (const a of AGENT_ACTIONS) {
    const chip = document.createElement("button");
    chip.className = "nt-chip";
    chip.textContent = a.label;
    chip.addEventListener("click", () => {
      input.value = a.prompt;
      send();
    });
    chipsEl.appendChild(chip);
  }
  quickEl.hidden = false;
}

/* ── Sidebar toggle ─────────────────────────────────────────────── */
const sidebarBtn = document.getElementById("nt-sidebar");
if (sidebarBtn) {
  sidebarBtn.addEventListener("click", () => sendMessage({ type: "TOGGLE" }));
}

/* ── Tile navigation (open internal pages in sidebar) ───────────── */
document.addEventListener("click", (e) => {
  const tile = e.target.closest("[data-go]");
  if (tile) {
    // Signal the service worker to navigate or open the view
    sendMessage({ type: "NAVIGATE", view: tile.dataset.go }).catch(() => {});
  }
});

/* ── Events ─────────────────────────────────────────────────────── */
btn.addEventListener("click", send);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

onMessage((message) => {
  if (message?.type === "STATUS_UPDATE") {
    const online = message.payload && message.payload.kernel === "online";
    dot.className = "nt-dot " + (online ? "online" : "offline");
    statusEl.textContent = online ? "JARVIS online" : "JARVIS offline";
  }
  return undefined;
});

/* ── Init ───────────────────────────────────────────────────────── */
document.querySelector(".nt-wordmark").textContent = "ORBIT";
document.querySelector(".nt-sub").textContent = "Search or ask JARVIS";
buildChips();
ensureSession().then(refreshStatus);
input.focus();
