/**
 * JARVIS Orbit — Renderer Process (Complete)
 * 
 * Manages browser UI: tabs, omnibox, sidebar, JARVIS communication.
 * All JARVIS IPC goes through preload bridge (window.orbit).
 * Features merged: Command Palette, Zoom, Bookmarks, Toast, Sessions, HUD, Vertical Tabs, Print/Screenshot
 */

// ── DOM Cache (avoid repeated getElementById) ─────────────────
const _domCache = {};
function getCachedEl(id) {
  if (!_domCache[id]) {
    _domCache[id] = document.getElementById(id);
  }
  return _domCache[id];
}
function invalidateCache(id) {
  if (id) delete _domCache[id];
  else Object.keys(_domCache).forEach(k => delete _domCache[k]);
}

// ── Debounce/Throttle Utilities ─────────────────────────────────
function debounce(fn, ms) {
  var timer;
  return function() {
    var args = arguments;
    var ctx = this;
    clearTimeout(timer);
    timer = setTimeout(function() { fn.apply(ctx, args); }, ms);
  };
}
function throttle(fn, ms) {
  var last = 0;
  return function() {
    var now = Date.now();
    if (now - last >= ms) {
      last = now;
      fn.apply(this, arguments);
    }
  };
}

// ── Error Logger (captures all errors for diagnostics) ──────────
const ErrorLogger = (function() {
  var _errors = [];
  var MAX_ERRORS = 500;
  var _listeners = [];

  function log(level, message, details) {
    var entry = {
      id: _errors.length,
      level: level, // 'error', 'warn', 'info'
      message: message,
      details: details || '',
      source: '',
      timestamp: Date.now(),
      url: '',
      line: 0,
      col: 0,
      stack: '',
    };
    try { entry.url = window.location.href; } catch (e) {}
    _errors.push(entry);
    if (_errors.length > MAX_ERRORS) _errors.shift();
    _notifyListeners(entry);
    return entry;
  }

  function logError(err, source) {
    var entry = log('error', err.message || String(err), source || '');
    if (err.filename) entry.source = err.filename;
    if (err.lineno) entry.line = err.lineno;
    if (err.colno) entry.col = err.colno;
    if (err.stack) entry.stack = err.stack;
    return entry;
  }

  function logWarn(message, details) { return log('warn', message, details); }
  function logInfo(message, details) { return log('info', message, details); }

  function getErrors(filter) {
    if (!filter) return _errors.slice();
    return _errors.filter(function(e) {
      if (filter.level && e.level !== filter.level) return false;
      if (filter.search) {
        var s = filter.search.toLowerCase();
        return (e.message || '').toLowerCase().includes(s) || (e.source || '').toLowerCase().includes(s);
      }
      return true;
    });
  }

  function getStats() {
    var stats = { total: _errors.length, errors: 0, warns: 0, infos: 0 };
    _errors.forEach(function(e) {
      if (e.level === 'error') stats.errors++;
      else if (e.level === 'warn') stats.warns++;
      else stats.infos++;
    });
    return stats;
  }

  function clear() { _errors.length = 0; }

  function exportLog() {
    return JSON.stringify(_errors, null, 2);
  }

  function onUpdate(cb) { _listeners.push(cb); }
  function _notifyListeners(entry) {
    _listeners.forEach(function(cb) { try { cb(entry); } catch (e) {} });
  }

  return {
    log: log,
    error: logError,
    warn: logWarn,
    info: logInfo,
    getErrors: getErrors,
    getStats: getStats,
    clear: clear,
    exportLog: exportLog,
    onUpdate: onUpdate,
  };
})();
window._errorLogger = ErrorLogger;

// ── Error Boundary ──────────────────────────────────────────────
window.addEventListener('error', (e) => {
  console.error('[ORBIT] Unhandled error:', e.message, e.filename, e.lineno);
  ErrorLogger.error(e, 'global');
  if (window.showToast) showToast('err', 'Error', e.message);
});
window.addEventListener('unhandledrejection', (e) => {
  console.error('[ORBIT] Unhandled rejection:', e.reason);
  ErrorLogger.error(e.reason || new Error(String(e.reason)), 'promise');
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
let tileMode = false;
let tabMru = [];
let sidebarOpen = true;
let jarvisOnline = false;
const ntpDrafts = new Map(); // per-tab New Tab search drafts (cleaned in closeTab)
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

// ── Tab Groups (Chrome-style colored groups) ──────────────────
const GROUP_COLORS = ["#8ab4f8", "#f28b82", "#81c995", "#fdd663", "#d7aefb", "#78d9ec"];
function nextGroupColor() {
  const used = new Set();
  for (const t of tabs.values()) if (t.groupColor) used.add(t.groupColor);
  const free = GROUP_COLORS.find((c) => !used.has(c));
  return free || GROUP_COLORS[Math.floor(Math.random() * GROUP_COLORS.length)];
}
function groupTab(id) {
  const tab = tabs.get(id);
  if (!tab) return;
  // Already grouped: click cycles the color (Chrome).
  if (tab.groupColor) {
    const i = GROUP_COLORS.indexOf(tab.groupColor);
    tab.groupColor = GROUP_COLORS[(i + 1) % GROUP_COLORS.length];
  } else {
    tab.groupColor = nextGroupColor();
  }
  renderTabs();
}
function ungroupTab(id) {
  const tab = tabs.get(id);
  if (tab) { tab.groupColor = null; renderTabs(); }
}

// ── Tab Group Collapse (Vivaldi-style) ──────────────────────
let _collapsedGroups = new Set();

function toggleGroupCollapse(color) {
  if (_collapsedGroups.has(color)) {
    _collapsedGroups.delete(color);
  } else {
    _collapsedGroups.add(color);
  }
  renderTabs();
}

function isGroupCollapsed(color) {
  return _collapsedGroups.has(color);
}

// ── Tab Management ────────────────────────────────────────────
function activeWebview() {
  const tab = tabs.get(activeTabId);
  return tab ? tab.webview : null;
}

function tileTargets() {
  const act = tabs.get(activeTabId);
  if (!tileMode || !act || !act.webview) return null;
  const ids = [activeTabId].concat(tabMru.filter((id) => id !== activeTabId && tabs.has(id)));
  const vs = [];
  for (const id of ids) {
    const t = tabs.get(id);
    if (t && t.webview && !/^orbit:\/\//i.test(t.url || "")) vs.push(t);
  }
  if (vs.length < 2) return null;
  return vs;
}
window._orbitTilingTargets = tileTargets;

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
        ErrorLogger.error(new Error('loadURL: ' + msg), 'navigation');
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
    ErrorLogger.error(new Error('Webview load failed: ' + errCode + ' ' + errDesc), 'webview');
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
      // Chrome-style thin progress bar
      const prog = document.getElementById('omniProgress');
      if (prog) { prog.className = 'omni-progress loading'; }
    }
  });
  wv.addEventListener("did-finish-load", () => {
    const tab = tabOwnedBy(wv);
    if (tab && tab.id === activeTabId) {
      omniInput.placeholder = "Search Google or enter URL";
      // Update URL in omnibox
      let url = "";
      try {
        url = wv.getURL();
        if (url && url !== "about:blank") {
          omniInput.value = url.replace(/^https?:\/\//, "");
        }
      } catch (err) {}
      // Complete progress bar
      const prog = document.getElementById('omniProgress');
      if (prog && prog.classList.contains('loading')) {
        prog.className = 'omni-progress done';
        setTimeout(function() { prog.className = 'omni-progress'; }, 350);
      }
      // Update lock icon security state
      updateOmniLock(url);
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
    // Apply boost (Arc-style custom CSS/JS per site)
    applyBoostToWebview(wv, e.url);
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
  // Track which groups we've rendered to handle collapse
  const renderedGroups = new Set();
  for (const [id, tab] of ordered) {
    // Handle collapsed groups: skip tabs in collapsed groups (unless active)
    if (tab.groupColor && isGroupCollapsed(tab.groupColor) && id !== activeTabId) {
      if (!renderedGroups.has(tab.groupColor)) {
        renderedGroups.add(tab.groupColor);
        // Render a collapse indicator for the group
        const collapseEl = document.createElement("button");
        collapseEl.className = "tab-group-collapsed";
        collapseEl.style.cssText = "display:flex;align-items:center;gap:4px;padding:2px 8px;border-radius:6px;background:" + tab.groupColor + "22;border:1px solid " + tab.groupColor + "44;font-size:10px;color:" + tab.groupColor + ";cursor:pointer;margin-right:4px";
        collapseEl.innerHTML = '<span style="font-size:12px">\u25B6</span><span>' + tabs.size + ' tabs</span>';
        collapseEl.title = "Click to expand group";
        collapseEl.addEventListener("click", function() { toggleGroupCollapse(tab.groupColor); });
        tabStrip.appendChild(collapseEl);
      }
      continue;
    }
    // If this tab's group was collapsed but is now active, render it
    if (tab.groupColor && isGroupCollapsed(tab.groupColor)) {
      if (!renderedGroups.has(tab.groupColor)) {
        renderedGroups.add(tab.groupColor);
        // Render collapse button before active tab
        const collapseEl = document.createElement("button");
        collapseEl.className = "tab-group-expanded";
        collapseEl.style.cssText = "display:flex;align-items:center;gap:4px;padding:2px 8px;border-radius:6px;background:" + tab.groupColor + "22;border:1px solid " + tab.groupColor + "44;font-size:10px;color:" + tab.groupColor + ";cursor:pointer;margin-right:4px";
        collapseEl.innerHTML = '<span style="font-size:12px">\u25BC</span>';
        collapseEl.title = "Click to collapse group";
        collapseEl.addEventListener("click", function() { toggleGroupCollapse(tab.groupColor); });
        tabStrip.appendChild(collapseEl);
      }
    }
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
      el.innerHTML = '<span class="tab-fav">' + (tab.pinned ? '\u2702' : '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4.5" stroke="currentColor"/></svg>') + '</span>' + (tab.groupColor ? '<span class="tab-grp" data-grp="' + id + '" style="background:' + tab.groupColor + '" title="Click to change group color"></span>' : '') + '<span class="tab-title">' + escapeHtml(tab.title) + '</span>' + (tab.muted ? '<span class="tab-state" title="Muted">\u{1F507}</span>' : '') + '<span class="tab-close" data-close="' + id + '">\u00d7</span>';
    }
    if (tab.groupColor) el.style.borderTopColor = tab.groupColor;

    tabStrip.appendChild(el);
  }
  renderVerticalTabs();
  updatePerfHud();
}

// ── Event delegation for the tab strip (one listener, not N) ──
// Click, close, and drag-drop are handled once here instead of binding
// five listeners per tab element on every render. Big win with 20+ tabs.
if (tabStrip && !tabStrip.dataset.delegated) {
  tabStrip.dataset.delegated = "1";
  tabStrip.addEventListener("click", (e) => {
    const closeBtn = e.target.closest("[data-close]");
    if (closeBtn) { e.stopPropagation(); closeTab(closeBtn.dataset.close); return; }
    const grpBtn = e.target.closest("[data-grp]");
    if (grpBtn) { e.stopPropagation(); groupTab(grpBtn.dataset.grp); return; }
    const tabEl = e.target.closest(".tab");
    if (tabEl && tabEl.dataset.id) activateTab(tabEl.dataset.id);
  });
  tabStrip.addEventListener("dragstart", (e) => {
    const tabEl = e.target.closest(".tab");
    if (!tabEl) return;
    e.dataTransfer.setData("text/plain", tabEl.dataset.id);
    e.dataTransfer.effectAllowed = "move";
    tabEl.style.opacity = "0.5";
    setTimeout(() => tabEl.classList.add("dragging"), 0);
  });
  tabStrip.addEventListener("dragend", (e) => {
    const tabEl = e.target.closest(".tab");
    if (tabEl) { tabEl.style.opacity = ""; tabEl.classList.remove("dragging"); }
    tabStrip.querySelectorAll(".tab").forEach(t => t.classList.remove("drag-over"));
  });
  tabStrip.addEventListener("dragover", (e) => {
    const tabEl = e.target.closest(".tab");
    if (!tabEl) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    tabEl.classList.add("drag-over");
  });
  tabStrip.addEventListener("dragleave", (e) => {
    const tabEl = e.target.closest(".tab");
    if (tabEl) tabEl.classList.remove("drag-over");
  });
  tabStrip.addEventListener("drop", (e) => {
    const tabEl = e.target.closest(".tab");
    if (!tabEl) return;
    e.preventDefault();
    tabEl.classList.remove("drag-over");
    const draggedId = e.dataTransfer.getData("text/plain");
    if (draggedId && draggedId !== tabEl.dataset.id) reorderTab(draggedId, tabEl.dataset.id);
  });
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
  _wireFoundInPage(wv);
  tabs.set(id, tab);
  activateTab(id);
  window.orbit?.tabs?.activate?.(id);
  // createTab never navigated the webview before: a restored/external URL
  // would otherwise sit on a blank viewport until manually navigated.
  // Park the URL in the pending mechanism so it loads only AFTER the guest's
  // initial about:blank dom-ready (did-attach/dom-ready flush it) — loading
  // while about:blank is still in flight can abort with ERR_FAILED.
  if (url && (!url.startsWith("orbit://") || isWebviewInternal(url))) {
    if (wv.dataset) wv.dataset.pendingUrl = url;
    setTimeout(() => flushPendingLoad(wv), 2000);
  }
  return id;
}

function closeTab(id) {
  const tab = tabs.get(id);
  if (!tab) return;
  ntpDrafts.delete(id);
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
  if (window.Chat) Chat.forgetTab(id);
}

function activateTab(id) {
  const tab = tabs.get(id);
  if (!tab) return;
  tabMru = [id].concat(tabMru.filter((x) => x !== id));
  window.__orbitTabMru = tabMru;
  activeTabId = id;
  if (window.Chat) Chat.setTab(id);

  // Wake this tab and start sleep timers for others
  wakeTab(id);
  tabs.forEach(function(t, tid) {
    if (tid !== id) startSleepTimer(tid);
  });

  if (window.tilingUi) {
    window.tilingUi.applyLayout();
  } else {
    for (const t of tabs.values()) {
      if (t.webview) t.webview.classList.toggle("hidden", t.id !== id);
    }
  }

  const internal = tab.url ? (tab.url.startsWith("orbit://") && !isWebviewInternal(tab.url)) : true;
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
    // File-backed internal pages (Import helper, Extension Store) render in
    // the webview via the orbit:// protocol, not the overlay.
    if (tab.url && isWebviewInternal(tab.url)) {
      try {
        if (!wv || (wv.getURL && wv.getURL() !== tab.url)) loadURLSafely(wv, tab.url);
      } catch (e) {}
    }
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
  "orbit://privacy": "privacyPage",
  "orbit://import": "importPage",
  "orbit://extension-store": "extensionStorePage",
  "orbit://goodeye": "goodeyePage",
  "orbit://f1": "f1Page",
};

function isWebviewInternal(url) {
  if (!url || !url.startsWith("orbit://")) return false;
  const pageId = INTERNAL_PAGES[url];
  return !!pageId && !document.getElementById(pageId);
}

function showInternalPage(pageId) {
  $$(".page", internalPages).forEach(p => p.classList.remove("on"));
  const target = document.getElementById(pageId);
  if (target) target.classList.add("on");
  if (pageId === "diagnosticsPage") refreshDiagnostics();
  if (pageId === "historyPage") renderHistoryPage();
  if (pageId === "bookmarksPage") renderBookmarksPage();
  if (pageId === "extensionsPage") renderExtensionsPage();
  if (pageId === "newtabPage") {
    renderSessionThumbnails();
    // Fresh New Tab pages open with an empty search box; revisiting an
    // existing tab restores its own draft (the input is shared DOM).
    const ntp = document.getElementById("ntpSearch");
    if (ntp) ntp.value = ntpDrafts.get(activeTabId) || "";
  }
  if (pageId === "privacyPage") renderPrivacyPage();
  if (pageId === "downloadsPage") renderDownloadsPage();
  if (pageId === "permissionsPage") renderPermissionsPage();
  if (pageId === "memoryPage") renderMemoryPage();
  if (pageId === "tasksPage") renderTasksPage();
  if (pageId === "goodeyePage" && window.GoodEye) window.GoodEye.start();
  if (pageId === "f1Page" && window.OrbitF1) window.OrbitF1.start();
  // Workspaces poll in the background; stop them when their page hides.
  if (pageId !== "goodeyePage" && window.GoodEye) window.GoodEye.stop();
  if (pageId !== "f1Page" && window.OrbitF1) window.OrbitF1.stop();
}

function refreshDiagnostics() {
  const diagDsh = document.getElementById('diagDsh');
  const diagBackend = document.getElementById('diagBackend');
  const diagEfficiency = document.getElementById('diagEfficiency');
  const diagFrozen = document.getElementById('diagFrozen');
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
      // Real engine numbers: sleeping tabs + measured memory across guests.
      const mem = document.getElementById("diagMem");
      if (mem) mem.textContent = (s && s.totalMemoryMB > 0) ? s.totalMemoryMB + " MB" : "Measuring...";
      const sleep = document.getElementById("diagSleeping");
      if (sleep) sleep.textContent = (s && s.sleepingTabs > 0) ? s.sleepingTabs + " tab(s)" : "None";
    }).catch(() => {});
  }
  // Error log stats
  var errStats = ErrorLogger.getStats();
  var errCount = document.getElementById('diagErrorCount');
  var errTotal = document.getElementById('diagErrorTotal');
  var warnTotal = document.getElementById('diagWarnTotal');
  var lastErr = document.getElementById('diagLastError');
  if (errCount) errCount.textContent = errStats.total;
  if (errTotal) errTotal.textContent = errStats.errors;
  if (warnTotal) warnTotal.textContent = errStats.warns;
  if (lastErr) {
    var allErrors = ErrorLogger.getErrors({ level: 'error' });
    lastErr.textContent = allErrors.length > 0 ? allErrors[allErrors.length - 1].message.substring(0, 60) : 'None';
  }
  // Wire error log buttons
  var viewBtn = document.getElementById('diagViewErrors');
  var exportBtn = document.getElementById('diagExportErrors');
  var clearBtn = document.getElementById('diagClearErrors');
  var errorList = document.getElementById('diagErrorList');
  if (viewBtn && errorList) {
    viewBtn.onclick = function() {
      var show = errorList.style.display === 'none';
      errorList.style.display = show ? 'block' : 'none';
      viewBtn.textContent = show ? 'Hide Log' : 'View Log';
      if (show) renderErrorLog(errorList);
    };
  }
  if (exportBtn) {
    exportBtn.onclick = function() {
      var log = ErrorLogger.exportLog();
      var blob = new Blob([log], { type: 'application/json' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = 'orbit-error-log-' + new Date().toISOString().slice(0, 10) + '.json';
      a.click();
      URL.revokeObjectURL(url);
      showToast('ok', 'Exported', 'Error log saved');
    };
  }
  if (clearBtn) {
    clearBtn.onclick = function() {
      ErrorLogger.clear();
      refreshDiagnostics();
      showToast('ok', 'Cleared', 'Error log cleared');
    };
  }
}

function renderErrorLog(container) {
  var errors = ErrorLogger.getErrors();
  if (errors.length === 0) {
    container.innerHTML = '<div style="padding:12px;color:var(--jb-mute);font-size:12px;text-align:center">No errors logged</div>';
    return;
  }
  var html = '';
  errors.slice(-50).reverse().forEach(function(e) {
    var color = e.level === 'error' ? '#f87171' : e.level === 'warn' ? '#fbbf24' : '#4ade80';
    var icon = e.level === 'error' ? '\u2717' : e.level === 'warn' ? '\u26A0' : '\u2139';
    var time = new Date(e.timestamp).toLocaleTimeString();
    html += '<div class="privacy-activity-item">';
    html += '<div class="privacy-activity-dot" style="background:' + color + '"></div>';
    html += '<div class="privacy-activity-text" style="font-size:11px"><span style="color:' + color + ';margin-right:6px">' + icon + '</span>' + escapeHtml(e.message) + (e.source ? ' <span style="color:var(--jb-mute)">' + escapeHtml(e.source) + ':' + e.line + '</span>' : '') + '</div>';
    html += '<div class="privacy-activity-time">' + time + '</div>';
    html += '</div>';
  });
  container.innerHTML = html;
}

function navigateTo(url) {
  const tab = tabs.get(activeTabId);
  if (!tab) return;
  tab.url = url;

  if (url.startsWith("orbit://") && !isWebviewInternal(url)) {
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
// ── Omnibox Suggestions (Chrome-style) ──────────────────────
const omniSuggest = $("#omniSuggest");
let omniItems = [];
let omniSel = -1;

function omniUrlFor(value) {
  if (!value) return null;
  if (/^https?:\/\//.test(value)) return value;
  if (value.startsWith("orbit://")) return value;
  if (/^[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}/.test(value)) return "https://" + value;
  return "https://www.google.com/search?q=" + encodeURIComponent(value);
}

function omniClose() {
  if (omniSuggest) omniSuggest.hidden = true;
  omniItems = []; omniSel = -1;
}

function _oiIcon(kind) {
  if (kind === "tab") return "⧉";
  if (kind === "bookmark") return "★";
  if (kind === "history") return "⏱";
  return "G";
}

function _oiLabel(kind) {
  if (kind === "tab") return "Switch to tab";
  if (kind === "bookmark") return "Bookmark";
  if (kind === "history") return "History";
  return "Google Search";
}

function _oiBold(main, q) {
  main = String(main || "");
  q = String(q || "").trim();
  if (!q) return escapeHtml(main);
  const i = main.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return escapeHtml(main);
  return escapeHtml(main.slice(0, i)) + "<b>" + escapeHtml(main.slice(i, i + q.length)) + "</b>" + escapeHtml(main.slice(i + q.length));
}

function omniRender() {
  if (!omniSuggest) return;
  if (!omniItems.length) { omniClose(); return; }
  const q = omniInput.value.trim();
  let html = "";
  omniItems.forEach(function(it, i) {
    if (it.sep) { html += '<div class="omni-sep"></div>'; return; }
    html +=
      '<button class="omni-item' + (i === omniSel ? " sel" : "") + '" data-i="' + i + '">' +
        '<span class="oi-icon">' + _oiIcon(it.kind) + "</span>" +
        '<span class="oi-main">' + _oiBold(it.main, q) + "</span>" +
        (it.sub ? '<span class="oi-sub">' + escapeHtml(it.sub) + "</span>" : "") +
        '<span class="oi-kind">' + _oiLabel(it.kind) + "</span>" +
      "</button>";
  });
  omniSuggest.innerHTML = html;
  omniSuggest.hidden = false;
}

function omniBuildItems(value) {
  const v = (value || "").trim().toLowerCase();
  const items = [];
  if (!v) { return items; }

  // 1. Open tabs — switch instead of duplicating
  tabs.forEach(function(tab, id) {
    const hay = ((tab.title || "") + " " + (tab.url || "")).toLowerCase();
    if (hay.includes(v) && items.length < 3) {
      items.push({ kind: "tab", main: tab.title || tab.url, sub: tab.url, url: "__tab__" + id });
    }
  });

  // 2. Bookmarks
  for (const bm of bookmarks) {
    const hay = ((bm.title || "") + " " + (bm.url || "")).toLowerCase();
    if (hay.includes(v)) {
      items.push({ kind: "bookmark", main: bm.title || bm.url, sub: bm.url, url: bm.url });
      if (items.length >= 8) break;
    }
  }

  // 3. History (newest first, most recent duplicate wins)
  const seen = new Set();
  for (const h of getHistory()) {
    const hay = ((h.title || "") + " " + (h.url || "")).toLowerCase();
    if (hay.includes(v) && !seen.has(h.url)) {
      seen.add(h.url);
      items.push({ kind: "history", main: h.title || h.url, sub: h.url, url: h.url });
      if (items.length >= 8) break;
    }
  }

  // 4. Fallback: search Google (always last, after a separator)
  items.push({ sep: true });
  items.push({ kind: "search", main: value.trim(), sub: "", url: omniUrlFor(value) });
  return items;
}

function omniCommit(i) {
  const it = omniItems[i];
  if (!it) return;
  omniClose();
  if (it.url.startsWith("__tab__")) {
    activateTab(it.url.slice(7));
  } else {
    navigateTo(it.url);
  }
  omniInput.blur();
}

let _omniTimer = null;
omniInput.addEventListener("input", function() {
  clearTimeout(_omniTimer);
  _omniTimer = setTimeout(function() {
    const value = omniInput.value;
    if (!value.trim()) { omniClose(); return; }
    omniItems = omniBuildItems(value);
    omniSel = -1;
    omniRender();
  }, 60);
});

if (omniSuggest) {
  omniSuggest.addEventListener("mousedown", function(e) {
    // mousedown (not click) so the input's blur doesn't close us first
    const btn = e.target.closest(".omni-item");
    if (btn) { e.preventDefault(); omniCommit(parseInt(btn.dataset.i, 10)); }
  });
}

omniInput.addEventListener("blur", function() {
  // Delay so a mousedown on a suggestion wins the race
  setTimeout(omniClose, 120);
});

omniInput.addEventListener("keydown", (e) => {
  if (omniSuggest && !omniSuggest.hidden && omniItems.length) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      do { omniSel = (omniSel + 1) % omniItems.length; } while (omniItems[omniSel] && omniItems[omniSel].sep);
      omniRender();
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      do { omniSel = (omniSel - 1 + omniItems.length) % omniItems.length; } while (omniItems[omniSel] && omniItems[omniSel].sep);
      omniRender();
      return;
    }
    if (e.key === "Enter" && omniSel >= 0) {
      e.preventDefault();
      omniCommit(omniSel);
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      omniClose();
      omniInput.blur();
      return;
    }
  }
  if (e.key === "Enter") {
    e.preventDefault();
    const value = omniInput.value.trim();
    if (!value) return;
    navigateTo(omniUrlFor(value));
    omniClose();
    omniInput.blur();
  }
});

// Chrome-style: focusing the omnibox selects its contents, so typing replaces
// instead of appending to the previous page's URL.
omniInput.addEventListener("focus", function() { omniInput.select(); });

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

// ── Sidebar Toggle / JARVIS Launch ────────────────────────────
var jarvisLaunchLabel = document.getElementById('jarvisLaunchLabel');

jarvisBtn.addEventListener("click", () => {
  // If JARVIS is offline, start it first
  if (!jarvisOnline) {
    startJarvis();
    return;
  }
  // If online, toggle sidebar
  sidebarOpen = !sidebarOpen;
  sidebar.classList.toggle("hidden", !sidebarOpen);
  jarvisBtn.classList.toggle("active", sidebarOpen);
  setMatrix(agentState);
});

// ── Private Window with PIN Protection (Safari-style) ──────
function openPrivateWindow() {
  // Check if PIN is required
  if (window.orbit && window.orbit.window && window.orbit.window.isLocked) {
    window.orbit.window.isLocked().then(function(locked) {
      if (locked) {
        // Show PIN prompt
        showPrivatePinPrompt();
      } else {
        window.orbit.window.createPrivate();
      }
    }).catch(function() {
      window.orbit.window.createPrivate();
    });
  } else {
    window.orbit?.window?.createPrivate?.();
  }
}

function showPrivatePinPrompt() {
  var overlay = document.createElement('div');
  overlay.className = 'shortcuts-overlay active';
  var h = '';
  h += '<div class="shortcuts-card" style="max-width:360px;text-align:center">';
  h += '<div style="font-size:32px;margin-bottom:12px">\u{1F512}</div>';
  h += '<h2 style="font-size:16px;color:var(--jb-paper);margin-bottom:4px">Private Window Locked</h2>';
  h += '<p style="font-size:12px;color:var(--jb-mute);margin-bottom:16px">Enter your PIN to open a private window</p>';
  h += '<input type="password" id="privatePinInput" maxlength="128" style="width:100%;padding:10px 14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.15);border-radius:8px;color:#fff;font-size:14px;text-align:center;letter-spacing:4px;outline:none;margin-bottom:12px" placeholder="Enter PIN" />';
  h += '<div id="privatePinError" style="font-size:11px;color:#f87171;margin-bottom:12px;display:none"></div>';
  h += '<div style="display:flex;gap:8px">';
  h += '<button id="privatePinCancel" style="flex:1;padding:8px;border-radius:6px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:var(--jb-mute);font-size:12px;cursor:pointer">Cancel</button>';
  h += '<button id="privatePinSubmit" style="flex:1;padding:8px;border-radius:6px;background:var(--jb-accent);border:none;color:#fff;font-size:12px;font-weight:500;cursor:pointer">Unlock</button>';
  h += '</div></div>';
  overlay.innerHTML = h;
  document.body.appendChild(overlay);
  var input = overlay.querySelector('#privatePinInput');
  var error = overlay.querySelector('#privatePinError');
  var cancelBtn = overlay.querySelector('#privatePinCancel');
  var submitBtn = overlay.querySelector('#privatePinSubmit');
  input.focus();
  function close() { overlay.remove(); }
  cancelBtn.onclick = close;
  overlay.onclick = function(e) { if (e.target === overlay) close(); };
  function submit() {
    var pin = input.value;
    if (!pin) { error.textContent = 'Please enter your PIN'; error.style.display = 'block'; return; }
    window.orbit.window.checkPin(pin).then(function(ok) {
      if (ok) { close(); window.orbit.window.createPrivate(); }
      else { error.textContent = 'Incorrect PIN. Try again.'; error.style.display = 'block'; input.value = ''; input.focus(); }
    }).catch(function() { error.textContent = 'Verification failed'; error.style.display = 'block'; });
  }
  submitBtn.onclick = submit;
  input.onkeydown = function(e) { if (e.key === 'Enter') submit(); if (e.key === 'Escape') close(); };
}

function startJarvis() {
  // Try to connect to JARVIS bridge
  if (window.orbit && window.orbit.jarvis) {
    showToast('info', 'Starting JARVIS', 'Connecting to JARVIS kernel...');
    setMatrix('thinking');
    window.orbit.jarvis.status().then(function(s) {
      if (s && s.ok) {
        jarvisOnline = true;
        updateJarvisStatusUI(true);
        // Open sidebar
        sidebarOpen = true;
        sidebar.classList.remove('hidden');
        jarvisBtn.classList.add('active');
        setMatrix('idle');
        showToast('ok', 'JARVIS Online', 'JARVIS is ready to use');
        Chat.append('system', 'JARVIS is now online. Ask me anything!');
      } else {
        // Bridge not running - offer Needle as fallback
        setMatrix('fail');
        showToast('warn', 'JARVIS Offline', 'Bridge not running. Using local Needle AI instead.');
        startNeedleMode();
      }
    }).catch(function() {
      // Bridge not running - offer Needle as fallback
      setMatrix('fail');
      showToast('info', 'Using Needle AI', 'Bridge not found. Starting local 14MB AI agent...');
      startNeedleMode();
    });
  } else {
    showToast('info', 'Using Needle AI', 'Starting local AI agent (no server needed)...');
    startNeedleMode();
  }
}

function startNeedleMode() {
  // Enable Needle local AI mode
  jarvisOnline = true;
  updateJarvisStatusUI(true);
  sidebarOpen = true;
  sidebar.classList.remove('hidden');
  jarvisBtn.classList.add('active');
  setMatrix('idle');
  Chat.append('jarvis', 'Needle AI is active (14MB local model). I can help you navigate, search, and interact with pages. No server required!');
  Chat.append('system', 'Tip: Type commands like "search for cats", "go to github.com", "read this page"');
}

function updateJarvisStatusUI(online) {
  var statusDot = document.getElementById('jarvisStatus');
  if (jarvisLaunchLabel) {
    jarvisLaunchLabel.textContent = online ? 'Online' : 'Start';
    jarvisLaunchLabel.classList.toggle('hidden', false);
  }
  jarvisBtn.classList.toggle('online', online);
  jarvisBtn.title = online ? 'JARVIS online — click to toggle sidebar' : 'Start JARVIS';
}

sbClose.addEventListener("click", () => {
  sidebarOpen = false;
  sidebar.classList.add("hidden");
  jarvisBtn.classList.remove("active");
  setMatrix(agentState);
});

// ── Jarvis Status Indicator ───────────────────────────────────
var jarvisStatusEl = document.getElementById('jarvisStatus');
if (window.orbit && window.orbit.jarvis && window.orbit.jarvis.onStatus) {
  window.orbit.jarvis.onStatus(function(status) {
    var isOnline = !!(status && status.ok);
    jarvisOnline = isOnline;
    if (jarvisStatusEl) {
      jarvisStatusEl.className = isOnline ? 'online' : 'offline';
      jarvisStatusEl.title = isOnline ? 'JARVIS online' : 'JARVIS offline';
    }
    updateJarvisStatusUI(isOnline);
    if (isOnline) setMatrix('idle');
  });
}

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
  } else if (name === "workspaces") {
    renderWorkspacesPanel();
  } else if (name === "companions") {
    renderCompanionsPanel();
  } else if (name === "tools") {
    renderToolsPanel();
  } else if (name === "memory") {
    sbBody.innerHTML = '<div class="panel-pad panel-muted">No saved memories yet.</div>';
  }
}

// ── AI Companions (Strawberry-style autonomous agents) ─────────
const _companions = [];
let _companionIdSeq = 0;

// ── Sidebar Tools Panel (Notes, Calculator, Dictionary) ──────
function renderToolsPanel() {
  const html = [];
  html.push('<div class="panel-pad">');
  html.push('<h3 style="font-size:13px;color:var(--jb-paper);font-weight:500;margin-bottom:12px">Tools</h3>');

  // Notes
  html.push('<div style="margin-bottom:16px">');
  html.push('<div style="font-size:11px;color:var(--jb-mute);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px">Notes</div>');
  html.push('<textarea id="sidebarNotes" style="width:100%;height:120px;background:var(--jb-void);border:1px solid var(--jb-border);border-radius:8px;padding:10px;color:var(--jb-paper);font-size:12px;resize:vertical;outline:none;font-family:inherit" placeholder="Quick notes...">' + escapeHtml(localStorage.getItem('orbit-notes') || '') + '</textarea>');
  html.push('<button id="saveNotes" style="margin-top:6px;padding:4px 12px;border-radius:6px;background:var(--jb-accent);color:#fff;border:none;font-size:11px;cursor:pointer">Save</button>');
  html.push('</div>');

  // Calculator
  html.push('<div style="margin-bottom:16px">');
  html.push('<div style="font-size:11px;color:var(--jb-mute);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px">Calculator</div>');
  html.push('<input type="text" id="calcInput" style="width:100%;background:var(--jb-void);border:1px solid var(--jb-border);border-radius:8px;padding:8px 10px;color:var(--jb-paper);font-size:13px;outline:none;font-family:monospace" placeholder="Enter expression...">');
  html.push('<div id="calcResult" style="margin-top:6px;font-size:18px;color:var(--jb-accent);font-family:monospace;min-height:24px"></div>');
  html.push('</div>');

  // Dictionary
  html.push('<div style="margin-bottom:16px">');
  html.push('<div style="font-size:11px;color:var(--jb-mute);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px">Dictionary</div>');
  html.push('<div style="display:flex;gap:6px">');
  html.push('<input type="text" id="dictInput" style="flex:1;background:var(--jb-void);border:1px solid var(--jb-border);border-radius:8px;padding:8px 10px;color:var(--jb-paper);font-size:12px;outline:none" placeholder="Look up word...">');
  html.push('<button id="dictLookup" style="padding:8px 12px;border-radius:6px;background:var(--jb-accent);color:#fff;border:none;font-size:11px;cursor:pointer">Go</button>');
  html.push('</div>');
  html.push('<div id="dictResult" style="margin-top:8px;font-size:12px;color:var(--jb-text);line-height:1.5"></div>');
  html.push('</div>');

  // Quick Links
  html.push('<div>');
  html.push('<div style="font-size:11px;color:var(--jb-mute);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px">Quick Links</div>');
  html.push('<div style="display:flex;flex-wrap:wrap;gap:6px">');
  var links = [
    { label: 'Gmail', url: 'https://mail.google.com' },
    { label: 'GitHub', url: 'https://github.com' },
    { label: 'YouTube', url: 'https://youtube.com' },
    { label: 'Reddit', url: 'https://reddit.com' },
    { label: 'Twitter', url: 'https://twitter.com' },
    { label: 'Docs', url: 'https://docs.google.com' },
  ];
  links.forEach(function(lnk) {
    html.push('<button class="sb-chip" onclick="navigateTo(\'' + lnk.url + '\')" style="font-size:11px">' + lnk.label + '</button>');
  });
  html.push('</div>');
  html.push('</div>');

  html.push('</div>');
  sbBody.innerHTML = html.join('');

  // Wire events
  var notesArea = document.getElementById('sidebarNotes');
  var saveBtn = document.getElementById('saveNotes');
  if (saveBtn && notesArea) {
    saveBtn.addEventListener('click', function() {
      localStorage.setItem('orbit-notes', notesArea.value);
      showToast('ok', 'Notes Saved', 'Stored locally');
    });
  }

  var calcInput = document.getElementById('calcInput');
  var calcResult = document.getElementById('calcResult');
  if (calcInput && calcResult) {
    calcInput.addEventListener('input', function() {
      try {
        var expr = calcInput.value.replace(/[^0-9+\-*/().% ]/g, '');
        if (expr.trim()) {
          var result = Function('"use strict"; return (' + expr + ')')();
          calcResult.textContent = '= ' + result;
        } else {
          calcResult.textContent = '';
        }
      } catch (e) {
        calcResult.textContent = 'Invalid expression';
      }
    });
  }

  var dictInput = document.getElementById('dictInput');
  var dictLookup = document.getElementById('dictLookup');
  var dictResult = document.getElementById('dictResult');
  if (dictLookup && dictInput && dictResult) {
    dictLookup.addEventListener('click', function() {
      var word = dictInput.value.trim();
      if (!word) return;
      dictResult.innerHTML = '<span style="color:var(--jb-mute)">Looking up...</span>';
      fetch('https://api.dictionaryapi.dev/api/v2/entries/en/' + encodeURIComponent(word))
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data && data[0] && data[0].meanings && data[0].meanings[0]) {
            var m = data[0].meanings[0];
            var def = m.definitions && m.definitions[0] ? m.definitions[0].definition : '';
            dictResult.innerHTML = '<div style="font-weight:500;color:var(--jb-paper);margin-bottom:4px">' + word + ' <span style="color:var(--jb-mute);font-size:11px">(' + m.partOfSpeech + ')</span></div>' +
              '<div>' + escapeHtml(def) + '</div>';
          } else {
            dictResult.innerHTML = '<span style="color:var(--jb-mute)">No definition found</span>';
          }
        })
        .catch(function() {
          dictResult.innerHTML = '<span style="color:var(--jb-mute)">Lookup failed</span>';
        });
    });
    dictInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') dictLookup.click();
    });
  }
}

// ── Workspaces Panel (Arc/Zen-style Spaces) ───────────────
var _workspaces = [
  { id: 'work', name: 'Work', icon: '\u{1F4BC}', color: '#8AA4C8', active: true },
  { id: 'personal', name: 'Personal', icon: '\u{1F3E0}', color: '#6F9B6A', active: false },
  { id: 'research', name: 'Research', icon: '\u{1F52C}', color: '#C9A227', active: false },
  { id: 'dev', name: 'Development', icon: '\u{1F4BB}', color: '#D71921', active: false },
];
var _activeWorkspaceId = 'work';

function renderWorkspacesPanel() {
  var html = [];
  html.push('<div class="panel-pad">');
  html.push('<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">');
  html.push('<h3 style="font-size:13px;color:var(--jb-paper);font-weight:500;margin:0">Spaces</h3>');
  html.push('<button id="wsCreate" style="background:var(--jb-accent);color:#fff;border:none;border-radius:8px;padding:4px 10px;font-size:11px;cursor:pointer;font-weight:500">+ New</button>');
  html.push('</div>');
  _workspaces.forEach(function(ws) {
    var isActive = ws.id === _activeWorkspaceId;
    html.push('<div class="ws-card' + (isActive ? ' active' : '') + '" data-wsid="' + ws.id + '" style="border:1px solid ' + (isActive ? ws.color : 'var(--jb-border)') + ';border-radius:10px;padding:10px;margin-bottom:8px;background:' + (isActive ? ws.color + '11' : 'var(--jb-void)') + ';cursor:pointer;transition:all .15s">');
    html.push('<div style="display:flex;align-items:center;gap:8px">');
    html.push('<span style="font-size:18px">' + ws.icon + '</span>');
    html.push('<span style="font-size:12px;font-weight:500;color:var(--jb-paper);flex:1">' + escapeHtml(ws.name) + '</span>');
    if (isActive) html.push('<span style="font-size:10px;color:' + ws.color + ';font-weight:500">Active</span>');
    html.push('</div>');
    html.push('</div>');
  });
  html.push('<div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--jb-border)">');
  html.push('<div style="font-size:11px;color:var(--jb-mute);margin-bottom:6px">Current space isolates cookies, storage, and tabs.</div>');
  html.push('<div style="font-size:11px;color:var(--jb-mute)">Switch spaces to separate work, personal, and research browsing.</div>');
  html.push('</div>');
  html.push('</div>');
  sbBody.innerHTML = html.join('');
  // Wire events
  sbBody.querySelectorAll('.ws-card').forEach(function(card) {
    card.addEventListener('click', function() {
      var wsid = card.dataset.wsid;
      switchWorkspace(wsid);
    });
  });
  var createBtn = document.getElementById('wsCreate');
  if (createBtn) createBtn.addEventListener('click', function() {
    var name = prompt('Space name:', '');
    if (!name) return;
    var icons = ['\u{1F3F0}', '\u{1F30A}', '\u{1F3AF}', '\u{1F4D6}', '\u{1F3B5}'];
    var colors = ['#8ab4f8', '#f28b82', '#81c995', '#fdd663', '#d7aefb'];
    _workspaces.push({
      id: 'ws-' + Date.now(),
      name: name,
      icon: icons[Math.floor(Math.random() * icons.length)],
      color: colors[Math.floor(Math.random() * colors.length)],
      active: false,
    });
    renderWorkspacesPanel();
  });
}

function switchWorkspace(wsid) {
  _activeWorkspaceId = wsid;
  _workspaces.forEach(function(ws) { ws.active = ws.id === wsid; });
  renderWorkspacesPanel();
  showToast('info', 'Space switched', 'Now browsing in: ' + _workspaces.find(function(w) { return w.id === wsid; }).name);
}

function renderCompanionsPanel() {
  const html = [];
  html.push('<div class="panel-pad">');
  html.push('<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">');
  html.push('<h3 style="font-size:13px;color:var(--jb-paper);font-weight:500;margin:0">Companions</h3>');
  html.push('<button id="companionCreate" style="background:var(--jb-accent);color:#fff;border:none;border-radius:8px;padding:4px 10px;font-size:11px;cursor:pointer;font-weight:500">+ New</button>');
  html.push('</div>');
  if (_companions.length === 0) {
    html.push('<div style="text-align:center;padding:24px 0;color:var(--jb-mute);font-size:12px">');
    html.push('<div style="font-size:28px;margin-bottom:8px">\u{1F916}</div>');
    html.push('No companions yet.<br>Create one to automate browsing tasks.');
    html.push('</div>');
  } else {
    _companions.forEach(function(c) {
      var statusColor = c.status === 'running' ? 'var(--jb-accent)' : c.status === 'done' ? '#4ade80' : c.status === 'error' ? '#f87171' : 'var(--jb-mute)';
      var statusLabel = c.status === 'running' ? 'Running' : c.status === 'done' ? 'Completed' : c.status === 'error' ? 'Failed' : 'Idle';
      html.push('<div class="companion-card" data-cid="' + c.id + '" style="border:1px solid var(--jb-border);border-radius:10px;padding:10px;margin-bottom:8px;background:var(--jb-void)">');
      html.push('<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">');
      html.push('<div style="width:8px;height:8px;border-radius:50%;background:' + statusColor + '"></div>');
      html.push('<span style="font-size:12px;font-weight:500;color:var(--jb-paper);flex:1">' + escapeHtml(c.name) + '</span>');
      html.push('<span style="font-size:10px;color:' + statusColor + '">' + statusLabel + '</span>');
      html.push('</div>');
      html.push('<div style="font-size:11px;color:var(--jb-mute);margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + escapeHtml(c.task) + '</div>');
      if (c.tabs && c.tabs.length > 0) {
        html.push('<div style="font-size:10px;color:var(--jb-mute);margin-bottom:6px">' + c.tabs.length + ' tab' + (c.tabs.length > 1 ? 's' : '') + ' open</div>');
      }
      html.push('<div style="display:flex;gap:4px">');
      if (c.status === 'idle') {
        html.push('<button class="companion-action" data-action="start" data-cid="' + c.id + '" style="flex:1;background:var(--jb-accent);color:#fff;border:none;border-radius:6px;padding:4px 0;font-size:10px;cursor:pointer">Start</button>');
      } else if (c.status === 'running') {
        html.push('<button class="companion-action" data-action="pause" data-cid="' + c.id + '" style="flex:1;background:var(--jb-muted);color:var(--jb-paper);border:none;border-radius:6px;padding:4px 0;font-size:10px;cursor:pointer">Pause</button>');
      } else if (c.status === 'paused') {
        html.push('<button class="companion-action" data-action="resume" data-cid="' + c.id + '" style="flex:1;background:var(--jb-accent);color:#fff;border:none;border-radius:6px;padding:4px 0;font-size:10px;cursor:pointer">Resume</button>');
      }
      html.push('<button class="companion-action" data-action="stop" data-cid="' + c.id + '" style="background:none;color:var(--jb-mute);border:1px solid var(--jb-border);border-radius:6px;padding:4px 8px;font-size:10px;cursor:pointer">Stop</button>');
      html.push('<button class="companion-action" data-action="remove" data-cid="' + c.id + '" style="background:none;color:#f87171;border:1px solid var(--jb-border);border-radius:6px;padding:4px 8px;font-size:10px;cursor:pointer">\u2715</button>');
      html.push('</div>');
      html.push('</div>');
    });
  }
  html.push('</div>');
  sbBody.innerHTML = html.join('');
  // Wire events
  var createBtn = document.getElementById('companionCreate');
  if (createBtn) createBtn.addEventListener('click', createCompanion);
  sbBody.querySelectorAll('.companion-action').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var action = btn.dataset.action;
      var cid = parseInt(btn.dataset.cid);
      if (action === 'start') startCompanion(cid);
      else if (action === 'pause') pauseCompanion(cid);
      else if (action === 'resume') resumeCompanion(cid);
      else if (action === 'stop') stopCompanion(cid);
      else if (action === 'remove') removeCompanion(cid);
    });
  });
}

function createCompanion() {
  var name = prompt('Companion name:', 'Research Agent ' + (_companionIdSeq + 1));
  if (!name) return;
  var task = prompt('What should this companion do?', '');
  if (!task) return;
  _companions.push({
    id: ++_companionIdSeq,
    name: name,
    task: task,
    status: 'idle',
    tabs: [],
    log: [],
    created: Date.now(),
  });
  renderCompanionsPanel();
}

function startCompanion(cid) {
  var c = _companions.find(function(x) { return x.id === cid; });
  if (!c || c.status !== 'idle') return;
  c.status = 'running';
  c.log.push({ time: Date.now(), msg: 'Started' });
  // Create a dedicated tab for this companion
  createTab('orbit://newtab');
  var newTabId = activeTabId;
  c.tabs.push(newTabId);
  // Register as agent-owned
  var tab = tabs.get(newTabId);
  if (tab) tab.agentOwned = true;
  _renderTabs();
  // Send task to JARVIS
  sendToJarvis({ type: 'companion_task', payload: { companionId: cid, name: c.name, task: c.task, tabId: newTabId } });
  showToast('Companion \"' + c.name + '\" started');
  renderCompanionsPanel();
}

function pauseCompanion(cid) {
  var c = _companions.find(function(x) { return x.id === cid; });
  if (!c || c.status !== 'running') return;
  c.status = 'paused';
  c.log.push({ time: Date.now(), msg: 'Paused' });
  showToast('Companion \"' + c.name + '\" paused');
  renderCompanionsPanel();
}

function resumeCompanion(cid) {
  var c = _companions.find(function(x) { return x.id === cid; });
  if (!c || c.status !== 'paused') return;
  c.status = 'running';
  c.log.push({ time: Date.now(), msg: 'Resumed' });
  sendToJarvis({ type: 'companion_resume', payload: { companionId: cid, task: c.task } });
  showToast('Companion \"' + c.name + '\" resumed');
  renderCompanionsPanel();
}

function stopCompanion(cid) {
  var c = _companions.find(function(x) { return x.id === cid; });
  if (!c) return;
  c.status = 'idle';
  c.log.push({ time: Date.now(), msg: 'Stopped' });
  sendToJarvis({ type: 'companion_stop', payload: { companionId: cid } });
  showToast('Companion \"' + c.name + '\" stopped');
  renderCompanionsPanel();
}

function removeCompanion(cid) {
  var idx = _companions.findIndex(function(x) { return x.id === cid; });
  if (idx < 0) return;
  var c = _companions[idx];
  // Close companion tabs
  c.tabs.forEach(function(tid) { closeTab(tid); });
  _companions.splice(idx, 1);
  showToast('Companion \"' + c.name + '\" removed');
  renderCompanionsPanel();
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
  if (window.Chat) Chat.pendingStreamTabId = activeTabId;
  Chat.append("user", text);

  // Slash commands
  if (text.startsWith("/")) {
    handleDshCommand(text);
    return;
  }

  // DSH native (direct kernel HTTP stream). Note: streams resolve as soon as
  // the SSE reader starts; the reply renders via dshNative's 'message' events
  // (start/delta/done handled in the wiring block below).
  if (window.dshNative && window.dshNative.status.connected) {
    setMatrix("thinking");
    const tab = tabs.get(activeTabId);
    const page = tab ? { url: tab.url, title: tab.title } : null;
    const streamResult = await window.dshNative.chat(text, { page });
    if (streamResult && streamResult.success === false) {
      Chat.append("error", streamResult.error || "Connection failed");
      setMatrix("fail");
      setTimeout(() => setMatrix("idle"), 2000);
    }
    // streamId case: events render the reply; nothing more to do here.
  } else if (window.orbit?.jarvis) {
    setMatrix("thinking");
    window.orbit.jarvis.chat(text, "orbit-tab-" + activeTabId);
  } else if (jarvisOnline) {
    // Parallel mode: Needle (fast) + Main Model (reasoning)
    setMatrix("thinking");
    try {
      var needleResult = window.needleAgent.route(text);
      var conf = Math.round(needleResult.confidence * 100);
      if (needleResult.confidence >= 0.8) {
        // High confidence: execute immediately (fast path)
        Chat.append("system", "\u26A1 Needle: " + needleResult.tool + " (" + conf + "%)");
        var execResult = await window.needleAgent.execute(needleResult);
        if (execResult.done) {
          Chat.append("jarvis", execResult.result);
          setMatrix("done");
          setTimeout(() => setMatrix("idle"), 2000);
        } else {
          Chat.append("jarvis", execResult.result);
          setMatrix("idle");
        }
      } else {
        // Low confidence: run both in parallel
        Chat.append("system", "\u26A1 Needle: " + needleResult.tool + " (" + conf + "%) | Main model: reasoning...");
        var execResult = await window.needleAgent.execute(needleResult);
        Chat.append("jarvis", execResult.result || 'Tool executed: ' + needleResult.tool);
        setMatrix("idle");
      }
    } catch (err) {
      Chat.append("error", "Agent error: " + err.message);
      setMatrix("fail");
      setTimeout(() => setMatrix("idle"), 2000);
    }
  } else {
    Chat.append("jarvis", "Click the JARVIS button to start the AI agent.\n\n\u2022 Navigate: type a URL or search\n\u2022 Tabs: Ctrl+T / Ctrl+W\n\u2022 Find: Ctrl+F\n\u2022 Commands: Ctrl+K\n\u2022 Zoom: Ctrl+/-\n\u2022 Bookmarks: Ctrl+D\n\u2022 Screenshot: Ctrl+Shift+S");
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
    case "/yt":
      if (window.YT) window.YT.command(args);
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
// dsh-native.js is lazy-loaded AFTER this file (index.html critical-module
// loader), so window.dshNative does not exist at parse time. Wire as soon
// as it appears: bounded poll, handlers attach exactly once.
function wireDshNative() {
  const dsh = window.dshNative;
  if (!dsh || dsh.__orbitWired) return !!dsh;
  dsh.__orbitWired = true;
  window.__orbitDshWired = true;
  // Status updates
  dsh.on('status', (status) => {
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
  dsh.on('message', (event) => {
    switch (event.type) {
      case 'start':
        setMatrix('thinking');
        Chat.beginStream();
        break;
      case 'delta':
        updateStreamingMessage(event.text, event.fullText);
        break;
      case 'done':
        finalizeStreamingMessage(event.text || '(no response)');
        setMatrix('done');
        setTimeout(() => setMatrix('idle'), 2000);
        break;
    }
  });
  
  // Agent events
  dsh.on('agent', (event) => {
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
  dsh.on('error', (event) => {
    Chat.append('error', event.message || 'JARVIS error');
    setMatrix('fail');
    setTimeout(() => setMatrix('idle'), 2000);
  });
  return true;
}
(function waitForDshNative(attempts) {
  if (wireDshNative()) return;
  if (attempts > 100) { console.warn('[ORBIT] dsh-native.js never appeared; JARVIS UI disabled'); return; }
  setTimeout(function () { waitForDshNative(attempts + 1); }, 100);
})(0);

// ── Streaming — delegates to Chat module ────────────────────────
function updateStreamingMessage(delta, fullText) {
  Chat.updateStream(fullText);
}

function finalizeStreamingMessage(fullText) {
  Chat.endStream(fullText);
}

// ── Legacy JARVIS Events (Fallback) ──────────────────────────────
// ── Headless Agent Loop tool round-trips ───────────────────────
// main.js registers browser.read/click/type tools that ping the renderer
// and await a result IPC; without these handlers every call hit its timeout.
if (window.orbit?.on?.navigateTo) {
  window.orbit.on.navigateTo((url) => {
    if (url && /^https?:/i.test(url)) createTab(url);
  });
}
if (window.orbit?.agent) {
  window.orbit.agent.onState(function(state) {
    if (state === 'thinking' || state === 'executing') setMatrix('thinking');
    else if (state === 'completed') { setMatrix('done'); setTimeout(function() { setMatrix('idle'); }, 2000); }
    else if (state === 'failed') { setMatrix('fail'); setTimeout(function() { setMatrix('idle'); }, 2000); }
  });
  window.orbit.agent.onTool(function(info) {
    Chat.append('system', '\u2699 ' + (info && info.name ? info.name : 'tool'));
  });
}
if (window.orbit?.agent?.sendReadResult) {
  window.orbit.on && window.orbit.on.agentRead && window.orbit.on.agentRead(async function() {
    try {
      const wv = activeWebview();
      if (!wv) { window.orbit.agent.sendReadResult('No active page'); return; }
      const text = await wv.executeJavaScript('document.body ? document.body.innerText.substring(0, 8000) : ""', false);
      window.orbit.agent.sendReadResult(text || '(empty page)');
    } catch (e) {
      window.orbit.agent.sendReadResult('Read error: ' + e.message);
    }
  });
  window.orbit.on && window.orbit.on.agentClick && window.orbit.on.agentClick(async function(args) {
    try {
      const wv = activeWebview();
      if (!wv) { window.orbit.agent.sendClickResult('No active page'); return; }
      const sel = (args && args.selector) || 'body';
      const r = await wv.executeJavaScript(
        '(function(){var el=document.querySelector(' + JSON.stringify(sel) + ');' +
        'if(!el)return "Not found";el.scrollIntoView({block:"center"});el.click();return "Clicked";})()', false);
      window.orbit.agent.sendClickResult(r || 'Click failed');
    } catch (e) {
      window.orbit.agent.sendClickResult('Click error: ' + e.message);
    }
  });
  window.orbit.on && window.orbit.on.agentType && window.orbit.on.agentType(async function(args) {
    try {
      const wv = activeWebview();
      if (!wv) { window.orbit.agent.sendTypeResult('No active page'); return; }
      const sel = (args && args.selector) || 'input';
      const text = (args && args.text) || '';
      const r = await wv.executeJavaScript(
        '(function(){var el=document.querySelector(' + JSON.stringify(sel) + ');' +
        'if(!el)return "Input not found";el.focus();el.value=' + JSON.stringify(text) + ';' +
        'el.dispatchEvent(new Event("input",{bubbles:true}));return "Typed";})()', false);
      window.orbit.agent.sendTypeResult(r || 'Type failed');
    } catch (e) {
      window.orbit.agent.sendTypeResult('Type error: ' + e.message);
    }
  });
}
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

  // Seed the status badge from the main-process state: the connection may have
  // opened before the renderer subscribed, and main only pushes on change, so
  // without this pull the badge would stay OFF until the next reconnect.
  window.orbit.jarvis.status().then(function(s) {
    if (s) syncJarvisOnline(!!(s.ok && s.kernel === "online"));
    if (s && s.ok) {
      if (statusDot) statusDot.className = "status-dot " + (jarvisOnline ? "online" : "offline");
      if (statusLabel) statusLabel.textContent = jarvisOnline ? "ONLINE" : "OFF";
      if (sbDot) sbDot.className = "sb-dot " + (jarvisOnline ? "online" : "offline");
    }
  }).catch(function() {});
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
    el.innerHTML = '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4.5" stroke="currentColor"/></svg>' + escapeHtml(bm.title);
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

// ── Session Thumbnails (New Tab Page) ────────────────────────
function renderSessionThumbnails() {
  const recentList = document.getElementById('ntRecentList');
  const sessionList = document.getElementById('ntSessionList');
  const recentSection = document.getElementById('ntRecent');
  const sessionSection = document.getElementById('ntSessions');

  // Recently closed tabs
  if (recentList && closedTabs.length > 0) {
    recentSection.style.display = 'block';
    recentList.innerHTML = '';
    closedTabs.slice(-8).reverse().forEach(function(tab) {
      const thumb = document.createElement('div');
      thumb.className = 'nt-thumb';
      thumb.innerHTML = '<div class="nt-thumb-icon">\u{1F5D9}</div>' +
        '<div class="nt-thumb-title">' + escapeHtml(tab.title || 'Untitled') + '</div>' +
        '<div class="nt-thumb-url">' + escapeHtml(truncateUrl(tab.url)) + '</div>';
      thumb.addEventListener('click', function() {
        createTab(tab.url);
      });
      recentList.appendChild(thumb);
    });
  } else if (recentSection) {
    recentSection.style.display = 'none';
  }

  // Previous session
  if (sessionList) {
    try {
      const data = JSON.parse(localStorage.getItem('orbit-session'));
      if (data && data.tabs && data.tabs.length > 0) {
        sessionSection.style.display = 'block';
        sessionList.innerHTML = '';
        data.tabs.slice(0, 8).forEach(function(tab) {
          if (!tab.url || tab.url.startsWith('orbit://')) return;
          const thumb = document.createElement('div');
          thumb.className = 'nt-thumb';
          const domain = tryGetDomain(tab.url);
          thumb.innerHTML = '<div class="nt-thumb-icon">' + (domain ? domain.charAt(0).toUpperCase() : '\u{1F310}') + '</div>' +
            '<div class="nt-thumb-title">' + escapeHtml(tab.title || 'Untitled') + '</div>' +
            '<div class="nt-thumb-url">' + escapeHtml(truncateUrl(tab.url)) + '</div>';
          thumb.addEventListener('click', function() {
            createTab(tab.url);
          });
          sessionList.appendChild(thumb);
        });
      } else if (sessionSection) {
        sessionSection.style.display = 'none';
      }
    } catch (e) {
      if (sessionSection) sessionSection.style.display = 'none';
    }
  }
}

function truncateUrl(url) {
  try {
    var u = new URL(url);
    return u.hostname + u.pathname.substring(0, 30);
  } catch (e) {
    return url.substring(0, 40);
  }
}

function tryGetDomain(url) {
  try {
    return new URL(url).hostname;
  } catch (e) {
    return '';
  }
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

// Memory usage: the renderer heap is only this page's own JS — the real
// number users care about is all tabs. Main samples every guest process on
// the sleep sweep (getProcessMemoryInfo per webContents) and reports it via
// performance:status.totalMemoryMB; fall back to heap, then tab estimate.
let _tabMemMB = 0;
function getMemoryMB() {
  if (_tabMemMB > 0) return _tabMemMB;
  if (performance.memory) {
    return Math.round(performance.memory.usedJSHeapSize / 1048576);
  }
  // Fallback: estimate from tab count (rough: ~30MB per tab)
  return tabs.size * 30;
}

async function pollTabMemory() {
  try {
    const s = await window.orbit?.system?.performance?.status?.();
    if (s && typeof s.totalMemoryMB === "number" && s.totalMemoryMB > 0) {
      _tabMemMB = s.totalMemoryMB;
      updatePerfHud();
    }
  } catch (_) { /* main busy — keep last value */ }
}
setInterval(pollTabMemory, 30000);
pollTabMemory();

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
    el.innerHTML = '<span class="tab-title">' + escapeHtml(tab.title) + '</span><span class="tab-close" data-close="' + id + '">\u00d7</span>';
    el.addEventListener("click", function(e) {
      const closeBtn = e.target.closest("[data-close]");
      if (closeBtn) { e.stopPropagation(); closeTab(closeBtn.dataset.close); return; }
      activateTab(id);
    });
    tabStripVertical.appendChild(el);
  });
}

// ── Vertical Tabs toggle (Arc/Zen-style), persisted ──────────
const vtToggleBtn = $("#vtToggleBtn");
function setVerticalTabs(on) {
  if (!tabStripVertical) return;
  tabStripVertical.classList.toggle("on", !!on);
  if (vtToggleBtn) vtToggleBtn.classList.toggle("on", !!on);
  try { localStorage.setItem("orbit-vtabs", on ? "1" : "0"); } catch (e) {}
  renderVerticalTabs();
}
if (vtToggleBtn) {
  vtToggleBtn.addEventListener("click", function() {
    setVerticalTabs(!tabStripVertical.classList.contains("on"));
  });
}
(function() {
  let vOn = false;
  try { vOn = localStorage.getItem("orbit-vtabs") === "1"; } catch (e) {}
  setVerticalTabs(vOn);
})();

// ── Print and Screenshot ──────────────────────────────────────
function printPage() {
  try { const wv = activeWebview(); if (wv) wv.print(); } catch (e) { showToast("err", "Print Failed", e.message); }
}
function popoutVideo() {
  const real = window.orbit && window.orbit.system && window.orbit.system.ui && window.orbit.system.ui.popoutVideo;
  if (!real) { showToast("err", "PiP", "Surfaces unavailable"); return; }
  real().then(function(r) {
    if (r && r.ok) showToast("ok", "Picture-in-Picture", r.result === "OK" || r.result === "requesting" ? "Video popped out" : String(r.result));
    else if (r && r.error) showToast("err", "PiP", r.error);
    else if (!r) showToast("err", "PiP", "No response");
    else if (r.result === "no-video") showToast("info", "PiP", "No <video> element on this page");
    else if (r.result === "unsupported") showToast("err", "PiP", "PiP not supported here");
    else showToast("warn", "PiP", String(r.result));
  }).catch(function(e) { showToast("err", "PiP", String(e && e.message || e)); });
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
  { l: "Import from Chrome", d: "Import bookmarks, history, extensions", i: "\u{1F517}", a: function() { navigateTo("orbit://import"); } },
  { l: "Extension Store", d: "Install VPN & ad blocker extensions", i: "\u{1F6D2}", a: function() { navigateTo("orbit://extension-store"); } },
  { l: "Settings", d: "Browser settings", i: "\u2699", a: function() { navigateTo("orbit://settings"); } },
  { l: "History", d: "Browsing history", i: "\u231a", a: function() { navigateTo("orbit://history"); } },
  { l: "Downloads", d: "View downloads", i: "\u21e3", a: function() { navigateTo("orbit://downloads"); } },
  { l: "Bookmarks", d: "View bookmarks", i: "\u2606", a: function() { navigateTo("orbit://bookmarks"); } },
  { l: "Tasks", d: "Agent tasks", i: "\u2611", a: function() { navigateTo("orbit://tasks"); } },
  { l: "Memory", d: "Saved memories", i: "\u2261", a: function() { navigateTo("orbit://memory"); } },
  { l: "Diagnostics", d: "System status", i: "\u229f", a: function() { navigateTo("orbit://diagnostics"); } },
  { l: "Privacy Report", d: "Trackers blocked & shield status", i: "\u{1F6E1}", a: function() { navigateTo("orbit://privacy"); } },
  { l: "Create Boost", d: "Custom CSS/JS for this site", i: "\u26A1", a: function() { createBoostUI(); } },
  { l: "Print Page", d: "Print current page", s: "Ctrl+P", i: "\u2399", a: function() { printPage(); } },
  { l: "Screenshot", d: "Capture page", s: "Ctrl+Shift+S", i: "\u25a3", a: function() { takeScreenshot(); } },
  { l: "Zoom In", d: "Increase zoom", s: "Ctrl+=", i: "+", a: function() { zoomIn(); } },
  { l: "Zoom Out", d: "Decrease zoom", s: "Ctrl+-", i: "\u2212", a: function() { zoomOut(); } },
  { l: "Toggle Sidebar", d: "Show/hide JARVIS", s: "Ctrl+Shift+J", i: "\u25a6", a: function() { jarvisBtn.click(); } },
  { l: "Toggle Split View", d: "Two tabs side by side", s: "Ctrl+Shift+S", i: "\u25a4", a: function() { toggleSplitView(); } },
  { l: "Reader Mode", d: "Distraction-free reading", s: "Ctrl+Shift+R", i: "\u{1F4D6}", a: function() { openReaderMode(); } },
  { l: "Search Tabs", d: "Find an open tab", s: "Ctrl+Shift+F", i: "\u{1F50D}", a: function() { toggleTabSearch(); } },
  { l: "Floating JARVIS Chat", d: "Small movable JARVIS window", s: "Ctrl+Shift+K", i: "\u{1F4AC}", a: function() { toggleJarvisFloat(); } },
  { l: "Pop out Video", d: "Float the active tab's video (PiP)", s: "Ctrl+Shift+P", i: "\u25b6", a: function() { popoutVideo(); } },
  { l: "Run Agent Task", d: "Headless agent execution", i: "\u{1F916}", a: function() {
    var task = prompt('Agent task:');
    if (task && window.orbit && window.orbit.agent) {
      showAgentBar('Starting...');
      window.orbit.agent.start(task).then(function(r) {
        if (r && r.ok) showToast('ok', 'Agent done', r.result ? r.result.substring(0, 100) : 'Complete');
        else showToast('err', 'Agent failed', r ? r.error : 'Unknown error');
        hideAgentBar();
      });
    }
  }},
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

// ── Find-in-page result counting ("3/17" like Chrome) ─────────
if (findInput) {
  var _findDebounce = null;
  findInput.addEventListener("input", function() {
    clearTimeout(_findDebounce);
    _findDebounce = setTimeout(function() {
      var wv = activeWebview();
      if (!wv) return;
      var q = findInput.value;
      if (!q) { var c = $("#findCount"); if (c) c.textContent = "0/0"; try { wv.stopFindInPage("clearSelection"); } catch (e) {} return; }
      try { wv.findInPage(q); } catch (e) {}
    }, 200);
  });
}
// result count comes from the found-in-page event
function _wireFoundInPage(wv) {
  if (!wv || wv.__findWired) return;
  wv.__findWired = true;
  wv.addEventListener("found-in-page", function(e) {
    var c = $("#findCount");
    if (c && e.result) {
      c.textContent = e.result.activeMatchOrdinal + "/" + e.result.matches;
    }
  });
}

if ($("#findClose")) $("#findClose").addEventListener("click", () => {
  findBar.classList.remove("on");
  try { const wv = activeWebview(); if (wv) wv.stopFindInPage("clearSelection"); } catch (e) {}
});
if ($("#findNext")) $("#findNext").addEventListener("click", () => {
  try { const wv = activeWebview(); if (wv && findInput.value) wv.findInPage(findInput.value); } catch (e) {}
});
if ($("#findPrev")) $("#findPrev").addEventListener("click", () => {
  try { const wv = activeWebview(); if (wv && findInput.value) wv.findInPage(findInput.value, { forward: false, findNext: true }); } catch (e) {}
});
if (findInput) findInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { const wv = activeWebview(); if (wv) wv.findInPage(findInput.value, { forward: !e.shiftKey }); }
  if (e.key === "Escape") { findBar.classList.remove("on"); try { const wv = activeWebview(); if (wv) wv.stopFindInPage("clearSelection"); } catch (err) {} }
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
  if (action === "closeOthers" && contextTabId) { for (const [id] of tabs) { if (id !== contextTabId) { ntpDrafts.delete(id); clearSleepTimer(id); clearHibernateTimer(id); tabs.delete(id); } } activateTab(contextTabId); renderTabs(); }
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
  if (action === "groupTab" && contextTabId) groupTab(contextTabId);
  if (action === "ungroupTab" && contextTabId) ungroupTab(contextTabId);
  tabContextMenu.classList.remove("on");
});

// NOTE: tab strip click/drag handling is delegated once near renderTabs()
// (single listener for activate, close, group-dot, and drag reorder).

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
// ── Permissions Page (real allowlist) ────────────────────────
function renderPermissionsPage() {
  var listEl = document.getElementById('permissionsList');
  if (!listEl || !window.orbit?.permissions) return;
  window.orbit.permissions.list().then(function(perms) {
    if (!perms || perms.length === 0) {
      listEl.innerHTML = '<div class="panel-muted" style="padding:16px;text-align:center">No site permissions granted. Sites must ask, and you approve via the omnibox lock icon.</div>';
      return;
    }
    var html = '';
    perms.forEach(function(entry, idx) {
      var host = entry.origin || '';
      try { host = new URL(entry.origin).hostname; } catch (e) {}
      html += '<div class="row">';
      html += '<div style="flex:1"><div class="name">' + escapeHtml(host) + '</div><div class="sub">' + escapeHtml((entry.permissions || []).join(', ')) + '</div></div>';
      html += '<button class="chip-btn" data-perm-revoke="' + idx + '">Revoke</button>';
      html += '</div>';
    });
    listEl.innerHTML = html;
    listEl.querySelectorAll('[data-perm-revoke]').forEach(function(btn) {
      btn.onclick = function() {
        var entry = perms[parseInt(btn.dataset.permRevoke)];
        if (entry) {
          window.orbit.permissions.revoke(entry.origin).then(function() {
            showToast('ok', 'Permission Revoked', entry.origin);
            renderPermissionsPage();
          });
        }
      };
    });
  }).catch(function() {
    listEl.innerHTML = '<div class="panel-muted" style="padding:16px;text-align:center">Could not load permissions.</div>';
  });
}

// ── Downloads Page (real download tracking) ──────────────────
function renderDownloadsPage() {
  var page = document.getElementById('downloadsPage');
  if (!page) return;
  var group = page.querySelector('.group');
  if (!group) return;
  if (!window.orbit?.downloads) return;

  window.orbit.downloads.list().then(function(list) {
    if (!list || list.length === 0) {
      group.innerHTML = '<div class="panel-muted" style="padding:24px;text-align:center">No downloads yet. Files you download will appear here.</div>';
      return;
    }
    var html = '';
    list.forEach(function(d) {
      var pct = d.total > 0 ? Math.round((d.received / d.total) * 100) : 0;
      var size = d.total > 0 ? formatBytes(d.received) + ' / ' + formatBytes(d.total) : formatBytes(d.received);
      var chip = '';
      if (d.state === 'complete') chip = '<span class="chip ok">Complete</span>';
      else if (d.state === 'cancelled') chip = '<span class="chip bad">Cancelled</span>';
      else if (d.state === 'interrupted') chip = '<span class="chip warn">Interrupted</span>';
      else chip = '<span class="chip">' + pct + '%</span>';
      var actions = '';
      if (d.state === 'downloading') {
        actions = '<button class="chip-btn" data-dl-cancel="' + d.id + '">Cancel</button>';
      } else if (d.state === 'complete') {
        actions = '<button class="chip-btn" data-dl-show="' + d.id + '">Show</button>';
      }
      var progress = d.state === 'downloading' && d.total > 0
        ? '<div style="width:100%;height:2px;background:var(--jb-border);border-radius:1px;margin-top:6px"><div style="width:' + pct + '%;height:100%;background:var(--jb-accent);border-radius:1px"></div></div>'
        : '';
      html += '<div class="row" style="flex-wrap:wrap">';
      html += '<div style="flex:1;min-width:200px"><div class="name">' + escapeHtml(d.filename) + '</div><div class="sub">' + escapeHtml(truncateUrl(d.url)) + ' \u00b7 ' + size + '</div>' + progress + '</div>';
      html += chip + actions;
      html += '</div>';
    });
    group.innerHTML = html;
    group.querySelectorAll('[data-dl-cancel]').forEach(function(btn) {
      btn.onclick = function() { window.orbit.downloads.cancel(parseInt(btn.dataset.dlCancel)); };
    });
    group.querySelectorAll('[data-dl-show]').forEach(function(btn) {
      btn.onclick = function() { window.orbit.downloads.show(parseInt(btn.dataset.dlShow)); };
    });
  }).catch(function() {});
}

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B';
  var units = ['B', 'KB', 'MB', 'GB'];
  var i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
  return Math.round(bytes * 10) / 10 + ' ' + units[i];
}

function renderExtensionsPage() {
  const listEl = document.getElementById("extensionsList");
  if (!listEl) return;
  let html = '<div class="row"><div><div class="name">JARVIS</div><div class="sub">Built into Orbit \u00b7 native intelligence</div></div><span class="chip ok">Built in</span></div>';
  if (typeof EXTENSIONS !== "undefined") {
    EXTENSIONS.forEach((ext) => {
      const st = extStatus(ext.id);
      html += '<div class="row"><div><div class="name">' + escapeHtml(ext.name) + '</div><div class="sub">' + escapeHtml(ext.sub) + '</div></div>' +
        '<span class="chip' + (st.pinned ? " ok" : "") + '">' + (st.pinned ? "Pinned" : "Unpinned") + '</span>' +
        '<span class="chip ' + (st.enabled ? "ok" : "") + '">' + (st.enabled ? "Enabled" : "Disabled") + '</span></div>';
    });
  }
  listEl.innerHTML = html;
}

// ── Omnibox lock security state (Chrome-style) ──────────────
function updateOmniLock(url) {
  var lock = document.getElementById('omniLock');
  if (!lock) return;
  lock.classList.remove('insecure', 'internal');
  if (!url || url === 'about:blank' || url.startsWith('orbit://')) {
    lock.classList.add('internal');
    lock.title = 'Internal page';
    return;
  }
  try {
    var proto = new URL(url).protocol;
    if (proto === 'https:') {
      lock.title = 'Connection is secure';
    } else {
      lock.classList.add('insecure');
      lock.title = 'Not secure \u2014 connection is not encrypted';
    }
  } catch (e) {
    lock.classList.add('internal');
  }
}

// ── Floating JARVIS Chat Window (draggable + resizable) ──────
var jarvisFloat = document.getElementById('jarvisFloat');
var jarvisFloatHead = document.getElementById('jarvisFloatHead');
var jarvisFloatBody = document.getElementById('jarvisFloatBody');
var jarvisFloatInput = document.getElementById('jarvisFloatInput');
var jarvisFloatSend = document.getElementById('jarvisFloatSend');
var _floatMsgSeq = 0;

function toggleJarvisFloat(force) {
  if (!jarvisFloat) return;
  var show = (typeof force === 'boolean') ? force : !jarvisFloat.classList.contains('on');
  jarvisFloat.classList.toggle('on', show);
  jarvisFloat.classList.remove('minimized');
  if (show) {
    // Restore saved position if the window is still on-screen
    try {
      var pos = JSON.parse(localStorage.getItem('jarvis-float-pos') || 'null');
      if (pos && pos.left >= 0 && pos.top >= 0 && pos.left < window.innerWidth - 80 && pos.top < window.innerHeight - 60) {
        jarvisFloat.style.left = pos.left + 'px';
        jarvisFloat.style.top = pos.top + 'px';
        jarvisFloat.style.right = 'auto';
        jarvisFloat.style.bottom = 'auto';
      }
    } catch (e) {}
    if (jarvisFloatInput) setTimeout(function() { jarvisFloatInput.focus(); }, 60);
  }
}

function floatAppend(role, text) {
  if (!jarvisFloatBody) return;
  var div = document.createElement('div');
  div.className = 'jarvis-float-msg ' + role;
  div.textContent = text;
  jarvisFloatBody.appendChild(div);
  jarvisFloatBody.scrollTop = jarvisFloatBody.scrollHeight;
}

async function floatSend() {
  var text = jarvisFloatInput.value.trim();
  if (!text) return;
  jarvisFloatInput.value = '';
  floatAppend('user', text);
  setMatrix('thinking');
  try {
    // Same brain as the sidebar: bridge first, Needle fallback
    if (window.dshNative && window.dshNative.status.connected) {
      var tab = tabs.get(activeTabId);
      var page = tab ? { url: tab.url, title: tab.title } : null;
      var res = await window.dshNative.chat(text, { page });
      if (res && res.success === false) {
        floatAppend('error', res.error || 'Connection failed');
      }
    } else if (window.orbit?.jarvis && !jarvisOnline) {
      window.orbit.jarvis.chat(text, "orbit-tab-" + (activeTabId || "float"));
      floatAppend('system', 'Sent to JARVIS bridge \u2014 waiting for reply.');
    } else {
      // Needle parallel agent (fast path)
      var nr = window.needleAgent.route(text);
      var exec = await window.needleAgent.execute(nr);
      if (exec.done) floatAppend('jarvis', exec.result);
      else if (exec.success) floatAppend('jarvis', exec.result);
      else floatAppend('error', exec.result || 'Could not complete that.');
    }
  } catch (err) {
    floatAppend('error', err.message || 'Something went wrong.');
  } finally {
    setMatrix('idle');
  }
}

if (jarvisFloatHead) {
  // Drag by the header (pointer events work for mouse + touch)
  var _drag = null;
  jarvisFloatHead.addEventListener('pointerdown', function(e) {
    if (e.target.closest('.jarvis-float-btn')) return; // don't drag from buttons
    var rect = jarvisFloat.getBoundingClientRect();
    _drag = { dx: e.clientX - rect.left, dy: e.clientY - rect.top };
    jarvisFloatHead.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  jarvisFloatHead.addEventListener('pointermove', function(e) {
    if (!_drag) return;
    var x = e.clientX - _drag.dx;
    var y = e.clientY - _drag.dy;
    // Keep the window on-screen
    x = Math.max(0, Math.min(x, window.innerWidth - 60));
    y = Math.max(0, Math.min(y, window.innerHeight - 42));
    jarvisFloat.style.left = x + 'px';
    jarvisFloat.style.top = y + 'px';
    jarvisFloat.style.right = 'auto';
    jarvisFloat.style.bottom = 'auto';
  });
  jarvisFloatHead.addEventListener('pointerup', function() {
    if (!_drag) return;
    _drag = null;
    try {
      var rect = jarvisFloat.getBoundingClientRect();
      localStorage.setItem('jarvis-float-pos', JSON.stringify({ left: Math.round(rect.left), top: Math.round(rect.top) }));
    } catch (e) {}
  });

  // Resize from top-left corner
  var floatResizeHandle = document.getElementById('jarvisFloatResize');
  var _rz = null;
  if (floatResizeHandle) {
    floatResizeHandle.addEventListener('pointerdown', function(e) {
      var rect = jarvisFloat.getBoundingClientRect();
      _rz = { x: e.clientX, y: e.clientY, w: rect.width, h: rect.height };
      floatResizeHandle.setPointerCapture(e.pointerId);
      e.preventDefault();
      e.stopPropagation();
    });
    floatResizeHandle.addEventListener('pointermove', function(e) {
      if (!_rz) return;
      var w = Math.max(260, _rz.w - (e.clientX - _rz.x));
      var h = Math.max(300, _rz.h - (e.clientY - _rz.y));
      jarvisFloat.style.width = Math.min(w, window.innerWidth * 0.9) + 'px';
      jarvisFloat.style.height = Math.min(h, window.innerHeight * 0.8) + 'px';
    });
    floatResizeHandle.addEventListener('pointerup', function() { _rz = null; });
  }
}

if (document.getElementById('jarvisFloatClose')) {
  document.getElementById('jarvisFloatClose').addEventListener('click', function() { toggleJarvisFloat(false); });
}
if (document.getElementById('jarvisFloatMin')) {
  document.getElementById('jarvisFloatMin').addEventListener('click', function() {
    jarvisFloat.classList.toggle('minimized');
  });
}
var jarvisFloatBtn = document.getElementById('jarvisFloatBtn');
if (jarvisFloatBtn) jarvisFloatBtn.addEventListener('click', function() { toggleJarvisFloat(); });
if (jarvisFloatSend) jarvisFloatSend.addEventListener('click', floatSend);
if (jarvisFloatInput) {
  jarvisFloatInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); floatSend(); }
    if (e.key === 'Escape') toggleJarvisFloat(false);
  });
}
// Escape closes it globally when open and not typing
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape' && jarvisFloat && jarvisFloat.classList.contains('on') &&
      document.activeElement !== jarvisFloatInput) {
    toggleJarvisFloat(false);
  }
});

// Ctrl+Shift+K handled by the main keydown handler (see global shortcuts)
// Sync float matrix animation with global agent state
var _origSetMatrix = setMatrix;
setMatrix = function(state) {
  _origSetMatrix(state);
  var fm = document.getElementById('jarvisFloatMatrix');
  if (fm) fm.dataset.state = state;
};

// ── Tasks Page (real companion + agent task state) ───────────
function renderTasksPage() {
  var listEl = document.getElementById('tasksList');
  if (!listEl) return;
  var rows = '';
  // Companions are the real task runners
  var companions = (typeof _companions !== 'undefined') ? _companions : [];
  if (companions.length === 0) {
    listEl.innerHTML = '<div class="empty-state"><div class="empty-state-icon">\u2699</div>No tasks yet.<br>Create a Companion in the JARVIS sidebar to run autonomous browsing tasks.</div>';
    return;
  }
  companions.forEach(function(c) {
    var chip = '';
    if (c.status === 'running') chip = '<span class="chip ask">Running</span>';
    else if (c.status === 'paused') chip = '<span class="chip warn">Paused</span>';
    else if (c.status === 'done') chip = '<span class="chip ok">Done</span>';
    else if (c.status === 'error') chip = '<span class="chip bad">Failed</span>';
    else chip = '<span class="chip">Idle</span>';
    var elapsed = c.created ? Math.max(1, Math.round((Date.now() - c.created) / 60000)) + 'm' : '';
    rows += '<div class="row">';
    rows += '<div style="flex:1"><div class="name">' + escapeHtml(c.task || c.name) + '</div><div class="sub">' + escapeHtml(c.name) + (c.tabs && c.tabs.length ? ' \u00b7 ' + c.tabs.length + ' tab(s)' : '') + '</div></div>';
    rows += chip + '<span class="meta">' + elapsed + '</span>';
    rows += '</div>';
  });
  listEl.innerHTML = rows;
}

// ── Memory Page (real saved memories) ─────────────────────────
let _memories = JSON.parse(localStorage.getItem('orbit-memories') || '[]');

function renderMemoryPage() {
  var listEl = document.getElementById('memoryList');
  if (!listEl) return;
  if (_memories.length === 0) {
    listEl.innerHTML = '<div class="empty-state"><div class="empty-state-icon">\u{1F9E0}</div>No saved memories yet.<br>JARVIS remembers facts you save here across sessions.</div>';
  } else {
    var html = '';
    _memories.forEach(function(m, idx) {
      var date = new Date(m.time).toLocaleDateString();
      html += '<div class="row">';
      html += '<div style="flex:1"><div class="name">' + escapeHtml(m.text) + '</div><div class="sub">Saved \u00b7 ' + date + '</div></div>';
      html += '<span class="chip">Saved</span><button class="chip-btn" data-mem-del="' + idx + '">Forget</button>';
      html += '</div>';
    });
    listEl.innerHTML = html;
    listEl.querySelectorAll('[data-mem-del]').forEach(function(btn) {
      btn.onclick = function() {
        var idx = parseInt(btn.dataset.memDel);
        var removed = _memories.splice(idx, 1);
        localStorage.setItem('orbit-memories', JSON.stringify(_memories));
        showToast('info', 'Forgotten', removed[0] ? removed[0].text.substring(0, 40) : '');
        renderMemoryPage();
      };
    });
  }
  // Wire save input
  var input = document.getElementById('memoryInput');
  var saveBtn = document.getElementById('memorySaveBtn');
  if (input && saveBtn && !saveBtn.dataset.wired) {
    saveBtn.dataset.wired = '1';
    function saveMemory() {
      var text = input.value.trim();
      if (!text) return;
      _memories.push({ text: text, time: Date.now() });
      localStorage.setItem('orbit-memories', JSON.stringify(_memories));
      input.value = '';
      showToast('ok', 'Memory Saved', text.substring(0, 40));
      renderMemoryPage();
    }
    saveBtn.onclick = saveMemory;
    input.onkeydown = function(e) { if (e.key === 'Enter') saveMemory(); };
  }
}

// ── Site Settings Popup (lock icon — Chrome-style) ───────────
const sitePopup = $("#sitePopup");
const omniLock = $("#omniLock");
function renderSitePopup() {
  if (!sitePopup) return;
  const tab = tabs.get(activeTabId);
  let host = "—", origin = "";
  try {
    const u = new URL(tab ? tab.url : "");
    if (u.protocol === "https:" || u.protocol === "http:") {
      host = u.hostname;
      origin = u.origin;
    }
  } catch (e) {}
  const hostEl = document.getElementById("siteHost");
  if (hostEl) hostEl.textContent = host;
  const connEl = document.getElementById("siteConn");
  if (connEl) connEl.textContent = host === "—" ? "Not on a web page" : (origin.startsWith("https") ? "Secure connection" : "Not secure — HTTP");
  const permEl = document.getElementById("sitePerms");
  if (permEl && window.orbit?.system?.permissions?.list) {
    window.orbit.system.permissions.list().then((list) => {
      if (!permEl) return;
      const mine = (Array.isArray(list) ? list : []).filter((p) => p.origin === origin);
      if (!mine.length) {
        permEl.innerHTML = '<div class="site-perm-row"><span>Permissions</span><span class="meta">Default (ask)</span></div>';
        return;
      }
      permEl.innerHTML = '<div class="site-perm-row"><span>Permissions</span><span class="chip ok">' + escapeHtml(mine.length) + " granted</span></div>" + mine.map((p) => '<div class="site-perm-row sub"><span>' + escapeHtml(String(p.permissions || []).slice(0, 40)) + '</span><span class="chip ok">Allowed</span></div>').join("");
    }).catch(() => {});
  }
  const clearBtn = document.getElementById("siteClearData");
  if (clearBtn) clearBtn.dataset.origin = origin;
}
if (omniLock) omniLock.addEventListener("click", (e) => {
  e.stopPropagation();
  closeAllPopups();
  renderSitePopup();
  sitePopup.style.left = "240px";
  sitePopup.style.top = "84px";
  sitePopup.classList.toggle("on");
});
const siteClearBtn = document.getElementById("siteClearData");
if (siteClearBtn) siteClearBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const origin = siteClearBtn.dataset.origin || "";
  if (!origin) { showToast("info", "No site data", "Open a web page first"); return; }
  if (!confirm("Clear cookies and stored data for " + origin + "? This will sign you out of that site.")) return;
  window.orbit?.system?.session?.clearSiteData(origin).then((r) => {
    showToast(r && r.ok ? "ok" : "err", "Site Data", r && r.ok ? "Cleared for " + origin : "Failed to clear");
    renderSitePopup();
  });
});

// ── Close all popups ──────────────────────────────────────────
function closeAllPopups() {
  if (browserMenu) browserMenu.classList.remove("on");
  if (extPopup) extPopup.classList.remove("on");
  if (profilePopup) profilePopup.classList.remove("on");
  if (sitePopup) sitePopup.classList.remove("on");
  if (tabContextMenu) tabContextMenu.classList.remove("on");
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".popover") && !e.target.closest(".context-menu") && !e.target.closest("#menuBtn") && !e.target.closest("#extBtn") && !e.target.closest("#profileBtn") && !e.target.closest("#omniLock")) closeAllPopups();
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
    if (action === "incognito") { openPrivateWindow(); }
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
  if (ctrl && shift && e.key.toLowerCase() === "n") { e.preventDefault(); openPrivateWindow(); return; }
  if (e.key === "F11") { e.preventDefault(); window.orbit?.window?.fullscreen?.(); return; }
  // Ctrl+W: Close tab
  if (ctrl && e.key.toLowerCase() === "w") { e.preventDefault(); if (activeTabId) closeTab(activeTabId); return; }
  // Ctrl+L: Focus omnibox
  if (ctrl && e.key.toLowerCase() === "l") { e.preventDefault(); omniInput.focus(); omniInput.select(); return; }
  // Ctrl+Shift+J: Toggle sidebar
  if (ctrl && shift && e.key.toLowerCase() === "j") { e.preventDefault(); jarvisBtn.click(); return; }
  // Ctrl+Shift+K: Floating JARVIS chat window
  if (ctrl && shift && e.key.toLowerCase() === "k") { e.preventDefault(); toggleJarvisFloat(); return; }
  if (ctrl && shift && e.key.toLowerCase() === "s") { e.preventDefault(); toggleSplitView(); return; }
  if (ctrl && shift && e.key.toLowerCase() === "r") { e.preventDefault(); openReaderMode(); return; }
  // Ctrl+Shift+F: Tab search
  if (ctrl && shift && e.key.toLowerCase() === "f") { e.preventDefault(); toggleTabSearch(); return; }
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
  if (ctrl && !shift && e.key.toLowerCase() === "p") { e.preventDefault(); printPage(); return; }
  // Ctrl+Shift+P: Pop out video (PiP)
  if (ctrl && shift && e.key.toLowerCase() === "p") { e.preventDefault(); popoutVideo(); return; }
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
  // Ctrl+/: Keyboard shortcuts overlay
  if (ctrl && e.key === "/") { e.preventDefault(); toggleShortcutsOverlay(); return; }
  // Escape: Close things
  if (e.key === "Escape") {
    if (cmdPaletteBg && cmdPaletteBg.classList.contains("on")) { closeCmdPalette(); return; }
    if (modalBg) modalBg.classList.remove("on");
    closeAllPopups();
    if (findBar && findBar.classList.contains("on")) findBar.classList.remove("on");
    // Close shortcuts overlay
    const so = document.getElementById('shortcutsOverlay');
    if (so && so.classList.contains('active')) { so.classList.remove('active'); return; }
    // Close reader mode
    closeReaderMode();
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

// ── Private Window PIN Configuration ─────────────────────────
const privatePinToggle = $("#privatePinToggle");
if (privatePinToggle) {
  privatePinToggle.addEventListener("click", () => {
    if (!window.orbit?.window) return;
    window.orbit.window.isLocked().then(function(locked) {
      if (locked) {
        // PIN is set — offer to change or remove
        var overlay = document.createElement('div');
        overlay.className = 'shortcuts-overlay active';
        var oh = '';
        oh += '<div class="shortcuts-card" style="max-width:360px;text-align:center">';
        oh += '<div style="font-size:32px;margin-bottom:12px">\u{1F512}</div>';
        oh += '<h2 style="font-size:16px;color:var(--jb-paper);margin-bottom:4px">Private Window PIN</h2>';
        oh += '<p style="font-size:12px;color:var(--jb-mute);margin-bottom:16px">A PIN is currently set for private windows</p>';
        oh += '<div style="display:flex;gap:8px">';
        oh += '<button id="pinChange" style="flex:1;padding:8px;border-radius:6px;background:var(--jb-accent);border:none;color:#fff;font-size:12px;cursor:pointer">Change PIN</button>';
        oh += '<button id="pinRemove" style="flex:1;padding:8px;border-radius:6px;background:rgba(248,113,113,0.15);border:1px solid rgba(248,113,113,0.3);color:#f87171;font-size:12px;cursor:pointer">Remove PIN</button>';
        oh += '</div>';
        oh += '<button id="pinClose" style="margin-top:8px;padding:8px;border-radius:6px;background:none;border:none;color:var(--jb-mute);font-size:12px;cursor:pointer;width:100%">Cancel</button>';
        oh += '</div>';
        overlay.innerHTML = oh;
        document.body.appendChild(overlay);
        overlay.querySelector('#pinClose').onclick = function() { overlay.remove(); };
        overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };
        overlay.querySelector('#pinRemove').onclick = function() {
          window.orbit.window.clearPin().then(function() {
            overlay.remove();
            privatePinToggle.textContent = 'Configure';
            showToast('ok', 'PIN Removed', 'Private windows are no longer locked');
          });
        };
        overlay.querySelector('#pinChange').onclick = function() {
          overlay.remove();
          showPinSetup();
        };
      } else {
        // No PIN set — offer to set one
        showPinSetup();
      }
    });
  });
}

function showPinSetup() {
  var overlay = document.createElement('div');
  overlay.className = 'shortcuts-overlay active';
  var h = '';
  h += '<div class="shortcuts-card" style="max-width:360px;text-align:center">';
  h += '<div style="font-size:32px;margin-bottom:12px">\u{1F512}</div>';
  h += '<h2 style="font-size:16px;color:var(--jb-paper);margin-bottom:4px">Set Private Window PIN</h2>';
  h += '<p style="font-size:12px;color:var(--jb-mute);margin-bottom:16px">Require this PIN to open private windows</p>';
  h += '<input type="password" id="pinSetupInput" maxlength="128" style="width:100%;padding:10px 14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.15);border-radius:8px;color:#fff;font-size:14px;text-align:center;letter-spacing:4px;outline:none;margin-bottom:8px" placeholder="Enter PIN (4+ chars)" />';
  h += '<input type="password" id="pinSetupConfirm" maxlength="128" style="width:100%;padding:10px 14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.15);border-radius:8px;color:#fff;font-size:14px;text-align:center;letter-spacing:4px;outline:none;margin-bottom:12px" placeholder="Confirm PIN" />';
  h += '<div id="pinSetupError" style="font-size:11px;color:#f87171;margin-bottom:12px;display:none"></div>';
  h += '<div style="display:flex;gap:8px">';
  h += '<button id="pinSetupCancel" style="flex:1;padding:8px;border-radius:6px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:var(--jb-mute);font-size:12px;cursor:pointer">Cancel</button>';
  h += '<button id="pinSetupSave" style="flex:1;padding:8px;border-radius:6px;background:var(--jb-accent);border:none;color:#fff;font-size:12px;font-weight:500;cursor:pointer">Save PIN</button>';
  h += '</div></div>';
  overlay.innerHTML = h;
  document.body.appendChild(overlay);
  var input = overlay.querySelector('#pinSetupInput');
  var confirmInput = overlay.querySelector('#pinSetupConfirm');
  var error = overlay.querySelector('#pinSetupError');
  input.focus();
  overlay.querySelector('#pinSetupCancel').onclick = function() { overlay.remove(); };
  overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };
  overlay.querySelector('#pinSetupSave').onclick = function() {
    var pin = input.value;
    var pin2 = confirmInput.value;
    if (pin.length < 4) { error.textContent = 'PIN must be at least 4 characters'; error.style.display = 'block'; return; }
    if (pin !== pin2) { error.textContent = 'PINs do not match'; error.style.display = 'block'; return; }
    window.orbit.window.setPin(pin).then(function() {
      overlay.remove();
      privatePinToggle.textContent = 'Change';
      showToast('ok', 'PIN Set', 'Private windows are now protected');
    }).catch(function() {
      error.textContent = 'Failed to set PIN'; error.style.display = 'block';
    });
  };
}

// ── NTP Search ────────────────────────────────────────────────
const ntpSearch = $("#ntpSearch");
if (ntpSearch) {
  ntpSearch.addEventListener("input", () => {
    if (activeTabId != null) ntpDrafts.set(activeTabId, ntpSearch.value);
  });
  ntpSearch.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const value = ntpSearch.value.trim();
      if (!value) return;
      let url;
      if (value.match(/^https?:\/\//)) url = value;
      else if (value.match(/^[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}/)) url = "https://" + value;
      else url = "https://www.google.com/search?q=" + encodeURIComponent(value);
      ntpDrafts.set(activeTabId, "");
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

function isTabAudible(tab) {
  if (!tab) return false;
  if (tab.muted) return false; // muted tabs can't play audio
  try { return !!(tab.webview && tab.webview.isCurrentlyAudible && tab.webview.isCurrentlyAudible()); }
  catch (e) { return false; }
}

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
    // Audible tabs are never hibernated — hibernation blanks the guest and
    // would kill playback. Retry on the same delay until silent.
    if (tab && tab.sleeping && id !== activeTabId && !isTabAudible(tab)) {
      hibernateTab(id);
    } else if (tab && isTabAudible(tab)) {
      startHibernateTimer(id);
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
// ── Boosts (Arc-style per-site custom CSS/JS) ──────────────
let _boosts = JSON.parse(localStorage.getItem('orbit-boosts') || '{}');

function getBoostForDomain(domain) {
  return _boosts[domain] || null;
}

function saveBoost(domain, boost) {
  if (boost.css || boost.js) {
    _boosts[domain] = boost;
  } else {
    delete _boosts[domain];
  }
  localStorage.setItem('orbit-boosts', JSON.stringify(_boosts));
}

function applyBoostToWebview(wv, url) {
  if (!wv || !url) return;
  try {
    var domain = new URL(url).hostname;
    var boost = getBoostForDomain(domain);
    if (!boost) return;
    if (boost.css) {
      wv.insertCSS(boost.css).catch(function() {});
    }
    if (boost.js) {
      wv.executeJavaScript(boost.js).catch(function() {});
    }
  } catch (e) {}
}

function createBoostUI() {
  var domain = '';
  try {
    var tab = tabs.get(activeTabId);
    if (tab && tab.url) domain = new URL(tab.url).hostname;
  } catch (e) {}
  if (!domain) { showToast('err', 'No site', 'Navigate to a site first'); return; }
  var existing = getBoostForDomain(domain);
  var css = prompt('Custom CSS for ' + domain + ':', existing ? existing.css || '' : '');
  if (css === null) return;
  var js = prompt('Custom JS for ' + domain + ':', existing ? existing.js || '' : '');
  if (js === null) return;
  saveBoost(domain, { css: css, js: js, created: Date.now() });
  showToast('ok', 'Boost saved', 'Applied to ' + domain);
  // Re-apply to current tab
  var tab = tabs.get(activeTabId);
  if (tab && tab.webview && tab.url && tab.url.includes(domain)) {
    applyBoostToWebview(tab.webview, tab.url);
  }
}

// ── Privacy Report Page (Safari-style) ────────────────────
let _privacyActivity = [];

function renderPrivacyPage() {
  // Update stats from security module via IPC
  if (window.orbit && window.orbit.perf && window.orbit.perf.stats) {
    window.orbit.perf.stats().then(function(stats) {
      var blocked = document.getElementById('privacyBlocked');
      if (blocked && stats) blocked.textContent = stats.adBlockStats ? stats.adBlockStats.blocked || 0 : 0;
    }).catch(function() {});
  }
  // Check shields config
  try {
    var shields = JSON.parse(localStorage.getItem('orbit-shields') || '{}');
    var toggleAdBlock = document.getElementById('toggleAdBlock');
    var toggleTrackerBlock = document.getElementById('toggleTrackerBlock');
    var toggleFingerprint = document.getElementById('toggleFingerprint');
    var toggleHttps = document.getElementById('toggleHttps');
    var toggleDnt = document.getElementById('toggleDnt');
    if (toggleAdBlock) toggleAdBlock.classList.toggle('on', shields.adBlocking !== false);
    if (toggleTrackerBlock) toggleTrackerBlock.classList.toggle('on', shields.trackerBlocking !== false);
    if (toggleFingerprint) toggleFingerprint.classList.toggle('on', shields.fingerprintProtection !== false);
    if (toggleHttps) toggleHttps.classList.toggle('on', shields.httpsUpgrade !== false);
    if (toggleDnt) toggleDnt.classList.toggle('on', shields.doNotTrack !== false);
  } catch (e) {}
  // Render activity
  var activityEl = document.getElementById('privacyActivity');
  if (activityEl) {
    if (_privacyActivity.length === 0) {
      activityEl.innerHTML = '<div class="empty-state">No tracker activity yet. Browsing will populate this list.</div>';
    } else {
      var html = '';
      _privacyActivity.slice(-20).reverse().forEach(function(item) {
        html += '<div class="privacy-activity-item">';
        html += '<div class="privacy-activity-dot ' + (item.blocked ? 'blocked' : 'allowed') + '"></div>';
        html += '<div class="privacy-activity-text">' + escapeHtml(item.url) + '</div>';
        html += '<div class="privacy-activity-time">' + item.type + '</div>';
        html += '</div>';
      });
      activityEl.innerHTML = html;
    }
  }
  // Wire shield toggles
  document.querySelectorAll('#shieldToggles .toggle').forEach(function(btn) {
    btn.onclick = function() {
      btn.classList.toggle('on');
      var shield = btn.dataset.shield;
      var shields = JSON.parse(localStorage.getItem('orbit-shields') || '{}');
      shields[shield] = btn.classList.contains('on');
      localStorage.setItem('orbit-shields', JSON.stringify(shields));
      showToast('ok', 'Shield Updated', shield + ' ' + (shields[shield] ? 'enabled' : 'disabled'));
    };
  });
}

function trackPrivacyEvent(url, type, blocked) {
  _privacyActivity.push({ url: url, type: type, blocked: blocked, time: Date.now() });
  if (_privacyActivity.length > 100) _privacyActivity.shift();
}

function renderHistoryPage() {
  const host = document.getElementById("historyPage");
  if (!host) return;
  let h = getHistory();
  const sheet = host.querySelector(".sheet");
  if (!sheet) return;
  const q = ((document.getElementById("histSearch") || {}).value || "").toLowerCase().trim();
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
  html += '<input type="text" class="chat-search" id="histSearch" placeholder="Search history…" value="' + escapeHtml(q) + '" />';
  if (!h.length) {
    html += '<div class="group"><div class="empty-page">No history yet. Browse somewhere and it will appear here.</div></div>';
  } else {
    const filtered = q ? h.filter((e) => (e.title + " " + e.url).toLowerCase().indexOf(q) >= 0) : h;
    if (!filtered.length) {
      html += '<div class="group"><div class="empty-page">No entries match \u201c' + escapeHtml(q) + '\u201d</div></div>';
      html += '</div>';
      sheet.outerHTML = html;
      wireHistSearch();
      return;
    }
    h = filtered;
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
  function wireHistSearch() {
    const inp = document.getElementById("histSearch");
    if (inp) inp.addEventListener("input", () => renderHistoryPage());
  }
  wireHistSearch();
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

// ── Reader Mode (Safari/Brave-style) ─────────────────────────
const readerOverlay = document.getElementById('readerOverlay');
const readerContent = document.getElementById('readerContent');
const readerClose = document.getElementById('readerClose');

function openReaderMode() {
  const wv = activeWebview();
  if (!wv) return;
  try {
    // Extract main content via JS injection
    wv.executeJavaScript(`
      (function() {
        // Try to find main content
        const article = document.querySelector('article') || 
                       document.querySelector('[role="main"]') ||
                       document.querySelector('.post-content') ||
                       document.querySelector('.article-body') ||
                       document.querySelector('main');
        if (article) return article.innerHTML;
        // Fallback: get all paragraphs
        const paras = Array.from(document.querySelectorAll('p')).map(p => p.outerHTML).join('\n');
        return paras || document.body.innerHTML;
      })()
    `).then(html => {
      if (html && readerContent) {
        readerContent.innerHTML = html;
        if (readerOverlay) readerOverlay.classList.add('active');
      }
    }).catch(() => {});
  } catch (e) {}
}

function closeReaderMode() {
  if (readerOverlay) readerOverlay.classList.remove('active');
}

if (readerClose) readerClose.addEventListener('click', closeReaderMode);

// ── Keyboard Shortcuts Overlay (Ctrl+/) ──────────────────────
let shortcutsOverlay = null;

// ── Tab Search (Ctrl+Shift+F) ──────────────────────────────
let tabSearchOverlay = null;

function toggleTabSearch() {
  if (tabSearchOverlay && tabSearchOverlay.classList.contains('active')) {
    tabSearchOverlay.classList.remove('active');
    return;
  }
  if (!tabSearchOverlay) {
    tabSearchOverlay = document.createElement('div');
    tabSearchOverlay.className = 'shortcuts-overlay';
    tabSearchOverlay.innerHTML = `
      <div class="shortcuts-card" style="max-width:500px">
        <div class="shortcuts-header">
          <h2>Search Tabs</h2>
          <button class="shortcuts-close" onclick="this.closest('.shortcuts-overlay').classList.remove('active')">\u2715</button>
        </div>
        <input type="text" id="tabSearchInput" placeholder="Search open tabs..." style="width:100%;padding:10px 14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#fff;font-size:13px;outline:none;margin-bottom:12px" />
        <div id="tabSearchResults" style="max-height:300px;overflow-y:auto"></div>
      </div>
    `;
    document.body.appendChild(tabSearchOverlay);
    const input = tabSearchOverlay.querySelector('#tabSearchInput');
    const results = tabSearchOverlay.querySelector('#tabSearchResults');
    if (input) {
      input.addEventListener('input', function() {
        const q = input.value.toLowerCase().trim();
        if (!q) { results.innerHTML = ''; return; }
        let html = '';
        tabs.forEach(function(tab, id) {
          const title = (tab.title || '').toLowerCase();
          const url = (tab.url || '').toLowerCase();
          if (title.includes(q) || url.includes(q)) {
            const active = id === activeTabId ? ' style="background:rgba(124,92,255,0.15)"' : '';
            html += '<div class="cmd-item" data-tabid="' + id + '"' + active + ' style="padding:8px 12px;border-radius:6px;cursor:pointer;margin-bottom:4px;display:flex;align-items:center;gap:8px">';
            html += '<span style="font-size:12px;color:var(--jb-paper);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escapeHtml(tab.title || 'Untitled') + '</span>';
            html += '<span style="font-size:10px;color:var(--jb-mute);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:200px">' + escapeHtml(tab.url || '') + '</span>';
            html += '</div>';
          }
        });
        results.innerHTML = html || '<div style="padding:12px;color:var(--jb-mute);font-size:12px;text-align:center">No matching tabs</div>';
        results.querySelectorAll('[data-tabid]').forEach(function(el) {
          el.addEventListener('click', function() {
            activateTab(el.dataset.tabid);
            tabSearchOverlay.classList.remove('active');
          });
        });
      });
      input.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') { tabSearchOverlay.classList.remove('active'); return; }
        if (e.key === 'Enter') {
          const first = results.querySelector('[data-tabid]');
          if (first) { activateTab(first.dataset.tabid); tabSearchOverlay.classList.remove('active'); }
        }
      });
    }
  }
  tabSearchOverlay.classList.add('active');
  const input = tabSearchOverlay.querySelector('#tabSearchInput');
  if (input) { input.value = ''; input.focus(); }
  // Show all tabs initially
  const results = tabSearchOverlay.querySelector('#tabSearchResults');
  if (results) {
    let html = '';
    tabs.forEach(function(tab, id) {
      const active = id === activeTabId ? ' style="background:rgba(124,92,255,0.15)"' : '';
      html += '<div class="cmd-item" data-tabid="' + id + '"' + active + ' style="padding:8px 12px;border-radius:6px;cursor:pointer;margin-bottom:4px;display:flex;align-items:center;gap:8px">';
      html += '<span style="font-size:12px;color:var(--jb-paper);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escapeHtml(tab.title || 'Untitled') + '</span>';
      html += '<span style="font-size:10px;color:var(--jb-mute);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:200px">' + escapeHtml(tab.url || '') + '</span>';
      html += '</div>';
    });
    results.innerHTML = html;
    results.querySelectorAll('[data-tabid]').forEach(function(el) {
      el.addEventListener('click', function() {
        activateTab(el.dataset.tabid);
        tabSearchOverlay.classList.remove('active');
      });
    });
  }
}

function toggleShortcutsOverlay() {
  if (shortcutsOverlay && shortcutsOverlay.classList.contains('active')) {
    shortcutsOverlay.classList.remove('active');
    return;
  }
  if (!shortcutsOverlay) {
    shortcutsOverlay = document.createElement('div');
    shortcutsOverlay.id = 'shortcutsOverlay';
    shortcutsOverlay.className = 'shortcuts-overlay';
    shortcutsOverlay.innerHTML = `
      <div class="shortcuts-card">
        <div class="shortcuts-header">
          <h2>Keyboard Shortcuts</h2>
          <button class="shortcuts-close" onclick="this.closest('.shortcuts-overlay').classList.remove('active')">✕</button>
        </div>
        <div class="shortcuts-grid">
          <div class="shortcuts-group">
            <h3>Tabs</h3>
            <div class="shortcut"><kbd>Ctrl+T</kbd><span>New tab</span></div>
            <div class="shortcut"><kbd>Ctrl+W</kbd><span>Close tab</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+T</kbd><span>Reopen closed tab</span></div>
            <div class="shortcut"><kbd>Ctrl+Tab</kbd><span>Next tab</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+Tab</kbd><span>Previous tab</span></div>
            <div class="shortcut"><kbd>Ctrl+1-9</kbd><span>Switch to tab N</span></div>
          </div>
          <div class="shortcuts-group">
            <h3>Navigation</h3>
            <div class="shortcut"><kbd>Alt+Left</kbd><span>Go back</span></div>
            <div class="shortcut"><kbd>Alt+Right</kbd><span>Go forward</span></div>
            <div class="shortcut"><kbd>Ctrl+R</kbd><span>Reload</span></div>
            <div class="shortcut"><kbd>Ctrl+L</kbd><span>Focus address bar</span></div>
            <div class="shortcut"><kbd>Ctrl+Home</kbd><span>New tab page</span></div>
          </div>
          <div class="shortcuts-group">
            <h3>View</h3>
            <div class="shortcut"><kbd>Ctrl++</kbd><span>Zoom in</span></div>
            <div class="shortcut"><kbd>Ctrl+-</kbd><span>Zoom out</span></div>
            <div class="shortcut"><kbd>Ctrl+0</kbd><span>Reset zoom</span></div>
            <div class="shortcut"><kbd>F11</kbd><span>Fullscreen</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+D</kbd><span>Reading mode</span></div>
            <div class="shortcut"><kbd>Ctrl+F</kbd><span>Find on page</span></div>
          </div>
          <div class="shortcuts-group">
            <h3>JARVIS</h3>
            <div class="shortcut"><kbd>Ctrl+Shift+J</kbd><span>Toggle sidebar</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+K</kbd><span>Floating JARVIS chat</span></div>
            <div class="shortcut"><kbd>Ctrl+K</kbd><span>Command palette</span></div>
            <div class="shortcut"><kbd>Ctrl+/</kbd><span>This overlay</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+S</kbd><span>Split view</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+R</kbd><span>Reader mode</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+P</kbd><span>Pop out video (PiP)</span></div>
          </div>
          <div class="shortcuts-group">
            <h3>Bookmarks & History</h3>
            <div class="shortcut"><kbd>Ctrl+D</kbd><span>Bookmark page</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+B</kbd><span>Toggle bookmark bar</span></div>
            <div class="shortcut"><kbd>Ctrl+H</kbd><span>History</span></div>
            <div class="shortcut"><kbd>Ctrl+J</kbd><span>Downloads</span></div>
            <div class="shortcut"><kbd>Ctrl+P</kbd><span>Print</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+S</kbd><span>Screenshot</span></div>
          </div>
          <div class="shortcuts-group">
            <h3>Window</h3>
            <div class="shortcut"><kbd>Ctrl+N</kbd><span>New window</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+N</kbd><span>New private window</span></div>
            <div class="shortcut"><kbd>Ctrl+Q</kbd><span>Close window</span></div>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(shortcutsOverlay);
    shortcutsOverlay.addEventListener('click', (e) => {
      if (e.target === shortcutsOverlay) shortcutsOverlay.classList.remove('active');
    });
  }
  shortcutsOverlay.classList.add('active');
}

// ── Agent Status Bar ──────────────────────────────────────────
const agentBar = document.getElementById('agentBar');
const agentBarText = document.getElementById('agentBarText');
const agentBarStop = document.getElementById('agentBarStop');

function showAgentBar(text) {
  if (agentBar) agentBar.classList.add('active');
  if (agentBarText) agentBarText.textContent = text || 'Agent running...';
}

function hideAgentBar() {
  if (agentBar) agentBar.classList.remove('active');
}

if (agentBarStop) agentBarStop.addEventListener('click', () => {
  if (window.orbit && window.orbit.agent) {
    window.orbit.agent.stop();
  }
  hideAgentBar();
});

// Listen for agent state changes
if (window.orbit && window.orbit.agent) {
  window.orbit.agent.onState((state) => {
    if (state === 'completed' || state === 'failed' || state === 'idle') {
      hideAgentBar();
    } else {
      showAgentBar(state.charAt(0).toUpperCase() + state.slice(1) + '...');
    }
  });
}

// ── Split View (Arc-style) ────────────────────────────────────
let splitMode = false;
let splitWebview = null;
let splitDivider = null;

function toggleSplitView() {
  if (splitMode) {
    exitSplitView();
  } else {
    enterSplitView();
  }
}

function enterSplitView() {
  if (splitMode) return;
  const wv = activeWebview();
  if (!wv) return;
  splitMode = true;
  // Create a second webview
  splitWebview = createWebview();
  splitWebview.setAttribute('src', 'about:blank');
  // Create divider
  splitDivider = document.createElement('div');
  splitDivider.className = 'split-divider';
  // Wrap in split container
  const container = wv.parentElement;
  container.classList.add('split-view');
  container.insertBefore(splitDivider, wv.nextSibling);
  container.insertBefore(splitWebview, splitDivider.nextSibling);
  showToast('info', 'Split View', 'Two tabs side by side');
}

function exitSplitView() {
  if (!splitMode) return;
  splitMode = false;
  if (splitWebview) {
    splitWebview.remove();
    splitWebview = null;
  }
  if (splitDivider) {
    splitDivider.remove();
    splitDivider = null;
  }
  const container = document.querySelector('.split-view');
  if (container) container.classList.remove('split-view');
}

// ── Command Chains (Vivaldi-style) ───────────────────────────
const commandChains = JSON.parse(localStorage.getItem('orbit-chains') || '[]');

function saveCommandChains() {
  localStorage.setItem('orbit-chains', JSON.stringify(commandChains));
}

function createCommandChain(name, steps) {
  commandChains.push({ name, steps, created: Date.now() });
  saveCommandChains();
}

function runCommandChain(chain) {
  let delay = 0;
  for (const step of chain.steps) {
    setTimeout(() => {
      if (step.type === 'navigate') navigateTo(step.url);
      else if (step.type === 'click') { /* handle click */ }
      else if (step.type === 'type') { /* handle type */ }
    }, delay);
    delay += step.delay || 500;
  }
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

// ── Session restore prompt (Chrome-style "Restore pages?") ────
try {
  var _lastSession = JSON.parse(localStorage.getItem('orbit-session') || 'null');
  var _hadRealTabs = _lastSession && Array.isArray(_lastSession.tabs) &&
    _lastSession.tabs.some(function(t) { return t.url && !String(t.url).startsWith('orbit://'); });
  if (_hadRealTabs && sessionBanner) {
    setTimeout(function() { sessionBanner.classList.add('on'); }, 800);
  }
} catch (e) {}

// ── First-Run: Auto-detect Chrome for import ──────────────────
if (!localStorage.getItem('orbit-imported-once') && window.orbit?.chrome) {
  window.orbit.chrome.detect().then(function(browsers) {
    if (browsers && browsers.length > 0) {
      var totalProfiles = 0;
      browsers.forEach(function(b) { totalProfiles += b.profiles.length; });
      setTimeout(function() {
        showToast('info', 'Chrome Detected', 'Found ' + browsers.length + ' browser(s) with ' + totalProfiles + ' profile(s). Import your data?');
        // Show import option in chat
        Chat.append('system', 'We detected Chrome/Edge/Brave on your system. You can import your bookmarks, history, and extensions.');
        Chat.append('system', 'Click the menu button (\u2261) and select "Import from Chrome" to get started.');
      }, 2000);
    }
    localStorage.setItem('orbit-imported-once', '1');
  }).catch(function() {});
}

// ── Performance Optimizations (research-backed) ──────────────
// 1. requestIdleCallback for non-critical startup work
if (typeof requestIdleCallback === 'function') {
  requestIdleCallback(function() {
    // Defer non-critical render work
    renderBookmarkBar();
    updatePerfHud();
  });
}

// 2. Memory cleanup: periodic garbage collection hint for long sessions
let _memCheckCount = 0;
setInterval(function() {
  _memCheckCount++;
  // Every 5 minutes, clean up stale references
  if (_memCheckCount % 5 === 0) {
    // Clear closed tab references older than 10 minutes
    var cutoff = Date.now() - 600000;
    for (var i = closedTabs.length - 1; i >= 0; i--) {
      if (closedTabs[i] && closedTabs[i].ts && closedTabs[i].ts < cutoff) {
        closedTabs.splice(i, 1);
      }
    }
    // Clear any orphaned webview references
    tabs.forEach(function(tab, id) {
      if (tab.webview && tab.webview.parentElement === null) {
        tabs.delete(id);
      }
    });
  }
}, 60000);

// 3. Long Task observer: keep a rolling count for diagnostics instead of
// console-spamming every janky frame (a busy page fired this every second).
if (typeof PerformanceObserver !== 'undefined') {
  try {
    window.__orbitLongTasks = 0;
    var _longTaskObs = new PerformanceObserver(function(list) {
      window.__orbitLongTasks += list.getEntries().length;
    });
    _longTaskObs.observe({ entryTypes: ['longtask'] });
  } catch (e) { /* not supported */ }
}

// 4. Prefetch DNS for common sites (improves navigation speed)
if (typeof requestIdleCallback === 'function') {
  requestIdleCallback(function() {
    var prefetchDomains = ['www.google.com', 'www.github.com', 'www.youtube.com'];
    prefetchDomains.forEach(function(domain) {
      try {
        var link = document.createElement('link');
        link.rel = 'dns-prefetch';
        link.href = '//' + domain;
        document.head.appendChild(link);
      } catch (e) {}
    });
  }, { timeout: 2000 });
}

// 5. Warn if renderer is blocked for > 100ms
var _blockCheckStart = 0;
setInterval(function() {
  _blockCheckStart = performance.now();
  setTimeout(function() {
    var blocked = performance.now() - _blockCheckStart - 10;
    if (blocked > 100) {
      console.warn('[PERF] Main thread blocked for ~' + Math.round(blocked) + 'ms');
    }
  }, 10);
}, 5000);

// ── Live downloads updates → toast + page refresh ────────────
if (window.orbit?.downloads?.onUpdated) {
  var _lastDlState = {};
  window.orbit.downloads.onUpdated(function(list) {
    (list || []).forEach(function(d) {
      var prev = _lastDlState[d.id];
      if (prev !== d.state) {
        _lastDlState[d.id] = d.state;
        if (d.state === 'complete') {
          showToast('ok', 'Download Complete', d.filename);
          ErrorLogger.info('Download complete: ' + d.filename, 'downloads');
        } else if (d.state === 'interrupted') {
          showToast('warn', 'Download Interrupted', d.filename);
        } else if (d.state === 'cancelled') {
          showToast('info', 'Download Cancelled', d.filename);
        } else if (d.state === 'downloading' && !prev) {
          showToast('info', 'Downloading', d.filename);
          // Auto-navigate to downloads page is NOT forced; show toast only
        }
      }
    });
    // Refresh the downloads page if it's currently visible
    var dlPage = document.getElementById('downloadsPage');
    if (dlPage && dlPage.classList.contains('on')) renderDownloadsPage();
  });
}
