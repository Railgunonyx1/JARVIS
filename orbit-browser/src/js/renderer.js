/**
 * JARVIS Orbit — Renderer Process (split)
 *
 * This file carries the browser chrome tail + init. Shared infra and state
 * live in core.js (DOM cache, error logger, DOM refs, state, toast, matrix).
 * Feature code lives in sibling modules: tabs.js, sidebar.js, jarvis.js,
 * nav-tools.js, menus.js, pages.js, settings-ux.js, data-pages.js, loaded
 * BEFORE this file so init sees every cross-file reference.
 * Regenerate: python scripts/split_renderer.py
 */
// ---------------------------------------------------------------------
// ── Reader Mode (Safari/Brave-style) ────────────────────────
// A-07: guest HTML is NEVER parsed/inserted in this privileged renderer.
// The guest returns structured JSON (tag + text), and we rebuild the DOM
// here with createElement/textContent only — no innerHTML path exists for
// untrusted content, so event-handler injection is structurally impossible.
const readerOverlay = document.getElementById('readerOverlay');
const readerContent = document.getElementById('readerContent');
const readerClose = document.getElementById('readerClose');

const _READER_TAGS = new Set(['H1', 'H2', 'H3', 'H4', 'P', 'LI', 'BLOCKQUOTE', 'PRE']);

function openReaderMode() {
  const wv = activeWebview();
  if (!wv) return;
  try {
    wv.executeJavaScript(`
      (function() {
        var root = document.querySelector('article') ||
                   document.querySelector('[role="main"]') ||
                   document.querySelector('.post-content') ||
                   document.querySelector('.article-body') ||
                   document.querySelector('main') || document.body;
        var blocks = [];
        var nodes = root.querySelectorAll('h1,h2,h3,h4,p,li,blockquote,pre');
        for (var i = 0; i < nodes.length && blocks.length < 400; i++) {
          var el = nodes[i];
          var txt = (el.innerText || el.textContent || '').trim();
          if (!txt || txt.length < 2) continue;
          if (blocks.length && blocks[blocks.length-1].t === txt) continue;
          blocks.push({ tag: el.tagName, t: txt.substring(0, 2000) });
        }
        return JSON.stringify({ title: (document.title || '').substring(0, 200), blocks: blocks });
      })()
    `).then(raw => {
      if (!raw || !readerContent) return;
      let data;
      try { data = JSON.parse(raw); } catch (_) { return; }
      // Rebuild from scratch — textContent only, no markup from the guest
      while (readerContent.firstChild) readerContent.removeChild(readerContent.firstChild);
      if (data.title) {
        const h = document.createElement('h1');
        h.textContent = data.title;
        readerContent.appendChild(h);
      }
      let count = 0;
      for (const b of (data.blocks || [])) {
        const tag = _READER_TAGS.has(b.tag) ? b.tag : 'P';
        const el = document.createElement(tag.toLowerCase());
        el.textContent = b.t;
        readerContent.appendChild(el);
        count++;
      }
      if (!count) {
        const p = document.createElement('p');
        p.textContent = 'No readable content found on this page.';
        readerContent.appendChild(p);
      }
      if (readerOverlay) readerOverlay.classList.add('active');
    }).catch(() => {});
  } catch (e) {}
}

function closeReaderMode() {
  if (readerOverlay) readerOverlay.classList.remove('active');
}

if (readerClose) readerClose.addEventListener('click', closeReaderMode);

// Delegated close for the shortcuts overlays (CSP: no inline handlers)
document.addEventListener('click', function (e) {
  const t = e.target && e.target.closest ? e.target.closest('[data-shclose]') : null;
  if (t) {
    const ov = t.closest('.shortcuts-overlay');
    if (ov) ov.classList.remove('active');
  }
});

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
          <button class="shortcuts-close" data-shclose="1">\u2715</button>
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
          <button class="shortcuts-close" data-shclose="1">✕</button>
        </div>
        <div class="shortcuts-grid">
          <div class="shortcuts-group">
            <h3>Tabs</h3>
            <div class="shortcut"><kbd>Ctrl+T</kbd><span>New tab</span></div>
            <div class="shortcut"><kbd>Ctrl+W</kbd><span>Close tab (closes window when none left)</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+T</kbd><span>Reopen closed tab</span></div>
            <div class="shortcut"><kbd>Ctrl+Tab</kbd><span>Next tab</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+Tab</kbd><span>Previous tab</span></div>
            <div class="shortcut"><kbd>Ctrl+1-8</kbd><span>Switch to tab N</span></div>
            <div class="shortcut"><kbd>Ctrl+9</kbd><span>Jump to last tab</span></div>
          </div>
          <div class="shortcuts-group">
            <h3>Navigation</h3>
            <div class="shortcut"><kbd>Alt+Left</kbd><span>Go back</span></div>
            <div class="shortcut"><kbd>Alt+Right</kbd><span>Go forward</span></div>
            <div class="shortcut"><kbd>Ctrl+R</kbd><span>Reload</span></div>
            <div class="shortcut"><kbd>Ctrl+L</kbd><span>Focus address bar</span></div>
            <div class="shortcut"><kbd>Alt+Home</kbd><span>Home page</span></div>
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
            <div class="shortcut"><kbd>Ctrl+Shift+\\</kbd><span>Split view</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+S</kbd><span>Screenshot</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+R</kbd><span>Reader mode</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+P</kbd><span>Pop out video (PiP)</span></div>
          </div>
          <div class="shortcuts-group">
            <h3>Bookmarks & History</h3>
            <div class="shortcut"><kbd>Ctrl+D</kbd><span>Bookmark page</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+B</kbd><span>Toggle bookmark bar</span></div>
            <div class="shortcut"><kbd>Ctrl+H</kbd><span>History</span></div>
            <div class="shortcut"><kbd>Ctrl+J</kbd><span>Downloads</span></div>
            <div class="shortcut"><kbd>Shift+Esc</kbd><span>Task manager</span></div>
            <div class="shortcut"><kbd>Ctrl+Shift+Del</kbd><span>Clear browsing data</span></div>
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
  // Stopping runs through the JARVIS bridge (dshNative abort), not a local
  // Electron agent -- that loop is quarantined. See main.js A-04.
  try {
    if (window.dshNative && typeof window.dshNative.abort === 'function') {
      window.dshNative.abort();
    }
  } catch (err) {
    console.warn('[ORBIT] agent abort failed', err);
  }
  hideAgentBar();
});

// Agent state now arrives on the JARVIS channel (dsh.on('agent'/'status')),
// which jarvis.js owns. There is no local agent to subscribe to.

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
if (window.Chat) Chat.init(sbBody, sbRail);
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
// Apply persisted sidebar visibility (sidebarOpen is restored in core.js).
if (sidebar && !sidebarOpen) sidebar.classList.add("hidden");
// Render dynamic popup contents (profiles, extensions) and sync the avatar.
syncProfileAvatar();
renderProfilePopup();
renderExtPopup();
renderBookmarkBar();
updatePerfHud();
// Show initial JARVIS welcome
if (typeof _syncPanelTitle === "function") _syncPanelTitle("jarvis");
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

// All feature modules have booted — panel/page swaps may animate now.
window.__orbitBooted = true;
