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
