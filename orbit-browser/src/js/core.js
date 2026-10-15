/* core - extracted from renderer.js by scripts/split_renderer.py.
 * Classic script, loads in the shared global scope before renderer.js.
 * Event bindings use closures so load order never matters.
 */

// ---------------------------------------------------------------------

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

// ── Debounce/Throttle Utilities ───────────────────────────────
function debounce(fn, ms) {
  var timer;
  return function() {
    var args = arguments;
    var ctx = this;
    clearTimeout(timer);
    timer = setTimeout(function() { fn.apply(ctx, args); }, ms);
  }
}
function throttle(fn, ms) {
  var last = 0;
  return function() {
    var now = Date.now();
    if (now - last >= ms) {
      last = now;
      fn.apply(this, arguments);
    }
  }
}

// ── Shared log channel (bridge panel reads this) ──────────────
// Renderers push structured events here; the bridge panel polls GET /v1/logs.
function _batchLog() {
  var events = window._orbitLogBatch || [];
  window._orbitLogBatch = [];
  return events;
}
function _flushLog() {
  var events = _batchLog();
  if (!events.length) return;
  if (window.orbit && typeof window.orbit.perf.logs === "function") {
    try { window.orbit.perf.logs(events); } catch (e) { /* never throw from logging */ }
  }
  // Fall back to the bridge endpoint directly when the perf extension is not ready.
  if (window._orbitLastLogsUrl) {
    try {
      var body = JSON.stringify({ entries: events });
      var xhr = new XMLHttpRequest();
      xhr.open("POST", window._orbitLastLogsUrl, false);
      xhr.setRequestHeader("Content-Type", "application/json");
      xhr.send(body);
    } catch (e) { /* never throw from logging */ }
  }
}
function _log(level, source, message, detail) {
  var entry = {
    ts: new Date().toISOString(),
    level: level || "info",
    source: source || "",
    message: message || "",
    detail: detail || null,
    tabId: null,
    duration_ms: null,
  };
  if (window._orbitTabs && window.activeTabId !== undefined) {
    entry.tabId = window.activeTabId;
  }
  if (detail && (detail.tabId !== undefined || detail.duration_ms !== undefined)) {
    entry.tabId = entry.tabId === null ? detail.tabId : entry.tabId;
    entry.duration_ms = detail.duration_ms;
  }
  window._orbitLogBatch = window._orbitLogBatch || [];
  window._orbitLogBatch.push(entry);
  if (window._orbitLogBatch.length >= 50) {
    _flushLog();
  }
  if (window._orbitLogListeners) {
    try { window._orbitLogListeners.forEach(function(cb) { try { cb(entry); } catch (e) {} }); } catch (e) {}
  }
  return entry;
}
window._log = _log;
window._orbitLogListeners = [];
window._orbitLogListeners.push(function(entry) {
  // keep the in-process ErrorLogger's own store in sync
  if (window._errorLogger && typeof window._errorLogger.record === "function") {
    try { window._errorLogger.record(entry); } catch (e) {}
  }
});

// ── Error Logger (captures all errors for diagnostics) ──────────
const ErrorLogger = (function() {
  var _errors = [];
  var MAX_ERRORS = 500;
  var _listeners = [];
  var _logAt = Object.create(null);

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
    var entry;
    if (window._log) {
      entry = window._log('error', source || '', err.message || String(err), {
        filename: err.filename,
        lineno: err.lineno,
        colno: err.colno,
        stack: err.stack,
      });
    } else {
      entry = log('error', err.message || String(err), source || '');
      if (err.filename) entry.source = err.filename;
      if (err.lineno) entry.line = err.lineno;
      if (err.colno) entry.col = err.colno;
      if (err.stack) entry.stack = err.stack;
    }
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
const sbRail = $("#sbRail");   // Opera GX-style icon rail (sidebar.js binds clicks)
const sbPanelTitle = $("#sbPanelTitle");
const sbMatrix = $("#sbMatrix");
const sbDot = $("#sbDot");
const sbStateLabel = $("#sbStateLabel");
const sbPageTitle = $("#sbPageTitle");
// Toolbar JARVIS badge removed — status lives on the JARVIS button itself.
const statusDot = null;
const statusLabel = null;
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
// Sidebar open state persists across restarts (default: open).
let sidebarOpen = (function(){ try { return localStorage.getItem("orbit-sidebar-open") !== "0"; } catch (_) { return true; } })();
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
  // Orb loop revive: v2's canvas loop parks itself when every orb is static
  // (offline/fail). A new animated state must spin it back up.
  if (typeof window.kickOrbLoop === "function") window.kickOrbLoop();
  const label = {
    idle: "IDLE", thinking: "THINK", planning: "PLAN",
    running: "RUN", ask: "ASK", done: "DONE", fail: "FAIL",
    offline: "OFF", link: "LINK",
  }[state] || state.toUpperCase();
  if (sbStateLabel) sbStateLabel.textContent = jarvisOnline ? label : "OFF";
  const running = ["thinking", "planning", "running", "ask"].includes(state);
  // Opera-rail pulse: chat icon breathes while the agent works
  const chatRailBtn = sbRail?.querySelector('[data-panel="jarvis"]');
  if (chatRailBtn) chatRailBtn.classList.toggle("agent-active", running && jarvisOnline);
  if (floatGlyph) floatGlyph.classList.toggle("show", running && !sidebarOpen && jarvisOnline);
  if (floatTitle) floatTitle.textContent = state === "ask" ? "Approval needed" : "Researching";
  if (floatMatrix) floatMatrix.dataset.state = state === "ask" ? "ask" : "running";
}

window._log = _log;

// ── Perf bridge extension ─────────────────────────────────────
// Expose batch logs to the bridge bridge (`window.orbit.perf.logs()`), used
// by the unified log panel (v2-sidebar `renderLogPanel` → `GET /v1/logs`).
try {
  if (window.orbit && window.orbit.perf && !window.orbit.perf.logs) {
    window.orbit.perf.logs = function(entries) {
      // Handled by the bridge; the panel polls GET /v1/logs instead.
      return entries;
    };
  }
} catch (e) { /* never throw from init */ }
