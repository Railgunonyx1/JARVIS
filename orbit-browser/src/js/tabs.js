/* tabs - extracted from renderer.js by scripts/split_renderer.py.
 * Classic script, loads in the shared global scope before renderer.js.
 * Event bindings use closures so load order never matters.
 */
// ---------------------------------------------------------------------
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
  // Absolute path supplied by main.js. A relative one resolves against
  // src/index.html and silently loads nothing (verified: __ORBIT_GUEST__ never
  // appeared, so guests ran unhardened and the first-party orbit:// bridge in
  // guests was dead).
  wv.setAttribute("preload", seed?.getAttribute("preload") || window.orbit?.guestPreload || "../guest-preload.js");
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
  // Tab crash recovery: log it, tell the user, and reload once so the tab
  // isn't just a blank rectangle. Repeated crashes within 30s are NOT
  // auto-reloaded (crash loop guard) — the user gets a toast instead.
  wv.addEventListener("render-process-gone", (e) => {
    const t = tabOwnedBy(wv);
    const reason = e && e.details ? e.details.reason : "unknown";
    ErrorLogger.error(new Error("Tab crashed: " + reason + (t ? " (" + t.url + ")" : "")), "tab-crash");

    // CRITICAL: a crashed guest keeps OS-level keyboard focus, so every
    // host input (omnibox, NTP search, chat) shows a caret but silently
    // swallows keystrokes — the "can't type anywhere" report. Hand focus
    // back to the host UI before anything else.
    try { wv.blur(); } catch (_) {}
    try { if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur(); } catch (_) {}
    try { window.focus(); } catch (_) {}

    if (t && !t._lastCrashTs) t._lastCrashTs = 0;
    const now = Date.now();
    if (t && now - t._lastCrashTs > 30000) {
      t._lastCrashTs = now;
      showToast("warn", "Tab crashed — reloading", t.title || t.url || "");
      setTimeout(() => { try { wv.reload(); } catch (_) {} }, 400);
    } else {
      // Crash loop (e.g. GPU-process crashes on WebGL-heavy sites):
      // retire the dead guest instead of leaving a zombie webview that
      // holds focus and breaks the whole browser. The internal page
      // overlay keeps the webview attached (per pool design) while the
      // host UI becomes immediately usable again.
      showToast("err", "Tab keeps crashing — sent to New Tab", (t && (t.title || t.url)) || reason);
      try { wv.stop(); } catch (_) {}
      if (t && t.id === activeTabId) navigateTo("orbit://newtab");
    }
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
      // Pinned tabs: icon only — no title, no close button (Chrome-style)
      el.innerHTML = '<span class="tab-fav">' + (tab.pinned ? '\u2702' : '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4.5" stroke="currentColor"/></svg>') + '</span>' + (tab.groupColor ? '<span class="tab-grp" data-grp="' + id + '" style="background:' + tab.groupColor + '" title="Click to change group color"></span>' : '') + (tab.pinned ? '' : '<span class="tab-title">' + escapeHtml(tab.title) + '</span>') + (tab.muted ? '<span class="tab-state" title="Muted">\u{1F507}</span>' : '') + (tab.pinned ? '' : '<span class="tab-close" data-close="' + id + '">\u00d7</span>');
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

// Human titles for internal pages — orbit:// guests never fire
// page-title-updated, so without this every workspace tab reads "New tab".
const INTERNAL_TITLES = {
  "orbit://newtab": "New tab",
  "orbit://settings": "Settings",
  "orbit://history": "History",
  "orbit://bookmarks": "Bookmarks",
  "orbit://downloads": "Downloads",
  "orbit://tasks": "Tasks",
  "orbit://permissions": "Permissions",
  "orbit://memory": "Memory",
  "orbit://extensions": "Extensions",
  "orbit://diagnostics": "Diagnostics",
  "orbit://security": "Security",
  "orbit://privacy": "Privacy",
  "orbit://import": "Import",
  "orbit://extension-store": "Extension Store",
  "orbit://goodeye": "God's Eye",
  "orbit://f1": "F1 Live",
  "orbit://worldmon": "World Monitor",
};

function createTab(url) {
  url = url || "orbit://newtab";
  showEmptyScreen(false);
  const id = "tab-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
  const tab = {
    id, url, title: INTERNAL_TITLES[url] || "New tab", favicon: null,
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
      if (zoomIndicator) {
        zoomIndicator.textContent = Math.round(currentZoom * 100) + "%";
        zoomIndicator.style.display = currentZoom === 1 ? "none" : "";
      }
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
  "orbit://worldmon": "worldmonPage",
  "orbit://tools": "toolsPage",
  "orbit://watch": "watchPage",
};

function isWebviewInternal(url) {
  if (!url || !url.startsWith("orbit://")) return false;
  const pageId = INTERNAL_PAGES[url];
  return !!pageId && !document.getElementById(pageId);
}

function showInternalPage(pageId) {
  // Cross-fade just the content region (chrome stays static — lateral
  // navigation communicates no depth, so no directional slide). Instant
  // swap without the View Transition API or under reduced-motion.
  UI.viewTransition(function () {
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
    if (pageId === "goodeyePage" || pageId === "f1Page" || pageId === "worldmonPage") {
      ensureWorkspace(pageId, function () {
        if (pageId === "goodeyePage" && window.GoodEye) window.GoodEye.start();
        if (pageId === "f1Page" && window.OrbitF1) window.OrbitF1.start();
        if (pageId === "worldmonPage" && window.WorldMon) window.WorldMon.start();
      });
    } else {
      // Workspaces poll in the background; stop them when their page hides.
      if (window.GoodEye) window.GoodEye.stop();
      if (window.OrbitF1) window.OrbitF1.stop();
      if (window.WorldMon) window.WorldMon.stop();
    }
  });
}

// ── Lazy workspace load ───────────────────────────────────────────
// God's Eye / F1 / WorldMon are full page apps only shown from their own
// orbit:// pages. Loading them on first open (instead of at boot) skips
// their parse + top-level init on every browser start. They keep the global
// lifecycle contract, so tabs.js loads the script ahead of the first start().
const WORKSPACE_PAGES = {
  goodeyePage: { script: "js/goodeye.js", global: "GoodEye" },
  f1Page: { script: "js/f1.js", global: "OrbitF1" },
  worldmonPage: { script: "js/worldmon.js", global: "WorldMon" },
};
const _scriptsLoaded = {};

function loadOnce(src, cb) {
  if (_scriptsLoaded[src]) { cb(); return; }
  _scriptsLoaded[src] = true;
  var s = document.createElement("script");
  s.async = true;
  s.src = src;
  s.onload = cb;
  s.onerror = function () { console.error("[LOAD] " + src + " failed"); cb(); };
  document.head.appendChild(s);
}

function ensureWorkspace(pageId, cb) {
  var wk = WORKSPACE_PAGES[pageId];
  if (!wk) { cb(); return; }
  if (window[wk.global]) { cb(); return; }
  // worldmap.js first (goodeye/worldmon draw through it), then the shared
  // workspace base, then the page module itself.
  loadOnce("js/worldmap.js", function () {
    loadOnce("js/workspace.js", function () { loadOnce(wk.script, cb); });
  });
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
  // Error log stats (merged: renderer ErrorLogger + main-process log)
  var errStats = ErrorLogger.getStats();
  var errCount = document.getElementById('diagErrorCount');
  var errTotal = document.getElementById('diagErrorTotal');
  var warnTotal = document.getElementById('diagWarnTotal');
  var lastErr = document.getElementById('diagLastError');
  if (errCount) errCount.textContent = errStats.total;
  if (errTotal) errTotal.textContent = errStats.errors;
  if (warnTotal) warnTotal.textContent = errStats.warns;
  // Main-process log (crashes, uncaught exceptions, tab hangs) — previously
  // captured but never displayed anywhere.
  var mainErrors = [];
  try {
    var mainResult = window.orbit && window.orbit.perf && window.orbit.perf.errorLog();
    if (mainResult && typeof mainResult.then === 'function') {
      mainResult.then(function (entries) {
        mainErrors = entries || [];
        var mainEl = document.getElementById('diagMainErrors');
        if (mainEl) mainEl.textContent = String(mainErrors.length);
        if (errorList && errorList.style.display !== 'none') renderErrorLog(errorList);
      }).catch(function () {});
    }
  } catch (_) {}
  if (lastErr) {
    var allErrors = ErrorLogger.getErrors({ level: 'error' });
    var lastMsg = allErrors.length > 0 ? allErrors[allErrors.length - 1].message : null;
    if (!lastMsg && mainErrors.length > 0) lastMsg = mainErrors[mainErrors.length - 1].message;
    lastErr.textContent = lastMsg ? lastMsg.substring(0, 60) : 'None';
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
      try { if (window.orbit && window.orbit.perf && window.orbit.perf.clearErrorLog) window.orbit.perf.clearErrorLog(); } catch (_) {}
      refreshDiagnostics();
      showToast('ok', 'Cleared', 'Error log cleared');
    };
  }
}

function renderErrorLog(container) {
  var errors = ErrorLogger.getErrors().map(function(e) {
    return { level: e.level, message: e.message, source: e.source, line: e.line, timestamp: e.timestamp, origin: 'renderer' };
  });
  // Merge main-process entries (tab crashes, uncaught exceptions) if available.
  try {
    var mr = window.orbit && window.orbit.perf && window.orbit.perf.errorLog();
    if (mr && typeof mr.then !== 'function' && Array.isArray(mr)) {
      mr.forEach(function(e) { errors.push({ level: e.level, message: e.message, source: e.detail || '', line: 0, timestamp: e.timestamp, origin: 'main' }); });
    }
  } catch (_) {}
  if (errors.length === 0) {
    container.innerHTML = '<div style="padding:12px;color:var(--jb-mute);font-size:12px;text-align:center">No errors logged</div>';
    return;
  }
  errors.sort(function(a, b) { return b.timestamp - a.timestamp; });
  var html = '';
  errors.slice(0, 60).forEach(function(e) {
    var color = e.level === 'error' ? 'var(--jb-danger)' : e.level === 'warn' ? 'var(--jb-warning)' : 'var(--jb-success)';
    var icon = e.level === 'error' ? '\u2717' : e.level === 'warn' ? '\u26A0' : '\u2139';
    var time = new Date(e.timestamp).toLocaleTimeString();
    html += '<div class="privacy-activity-item">';
    html += '<div class="privacy-activity-dot" style="background:' + color + '"></div>';
    html += '<div class="privacy-activity-text" style="font-size:11px"><span style="color:' + color + ';margin-right:6px">' + icon + '</span>' + (e.origin === 'main' ? '<span style="color:var(--jb-mute);margin-right:4px">[main]</span>' : '') + escapeHtml(e.message) + (e.source && e.origin !== 'main' ? ' <span style="color:var(--jb-mute)">' + escapeHtml(e.source) + ':' + e.line + '</span>' : '') + '</div>';
    html += '<div class="privacy-activity-time">' + time + '</div>';
    html += '</div>';
  });
  container.innerHTML = html;
}

function navigateTo(url) {
  const tab = tabs.get(activeTabId);
  if (!tab) return;
  tab.url = url;
  if (url.startsWith("orbit://")) {
    // Internal pages never emit page-title-updated — carry the title here.
    const t = INTERNAL_TITLES[url];
    if (t) { tab.title = t; renderTabs(); if (sbPageTitle) sbPageTitle.textContent = t; }
  }

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
  // Chrome site-search parity: "!g cats", "!ddg cats", "!b cats", "!w cats",
  // "!yt cats" route to the named engine (DuckDuckGo bangs, honored subset).
  const bang = value.match(/^!(g|ddg|b|w|yt)\s+(.+)/i);
  if (bang) {
    const q = encodeURIComponent(bang[2].trim());
    const engine = bang[1].toLowerCase();
    if (engine === "g") return "https://www.google.com/search?q=" + q;
    if (engine === "ddg") return "https://duckduckgo.com/?q=" + q;
    if (engine === "b") return "https://www.bing.com/search?q=" + q;
    if (engine === "w") return "https://en.wikipedia.org/wiki/Special:Search?search=" + q;
    if (engine === "yt") return "https://www.youtube.com/results?search_query=" + q;
  }
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

// ── New Tab (sidebar + empty state) ─────────────────────────
newTabBtn.addEventListener("click", () => createTab());
if (emptyNewTabBtn) emptyNewTabBtn.addEventListener("click", () => createTab());

// Add-tab in the vertical sidebar tab list
const addTabBtn = $("#addTabBtn");
if (addTabBtn) {
  addTabBtn.addEventListener("click", () => createTab());
}

// Keyboard: Ctrl+1..9 switch tabs
document.addEventListener("keydown", (e) => {
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && !e.shiftKey && /^[1-9]$/.test(e.key)) {
    e.preventDefault();
    const ids = Array.from(tabs.keys());
    if (!ids.length) return;
    const n = parseInt(e.key, 10);
    const target = n === 9 ? ids[ids.length - 1] : ids[n - 1];
    if (target) activateTab(target);
  }
});

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
