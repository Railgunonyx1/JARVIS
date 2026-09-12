/* settings-ux - extracted from renderer.js by scripts/split_renderer.py.
 * Classic script, loads in the shared global scope before renderer.js.
 * Event bindings use closures so load order never matters.
 */
// ---------------------------------------------------------------------
// ── Close all popups ──────────────────────────────────────────
function closeAllPopups() {
  if (browserMenu) browserMenu.classList.remove("on");
  if (extPopup) extPopup.classList.remove("on");
  if (profilePopup) profilePopup.classList.remove("on");
  if (sitePopup) sitePopup.classList.remove("on");
  if (typeof systemPopup !== "undefined" && systemPopup) systemPopup.classList.remove("on");
  if (tabContextMenu) tabContextMenu.classList.remove("on");
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".popover") && !e.target.closest(".context-menu") && !e.target.closest("#menuBtn") && !e.target.closest("#extBtn") && !e.target.closest("#profileBtn") && !e.target.closest("#sysBtn") && !e.target.closest("#omniLock")) closeAllPopups();
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
// Restore persisted width (clamped to the same 280-600 range).
try {
  const savedW = parseInt(localStorage.getItem("orbit-sidebar-w"), 10);
  if (savedW >= 280 && savedW <= 600 && sidebar) sidebar.style.width = savedW + "px";
} catch (_) {}
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
    // Persist so the width survives restarts.
    try { localStorage.setItem("orbit-sidebar-w", parseInt(sidebar.style.width, 10) || ""); } catch (_) {}
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
