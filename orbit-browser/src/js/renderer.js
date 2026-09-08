/**
 * JARVIS Orbit — Renderer Process (Complete)
 * 
 * Manages browser UI: tabs, omnibox, sidebar, JARVIS communication.
 * All JARVIS IPC goes through preload bridge (window.orbit).
 * Features merged: Command Palette, Zoom, Bookmarks, Toast, Sessions, HUD, Vertical Tabs, Print/Screenshot
 */

// ── Error Boundary ──────────────────────────────────────────────
window.addEventListener('error', (e) => {
  console.error('[ORBIT] Unhandled error:', e.message, e.filename, e.lineno);
  if (window.showToast) showToast('err', 'Error', e.message);
});
window.addEventListener('unhandledrejection', (e) => {
  console.error('[ORBIT] Unhandled rejection:', e.reason);
});

// ── DOM Refs ──────────────────────────────────────────────────
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const tabStrip = $("#tabStrip");
const newTabBtn = $("#newTabBtn");
const webview = $("#webview");
const contentArea = $("#contentArea");
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
const bookmarkBar = $("#bookmarkBar");
const cmdPaletteBg = $("#cmdPaletteBg");
const cmdInput = $("#cmdInput");
const cmdResults = $("#cmdResults");
const toastContainer = $("#toastContainer");
const perfHud = $("#perfHud");
const findBar = $("#findBar");
const findInput = $("#findInput");
const tabStripVertical = $("#tabStripVertical");
const omniStar = $("#omniStar");
const zoomIndicator = $("#zoomIndicator");
const sessionBanner = $("#sessionBanner");
const emptyTabs = $("#emptyTabs");
const emptyNewTabBtn = $("#emptyNewTab");

// ── State ─────────────────────────────────────────────────────
let tabs = new Map();
window._orbitTabs = tabs; // Expose for thumbnail/vision modules
let activeTabId = null;
let sidebarOpen = true;
let jarvisOnline = false;
let agentState = "idle";
let bookmarks = JSON.parse(localStorage.getItem("orbit-bookmarks") || "[]");
let zoomLevels = JSON.parse(localStorage.getItem("orbit-zoom") || "{}");
let currentZoom = 1.0;
let _navigating = false; // guard: true while navigateTo is executing

// ── Toast Notifications ───────────────────────────────────────
function showToast(type, title, msg, dur) {
  dur = dur || 4000;
  const icons = { ok: "\u2713", warn: "\u26a0", err: "\u2717", info: "\u2139" };
  const t = document.createElement("div");
  t.className = "toast";
  let html = '<div class="toast-icon ' + type + '">' + (icons[type] || "") + '</div>';
  html += '<div class="toast-body"><div class="toast-title">' + title + '</div>';
  if (msg) html += '<div class="toast-msg">' + msg + '</div>';
  html += '</div><button class="toast-close">\u00d7</button>';
  t.innerHTML = html;
  if (toastContainer) toastContainer.appendChild(t);
  const closeBtn = t.querySelector(".toast-close");
  if (closeBtn) closeBtn.onclick = function() { t.classList.add("out"); setTimeout(function() { t.remove(); }, 200); };
  setTimeout(function() { t.classList.add("out"); setTimeout(function() { t.remove(); }, 200); }, dur);
}

// ── Matrix Renderer ───────────────────────────────────────────
function initMatrix(el) {
  if (!el || el.childElementCount) return;
  el.innerHTML = Array.from({ length: 49 }, () => "<i></i>").join("");
}

function setMatrix(state) {
  agentState = state;
  if (sbMatrix) sbMatrix.dataset.state = state;
  const label = {
    idle: "IDLE", thinking: "THINK", planning: "PLAN",
    running: "RUN", ask: "ASK", done: "DONE", fail: "FAIL",
    offline: "OFF", link: "LINK",
  }[state] || state.toUpperCase();
  if (sbStateLabel) sbStateLabel.textContent = jarvisOnline ? label : "OFF";
  const running = ["thinking", "planning", "running", "ask"].includes(state);
  if (floatGlyph) floatGlyph.classList.toggle("show", running && !sidebarOpen && jarvisOnline);
  if (floatTitle) floatTitle.textContent = state === "ask" ? "Approval needed" : "Researching";
  if (floatMatrix) floatMatrix.dataset.state = state === "ask" ? "ask" : "running";
}

// ── Reopen Closed Tab (Chrome-style Ctrl+Shift+T) ─────────────
const closedTabs = [];
const MAX_CLOSED_TABS = 20;

function reopenClosedTab() {
  const last = closedTabs.pop();
  if (!last) { showToast("info", "No closed tabs", "Nothing to reopen"); return; }
  createTab(last.url);
  showToast("ok", "Tab Reopened", last.title || last.url);
}

// ── Tab Management ────────────────────────────────────────────
function activeWebview() {
  const tab = tabs.get(activeTabId);
  return tab ? tab.webview : null;
}

function tabOwnedBy(wv) {
  for (const tab of tabs.values()) {
    if (tab.webview === wv) return tab;
  }
  return null;
}

function currentPartition() {
  const seed = $("#webview");
  return (
    window.__orbitPartition ||
    (window.orbit && window.orbit.partition) ||
    (seed && seed.getAttribute("partition")) ||
    "persist:orbit"
  );
}

function isPrivateWindow() {
  return currentPartition() !== "persist:orbit";
}

function createWebview() {
  const seed = $("#webview");
  const wv = document.createElement("webview");
  // NEVER create a webview hidden: a display:none webview's guest process
  // never attaches, so the first loadURL throws and the user sees a white
  // screen. Guests attach while visible; background tabs get display:none
  // later (in activateTab) once already attached.
  wv.className = "webview";
  // A webview with NO src attribute never starts its guest in Electron 28
  // (no did-attach, no dom-ready — loadURL then throws synchronously). Seed
  // it with about:blank so the guest is alive before the first navigation.
  wv.setAttribute("src", "about:blank");
  wv.setAttribute("partition", currentPartition());
  wv.setAttribute("preload", seed?.getAttribute("preload") || "./guest-preload.js");
  wv.setAttribute("webpreferences", seed?.getAttribute("webpreferences") || "contextIsolation=yes,nodeIntegration=no,webSecurity=yes,spellcheck=false");
  contentArea.appendChild(wv);
  return wv;
}

function _doLoad(wv, url, attempt) {
  // Shared loader: catches both the synchronous not-attached throw (which
  // .catch() alone would miss — the original white-screen bug) and Promise
  // rejections. Transient failures (guest session still initializing, an
  // in-flight about:blank load) get one automatic retry, like Chrome.
  attempt = attempt || 0;
  try {
    wv.loadURL(url)
      .then(() => { if (wv.dataset) wv.dataset.pendingTries = "0"; })
      .catch((err) => {
        const msg = (err && err.message) ? err.message : String(err);
        // ERR_ABORTED is a benign cancellation (a newer navigation superseded
        // this one) — never retry or toast it, or we'd stomp the user's new URL.
        const aborted = /ERR_ABORTED/.test(msg);
        console.error("[NAV] loadURL rejected:", msg);
        if (!aborted && attempt < 2) {
          setTimeout(() => _doLoad(wv, url, attempt + 1), 500);
        } else if (!aborted) {
          showToast("err", "Navigation failed", msg.substring(0, 200));
        }
      });
  } catch (err) {
    // Guest not attached / dom-ready not emitted yet (webview created behind
    // an internal page). Park the URL; did-attach/dom-ready flush it. The
    // retry chain is BOUNDED (each attempt waits longer) so a guest that
    // never becomes ready fails loudly instead of retrying silently forever.
    if (wv.dataset) {
      wv.dataset.pendingUrl = url;
      const tries = parseInt(wv.dataset.pendingTries || "0", 10) + 1;
      wv.dataset.pendingTries = String(tries);
      if (tries <= 10) {
        console.warn("[NAV] webview not ready (try " + tries + "), deferring load:", url);
        setTimeout(() => flushPendingLoad(wv), 400 * tries);
      } else {
        wv.dataset.pendingUrl = "";
        console.error("[NAV] webview never became ready:", url);
        showToast("err", "Navigation failed", "The tab could not start loading (webview never became ready)");
      }
    }
  }
}

function loadURLSafely(wv, url) {
  _doLoad(wv, url, 0);
}

function flushPendingLoad(wv) {
  if (!wv.dataset || !wv.dataset.pendingUrl) return;
  const url = wv.dataset.pendingUrl;
  wv.dataset.pendingUrl = "";
  _doLoad(wv, url, 0);
  // If _doLoad hit the not-attached path again (did-attach can fire before
  // dom-ready), it re-parks the URL for the dom-ready flush.
}

function attachWebviewEvents(wv) {
  wv.addEventListener("did-attach", () => {
    flushPendingLoad(wv);
    const t = tabOwnedBy(wv);
    if (t) window.orbit?.tabs?.attach?.(t.id, t.url, wv.getWebContentsId?.() || 0);
  });
  wv.addEventListener("dom-ready", () => flushPendingLoad(wv));
  wv.addEventListener("did-fail-load", (e) => {
    // Only show errors for main-frame loads (not subresources)
    if (e.isMainFrame === false && e.type !== "other") return;
    const errCode = e.errorCode || 0;
    const errDesc = e.errorDescription || "Unknown error";
    console.error("[Webview] Load failed:", errCode, errDesc, e.validatedURL);
    // ERR_ABORTED (-3) is normal for cancelled navigations — don't toast
    if (errCode === -3) return;
    // Show user-visible error
    const msg = errDesc;
    if (errCode === -6) msg = "Server not found (DNS resolution failed)";
    else if (errCode === -7) msg = "Connection timed out";
    else if (errCode === -102) msg = "Connection refused";
    else if (errCode === -105) msg = "Name not resolved";
    else if (errCode === -106) msg = "Network offline";
    showToast("err", "Page failed to load", msg + " (" + errCode + ")");
  });
  wv.addEventListener("did-start-loading", () => {
    const tab = tabOwnedBy(wv);
    if (tab && tab.id === activeTabId) {
      omniInput.placeholder = "Loading...";
    }
  });
  wv.addEventListener("did-finish-load", () => {
    const tab = tabOwnedBy(wv);
    if (tab && tab.id === activeTabId) {
      omniInput.placeholder = "Search Google or enter URL";
      // Update URL in omnibox
      try {
        const url = wv.getURL();
        if (url && url !== "about:blank") {
          omniInput.value = url.replace(/^https?:\/\//, "");
        }
      } catch (err) {}
    }
  });
  wv.addEventListener("did-navigate", (e) => {
    const tab = tabOwnedBy(wv);
    if (!tab) return;
    // Ignore about:blank (the webview's initial load) — it would clobber the
    // tab's real URL and record blank history entries.
    if (!e.url || e.url === "about:blank") return;
    tab.url = e.url;
    recordHistory(e.url, tab.title || e.url);
    // Only update omnibox for the active tab. Prevent stale did-navigate
    // events from other tabs overwriting the current omnibox value.
    if (tab.id !== activeTabId) return;
    omniInput.value = e.url.replace(/^https?:\/\//, "");
    omniInput.placeholder = "Search or enter URL";
    wv.classList.remove("hidden");
    internalPages.classList.remove("visible");
    $$(".page", internalPages).forEach(p => p.classList.remove("on"));
    try {
      backBtn.disabled = !wv.canGoBack();
      forwardBtn.disabled = !wv.canGoForward();
    } catch (err) { /* webview not ready */ }
  });
  wv.addEventListener("did-navigate-in-page", (e) => {
    if (!e.isMainFrame) return;
    const tab = tabOwnedBy(wv);
    if (tab && tab.id === activeTabId) {
      tab.url = e.url;
      if (e.url && e.url !== "about:blank") {
        omniInput.value = e.url.replace(/^https?:\/\//, "");
      }
    }
  });
  wv.addEventListener("page-title-updated", (e) => {
    const tab = tabOwnedBy(wv);
    if (tab) {
      tab.title = e.title;
      if (tab.id === activeTabId) {
        renderTabs();
        if (sbPageTitle) sbPageTitle.textContent = e.title;
      }
    }
  });
  wv.addEventListener("did-start-loading", () => {
    if (reloadBtn) reloadBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.4"/></svg>';
  });
  wv.addEventListener("did-stop-loading", () => {
    if (reloadBtn) reloadBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8a5 5 0 019-2.5M13 8a5 5 0 01-9 2.5" stroke="currentColor" stroke-width="1.4"/><path d="M12 2.5V5.5H9" stroke="currentColor" stroke-width="1.4"/></svg>';
  });
}

let _renderTabsPending = false;
function renderTabs() {
  if (_renderTabsPending) return;
  _renderTabsPending = true;
  requestAnimationFrame(function() {
    _renderTabsPending = false;
    _renderTabsInner();
  });
}
function _renderTabsInner() {
  tabStrip.innerHTML = "";
  // Pinned tabs first (Chrome-style), then normal tabs in open order.
  const ordered = Array.from(tabs.entries()).sort((a, b) => (b[1].pinned ? 1 : 0) - (a[1].pinned ? 1 : 0));
  for (const [id, tab] of ordered) {
    const el = document.createElement("button");
    const sleeping = tab.sleeping ? " sleeping" : "";
    const pinned = tab.pinned ? " pinned" : "";
    const muted = tab.muted ? " muted" : "";
    el.className = "tab " + (id === activeTabId ? "active " : "") + (tab.agentOwned ? "agent-owned " : "") + sleeping + pinned + muted;
    el.dataset.id = id;
    el.title = tab.title + (tab.muted ? " (muted)" : "");

    if (tab.agentOwned) {
      el.innerHTML = '<span class="tab-glyph"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></span><span class="tab-title">' + escapeHtml(tab.title) + '</span><span class="tab-close" data-close="' + id + '">\u00d7</span>';
    } else {
      el.innerHTML = '<span class="tab-fav">' + (tab.pinned ? '\u2702' : '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4.5" stroke="currentColor"/></svg>') + '</span><span class="tab-title">' + escapeHtml(tab.title) + '</span>' + (tab.muted ? '<span class="tab-state" title="Muted">\u{1F507}</span>' : '') + '<span class="tab-close" data-close="' + id + '">\u00d7</span>';
    }

    el.addEventListener("click", (e) => {
      const closeBtn = e.target.closest("[data-close]");
      if (closeBtn) { e.stopPropagation(); closeTab(closeBtn.dataset.close); return; }
      activateTab(id);
    });

    // Drag-and-drop tab reordering
    el.draggable = true;
    el.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", id);
      e.dataTransfer.effectAllowed = "move";
      el.style.opacity = "0.5";
      setTimeout(() => el.classList.add("dragging"), 0);
    });
    el.addEventListener("dragend", () => {
      el.style.opacity = "";
      el.classList.remove("dragging");
      tabStrip.querySelectorAll(".tab").forEach(t => t.classList.remove("drag-over"));
    });
    el.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      el.classList.add("drag-over");
    });
    el.addEventListener("dragleave", () => {
      el.classList.remove("drag-over");
    });
    el.addEventListener("drop", (e) => {
      e.preventDefault();
      el.classList.remove("drag-over");
      const draggedId = e.dataTransfer.getData("text/plain");
      if (draggedId && draggedId !== id) {
        reorderTab(draggedId, id);
      }
    });

    tabStrip.appendChild(el);
  }
  renderVerticalTabs();
  updatePerfHud();
}

function reorderTab(draggedId, targetId) {
  // Convert Map to array, reorder, then rebuild Map
  const entries = Array.from(tabs.entries());
  const dragIdx = entries.findIndex(([id]) => id === draggedId);
  const targetIdx = entries.findIndex(([id]) => id === targetId);
  if (dragIdx === -1 || targetIdx === -1 || dragIdx === targetIdx) return;
  const [moved] = entries.splice(dragIdx, 1);
  entries.splice(targetIdx, 0, moved);
  tabs = new Map(entries);
  window._orbitTabs = tabs;
  renderTabs();
  saveSession();
}

function showEmptyScreen(show) {
  if (emptyTabs) emptyTabs.classList.toggle("on", show);
  if (webview) webview.classList.toggle("hidden", show);
  internalPages.classList.toggle("visible", !show);
  if (show) {
    backBtn.disabled = true;
    forwardBtn.disabled = true;
    omniInput.value = "";
    omniInput.placeholder = "Open a new tab to start browsing";
    sbPageTitle.textContent = "No tabs";
  }
}

function createTab(url) {
  url = url || "orbit://newtab";
  showEmptyScreen(false);
  const id = "tab-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
  const tab = {
    id, url, title: "New tab", favicon: null,
    loading: false, agentOwned: false, sleeping: false,
    webview: null, wcId: 0,
  };
  const seed = $("#webview");
  // Private windows never reuse the persist:orbit seed — every tab gets a
  // fresh in-memory webview (and the seed is hidden so it can't show through).
  const privateMode = isPrivateWindow();
  const wv = tabs.size === 0 && seed && !privateMode ? seed : createWebview();
  if (privateMode && seed) seed.classList.add("hidden");
  tab.webview = wv;
  attachWebviewEvents(wv);
  tabs.set(id, tab);
  activateTab(id);
  window.orbit?.tabs?.activate?.(id);
  // createTab never navigated the webview before: a restored/external URL
  // would otherwise sit on a blank viewport until manually navigated.
  // Park the URL in the pending mechanism so it loads only AFTER the guest's
  // initial about:blank dom-ready (did-attach/dom-ready flush it) — loading
  // while about:blank is still in flight can abort with ERR_FAILED.
  if (url && !url.startsWith("orbit://")) {
    if (wv.dataset) wv.dataset.pendingUrl = url;
    setTimeout(() => flushPendingLoad(wv), 2000);
  }
  return id;
}

function closeTab(id) {
  const tab = tabs.get(id);
  if (!tab) return;
  // Remember the tab for Ctrl+Shift+T reopen (skip internal pages).
  if (tab.url && !tab.url.startsWith("orbit://")) {
    closedTabs.push({ url: tab.url, title: tab.title || tab.url });
    if (closedTabs.length > MAX_CLOSED_TABS) closedTabs.shift();
  }
  clearSleepTimer(id);
  clearHibernateTimer(id);
  if (tab.webview) {
    try { tab.webview.remove(); } catch (e) { console.warn("[TAB] Webview teardown failed:", e); }
  }
  tabs.delete(id);
  window.orbit?.tabs?.close?.(id);
  if (tabs.size === 0) {
    activeTabId = null;
    showEmptyScreen(true);
    renderTabs();
    return;
  }
  if (activeTabId === id) {
    const remaining = Array.from(tabs.keys());
    activateTab(remaining[remaining.length - 1]);
  } else {
    renderTabs();
  }
}

function activateTab(id) {
  const tab = tabs.get(id);
  if (!tab) return;
  activeTabId = id;

  // Wake this tab and start sleep timers for others
  wakeTab(id);
  tabs.forEach(function(t, tid) {
    if (tid !== id) startSleepTimer(tid);
  });

  for (const t of tabs.values()) {
    if (t.webview) t.webview.classList.toggle("hidden", t.id !== id);
  }

  const internal = tab.url ? tab.url.startsWith("orbit://") : true;
  if (internal) {
    // Overlay (see navigateTo): the webview stays visible so its guest stays
    // attached and navigable.
    internalPages.classList.add("visible");
    const pageId = INTERNAL_PAGES[tab.url];
    showInternalPage(pageId || "newtabPage");
    backBtn.disabled = true;
    forwardBtn.disabled = true;
    omniInput.value = "";
    omniInput.placeholder = (tab.url || "orbit://newtab").replace("orbit://", "orbit://");
  } else {
    internalPages.classList.remove("visible");
    $$(".page", internalPages).forEach((p) => p.classList.remove("on"));
    const wv = activeWebview();
    if (wv) wv.classList.remove("hidden");
    omniInput.value = tab.url.replace(/^https?:\/\//, "");
    omniInput.placeholder = "Search Google or enter URL";
    try {
      backBtn.disabled = !wv || !wv.canGoBack();
      forwardBtn.disabled = !wv || !wv.canGoForward();
    } catch (err) { backBtn.disabled = true; forwardBtn.disabled = true; }
    // Restore zoom for this domain
    try {
      const domain = new URL(tab.url).hostname;
      currentZoom = zoomLevels[domain] || 1.0;
      if (zoomIndicator) zoomIndicator.textContent = Math.round(currentZoom * 100) + "%";
      if (wv) wv.setZoomFactor(currentZoom);
    } catch (e) {}
  }

  renderTabs();
  if (sbPageTitle) sbPageTitle.textContent = tab.title;
  window.orbit?.tabs?.activate?.(id);
}

// ── Navigation ────────────────────────────────────────────────
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
  "orbit://security": "securityPage",
};

function showInternalPage(pageId) {
  $$(".page", internalPages).forEach(p => p.classList.remove("on"));
  const target = document.getElementById(pageId);
  if (target) target.classList.add("on");
  if (pageId === "diagnosticsPage") refreshDiagnostics();
  if (pageId === "historyPage") renderHistoryPage();
  if (pageId === "bookmarksPage") renderBookmarksPage();
  if (pageId === "extensionsPage") renderExtensionsPage();
}

function refreshDiagnostics() {
  const diagDsh = diagDsh;
  const diagBackend = diagBackend;
  const diagEfficiency = diagEfficiency;
  const diagFrozen = diagFrozen;
  const setChip = (el, text, ok) => {
    if (!el) return;
    el.textContent = text;
    el.className = "chip " + (ok ? "ok" : "err");
  };
  const j = window.orbit?.jarvis?.status?.();
  if (j && typeof j.then === "function") {
    j.then((s) => {
      const online = !!(s && s.ok && s.kernel === "online");
      setChip(diagDsh, online ? "Connected" : "Offline", online);
      setChip(diagBackend, s?.bridge || "Offline", online);
    }).catch(() => {
      setChip(diagDsh, "Error", false);
    });
  } else {
    setChip(diagDsh, "Unavailable", false);
  }
  const p = window.orbit?.system?.performance?.status?.();
  if (p && typeof p.then === "function") {
    p.then((s) => {
      const eff = s && s.efficiencyMode;
      setChip(diagEfficiency, eff ? "On" : "Off", !!eff);
      const frozen = diagFrozen;
      if (frozen) frozen.textContent = (s && s.frozen) ? s.frozen + " tab(s)" : "None";
    }).catch(() => {});
  }
}

function navigateTo(url) {
  const tab = tabs.get(activeTabId);
  if (!tab) return;
  tab.url = url;

  if (url.startsWith("orbit://")) {
    omniInput.value = "";
    omniInput.placeholder = url.replace("orbit://", "orbit://");
    // Internal pages overlay the (attached, visible) webview instead of
    // display:none'ing it — hiding a webview before its guest attaches
    // permanently breaks navigation for that tab.
    internalPages.classList.add("visible");
    const pageId = INTERNAL_PAGES[url];
    showInternalPage(pageId || "newtabPage");
    backBtn.disabled = true;
    forwardBtn.disabled = true;
  } else {
    omniInput.value = url.replace(/^https?:\/\//, "");
    omniInput.placeholder = "Search Google or enter URL";
    internalPages.classList.remove("visible");
    $$(".page", internalPages).forEach(p => p.classList.remove("on"));
    const wv = activeWebview();
    if (!wv) { console.error("[NAV] No webview for active tab"); showToast("err", "No webview", "Tab has no webview attached. Try creating a new tab."); return; }
    wv.classList.remove("hidden");
    // Show the viewport first so a hidden guest can attach, then load.
    // loadURLSafely handles both Promise rejections AND the synchronous
    // not-attached-yet throw that caused the white screen.
    loadURLSafely(wv, url);
    setTimeout(() => {
      try {
        backBtn.disabled = !wv.canGoBack();
        forwardBtn.disabled = !wv.canGoForward();
      } catch (err) { /* webview not ready */ }
    }, 200);
  }

  updateStarIcon(url);
  saveSession();
  setTimeout(updatePerfHud, 200);
}

// ── Omnibox ───────────────────────────────────────────────────
omniInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const value = omniInput.value.trim();
    if (!value) return;
    let url;
    if (value.match(/^https?:\/\//)) url = value;
    else if (value.match(/^[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}/)) url = "https://" + value;
    else if (value.startsWith("orbit://")) url = value;
    else url = "https://www.google.com/search?q=" + encodeURIComponent(value);
    navigateTo(url);
    omniInput.blur();
  }
});

// ── Navigation Buttons (FIXED: use activeWebview()) ───────────
backBtn.addEventListener("click", () => {
  try {
    const wv = activeWebview();
    if (wv && !wv.classList.contains("hidden") && wv.canGoBack()) wv.goBack();
  } catch (e) { console.error("[NAV] Go back failed:", e); }
});

forwardBtn.addEventListener("click", () => {
  try {
    const wv = activeWebview();
    if (wv && !wv.classList.contains("hidden") && wv.canGoForward()) wv.goForward();
  } catch (e) { console.error("[NAV] Go forward failed:", e); }
});

reloadBtn.addEventListener("click", () => {
  try {
    const wv = activeWebview();
    if (wv) wv.reload();
  } catch (e) { console.error("[NAV] Reload failed:", e); }
});

// ── New Tab ───────────────────────────────────────────────────
newTabBtn.addEventListener("click", () => createTab());
if (emptyNewTabBtn) emptyNewTabBtn.addEventListener("click", () => createTab());

// Middle-click on a tab closes it (Chrome), double-click on empty
// strip space opens a new tab.
if (tabStrip) {
  tabStrip.addEventListener("auxclick", (e) => {
    if (e.button === 1) {
      const el = e.target.closest(".tab");
      if (el && el.dataset.id) closeTab(el.dataset.id);
    }
  });
  tabStrip.addEventListener("dblclick", (e) => {
    if (e.target === tabStrip || e.target.classList.contains("tab-strip")) createTab();
  });
}

// ── Home Button ───────────────────────────────────────────────
const homeBtn = $("#homeBtn");
if (homeBtn) {
  homeBtn.addEventListener("click", () => navigateTo("orbit://newtab"));
}

// ── Window Controls (frameless window) ────────────────────────
const winClose = $("#winClose");
const winMinimize = $("#winMinimize");
const winMaximize = $("#winMaximize");
if (winClose) winClose.addEventListener("click", () => window.orbit?.window?.close?.());
if (winMinimize) winMinimize.addEventListener("click", () => window.orbit?.window?.minimize?.());
if (winMaximize) winMaximize.addEventListener("click", () => window.orbit?.window?.maximize?.());

// ── Sidebar Toggle ────────────────────────────────────────────
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

if (floatGlyph) floatGlyph.addEventListener("click", () => {
  sidebarOpen = true;
  sidebar.classList.remove("hidden");
  jarvisBtn.classList.add("active");
  setMatrix(agentState);
});

// ── Sidebar Navigation ────────────────────────────────────────
if (sbNav) sbNav.addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (btn?.dataset.panel) {
    sbNav.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === btn));
    renderPanel(btn.dataset.panel);
  }
});

function renderPanel(name) {
  // Delegate chat panels to Chat module
  if (name === "jarvis" || name === "chat-history" || name === "activity") {
    Chat.renderPanel(name);
    return;
  }
  if (name === "vision") { renderVisionPanel(); return; }
  if (name === "agents") {
    sbBody.innerHTML = '<div class="panel-pad"><div style="border:1px solid var(--jb-border);border-radius:12px;padding:12px;background:var(--jb-void);margin-bottom:8px"><div style="display:flex;align-items:center;gap:8px"><div class="sb-matrix" data-state="idle"></div><h3 style="font-size:13px;color:var(--jb-paper);font-weight:500">Main agent</h3></div><p style="color:var(--jb-mute);font-size:12px;margin-top:6px">No active task</p></div></div>';
    sbBody.querySelectorAll(".sb-matrix").forEach(initMatrix);
  } else if (name === "memory") {
    sbBody.innerHTML = '<div class="panel-pad panel-muted">No saved memories yet.</div>';
  }
}

// ── Composer (DSH Native Integration) ──────────────────────────
if (sbSend) sbSend.addEventListener("click", sendToJarvis);
if (sbInput) {
  sbInput.addEventListener("keydown", (e) => {
    // Slash-command popup keyboard navigation
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      const popup = document.querySelector(".cmd-popup");
      if (popup && popup.style.display !== "none") {
        e.preventDefault();
        const items = popup.querySelectorAll(".cmd-popup-item");
        if (!items.length) return;
        let idx = Array.from(items).findIndex((el) => el.classList.contains("active"));
        if (e.key === "ArrowDown") idx = (idx + 1) % items.length;
        else idx = (idx - 1 + items.length) % items.length;
        items.forEach((el) => el.classList.remove("active"));
        items[idx].classList.add("active");
        items[idx].scrollIntoView({ block: "nearest" });
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      // If a slash-command item is highlighted, fill it instead of sending
      const active = document.querySelector(".cmd-popup-item.active");
      if (active) {
        e.preventDefault();
        sbInput.value = active.dataset.cmd + " ";
        Chat.hideCmdPopup();
        sbInput.focus();
        return;
      }
      e.preventDefault(); sendToJarvis();
    }
    // Escape closes command popup
    if (e.key === "Escape") Chat.hideCmdPopup();
  });
  // Slash-command autocomplete
  sbInput.addEventListener("input", () => {
    const val = sbInput.value;
    if (val.startsWith("/")) {
      Chat.showCmdPopup(val.substring(1));
    } else {
      Chat.hideCmdPopup();
    }
  });
}

async function sendToJarvis() {
  const text = sbInput.value.trim();
  if (!text) return;
  sbInput.value = "";
  Chat.hideCmdPopup();
  Chat.append("user", text);
  
  // Slash commands
  if (text.startsWith("/")) {
    handleDshCommand(text);
    return;
  }
  
  // DSH native (built into JARVIS)
  if (window.dshNative && window.dshNative.status.connected) {
    setMatrix("thinking");
    const tab = tabs.get(activeTabId);
    const page = tab ? { url: tab.url, title: tab.title } : null;
    const streamResult = await window.dshNative.chat(text, { page });
    if (streamResult.streamId) {
    } else if (streamResult.success === false) {
      Chat.append("error", streamResult.error || "Connection failed");
      setMatrix("fail");
      setTimeout(() => setMatrix("idle"), 2000);
    }
  } else if (window.orbit?.jarvis) {
    setMatrix("thinking");
    window.orbit.jarvis.chat(text, "orbit-session");
  } else {
    Chat.append("jarvis", "I'm not connected to a backend yet. Start the JARVIS bridge server on port 8170 for full functionality. Meanwhile:\n\n\u2022 Navigate: type a URL or search\n\u2022 Tabs: Ctrl+T / Ctrl+W\n\u2022 Find: Ctrl+F\n\u2022 Commands: Ctrl+K\n\u2022 Zoom: Ctrl+/-\n\u2022 Bookmarks: Ctrl+D\n\u2022 Screenshot: Ctrl+Shift+S");
    setMatrix("idle");
  }
}

function handleDshCommand(text) {
  const parts = text.split(" ");
  const cmd = parts[0].toLowerCase();
  const args = parts.slice(1).join(" ");
  const send = (role, msg) => Chat.append(role, msg);

  switch (cmd) {
    case "/task":
      runAgentTask(args);
      break;
    case "/research":
      runAgentTask("Research: " + args);
      break;
    case "/summarize":
      runAgentTask("Summarize this page");
      break;
    case "/navigate":
      if (args) navigateTo(args);
      break;
    case "/read":
      readPage();
      break;
    case "/screenshot":
      takeScreenshot();
      break;
    case "/status":
      showDshStatus();
      break;
    case "/help":
      send("jarvis", "Available commands:\n" +
        Chat.COMMANDS.map((c) => "  " + c.cmd + " \u2014 " + c.desc).join("\n"));
      break;
    default:
      send("error", "Unknown command: " + cmd + ". Type /help for available commands.");
  }
}

async function runAgentTask(task) {
  if (!window.dshNative || !window.dshNative.status.connected) {
    Chat.append("error", "JARVIS backend is not connected.");
    return;
  }
  setMatrix("running");
  Chat.append("system", "Starting agent task: " + task);
  const tab = tabs.get(activeTabId);
  const page = tab ? { url: tab.url, title: tab.title } : null;
  const result = await window.dshNative.runAgent(task, { page });
  if (result.streamId) {
  } else if (result.success === false) {
    Chat.append("error", result.error || "Agent task failed");
    setMatrix("fail");
    setTimeout(() => setMatrix("idle"), 2000);
  }
}

async function readPage() {
  if (!window.dshNative || !window.dshNative.status.connected) {
    Chat.append("error", "JARVIS backend is not connected.");
    return;
  }
  setMatrix("thinking");
  const result = await window.dshNative.read();
  if (result.success) {
    Chat.append("jarvis", result.text || "Page content retrieved");
    setMatrix("done");
    setTimeout(() => setMatrix("idle"), 2000);
  } else {
    Chat.append("error", result.error || "Failed to read page");
    setMatrix("fail");
    setTimeout(() => setMatrix("idle"), 2000);
  }
}

function showDshStatus() {
  if (!window.dshNative) {
    Chat.append("error", "JARVIS module not loaded.");
    return;
  }
  const s = window.dshNative.getStatus();
  Chat.append("system", [
    "JARVIS Status:",
    "  Connected: " + (s.connected ? "Yes" : "No"),
    "  Kernel: " + s.kernel,
    "  Last check: " + (s.lastCheck ? new Date(s.lastCheck).toLocaleTimeString() : "Never"),
    "  Sessions: " + s.activeSessions,
    "  Streams: " + s.activeStreams,
    "  Queued: " + s.queuedMessages,
  ].join("\n"));
}

// ── Chat module: all persistence/rendering in src/js/chat.js ──
// Chat.append(), Chat.beginStream(), Chat.updateStream(),
// Chat.endStream(), Chat.renderPanel(), Chat.COMMANDS

// Expose jarvisOnline for Chat module
window._jarvisOnline = false;
function syncJarvisOnline(val) {
  jarvisOnline = val;
  window._jarvisOnline = val;
}

// ── DSH Native Events ──────────────────────────────────────────
if (window.dshNative) {
  // Status updates
  window.dshNative.on('status', (status) => {
    syncJarvisOnline(status.connected && status.kernel === 'online');
    if (statusDot) statusDot.className = 'status-dot ' + (jarvisOnline ? 'online' : 'offline');
    if (statusLabel) statusLabel.textContent = jarvisOnline ? 'ONLINE' : 'OFF';
    if (sbDot) sbDot.className = 'sb-dot ' + (jarvisOnline ? 'online' : 'offline');
    setMatrix(jarvisOnline ? 'idle' : 'offline');
    updatePerfHud();
    
    // Update JARVIS panel status if visible
    if (sbNav && sbNav.querySelector('[data-panel="jarvis"]')?.classList.contains('on')) {
      // Refresh the JARVIS panel header with new status
      const jarvisPanel = sbBody.querySelector('.jarvis-status-header');
      if (jarvisPanel) {
        jarvisPanel.textContent = jarvisOnline ? 'READY' : 'OFF';
      }
    }
  });
  
  // Chat messages — all persistence handled by Chat.endStream()
  window.dshNative.on('message', (event) => {
    switch (event.type) {
      case 'start':
        setMatrix('thinking');
        Chat.beginStream();
        break;
      case 'delta':
        updateStreamingMessage(event.text, event.fullText);
        break;
      case 'done':
        finalizeStreamingMessage(event.text);
        setMatrix('done');
        setTimeout(() => setMatrix('idle'), 2000);
        break;
    }
  });
  
  // Agent events
  window.dshNative.on('agent', (event) => {
    switch (event.type) {
      case 'start':
        setMatrix('running');
        Chat.append('system', 'Agent started: ' + (event.task || 'Unknown task'));
        break;
      case 'step':
        if (event.step) Chat.append('system', 'Step: ' + JSON.stringify(event.step));
        break;
      case 'done':
        if (event.text) Chat.append('jarvis', event.text);
        setMatrix('done');
        setTimeout(() => setMatrix('idle'), 2000);
        break;
    }
  });
  
  // Errors
  window.dshNative.on('error', (event) => {
    Chat.append('error', event.message || 'JARVIS error');
    setMatrix('fail');
    setTimeout(() => setMatrix('idle'), 2000);
  });
}

// ── Streaming — delegates to Chat module ────────────────────────
function updateStreamingMessage(delta, fullText) {
  Chat.updateStream(fullText);
}

function finalizeStreamingMessage(fullText) {
  Chat.endStream(fullText);
}

// ── Legacy JARVIS Events (Fallback) ──────────────────────────────
if (window.orbit?.on?.navigateTo) {
  window.orbit.on.navigateTo((url) => {
    if (url && /^https?:/i.test(url)) createTab(url);
  });
}
if (window.orbit?.on?.tabCreated) {
  window.orbit.on.tabCreated((tab) => {
    const id = tab && tab.id;
    if (!id || tabs.has(id) || !tab.url) return;
    if (bootTabId && !bootReplaced && tabs.has(bootTabId)) {
      bootReplaced = true;
      navigateTo(tab.url);
      return;
    }
    createTab(tab.url);
  });
}
if (window.orbit?.on?.tabSleep) {
  window.orbit.on.tabSleep((id) => {
    const tab = tabs.get(id);
    if (tab && !tab.hibernated) {
      tab.sleeping = true;
      if (id !== activeTabId) renderTabs();
    }
  });
  window.orbit.on.tabWake((id) => {
    const tab = tabs.get(id);
    if (tab) {
      tab.sleeping = false;
      clearSleepTimer(id);
      if (id === activeTabId) renderTabs();
    }
  });
}
if (window.orbit?.jarvis && !window.dshNative?.status.connected) {
  window.orbit.jarvis.onStatus((status) => {
    syncJarvisOnline(status.ok && status.kernel === "online");
    if (statusDot) statusDot.className = "status-dot " + (jarvisOnline ? "online" : "offline");
    if (statusLabel) statusLabel.textContent = jarvisOnline ? "ONLINE" : "OFF";
    if (sbDot) sbDot.className = "sb-dot " + (jarvisOnline ? "online" : "offline");
    setMatrix(jarvisOnline ? "idle" : "offline");
    updatePerfHud();
  });
  window.orbit.jarvis.onChat((payload) => {
    if (payload.kind === "delta") { /* Stream response */ }
    else if (payload.kind === "done") {
      Chat.append("jarvis", payload.text || "(no response)");
      setMatrix("done");
      setTimeout(() => setMatrix("idle"), 2000);
    } else if (payload.kind === "error") {
      Chat.append("error", payload.error?.message || "JARVIS error");
      setMatrix("fail");
      setTimeout(() => setMatrix("idle"), 2000);
    }
  });
  window.orbit.jarvis.onAgentEvent((event) => { if (event.state) setMatrix(event.state); });
  window.orbit.jarvis.onApproval((request) => { showApprovalModal(request); });
}

// ── Approval Modal ────────────────────────────────────────────
function showApprovalModal(request) {
  setMatrix("ask");
  modalBg.classList.add("on");
  const title = $("#modalTitle");
  const desc = $("#modalDesc");
  const kv = $("#modalKv");
  if (title) title.textContent = request.title || "JARVIS wants to take an action";
  if (desc) desc.textContent = request.description || "This action requires your approval.";
  if (kv) {
    kv.innerHTML = "";
    if (request.details) {
      for (const [key, value] of Object.entries(request.details)) {
        kv.innerHTML += "<dt>" + escapeHtml(key) + "</dt><dd>" + escapeHtml(value) + "</dd>";
      }
    }
  }
}

if (modalDeny) modalDeny.addEventListener("click", () => { modalBg.classList.remove("on"); setMatrix("done"); setTimeout(() => setMatrix("idle"), 2000); });
if (modalAllowOnce) modalAllowOnce.addEventListener("click", () => { modalBg.classList.remove("on"); setMatrix("running"); });
if (modalAllowSite) modalAllowSite.addEventListener("click", () => { modalBg.classList.remove("on"); setMatrix("running"); });
if (modalBg) modalBg.addEventListener("click", (e) => { if (e.target === modalBg) modalBg.classList.remove("on"); });

// ── Bookmark System ───────────────────────────────────────────
function renderBookmarkBar() {
  if (!bookmarkBar) return;
  const addBtn = bookmarkBar.querySelector(".bm-add");
  const sep = bookmarkBar.querySelector(".bm-sep");
  bookmarkBar.innerHTML = "";
  if (addBtn) bookmarkBar.appendChild(addBtn);
  if (sep) bookmarkBar.appendChild(sep);
  bookmarks.forEach(function(bm, i) {
    const el = document.createElement("button");
    el.className = "bm-item";
    el.innerHTML = '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4.5" stroke="currentColor"/></svg>' + bm.title;
    el.title = bm.url;
    el.addEventListener("click", function() { navigateTo(bm.url); });
    el.addEventListener("contextmenu", function(e) {
      e.preventDefault();
      if (confirm("Remove: " + bm.title + "?")) {
        bookmarks.splice(i, 1);
        localStorage.setItem("orbit-bookmarks", JSON.stringify(bookmarks));
        renderBookmarkBar();
      }
    });
    bookmarkBar.appendChild(el);
  });
}

function addBookmark() {
  const tab = tabs.get(activeTabId);
  if (!tab) return;
  const title = prompt("Bookmark name:", tab.title);
  if (!title) return;
  bookmarks.push({ title: title, url: tab.url });
  localStorage.setItem("orbit-bookmarks", JSON.stringify(bookmarks));
  renderBookmarkBar();
  updateStarIcon(tab.url);
  showToast("ok", "Bookmark Added", title);
}

function updateStarIcon(url) {
  if (!omniStar) return;
  const isBookmarked = bookmarks.some(b => b.url === url);
  omniStar.classList.toggle("bookmarked", isBookmarked);
}

if (omniStar) omniStar.addEventListener("click", addBookmark);
if ($("#bmAddBtn")) $("#bmAddBtn").addEventListener("click", addBookmark);

// ── Session Management ────────────────────────────────────────
function saveSession() {
  const s = [];
  tabs.forEach(function(tab, id) {
    s.push({ id: id, url: tab.url, title: tab.title, agentOwned: tab.agentOwned });
  });
  localStorage.setItem("orbit-session", JSON.stringify({ tabs: s, activeTabId: activeTabId, savedAt: Date.now() }));
}

function restoreSession() {
  try {
    const data = JSON.parse(localStorage.getItem("orbit-session"));
    if (!data || !data.tabs || !data.tabs.length) return false;
    // createTab generates new IDs, so track which index was active
    let activeIdx = 0;
    if (data.activeTabId) {
      activeIdx = data.tabs.findIndex((t) => t.id === data.activeTabId);
      if (activeIdx < 0) activeIdx = 0;
    }
    let restoredId = null;
    const ids = Array.from(tabs.keys());
    data.tabs.forEach((t) => { restoredId = createTab(t.url); });
    // Activate the tab that corresponds to the previously active one
    const allIds = Array.from(tabs.keys());
    if (allIds.length > ids.length) {
      const newIds = allIds.slice(ids.length);
      activateTab(newIds[Math.min(activeIdx, newIds.length - 1)]);
    }
    showToast("ok", "Session Restored", data.tabs.length + " tabs recovered");
    return true;
  } catch (e) { return false; }
}

// ── Zoom Controls ─────────────────────────────────────────────
function getZoomDomain() {
  try { var t = tabs.get(activeTabId); return t ? new URL(t.url).hostname : ""; } catch (e) { return ""; }
}
function zoomIn() { setZoom(currentZoom + 0.1); }
function zoomOut() { setZoom(currentZoom - 0.1); }
function zoomReset() { setZoom(1.0); }
function setZoom(level) {
  currentZoom = Math.max(0.25, Math.min(5.0, level));
  const dom = getZoomDomain();
  if (dom) { zoomLevels[dom] = currentZoom; localStorage.setItem("orbit-zoom", JSON.stringify(zoomLevels)); }
  if (zoomIndicator) zoomIndicator.textContent = Math.round(currentZoom * 100) + "%";
  const wv = activeWebview();
  if (wv) wv.setZoomFactor(currentZoom);
  updatePerfHud();
}

// ── Performance HUD ───────────────────────────────────────────
const perfData = { fps: 60, memMB: 0, domCount: 0, lastFrameTime: performance.now(), frameCount: 0 };

// FPS calculation using requestAnimationFrame
(function fpsLoop() {
  perfData.frameCount++;
  const now = performance.now();
  if (now - perfData.lastFrameTime >= 1000) {
    perfData.fps = perfData.frameCount;
    perfData.frameCount = 0;
    perfData.lastFrameTime = now;
    updatePerfHud();
  }
  requestAnimationFrame(fpsLoop);
})();

// Memory usage (with fallback for non-Chrome)
function getMemoryMB() {
  if (performance.memory) {
    return Math.round(performance.memory.usedJSHeapSize / 1048576);
  }
  // Fallback: estimate from tab count (rough: ~30MB per tab)
  return tabs.size * 30;
}

// Cached DOM refs for perf HUD (avoid repeated getElementById)
const _perfRefs = {};
let _perfHudPending = false;
function _getPerfRef(id) {
  if (!_perfRefs[id]) _perfRefs[id] = document.getElementById(id);
  return _perfRefs[id];
}
function updatePerfHud() {
  if (_perfHudPending) return; // throttle to one rAF per frame
  _perfHudPending = true;
  requestAnimationFrame(() => {
    _perfHudPending = false;
    const jd = _getPerfRef("perfJarvisDot");
    const jl = _getPerfRef("perfJarvis");
    const tl = _getPerfRef("perfTabs");
    const zl = _getPerfRef("perfZoom");
    const fl = _getPerfRef("perfFps");
    const ml = _getPerfRef("perfMem");
    const dl = _getPerfRef("perfDom");
    if (jd) jd.className = "perf-dot " + (jarvisOnline ? "ok" : "off");
    if (jl) jl.textContent = "JARVIS: " + (jarvisOnline ? "ON" : "OFF");
    if (tl) tl.textContent = tabs.size + " tab" + (tabs.size !== 1 ? "s" : "");
    if (zl) zl.textContent = Math.round(currentZoom * 100) + "%";
    if (fl) fl.textContent = "FPS: " + perfData.fps;
    if (ml) ml.textContent = "MEM: " + getMemoryMB() + "MB";
    if (dl) dl.textContent = "DOM: " + document.body.childElementCount;
  });
}

// Cleanup on window close
window.addEventListener("beforeunload", function() {
  saveSession();
});

if (perfHud) perfHud.addEventListener("click", function() { navigateTo("orbit://diagnostics"); });

// ── Vertical Tabs ─────────────────────────────────────────────
function renderVerticalTabs() {
  if (!tabStripVertical) return;
  tabStripVertical.innerHTML = "";
  tabs.forEach(function(tab, id) {
    const el = document.createElement("button");
    el.className = "tab" + (id === activeTabId ? " active" : "") + (tab.agentOwned ? " agent-owned" : "");
    el.dataset.id = id;
    el.innerHTML = '<span class="tab-title">' + tab.title + '</span><span class="tab-close" data-close="' + id + '">\u00d7</span>';
    el.addEventListener("click", function(e) {
      const closeBtn = e.target.closest("[data-close]");
      if (closeBtn) { e.stopPropagation(); closeTab(closeBtn.dataset.close); return; }
      activateTab(id);
    });
    tabStripVertical.appendChild(el);
  });
}

// ── Print and Screenshot ──────────────────────────────────────
function printPage() {
  try { const wv = activeWebview(); if (wv) wv.print(); } catch (e) { showToast("err", "Print Failed", e.message); }
}
function takeScreenshot() {
  try {
    const wv = activeWebview();
    if (wv) {
      wv.capturePage().then(function(image) {
        const dataUrl = image.toDataURL();
        const a = document.createElement("a");
        a.href = dataUrl;
        a.download = "orbit-screenshot-" + Date.now() + ".png";
        a.click();
        showToast("ok", "Screenshot Saved", "Downloaded to default folder");
      });
    }
  } catch (e) { showToast("err", "Screenshot Failed", e.message); }
}

// ── Command Palette (Ctrl+K) ─────────────────────────────────
const CMD_ITEMS = [
  { l: "New Tab", d: "Open new tab", s: "Ctrl+T", i: "+", a: function() { createTab(); } },
  { l: "Close Tab", d: "Close current", s: "Ctrl+W", i: "\u00d7", a: function() { if (activeTabId) closeTab(activeTabId); } },
  { l: "Reload", d: "Refresh page", s: "Ctrl+R", i: "\u21bb", a: function() { try { const wv = activeWebview(); if (wv) wv.reload(); } catch (e) {} } },
  { l: "Find on Page", d: "Search text", s: "Ctrl+F", i: "\u2315", a: function() { toggleFind(); } },
  { l: "Settings", d: "Browser settings", i: "\u2699", a: function() { navigateTo("orbit://settings"); } },
  { l: "History", d: "Browsing history", i: "\u231a", a: function() { navigateTo("orbit://history"); } },
  { l: "Downloads", d: "View downloads", i: "\u21e3", a: function() { navigateTo("orbit://downloads"); } },
  { l: "Bookmarks", d: "View bookmarks", i: "\u2606", a: function() { navigateTo("orbit://bookmarks"); } },
  { l: "Tasks", d: "Agent tasks", i: "\u2611", a: function() { navigateTo("orbit://tasks"); } },
  { l: "Memory", d: "Saved memories", i: "\u2261", a: function() { navigateTo("orbit://memory"); } },
  { l: "Diagnostics", d: "System status", i: "\u229f", a: function() { navigateTo("orbit://diagnostics"); } },
  { l: "Print Page", d: "Print current page", s: "Ctrl+P", i: "\u2399", a: function() { printPage(); } },
  { l: "Screenshot", d: "Capture page", s: "Ctrl+Shift+S", i: "\u25a3", a: function() { takeScreenshot(); } },
  { l: "Zoom In", d: "Increase zoom", s: "Ctrl+=", i: "+", a: function() { zoomIn(); } },
  { l: "Zoom Out", d: "Decrease zoom", s: "Ctrl+-", i: "\u2212", a: function() { zoomOut(); } },
  { l: "Toggle Sidebar", d: "Show/hide JARVIS", s: "Ctrl+Shift+J", i: "\u25a6", a: function() { jarvisBtn.click(); } },
];

let cmdIdx = 0;
let cmdFiltered = [];

function openCmdPalette() {
  if (!cmdPaletteBg) return;
  cmdPaletteBg.classList.add("on");
  cmdInput.value = "";
  cmdIdx = 0;
  filterCmd("");
  setTimeout(() => cmdInput.focus(), 50);
}

function closeCmdPalette() {
  if (cmdPaletteBg) cmdPaletteBg.classList.remove("on");
}

function filterCmd(q) {
  q = (q || "").toLowerCase().trim();
  cmdFiltered = [];
  if (!cmdResults) return;
  let html = "";
  if (q) {
    for (const [id, tab] of tabs) {
      if (tab.title.toLowerCase().indexOf(q) >= 0 || tab.url.toLowerCase().indexOf(q) >= 0) {
        cmdFiltered.push({ l: tab.title, d: tab.url, i: "T", a: function(tid) { return function() { activateTab(tid); }; }(id) });
      }
    }
  }
  CMD_ITEMS.forEach(function(c) {
    if (!q || c.l.toLowerCase().indexOf(q) >= 0 || c.d.toLowerCase().indexOf(q) >= 0) {
      cmdFiltered.push(c);
    }
  });
  if (cmdFiltered.length) html += '<div class="cmd-group-label">Results</div>';
  cmdFiltered.forEach(function(c, i) {
    html += '<div class="cmd-item' + (i === cmdIdx ? ' active' : '') + '" data-ci="' + i + '"><div class="cmd-item-icon">' + c.i + '</div><div class="cmd-item-label">' + c.l + '<div class="cmd-item-desc">' + c.d + '</div></div>' + (c.s ? '<div class="cmd-item-shortcut">' + c.s + '</div>' : '') + '</div>';
  });
  res.innerHTML = html;
  res.querySelectorAll(".cmd-item").forEach(function(el) {
    el.addEventListener("click", function() {
      const idx = parseInt(el.getAttribute("data-ci"));
      if (cmdFiltered[idx]) { cmdFiltered[idx].a(); closeCmdPalette(); }
    });
  });
}

// ── Find on Page ──────────────────────────────────────────────
function toggleFind() {
  if (findBar) findBar.classList.toggle("on");
  if (findBar && findBar.classList.contains("on")) { findInput.focus(); findInput.select(); }
}

if ($("#findClose")) $("#findClose").addEventListener("click", () => findBar.classList.remove("on"));
if ($("#findNext")) $("#findNext").addEventListener("click", () => {
  try { const wv = activeWebview(); if (wv && findInput.value) wv.findInPage(findInput.value); } catch (e) {}
});
if ($("#findPrev")) $("#findPrev").addEventListener("click", () => {
  try { const wv = activeWebview(); if (wv && findInput.value) wv.findInPage(findInput.value, { forward: false, findNext: true }); } catch (e) {}
});
if (findInput) findInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { const wv = activeWebview(); if (wv) wv.findInPage(findInput.value, { forward: !e.shiftKey }); }
  if (e.key === "Escape") findBar.classList.remove("on");
});

// ── Vision Panel ─────────────────────────────────────────────
function renderVisionPanel() {
  let html = '<div style="padding:16px;color:var(--jb-mute)">';
  
  html += '<div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--jb-ghost);margin-bottom:12px">Vision Agent</div>';
  
  html += '<div style="border:1px solid var(--jb-border);border-radius:12px;padding:12px;background:var(--jb-void);margin-bottom:12px">';
  html += '<div style="font-size:13px;color:var(--jb-paper);font-weight:500;margin-bottom:8px">Page Analysis</div>';
  html += '<p style="font-size:12px;color:var(--jb-mute);margin-bottom:10px">Capture screenshots and analyze page content with vision AI.</p>';
  html += '<button onclick="window.visionAgent && window.visionAgent.describePage().then(r => { if(r.success) alert(r.answer.slice(0,500)); else alert(r.error); })" style="padding:6px 12px;border:1px solid var(--jb-line-hard);border-radius:6px;background:var(--jb-surface);color:var(--jb-text);font-size:12px;cursor:pointer;margin-right:6px">Describe Page</button>';
  html += '<button onclick="window.readingMode && window.readingMode.toggle()" style="padding:6px 12px;border:1px solid var(--jb-line-hard);border-radius:6px;background:var(--jb-surface);color:var(--jb-text);font-size:12px;cursor:pointer">Reading Mode</button>';
  html += '</div>';
  
  html += '<div style="border:1px solid var(--jb-border);border-radius:12px;padding:12px;background:var(--jb-void);margin-bottom:12px">';
  html += '<div style="font-size:13px;color:var(--jb-paper);font-weight:500;margin-bottom:8px">Multi-Agent Planner</div>';
  html += '<p style="font-size:12px;color:var(--jb-mute);margin-bottom:10px">Decompose tasks into steps with planner + navigator architecture.</p>';
  html += '<textarea id="plannerInput" rows="2" placeholder="Describe a task..." style="width:100%;padding:8px;background:var(--jb-void);border:1px solid var(--jb-border);border-radius:6px;color:var(--jb-text);font-size:12px;resize:none;margin-bottom:8px"></textarea>';
  html += '<button id="plannerExecBtn" style="padding:6px 12px;border:1px solid var(--jb-line-hard);border-radius:6px;background:var(--jb-paper);color:var(--jb-void);font-size:12px;cursor:pointer;font-weight:500">Execute Task</button>';
  html += '</div>';
  
  html += '<div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--jb-ghost);margin-bottom:8px;margin-top:16px">Keyboard Shortcuts</div>';
  html += '<div style="font-size:12px;color:var(--jb-mute)">';
  html += '<div style="display:flex;justify-content:space-between;padding:4px 0"><span>Ctrl+Shift+D</span><span style="color:var(--jb-ghost)">Toggle reading mode</span></div>';
  html += '<div style="display:flex;justify-content:space-between;padding:4px 0"><span>Ctrl+Shift+V</span><span style="color:var(--jb-ghost)">Vision analysis</span></div>';
  html += '<div style="display:flex;justify-content:space-between;padding:4px 0"><span>Ctrl+K</span><span style="color:var(--jb-ghost)">Command palette</span></div>';
  html += '</div>';
  
  html += '</div>';
  sbBody.innerHTML = html;

  // Wire up planner button
  const plannerBtn = document.getElementById('plannerExecBtn');
  const plannerInput = document.getElementById('plannerInput');
  if (plannerBtn && plannerInput) {
    plannerBtn.addEventListener('click', function() {
      const task = plannerInput.value.trim();
      if (!task) return;
      if (window.multiAgentPlanner) {
        plannerBtn.textContent = 'Running...';
        plannerBtn.disabled = true;
        window.multiAgentPlanner.execute(task).then(function(r) {
          plannerBtn.textContent = 'Execute Task';
          plannerBtn.disabled = false;
          if (r.success) showToast('ok', 'Task Complete', r.result);
          else showToast('err', 'Task Failed', r.error);
        });
      }
    });
  }
}

// renderDshPanel removed — DSH is integrated into JARVIS (chat.js)

// ── Context Menu ──────────────────────────────────────────────
const tabContextMenu = $("#tabContextMenu");
let contextTabId = null;

if (tabStrip) tabStrip.addEventListener("contextmenu", (e) => {
  const tabEl = e.target.closest(".tab");
  if (!tabEl) return;
  e.preventDefault();
  contextTabId = tabEl.dataset.id;
  tabContextMenu.style.left = e.clientX + "px";
  tabContextMenu.style.top = e.clientY + "px";
  tabContextMenu.classList.add("on");
});

if (tabContextMenu) tabContextMenu.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  const action = btn.dataset.action;
  if (action === "newTab") createTab();
  if (action === "reopenTab") reopenClosedTab();
  if (action === "duplicate" && contextTabId) { const tab = tabs.get(contextTabId); if (tab) createTab(tab.url); }
  if (action === "closeTab" && contextTabId) closeTab(contextTabId);
  if (action === "closeOthers" && contextTabId) { for (const [id] of tabs) { if (id !== contextTabId) { clearSleepTimer(id); clearHibernateTimer(id); tabs.delete(id); } } activateTab(contextTabId); renderTabs(); }
  if (action === "closeRight" && contextTabId) {
    const ids = Array.from(tabs.keys());
    const idx = ids.indexOf(contextTabId);
    for (let i = idx + 1; i < ids.length; i++) {
      clearSleepTimer(ids[i]); clearHibernateTimer(ids[i]); tabs.delete(ids[i]);
    }
    activateTab(contextTabId); renderTabs();
  }
  if (action === "reload") { try { const wv = activeWebview(); if (wv) wv.reload(); } catch (e) {} }
  if (action === "copyUrl" && contextTabId) { const tab = tabs.get(contextTabId); if (tab) navigator.clipboard.writeText(tab.url); }
  if (action === "muteTab" && contextTabId) { const tab = tabs.get(contextTabId); if (tab && tab.webview) { tab.muted = !tab.muted; try { tab.webview.setAudioMuted(tab.muted); } catch (err) {} renderTabs(); } }
  if (action === "pinTab" && contextTabId) { const tab = tabs.get(contextTabId); if (tab) { tab.pinned = !tab.pinned; renderTabs(); saveSession(); } }
  tabContextMenu.classList.remove("on");
});

// ── Browser Menu ──────────────────────────────────────────────
const browserMenu = $("#browserMenu");
const menuBtn = $("#menuBtn");
if (menuBtn) menuBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  closeAllPopups();
  browserMenu.style.right = "10px";
  browserMenu.style.top = "84px";
  browserMenu.classList.toggle("on");
});

// ── About (browser menu) ──────────────────────────────────────
const aboutOrbit = document.getElementById("aboutOrbit");
if (aboutOrbit) aboutOrbit.addEventListener("click", (e) => {
  e.stopPropagation();
  closeAllPopups();
  showToast("info", "JARVIS Orbit 0.1.0", "Unbranded Chromium (Electron) \u00b7 DSH/1.0 \u00b7 Nothing Design System");
});

// ── Extension Popup ───────────────────────────────────────────
const extPopup = $("#extPopup");
const extBtn = $("#extBtn");
if (extBtn) extBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  closeAllPopups();
  renderExtPopup();
  extPopup.style.right = "50px";
  extPopup.style.top = "84px";
  extPopup.classList.toggle("on");
});

// ── Profile Popup ─────────────────────────────────────────────
const profilePopup = $("#profilePopup");
const profileBtn = $("#profileBtn");
if (profileBtn) profileBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  closeAllPopups();
  renderProfilePopup();
  profilePopup.style.right = "80px";
  profilePopup.style.top = "84px";
  profilePopup.classList.toggle("on");
});

// ── Profiles (Chrome-style multi-profile) ─────────────────────
const PROFILES_KEY = "orbit-profiles";
const PROFILE_COLORS = ["#8ab4f8", "#f28b82", "#81c995", "#fdd663", "#d7aefb", "#78d9ec", "#ff8bcb", "#9aa0a6"];
function getProfiles() {
  try {
    const p = JSON.parse(localStorage.getItem(PROFILES_KEY) || "[]");
    return (p && p.length) ? p : [{ id: "default", name: "Personal", color: "#9aa0a6", active: true }];
  } catch (e) { return [{ id: "default", name: "Personal", color: "#9aa0a6", active: true }]; }
}
function saveProfiles(p) { try { localStorage.setItem(PROFILES_KEY, JSON.stringify(p)); } catch (e) {} }
function activeProfile() { return getProfiles().find((x) => x.active) || getProfiles()[0]; }
function syncProfileAvatar() {
  const prof = activeProfile();
  const avatar = document.querySelector(".toolbar-avatar");
  if (avatar) {
    avatar.textContent = (prof.name || "P").charAt(0).toUpperCase();
    avatar.style.background = prof.color;
  }
}
function switchProfile(id) {
  const p = getProfiles();
  if (!p.some((x) => x.id === id)) return;
  p.forEach((x) => { x.active = (x.id === id); });
  saveProfiles(p);
  syncProfileAvatar();
  renderProfilePopup();
  const prof = activeProfile();
  showToast("ok", "Profile Switched", "Now using \"" + prof.name + "\"");
  closeAllPopups();
}
function addProfile() {
  const name = prompt("New profile name:", "");
  if (!name || !name.trim()) return;
  const p = getProfiles();
  p.push({ id: "p" + Date.now().toString(36), name: name.trim().slice(0, 24), color: PROFILE_COLORS[p.length % PROFILE_COLORS.length], active: false });
  saveProfiles(p);
  switchProfile(p[p.length - 1].id);
}
function toggleGuestMode() {
  const p = getProfiles();
  const active = activeProfile();
  if (active.id === "guest") {
    const fallback = p.find((x) => x.id !== "guest");
    if (fallback) switchProfile(fallback.id);
    return;
  }
  if (!p.some((x) => x.id === "guest")) {
    p.push({ id: "guest", name: "Guest", color: "#f28b82", active: false });
    saveProfiles(p);
  }
  switchProfile("guest");
  showToast("warn", "Guest Mode", "This session's data will not be saved");
}
function lockProfile() {
  localStorage.removeItem(HISTORY_KEY);
  localStorage.removeItem("orbit-bookmarks");
  localStorage.removeItem("orbit-session");
  bookmarks = [];
  closedTabs.length = 0;
  renderBookmarkBar();
  showToast("ok", "Profile Locked", "History and saved data cleared");
  renderProfilePopup();
}
function renderProfilePopup() {
  const popup = document.getElementById("profilePopup");
  if (!popup) return;
  const prof = activeProfile();
  const guest = prof.id === "guest";
  let html = '<div class="pop-header"><div class="profile-avatar" style="background:' + prof.color + '">' + escapeHtml(prof.name.charAt(0).toUpperCase()) + '</div><div><div class="pop-title">' + escapeHtml(prof.name) + '</div><div class="pop-sub">' + (guest ? "Guest \u00b7 not saved" : "Personal \u00b7 Sync on") + '</div></div></div>';
  getProfiles().forEach((p) => {
    html += '<button class="profile-item' + (p.active ? " on" : "") + '" data-profile="' + p.id + '"><span class="profile-avatar sm" style="background:' + p.color + '">' + escapeHtml(p.name.charAt(0).toUpperCase()) + '</span><span class="profile-name">' + escapeHtml(p.name) + '</span>' + (p.active ? '<span class="chip ok">Active</span>' : "") + '</button>';
  });
  html += '<div class="menu-sep"></div>';
  html += '<button class="menu-item" id="profileAdd">Add profile</button>';
  html += guest
    ? '<button class="menu-item" id="profileExitGuest">Exit guest mode</button>'
    : '<button class="menu-item" id="profileGuest">Guest mode</button>';
  html += '<button class="menu-item" id="profileLock">Lock profile</button>';
  html += '<div class="menu-sep"></div>';
  html += '<button class="menu-item" data-nav="orbit://settings">Profile settings</button>';
  popup.innerHTML = html;
  popup.querySelectorAll("[data-profile]").forEach((b) => b.addEventListener("click", () => switchProfile(b.dataset.profile)));
  const addBtn = document.getElementById("profileAdd");
  if (addBtn) addBtn.addEventListener("click", () => addProfile());
  const guestBtn = document.getElementById("profileGuest");
  if (guestBtn) guestBtn.addEventListener("click", () => toggleGuestMode());
  const exitBtn = document.getElementById("profileExitGuest");
  if (exitBtn) exitBtn.addEventListener("click", () => toggleGuestMode());
  const lockBtn = document.getElementById("profileLock");
  if (lockBtn) lockBtn.addEventListener("click", () => lockProfile());
}

// ── Extension Popup (interactive) ─────────────────────────────
const EXT_STATE_KEY = "orbit-ext-state";
const EXTENSIONS = [
  { id: "jarvis", name: "JARVIS", sub: "Built into Orbit", builtin: true },
  { id: "ublock", name: "uBlock Origin", sub: "Ad & tracker blocking" },
  { id: "bitwarden", name: "Bitwarden", sub: "Password manager" },
];
function getExtState() {
  try { return JSON.parse(localStorage.getItem(EXT_STATE_KEY) || "{}"); } catch (e) { return {}; }
}
function saveExtState(s) { try { localStorage.setItem(EXT_STATE_KEY, JSON.stringify(s)); } catch (e) {} }
function extStatus(id) { const s = getExtState()[id] || {}; return { pinned: !!s.pinned, enabled: s.enabled !== false }; }
function renderExtPopup() {
  const popup = document.getElementById("extPopup");
  if (!popup) return;
  let html = '<div class="pop-header"><span class="pop-title">Extensions</span></div>';
  EXTENSIONS.forEach((ext) => {
    const st = extStatus(ext.id);
    html += '<div class="ext-row' + (st.enabled ? "" : " disabled") + '"><div class="ext-icon">' + escapeHtml(ext.name.charAt(0).toUpperCase()) + '</div>' +
      '<div class="ext-info"><div class="ext-name">' + escapeHtml(ext.name) + '</div><div class="ext-sub">' + escapeHtml(ext.sub) + '</div></div>' +
      '<button class="chip ext-pin' + (st.pinned ? " ok" : "") + '" data-pin="' + ext.id + '" title="' + (st.pinned ? "Unpin from toolbar" : "Pin to toolbar") + '">' + (st.pinned ? "\u2713" : "Pin") + '</button>' +
      '<button class="ext-power' + (st.enabled ? " on" : "") + '" data-power="' + ext.id + '" title="' + (st.enabled ? "Disable extension" : "Enable extension") + '"></button>' +
      '</div>';
  });
  html += '<div class="menu-sep"></div>';
  html += '<button class="menu-item" data-nav="orbit://extensions">Manage extensions</button>';
  popup.innerHTML = html;
  popup.querySelectorAll("[data-pin]").forEach((b) => b.addEventListener("click", (e) => {
    e.stopPropagation();
    const s = getExtState(); const st = s[b.dataset.pin] || {};
    st.pinned = !st.pinned; s[b.dataset.pin] = st;
    saveExtState(s);
    renderExtPopup(); renderExtensionsPage();
  }));
  popup.querySelectorAll("[data-power]").forEach((b) => b.addEventListener("click", (e) => {
    e.stopPropagation();
    const s = getExtState(); const st = s[b.dataset.power] || {};
    st.enabled = st.enabled === false ? true : false; s[b.dataset.power] = st;
    saveExtState(s);
    renderExtPopup(); renderExtensionsPage();
  }));
}
function renderExtensionsPage() {
  const host = document.getElementById("extensionsPage");
  if (!host) return;
  const sheet = host.querySelector(".sheet");
  if (!sheet) return;
  let html = '<div class="sheet"><h1>Extensions</h1><p class="sheet-lede">JARVIS is built in. It is not a store banner.</p><div class="group">';
  EXTENSIONS.forEach((ext) => {
    const st = extStatus(ext.id);
    html += '<div class="row"><div><div class="name">' + escapeHtml(ext.name) + '</div><div class="sub">' + escapeHtml(ext.sub) + '</div></div>' +
      '<span class="chip' + (st.pinned ? " ok" : "") + '">' + (st.pinned ? "Pinned" : "Unpinned") + '</span>' +
      '<span class="chip ' + (st.enabled ? "ok" : "") + '">' + (st.enabled ? "Enabled" : "Disabled") + '</span></div>';
  });
  html += '</div></div>';
  sheet.outerHTML = html;
}

// ── Close all popups ──────────────────────────────────────────
function closeAllPopups() {
  if (browserMenu) browserMenu.classList.remove("on");
  if (extPopup) extPopup.classList.remove("on");
  if (profilePopup) profilePopup.classList.remove("on");
  if (tabContextMenu) tabContextMenu.classList.remove("on");
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".popover") && !e.target.closest(".context-menu") && !e.target.closest("#menuBtn") && !e.target.closest("#extBtn") && !e.target.closest("#profileBtn")) closeAllPopups();
});

document.addEventListener("contextmenu", (e) => {
  if (!e.target.closest(".tab") && tabContextMenu) tabContextMenu.classList.remove("on");
});

// ── Popover navigation ────────────────────────────────────────
document.addEventListener("click", (e) => {
  const navItem = e.target.closest("[data-nav]");
  if (navItem) { navigateTo(navItem.dataset.nav); closeAllPopups(); }
  const actionItem = e.target.closest("[data-action]");
  if (actionItem && actionItem.closest(".popover, .context-menu")) {
    const action = actionItem.dataset.action;
    if (action === "newTab") createTab();
    if (action === "newWindow") { window.orbit?.window?.create?.(); }
    if (action === "incognito") { window.orbit?.window?.createPrivate?.(); }
    if (action === "reopenTab") reopenClosedTab();
    if (action === "zoomIn") zoomIn();
    if (action === "zoomOut") zoomOut();
    if (action === "zoomReset") zoomReset();
    if (action === "find") toggleFind();
    if (action === "reload") { try { const wv = activeWebview(); if (wv) wv.reload(); } catch (e) {} }
    closeAllPopups();
  }
});

// ── Sidebar Resize ────────────────────────────────────────────
const resizeHandle = $("#resizeHandle");
let isResizing = false;
if (resizeHandle) resizeHandle.addEventListener("mousedown", (e) => {
  isResizing = true;
  resizeHandle.classList.add("active");
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
  e.preventDefault();
});
document.addEventListener("mousemove", (e) => {
  if (!isResizing) return;
  const newWidth = Math.max(280, Math.min(600, window.innerWidth - e.clientX));
  sidebar.style.width = newWidth + "px";
});
document.addEventListener("mouseup", () => {
  if (isResizing) {
    isResizing = false;
    if (resizeHandle) resizeHandle.classList.remove("active");
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }
});

// ── Keyboard Shortcuts (DEDUPED — single handler) ─────────────
document.addEventListener("keydown", (e) => {
  const ctrl = e.ctrlKey || e.metaKey;
  const shift = e.shiftKey;

  // Ctrl+K: Command Palette
  if (ctrl && e.key.toLowerCase() === "k") { e.preventDefault(); openCmdPalette(); return; }
  // Ctrl+T: New tab
  if (ctrl && e.key.toLowerCase() === "t") { e.preventDefault(); createTab(); return; }
  // Ctrl+N: New window / Ctrl+Shift+N: New private window
  if (ctrl && e.key.toLowerCase() === "n" && !shift) { e.preventDefault(); window.orbit?.window?.create?.(); return; }
  if (ctrl && shift && e.key.toLowerCase() === "n") { e.preventDefault(); window.orbit?.window?.createPrivate?.(); return; }
  // Ctrl+W: Close tab
  if (ctrl && e.key.toLowerCase() === "w") { e.preventDefault(); if (activeTabId) closeTab(activeTabId); return; }
  // Ctrl+L: Focus omnibox
  if (ctrl && e.key.toLowerCase() === "l") { e.preventDefault(); omniInput.focus(); omniInput.select(); return; }
  // Ctrl+Shift+J: Toggle sidebar
  if (ctrl && shift && e.key.toLowerCase() === "j") { e.preventDefault(); jarvisBtn.click(); return; }
  // Ctrl+Shift+B: Toggle bookmark bar
  if (ctrl && shift && e.key.toLowerCase() === "b") { e.preventDefault(); if (bookmarkBar) bookmarkBar.classList.toggle("hidden"); return; }
  // Ctrl+R: Reload
  if (ctrl && e.key.toLowerCase() === "r" && !shift) {
    e.preventDefault();
    try { const wv = activeWebview(); if (wv) wv.reload(); } catch (e) {}
    return;
  }
  // Ctrl+Shift+R: Hard reload
  if (ctrl && shift && e.key.toLowerCase() === "r") {
    e.preventDefault();
    try { const wv = activeWebview(); if (wv) wv.reloadIgnoringCache(); } catch (e) {}
    return;
  }
  // Ctrl+Shift+D: Toggle reading mode
  if (ctrl && shift && e.key.toLowerCase() === "d") {
    e.preventDefault();
    if (window.readingMode) window.readingMode.toggle();
    return;
  }
  // Ctrl+Shift+V: Vision analysis
  if (ctrl && shift && e.key.toLowerCase() === "v") {
    e.preventDefault();
    if (window.visionAgent) {
      showToast('info', 'Vision', 'Analyzing page...');
      window.visionAgent.describePage().then(r => {
        if (r.success) Chat.append('jarvis', r.answer);
        else showToast('err', 'Vision Failed', r.error);
      });
    }
    return;
  }
  // F12: Developer tools
  if (e.key === "F12") {
    e.preventDefault();
    try { const wv = activeWebview(); if (wv) wv.openDevTools(); } catch (e) {}
    return;
  }
  // Ctrl+F: Find on page
  if (ctrl && e.key.toLowerCase() === "f") { e.preventDefault(); toggleFind(); return; }
  // Ctrl+Tab: Next tab
  if (ctrl && e.key === "Tab") {
    e.preventDefault();
    const ids = Array.from(tabs.keys());
    const idx = ids.indexOf(activeTabId);
    const next = shift ? (idx - 1 + ids.length) % ids.length : (idx + 1) % ids.length;
    activateTab(ids[next]);
    return;
  }
  // Ctrl+=/-/0: Zoom
  if (ctrl && (e.key === "=" || e.key === "+")) { e.preventDefault(); zoomIn(); return; }
  if (ctrl && e.key === "-") { e.preventDefault(); zoomOut(); return; }
  if (ctrl && e.key === "0") { e.preventDefault(); zoomReset(); return; }
  // Ctrl+P: Print
  if (ctrl && e.key.toLowerCase() === "p") { e.preventDefault(); printPage(); return; }
  // Ctrl+Shift+S: Screenshot
  if (ctrl && shift && e.key.toLowerCase() === "s") { e.preventDefault(); takeScreenshot(); return; }
  // Ctrl+D: Bookmark
  if (ctrl && e.key.toLowerCase() === "d") { e.preventDefault(); addBookmark(); return; }
  // Ctrl+H: History
  if (ctrl && e.key.toLowerCase() === "h") { e.preventDefault(); navigateTo("orbit://history"); return; }
  // Ctrl+J: Downloads
  if (ctrl && e.key.toLowerCase() === "j") { e.preventDefault(); navigateTo("orbit://downloads"); return; }
  // Ctrl+Home: New tab
  if (ctrl && e.key === "Home") { e.preventDefault(); navigateTo("orbit://newtab"); return; }
  // Alt+Left: Go back
  if (e.altKey && e.key === "ArrowLeft") {
    e.preventDefault();
    try { const wv = activeWebview(); if (wv && wv.canGoBack()) wv.goBack(); } catch (e) {}
    return;
  }
  // Alt+Right: Go forward
  if (e.altKey && e.key === "ArrowRight") {
    e.preventDefault();
    try { const wv = activeWebview(); if (wv && wv.canGoForward()) wv.goForward(); } catch (e) {}
    return;
  }
  // Ctrl+Shift+T: Reopen closed tab (Chrome)
  if (ctrl && e.shiftKey && e.key.toLowerCase() === "t") {
    e.preventDefault();
    reopenClosedTab();
    return;
  }
  // Escape: Close things
  if (e.key === "Escape") {
    if (cmdPaletteBg && cmdPaletteBg.classList.contains("on")) { closeCmdPalette(); return; }
    if (modalBg) modalBg.classList.remove("on");
    closeAllPopups();
    if (findBar && findBar.classList.contains("on")) findBar.classList.remove("on");
    return;
  }
});

// ── New Tab Tiles ─────────────────────────────────────────────
document.addEventListener("click", (e) => {
  const tile = e.target.closest("[data-url]");
  if (tile) navigateTo(tile.dataset.url);
});

// ── Theme Toggle ──────────────────────────────────────────────
const themeToggle = $("#themeToggle");
if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const html = document.documentElement;
    const current = html.dataset.theme || "dark";
    html.dataset.theme = current === "dark" ? "light" : "dark";
    themeToggle.textContent = current === "dark" ? "Toggle dark" : "Toggle light";
    showToast("info", "Theme Changed", "Switched to " + html.dataset.theme + " mode");
  });
}

// ── NTP Search ────────────────────────────────────────────────
const ntpSearch = $("#ntpSearch");
if (ntpSearch) {
  ntpSearch.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const value = ntpSearch.value.trim();
      if (!value) return;
      let url;
      if (value.match(/^https?:\/\//)) url = value;
      else if (value.match(/^[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}/)) url = "https://" + value;
      else url = "https://www.google.com/search?q=" + encodeURIComponent(value);
      navigateTo(url);
    }
  });
}

// ── Zoom Indicator Click ──────────────────────────────────────
if (zoomIndicator) {
  zoomIndicator.addEventListener("click", function() {
    const input = prompt("Zoom level (25-500):", Math.round(currentZoom * 100));
    if (input) { var val = parseFloat(input); if (!isNaN(val)) setZoom(val / 100); }
  });
}

// ── Session Banner ────────────────────────────────────────────
if (sessionBanner) {
  if ($("#sessionRestore")) $("#sessionRestore").addEventListener("click", function() { restoreSession(); sessionBanner.classList.remove("on"); });
  if ($("#sessionDismiss")) $("#sessionDismiss").addEventListener("click", function() { sessionBanner.classList.remove("on"); });
}

// ── Sleeping Tabs (Hibernation) ─────────────────────────────
const SLEEP_TIMEOUT = 3 * 60 * 1000;
const HIBERNATE_TIMEOUT = 10 * 60 * 1000;
const sleepTimers = new Map();
const hibernateTimers = new Map();

function startSleepTimer(id) {
  clearSleepTimer(id);
  clearHibernateTimer(id);
  sleepTimers.set(id, setTimeout(function() {
    const tab = tabs.get(id);
    if (tab && id !== activeTabId && !tab.agentOwned) {
      tab.sleeping = true;
      renderTabs();
      // Start hibernation timer after sleep
      startHibernateTimer(id);
    }
  }, SLEEP_TIMEOUT));
}

function startHibernateTimer(id) {
  hibernateTimers.set(id, setTimeout(function() {
    const tab = tabs.get(id);
    if (tab && tab.sleeping && id !== activeTabId) {
      hibernateTab(id);
    }
  }, HIBERNATE_TIMEOUT - SLEEP_TIMEOUT));
}

function clearSleepTimer(id) {
  const timer = sleepTimers.get(id);
  if (timer) { clearTimeout(timer); sleepTimers.delete(id); }
}

function clearHibernateTimer(id) {
  const timer = hibernateTimers.get(id);
  if (timer) { clearTimeout(timer); hibernateTimers.delete(id); }
}

function hibernateTab(id) {
  const tab = tabs.get(id);
  if (!tab || !tab.webview || tab.hibernated) return;
  tab.hibernated = true;
  tab.url = tab.webview.getURL() || tab.url;
  try { tab.webview.src = 'about:blank'; } catch (e) {}
}

function wakeTab(id) {
  const tab = tabs.get(id);
  if (!tab) return;
  clearHibernateTimer(id);
  if (tab.hibernated) {
    tab.hibernated = false;
    if (tab.url && !tab.url.startsWith('orbit://') && tab.webview) {
      loadURLSafely(tab.webview, tab.url);
    }
  }
  if (tab.sleeping) {
    tab.sleeping = false;
  }
  renderTabs();
  startSleepTimer(id);
}

// ── Utility ───────────────────────────────────────────────────
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ── Security Test UI ────────────────────────────────────────────
const runSecurityTestsBtn = document.getElementById('runSecurityTests');
const exportSecurityReportBtn = document.getElementById('exportSecurityReport');

if (runSecurityTestsBtn) {
  runSecurityTestsBtn.addEventListener('click', async () => {
    if (!window.securityTester) {
      showToast('err', 'Security Tester', 'Module not loaded');
      return;
    }

    runSecurityTestsBtn.textContent = 'Running...';
    runSecurityTestsBtn.disabled = true;

    try {
      const report = await window.securityTester.runAllTests();
      renderSecurityResults(report);
      showToast('ok', 'Security Tests Complete', `Score: ${report.summary.score}/100`);
    } catch (error) {
      showToast('err', 'Security Tests Failed', error.message);
    } finally {
      runSecurityTestsBtn.textContent = 'Run Tests';
      runSecurityTestsBtn.disabled = false;
    }
  });
}

if (exportSecurityReportBtn) {
  exportSecurityReportBtn.addEventListener('click', () => {
    if (!window.securityTester) {
      showToast('err', 'Security Tester', 'Module not loaded');
      return;
    }

    const report = window.securityTester.exportReport('html');
    const blob = new Blob([report], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `security-report-${Date.now()}.html`;
    a.click();
    URL.revokeObjectURL(url);

    showToast('ok', 'Report Exported', 'Security report downloaded');
  });
}

function renderSecurityResults(report) {
  const scoreEl = document.getElementById('securityScoreValue');
  const totalEl = document.getElementById('statTotal');
  const passedEl = document.getElementById('statPassed');
  const failedEl = document.getElementById('statFailed');
  const warningsEl = document.getElementById('statWarnings');
  const listEl = document.getElementById('securityTestList');

  if (scoreEl) {
    scoreEl.textContent = report.summary.score;
    scoreEl.className = 'security-score-value ' + 
      (report.summary.score >= 80 ? 'good' : 
       report.summary.score >= 60 ? 'warning' : 'bad');
  }

  if (totalEl) totalEl.textContent = report.summary.totalTests;
  if (passedEl) passedEl.textContent = report.summary.passed;
  if (failedEl) failedEl.textContent = report.summary.failed;
  if (warningsEl) warningsEl.textContent = report.summary.warnings;

  if (listEl) {
    let html = '';

    // Vulnerabilities
    for (const vuln of report.vulnerabilities) {
      html += `
        <div class="security-test-item">
          <div class="security-test-icon failed">✗</div>
          <div class="security-test-name">${escapeHtml(vuln.name)}</div>
          <div class="security-test-severity ${vuln.severity}">${vuln.severity}</div>
        </div>
      `;
    }

    // Passed tests
    for (const test of report.passed) {
      html += `
        <div class="security-test-item">
          <div class="security-test-icon passed">✓</div>
          <div class="security-test-name">${escapeHtml(test.name)}</div>
        </div>
      `;
    }

    listEl.innerHTML = html;
  }
}

// ── Module Integration ──────────────────────────────────────────
// Integrate with new modules when they load

// Tab Management integration
if (window.tabManagement) {
  // Listen for tab management events
  document.addEventListener('tab-management-event', (e) => {
    const { type, data } = e.detail;
    renderTabs();
  });
}

// JARVIS Integration
if (window.jarvisIntegration) {
  // Listen for JARVIS events
  document.addEventListener('jarvis-integration-event', (e) => {
    const { type, data } = e.detail;
  });
}

// Enhanced Performance integration
if (window.enhancedPerformance) {
  // Listen for performance events
  document.addEventListener('performance-event', (e) => {
    const { type, data } = e.detail;
    if (type === 'tab-suspended' || type === 'tab-woken') {
      renderTabs();
    }
    if (type === 'memory-warning' || type === 'memory-critical') {
      showToast('warn', 'Memory Warning', `Memory usage: ${data.usage}MB`);
    }
  });
}

// Enhanced Security integration  
if (window.enhancedSecurity) {
}

// Security Tester integration
if (window.securityTester) {
}

// ── History (Chrome-style recent visits, recorded on navigate) ──
const HISTORY_KEY = "orbit-history";
function getHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); } catch (e) { return []; }
}
function recordHistory(url, title) {
  if (!url || url.startsWith("about:") || url.startsWith("orbit://") || url.startsWith("data:")) return;
  const h = getHistory();
  const now = Date.now();
  // Merge consecutive duplicates (same URL within a minute).
  if (h.length && h[0].url === url && (now - h[0].ts) < 60000) {
    h[0].title = title; h[0].ts = now;
  } else {
    h.unshift({ url: url, title: title || url, ts: now });
  }
  if (h.length > 400) h.length = 400;
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(h)); } catch (e) {}
}
function renderHistoryPage() {
  const host = document.getElementById("historyPage");
  if (!host) return;
  const h = getHistory();
  const sheet = host.querySelector(".sheet");
  if (!sheet) return;
  const dayLabel = (ts) => {
    const d = new Date(ts); const today = new Date();
    const sameDay = (a, b) => a.toDateString() === b.toDateString();
    if (sameDay(d, today)) return "Today";
    const yest = new Date(today); yest.setDate(today.getDate() - 1);
    if (sameDay(d, yest)) return "Yesterday";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  };
  const timeLabel = (ts) => new Date(ts).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  let html = '<div class="sheet"><h1>History</h1><p class="sheet-lede">Real visits from this device — recorded as you browse.</p>';
  if (!h.length) {
    html += '<div class="group"><div class="empty-page">No history yet. Browse somewhere and it will appear here.</div></div>';
  } else {
    let lastDay = "";
    h.forEach((e, i) => {
      const day = dayLabel(e.ts);
      if (day !== lastDay) { html += '<div class="group"><h2>' + day + '</h2>'; lastDay = day; }
      const fav = "<svg width='12' height='12' viewBox='0 0 12 12' fill='none'><circle cx='6' cy='6' r='4.5' stroke='currentColor'/></svg>";
      html += '<div class="row hist-row" data-url="' + escapeHtml(e.url) + '"><div class="hist-fav">' + fav + '</div><div class="hist-body"><div class="name">' + escapeHtml(e.title) + '</div><div class="sub">' + escapeHtml(e.url) + '</div></div><span class="meta">' + timeLabel(e.ts) + '</span><button class="hist-remove" data-remove="' + i + '" title="Remove">\u00d7</button></div>';
    });
    html += '</div>';
  }
  html += '<div class="hist-actions"><button class="chip-btn" id="histClear">Clear history</button></div></div>';
  sheet.outerHTML = html;
  const clearBtn = document.getElementById("histClear");
  if (clearBtn) clearBtn.addEventListener("click", () => {
    localStorage.removeItem(HISTORY_KEY);
    showToast("ok", "History Cleared", "All browsing history removed");
    renderHistoryPage();
  });
  host.querySelectorAll(".hist-remove").forEach((b) => {
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      const h2 = getHistory(); h2.splice(parseInt(b.dataset.remove, 10), 1);
      try { localStorage.setItem(HISTORY_KEY, JSON.stringify(h2)); } catch (err) {}
      renderHistoryPage();
    });
  });
  host.querySelectorAll(".hist-row").forEach((r) => {
    r.addEventListener("click", () => navigateTo(r.dataset.url));
  });
}
function renderBookmarksPage() {
  const host = document.getElementById("bookmarksPage");
  if (!host) return;
  const sheet = host.querySelector(".sheet");
  if (!sheet) return;
  let html = '<div class="sheet"><h1>Bookmarks</h1><p class="sheet-lede">Saved from the \u2605 star in the address bar.</p>';
  if (!bookmarks.length) {
    html += '<div class="group"><div class="empty-page">No bookmarks yet. Press the star in the address bar to save a page.</div></div>';
  } else {
    html += '<div class="group">';
    bookmarks.forEach((b, i) => {
      html += '<div class="row hist-row" data-url="' + escapeHtml(b.url) + '"><div class="hist-fav">\u2605</div><div class="hist-body"><div class="name">' + escapeHtml(b.title || b.url) + '</div><div class="sub">' + escapeHtml(b.url) + '</div></div><button class="hist-remove" data-remove="' + i + '" title="Remove">\u00d7</button></div>';
    });
    html += '</div><div class="hist-actions"><button class="chip-btn" id="bmOpenAll">Open all</button></div>';
  }
  html += '</div>';
  sheet.outerHTML = html;
  const openAll = document.getElementById("bmOpenAll");
  if (openAll) openAll.addEventListener("click", () => {
    bookmarks.forEach((b) => createTab(b.url));
    showToast("ok", "Bookmarks Opened", bookmarks.length + " tabs opened");
  });
  host.querySelectorAll(".hist-remove").forEach((b) => {
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      bookmarks.splice(parseInt(b.dataset.remove, 10), 1);
      localStorage.setItem("orbit-bookmarks", JSON.stringify(bookmarks));
      renderBookmarkBar(); renderBookmarksPage();
    });
  });
  host.querySelectorAll(".hist-row").forEach((r) => {
    r.addEventListener("click", () => navigateTo(r.dataset.url));
  });
}

// ── Init ──────────────────────────────────────────────────────
initMatrix(sbMatrix);
if (floatMatrix) initMatrix(floatMatrix);
// Initialize chat module with DOM refs
if (window.Chat) Chat.init(sbBody, sbNav);
// Wire non-chat panel renderer into Chat module
window._renderNonChatPanel = function(name) {
  if (name === "vision") { renderVisionPanel(); return; }
  if (name === "agents") {
    sbBody.innerHTML = '<div class="panel-pad"><div style="border:1px solid var(--jb-border);border-radius:12px;padding:12px;background:var(--jb-void);margin-bottom:8px"><div style="display:flex;align-items:center;gap:8px"><div class="sb-matrix" data-state="idle"></div><h3 style="font-size:13px;color:var(--jb-paper);font-weight:500">Main agent</h3></div><p style="color:var(--jb-mute);font-size:12px;margin-top:6px">No active task</p></div></div>';
    sbBody.querySelectorAll(".sb-matrix").forEach(initMatrix);
  } else if (name === "memory") {
    sbBody.innerHTML = '<div class="panel-pad panel-muted">No saved memories yet.</div>';
  }
};
var bootTabId = createTab("orbit://newtab");
var bootReplaced = false;
setMatrix("idle");
// Render dynamic popup contents (profiles, extensions) and sync the avatar.
syncProfileAvatar();
renderProfilePopup();
renderExtPopup();
renderBookmarkBar();
updatePerfHud();
// Show initial JARVIS welcome
Chat.renderPanel("jarvis");
