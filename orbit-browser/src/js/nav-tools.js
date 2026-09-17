/* nav-tools - extracted from renderer.js by scripts/split_renderer.py.
 * Classic script, loads in the shared global scope before renderer.js.
 * Event bindings use closures so load order never matters.
 */
// ---------------------------------------------------------------------
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
  if (zoomIndicator) {
    zoomIndicator.textContent = Math.round(currentZoom * 100) + "%";
    // 100% is the default — hide the chip so the omnibox stays clean.
    zoomIndicator.style.display = currentZoom === 1 ? "none" : "";
  }
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
    const jl = _getPerfRef("sysJarvis");
    const tl = _getPerfRef("sysTabs");
    const zl = _getPerfRef("sysZoom");
    const fl = _getPerfRef("sysFps");
    const ml = _getPerfRef("sysMem");
    const dl = _getPerfRef("sysDom");
    if (jl) {
      jl.innerHTML = '<span class="perf-dot ' + (jarvisOnline ? "ok" : "off") +
        '"></span>' + (jarvisOnline ? "ON" : "OFF");
    }
    if (tl) tl.textContent = String(tabs.size);
    if (zl) zl.textContent = Math.round(currentZoom * 100) + "%";
    if (fl) fl.textContent = String(perfData.fps);
    if (ml) ml.textContent = getMemoryMB() + " MB";
    if (dl) dl.textContent = String(document.body.childElementCount);
  });
}

// ── Vertical Tabs ─────────────────────────────────────────────
function renderVerticalTabs() {
  if (!tabStripVertical) return;
  // Clear only tab rows — the vtab-head (label + new-tab button) persists.
  tabStripVertical.querySelectorAll(".tab").forEach(function(n) { n.remove(); });
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
  // Duplicate navigation: when the vertical strip owns tab display, hide
  // the horizontal tabs. visibility (not display) keeps the strip's flex:1
  // space intact — it IS the titlebar's drag region and the spacer that
  // holds the window controls to the right edge.
  if (tabStrip) tabStrip.style.visibility = on ? "hidden" : "";
  // The vertical strip header now owns new-tab; the titlebar + would be a
  // second stranded control.
  const ntb = document.getElementById("newTabBtn");
  if (ntb) ntb.style.display = on ? "none" : "";
  try { localStorage.setItem("orbit-vtabs", on ? "1" : "0"); } catch (e) {}
  renderVerticalTabs();
}
if (vtToggleBtn) {
  vtToggleBtn.addEventListener("click", function() {
    setVerticalTabs(!tabStripVertical.classList.contains("on"));
  });
}
// New-tab button in the vertical strip header (compensation for the moved
// tab bar; same handler as the titlebar's +).
const vtabNewBtn = $("#vtabNewBtn");
if (vtabNewBtn) vtabNewBtn.addEventListener("click", function() { createTab(); });
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
  { l: "Run Agent Task", d: "Headless agent execution (kernel path)", i: "\u{1F916}", a: function() {
    var task = prompt('Agent task:');
    if (task && typeof runAgentTask === 'function') {
      // A-04: routed through the JARVIS kernel (permission engine + audit),
      // not the quarantined local loop.
      showAgentBar('Starting...');
      runAgentTask(task).then(function() { hideAgentBar(); });
    } else if (task) {
      showToast('err', 'Agent unavailable', 'JARVIS kernel path not loaded');
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
