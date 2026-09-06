/**
 * JARVIS Orbit — Renderer Process
 *
 * Manages the browser UI: tabs, omnibox, sidebar, and JARVIS communication.
 * All JARVIS IPC goes through the preload bridge (window.orbit).
 */

// ── DOM Refs ──────────────────────────────────────────────────────
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const tabStrip = $("#tabStrip");
const newTabBtn = $("#newTabBtn");
const webview = $("#webview");
const internalPages = $("#internalPages");
const newtabPage = $("#newtabPage");
const omnibox = $("#omnibox");
const omniInput = $("#omniInput");
const backBtn = $("#backBtn");
const forwardBtn = $("#forwardBtn");
const reloadBtn = $("#reloadBtn");
const jarvisBtn = $("#jarvisBtn");
const sidebar = $("#sidebar");
const sbClose = $("#sbClose");
const sbBody = $("#sbBody");
const sbInput = $("#sbInput");
const sbSend = $("#sbSend");
const sbNav = $("#sbNav");
const sbMatrix = $("#sbMatrix");
const sbDot = $("#sbDot");
const sbStateLabel = $("#sbStateLabel");
const sbPageTitle = $("#sbPageTitle");
const statusDot = $("#statusDot");
const statusLabel = $("#statusLabel");
const floatGlyph = $("#floatGlyph");
const floatMatrix = $("#floatMatrix");
const floatTitle = $("#floatTitle");
const modalBg = $("#modalBg");
const modalDeny = $("#modalDeny");
const modalAllowOnce = $("#modalAllowOnce");
const modalAllowSite = $("#modalAllowSite");

// ── State ─────────────────────────────────────────────────────────
let tabs = new Map();
let activeTabId = null;
let sidebarOpen = true;
let jarvisOnline = false;
let agentState = "idle";

// ── Matrix Renderer ───────────────────────────────────────────────
function initMatrix(el) {
  if (!el || el.childElementCount) return;
  el.innerHTML = Array.from({ length: 49 }, () => "<i></i>").join("");
}

function setMatrix(state) {
  agentState = state;
  sbMatrix.dataset.state = state;
  const label = {
    idle: "IDLE", thinking: "THINK", planning: "PLAN",
    running: "RUN", ask: "ASK", done: "DONE", fail: "FAIL",
    offline: "OFF", link: "LINK",
  }[state] || state.toUpperCase();
  sbStateLabel.textContent = jarvisOnline ? label : "OFF";

  // Sync floating glyph
  const running = ["thinking", "planning", "running", "ask"].includes(state);
  floatGlyph.classList.toggle("show", running && !sidebarOpen && jarvisOnline);
  floatTitle.textContent = state === "ask" ? "Approval needed" : "Researching";
  if (floatMatrix) floatMatrix.dataset.state = state === "ask" ? "ask" : "running";
}

// ── Tab Management ────────────────────────────────────────────────
function renderTabs() {
  tabStrip.innerHTML = "";
  for (const [id, tab] of tabs) {
    const el = document.createElement("button");
    el.className = `tab ${id === activeTabId ? "active" : ""} ${tab.agentOwned ? "agent-owned" : ""}`;
    el.dataset.id = id;
    el.title = tab.title;

    if (tab.agentOwned) {
      el.innerHTML = `
        <span class="tab-glyph"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></span>
        <span class="tab-title">${escapeHtml(tab.title)}</span>
        <span class="tab-close" data-close="${id}">×</span>
      `;
    } else {
      el.innerHTML = `
        <span class="tab-fav">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <circle cx="6" cy="6" r="4.5" stroke="currentColor"/>
          </svg>
        </span>
        <span class="tab-title">${escapeHtml(tab.title)}</span>
        <span class="tab-close" data-close="${id}">×</span>
      `;
    }

    // Click handlers
    el.addEventListener("click", (e) => {
      const closeBtn = e.target.closest("[data-close]");
      if (closeBtn) {
        e.stopPropagation();
        closeTab(closeBtn.dataset.close);
        return;
      }
      activateTab(id);
    });

    tabStrip.appendChild(el);
  }
}

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
  activateTab(id);
  return id;
}

function closeTab(id) {
  if (tabs.size <= 1) return; // Keep at least one tab
  tabs.delete(id);
  if (activeTabId === id) {
    const remaining = Array.from(tabs.keys());
    activateTab(remaining[remaining.length - 1]);
  }
  renderTabs();
}

function activateTab(id) {
  activeTabId = id;
  const tab = tabs.get(id);
  if (!tab) return;

  renderTabs();
  navigateTo(tab.url);
  sbPageTitle.textContent = tab.title;
}

// ── Navigation ────────────────────────────────────────────────────
// Map orbit:// URLs to page element IDs
const INTERNAL_PAGES = {
  "orbit://newtab": "newtabPage",
  "orbit://settings": "settingsPage",
  "orbit://history": "historyPage",
  "orbit://bookmarks": "bookmarksPage",
  "orbit://downloads": "downloadsPage",
  "orbit://tasks": "tasksPage",
  "orbit://permissions": "permissionsPage",
  "orbit://memory": "memoryPage",
  "orbit://extensions": "extensionsPage",
  "orbit://diagnostics": "diagnosticsPage",
};

function showInternalPage(pageId) {
  // Hide all pages, show the target
  $$(".page", internalPages).forEach(p => p.classList.remove("on"));
  const target = document.getElementById(pageId);
  if (target) target.classList.add("on");
}

function navigateTo(url) {
  const tab = tabs.get(activeTabId);
  if (!tab) return;

  tab.url = url;

  if (url.startsWith("orbit://")) {
    // Internal page — clear omnibox
    omniInput.value = "";
    omniInput.placeholder = url.replace("orbit://", "orbit://");
    webview.classList.add("hidden");
    internalPages.classList.add("visible");
    const pageId = INTERNAL_PAGES[url];
    if (pageId) {
      showInternalPage(pageId);
    } else {
      showInternalPage("newtabPage");
    }
  } else {
    // External page — show URL
    omniInput.value = url.replace(/^https?:\/\//, "");
    omniInput.placeholder = "Search or enter URL";
    webview.classList.remove("hidden");
    internalPages.classList.remove("visible");
    webview.loadURL(url);
  }

  backBtn.disabled = !webview.canGoBack();
  forwardBtn.disabled = !webview.canGoForward();
}

// ── Omnibox ───────────────────────────────────────────────────────
omniInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const value = omniInput.value.trim();
    if (!value) return;

    // Determine if it's a URL or search query
    let url;
    if (value.match(/^https?:\/\//)) {
      url = value;
    } else if (value.match(/^[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}/)) {
      url = `https://${value}`;
    } else {
      url = `https://www.google.com/search?q=${encodeURIComponent(value)}`;
    }

    navigateTo(url);
    omniInput.blur();
  }
});

// ── Navigation Buttons ────────────────────────────────────────────
backBtn.addEventListener("click", () => {
  if (webview.canGoBack()) webview.goBack();
});

forwardBtn.addEventListener("click", () => {
  if (webview.canGoForward()) webview.goForward();
});

reloadBtn.addEventListener("click", () => {
  webview.reload();
});

// ── New Tab ───────────────────────────────────────────────────────
newTabBtn.addEventListener("click", () => createTab());

// ── Sidebar Toggle ────────────────────────────────────────────────
jarvisBtn.addEventListener("click", () => {
  sidebarOpen = !sidebarOpen;
  sidebar.classList.toggle("hidden", !sidebarOpen);
  jarvisBtn.classList.toggle("active", sidebarOpen);
  setMatrix(agentState);
});

sbClose.addEventListener("click", () => {
  sidebarOpen = false;
  sidebar.classList.add("hidden");
  jarvisBtn.classList.remove("active");
  setMatrix(agentState);
});

floatGlyph.addEventListener("click", () => {
  sidebarOpen = true;
  sidebar.classList.remove("hidden");
  jarvisBtn.classList.add("active");
  setMatrix(agentState);
});

// ── Sidebar Navigation ────────────────────────────────────────────
sbNav.addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (btn?.dataset.panel) {
    sbNav.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === btn));
    renderPanel(btn.dataset.panel);
  }
});

function renderPanel(name) {
  if (name === "jarvis") {
    sbBody.innerHTML = `
      <div style="padding:24px 8px;color:var(--jb-mute)">
        <div style="font-family:var(--jb-font-display);font-size:22px;letter-spacing:.1em;color:var(--jb-paper);margin-bottom:8px">
          ${jarvisOnline ? "READY" : "OFF"}
        </div>
        <div style="color:var(--jb-mute)">
          ${jarvisOnline
            ? "The page stays primary. Invoke JARVIS when you need it."
            : "JARVIS is offline. Browse normally."
          }
        </div>
      </div>
    `;
  } else if (name === "agents") {
    sbBody.innerHTML = `
      <div style="padding:12px;color:var(--jb-mute)">
        <div style="border:1px solid var(--jb-border);border-radius:12px;padding:12px;background:var(--jb-void);margin-bottom:8px">
          <div style="display:flex;align-items:center;gap:8px">
            <div class="sb-matrix" data-state="idle"></div>
            <h3 style="font-size:13px;color:var(--jb-paper);font-weight:500">Main agent</h3>
          </div>
          <p style="color:var(--jb-mute);font-size:12px;margin-top:6px">No active task</p>
        </div>
      </div>
    `;
    sbBody.querySelectorAll(".sb-matrix").forEach(initMatrix);
  }
}

// ── Composer ──────────────────────────────────────────────────────
sbSend.addEventListener("click", sendToJarvis);
sbInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    sendToJarvis();
  }
});

async function sendToJarvis() {
  const text = sbInput.value.trim();
  if (!text) return;
  sbInput.value = "";

  // Add user message to sidebar
  appendMessage("user", text);

  // Send to JARVIS backend
  if (window.orbit?.jarvis) {
    setMatrix("thinking");
    window.orbit.jarvis.chat(text, "orbit-session");
  }
}

function appendMessage(role, content) {
  const msg = document.createElement("div");
  msg.style.cssText = "margin:0 0 14px";
  msg.innerHTML = `
    <div style="font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--jb-ghost);margin-bottom:4px">
      ${role === "user" ? "You" : "JARVIS"}
    </div>
    <div style="color:${role === "user" ? "var(--jb-paper)" : "var(--jb-text)"}">${escapeHtml(content)}</div>
  `;
  sbBody.appendChild(msg);
  sbBody.scrollTop = sbBody.scrollHeight;
}

// ── JARVIS Events ─────────────────────────────────────────────────
if (window.orbit?.jarvis) {
  window.orbit.jarvis.onStatus((status) => {
    jarvisOnline = status.ok && status.kernel === "online";
    statusDot.className = `status-dot ${jarvisOnline ? "online" : "offline"}`;
    statusLabel.textContent = jarvisOnline ? "ONLINE" : "OFF";
    sbDot.className = `sb-dot ${jarvisOnline ? "online" : "offline"}`;
    setMatrix(jarvisOnline ? "idle" : "offline");
  });

  window.orbit.jarvis.onChat((payload) => {
    if (payload.kind === "delta") {
      // Stream response
    } else if (payload.kind === "done") {
      appendMessage("jarvis", payload.text || "(no response)");
      setMatrix("done");
      setTimeout(() => setMatrix("idle"), 2000);
    } else if (payload.kind === "error") {
      appendMessage("error", payload.error?.message || "JARVIS error");
      setMatrix("fail");
      setTimeout(() => setMatrix("idle"), 2000);
    }
  });

  window.orbit.jarvis.onAgentEvent((event) => {
    if (event.state) setMatrix(event.state);
  });

  window.orbit.jarvis.onApproval((request) => {
    showApprovalModal(request);
  });
}

// ── Approval Modal ────────────────────────────────────────────────
function showApprovalModal(request) {
  setMatrix("ask");
  modalBg.classList.add("on");

  const title = $("#modalTitle");
  const desc = $("#modalDesc");
  const kv = $("#modalKv");

  title.textContent = request.title || "JARVIS wants to take an action";
  desc.textContent = request.description || "This action requires your approval.";

  kv.innerHTML = "";
  if (request.details) {
    for (const [key, value] of Object.entries(request.details)) {
      kv.innerHTML += `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`;
    }
  }
}

modalDeny.addEventListener("click", () => {
  modalBg.classList.remove("on");
  setMatrix("done");
  setTimeout(() => setMatrix("idle"), 2000);
});

modalAllowOnce.addEventListener("click", () => {
  modalBg.classList.remove("on");
  setMatrix("running");
});

modalAllowSite.addEventListener("click", () => {
  modalBg.classList.remove("on");
  setMatrix("running");
});

modalBg.addEventListener("click", (e) => {
  if (e.target === modalBg) modalBg.classList.remove("on");
});

// ── Webview Events ────────────────────────────────────────────────
webview.addEventListener("did-fail-load", (e) => {
  console.error("[Webview] Load failed:", e.errorCode, e.errorDescription);
});

webview.addEventListener("did-finish-load", () => {
  console.log("[Webview] Loaded:", webview.getURL());
});
webview.addEventListener("did-navigate", (e) => {
  const tab = tabs.get(activeTabId);
  if (tab) {
    tab.url = e.url;
    omniInput.value = e.url.replace(/^https?:\/\//, "");
  }
});

webview.addEventListener("page-title-updated", (e) => {
  const tab = tabs.get(activeTabId);
  if (tab) {
    tab.title = e.title;
    renderTabs();
    sbPageTitle.textContent = e.title;
  }
});

webview.addEventListener("did-start-loading", () => {
  reloadBtn.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.4"/>
    </svg>
  `;
});

webview.addEventListener("did-stop-loading", () => {
  reloadBtn.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M3 8a5 5 0 019-2.5M13 8a5 5 0 01-9 2.5" stroke="currentColor" stroke-width="1.4"/>
      <path d="M12 2.5V5.5H9" stroke="currentColor" stroke-width="1.4"/>
    </svg>
  `;
});

// ── New Tab Tiles ────────────────────────────────────────────────
document.addEventListener("click", (e) => {
  const tile = e.target.closest("[data-url]");
  if (tile) {
    navigateTo(tile.dataset.url);
  }
});

// ── Theme Toggle ─────────────────────────────────────────────────
const themeToggle = $("#themeToggle");
if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const html = document.documentElement;
    const current = html.dataset.theme || "dark";
    html.dataset.theme = current === "dark" ? "light" : "dark";
    themeToggle.textContent = current === "dark" ? "Toggle dark" : "Toggle light";
  });
}

// ── NTP Search ───────────────────────────────────────────────────
const ntpSearch = $("#ntpSearch");
if (ntpSearch) {
  ntpSearch.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const value = ntpSearch.value.trim();
      if (!value) return;
      let url;
      if (value.match(/^https?:\/\//)) {
        url = value;
      } else if (value.match(/^[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}/)) {
        url = `https://${value}`;
      } else {
        url = `https://www.google.com/search?q=${encodeURIComponent(value)}`;
      }
      navigateTo(url);
    }
  });
}

// ── Keyboard Shortcuts ────────────────────────────────────────────
document.addEventListener("keydown", (e) => {
  // Ctrl+T: New tab
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "t") {
    e.preventDefault();
    createTab();
  }
  // Ctrl+W: Close tab
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "w") {
    e.preventDefault();
    if (activeTabId) closeTab(activeTabId);
  }
  // Ctrl+L: Focus omnibox
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "l") {
    e.preventDefault();
    omniInput.focus();
    omniInput.select();
  }
  // Ctrl+Shift+J: Toggle sidebar
  if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "j") {
    e.preventDefault();
    jarvisBtn.click();
  }
  // Escape: Close modal
  if (e.key === "Escape") {
    modalBg.classList.remove("on");
  }
});

// ── Utility ───────────────────────────────────────────────────────
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ── Init ──────────────────────────────────────────────────────────
initMatrix(sbMatrix);
initMatrix(floatMatrix);
createTab("orbit://newtab");
setMatrix("idle");
