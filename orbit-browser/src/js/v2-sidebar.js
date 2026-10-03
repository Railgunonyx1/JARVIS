/* ORBIT v2.1 — Opera GX sidebar completion.
 * Loads AFTER sidebar.js (defer order), so its renderPanel definition wins
 * the global name resolution and panels route through here first.
 *
 * 1. renderPanel override — adds Flow / Bookmarks / History / Downloads /
 *    Watches panels; delegates the original panels to the previous renderer.
 * 2. Watches panel — bridge-fed via the orbit-watches localStorage mirror
 *    (v2-watch.js) with a live badge on the rail icon.
 * 3. Flow panel — clock, quick notes, session telemetry (glances-style).
 * 4. Bookmarks/History/Downloads — the "middle of the page" content, moved
 *    into the rail where Opera GX puts it.
 * 5. NTP quick tiles — the index.html tiles had no click wiring (dead
 *    buttons); navigate on click, opened in a new tab on Ctrl+click.
 *
 * Everything is additive and defensive: any missing element or module
 * degrades to the previous behavior, never breaks the shell.
 */
(function () {
  'use strict';

  if (typeof renderPanel !== 'function') {
    if (window.__ORBIT_DEBUG__) console.warn('[v2-sidebar] no base renderPanel; skipping override');
    return;
  }
  // Extend the sidebar's panel-title map (const object — mutate, don't rebind).
  if (typeof PANEL_TITLES === 'object' && PANEL_TITLES) {
    Object.assign(PANEL_TITLES, {
      flow: 'Flow', bookmarks: 'Bookmarks', 'browser-history': 'History',
      downloads: 'Downloads', watches: 'Watches',
    });
  }
  var _baseRenderPanel = renderPanel;
  var _ext = {
    flow: renderFlowPanel, bookmarks: renderBookmarksPanel,
    'browser-history': renderHistoryPanelSide, downloads: renderDownloadsPanel,
    watches: renderWatchesPanel,
    log: renderLogPanel,
  };

  renderPanel = function (name) {
    if (_ext[name]) {
      var swap = function () {
        if (typeof _syncPanelTitle === 'function') _syncPanelTitle(name);
        _ext[name]();
      };
      if (window.__orbitBooted && window.UI && UI.viewTransition) UI.viewTransition(swap);
      else swap();
      // Persist the active panel so a relaunch reopens where you were.
      try { localStorage.setItem('orbit-panel', name); } catch (e) {}
      return;
    }
    var base = _baseRenderPanel(name);
    try { localStorage.setItem('orbit-panel', name); } catch (e) {}
    return base;
  };
  // Re-route Chat panels through the same entry (Chat.renderPanel skips its
  // own title sync for non-chat panels; keep titles consistent).

  // ── Log panel (unified browser/bridge/main-process log) ──────────────
  function renderLogPanel() {
    sbBody.innerHTML =
      '<div class="panel-pad">' +
        '<div class="log-toolbar">' +
          '<div class="log-seg">' +
            '<select id="logLevel" aria-label="Log level">' +
              '<option value="">All levels</option>' +
              '<option value="debug">debug</option>' +
              '<option value="info">info</option>' +
              '<option value="warn">warn</option>' +
              '<option value="error">error</option>' +
              '<option value="fatal">fatal</option>' +
            '</select>' +
          '</div>' +
          '<div class="log-seg"><input id="logSearch" class="log-search" placeholder="Search message/source..." aria-label="Search" /></div>' +
          '<div class="log-seg"><input id="logSource" class="log-search" placeholder="Source module..." aria-label="Source" /></div>' +
          '<div class="log-seg"><span class="log-count" id="logCount">0 entries</span></div>' +
          '<div class="log-seg log-actions">' +
            '<button id="logClear" class="ui-btn ui-btn--ghost">Clear</button>' +
            '<button id="logExport" class="ui-btn ui-btn--ghost">Export</button>' +
            '<button id="logMain" class="ui-btn ui-btn--ghost">Main</button>' +
          '</div>' +
        '</div>' +
        '<div id="logList" class="log-list"></div>' +
      '</div>';

    var listEl = document.getElementById('logList');
    var filter = {
      level: '',
      q: '',
      source: '',
      main: false,
    };

    function escapeHtml(s) {
      return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function levelClass(lvl) {
      return 'log-level-' + lvl;
    }

    function render(entry) {
      var time = entry.ts || '';
      var level = entry.level || 'info';
      var src = entry.source || '';
      var msg = entry.message || '';
      var detail = entry.detail;
      var li = document.createElement('div');
      li.className = 'log-row' + (level === 'error' ? ' log-row-err' : '');
      li.innerHTML =
        '<div class="log-time">' + escapeHtml(time) + '</div>' +
        '<div class="log-level ' + levelClass(level) + '">' + escapeHtml(level.toUpperCase()) + '</div>' +
        '<div class="log-src">' + escapeHtml(src) + '</div>' +
        '<div class="log-msg">' + escapeHtml(msg) + '</div>';
      if (detail && typeof detail === 'object') {
        var d = detail;
        if (d.duration_ms !== undefined) {
          li.innerHTML += '<div class="log-meta">' + d.duration_ms + 'ms</div>';
        }
        if (d.tabId !== undefined) {
          li.innerHTML += '<div class="log-meta">tab ' + escapeHtml(d.tabId) + '</div>';
        }
        if (d.message !== undefined) {
          // If the entry we rendered is actually a detail-structured blob, the
          // original message lives in detail.message — keep that as the main text.
          li.innerHTML = '<div class="log-time">' + escapeHtml(time) + '</div>' +
            '<div class="log-level ' + levelClass(level) + '">' + escapeHtml(level.toUpperCase()) + '</div>' +
            '<div class="log-src">' + escapeHtml(src) + '</div>' +
            '<div class="log-msg">' + escapeHtml(String(d.message || msg)) + '</div>';
        }
      }
      li.dataset.src = src;
      li.dataset.level = level;
      return li;
    }

    function load() {
      var url = '/v1/logs?tail=400';
      if (filter.level) url += '&level=' + encodeURIComponent(filter.level);
      if (filter.q) url += '&q=' + encodeURIComponent(filter.q);
      if (filter.source) url += '&source=' + encodeURIComponent(filter.source);
      fetch(url, { headers: { 'X-Log-Tail': '400' } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          try {
            var entries = (data && data.entries) || [];
            listEl.innerHTML = entries.map(render).join('') || '<div class="log-empty">No matching log entries.</div>';
            document.getElementById('logCount').textContent = entries.length + ' entry' + (entries.length !== 1 ? 's' : '');
            // Keep the list scrolled to the bottom unless the user has scrolled up.
            if (listEl.scrollHeight - listEl.clientHeight - listEl.scrollTop < 60) {
              listEl.scrollTop = listEl.scrollHeight;
            }
          } catch (e) {
            listEl.textContent = 'Log fetch failed';
          }
        })
        .catch(function () { listEl.textContent = 'Log fetch failed'; });
    }

    // Wire controls.
    var levelSel = document.getElementById('logLevel');
    if (levelSel) levelSel.addEventListener('change', function () { filter.level = levelSel.value; load(); });
    var searchIn = document.getElementById('logSearch');
    if (searchIn) {
      var debounce = null;
      searchIn.addEventListener('input', function () {
        clearTimeout(debounce);
        debounce = setTimeout(function () { filter.q = searchIn.value; load(); }, 180);
      });
    }
    var srcIn = document.getElementById('logSource');
    if (srcIn) {
      var debounce2 = null;
      srcIn.addEventListener('input', function () {
        clearTimeout(debounce2);
        debounce2 = setTimeout(function () { filter.source = srcIn.value; load(); }, 180);
      });
    }
    var clearBtn = document.getElementById('logClear');
    if (clearBtn) clearBtn.addEventListener('click', function () {
      listEl.textContent = 'Cleared.';
      document.getElementById('logCount').textContent = '0 entries';
    });
    var exportBtn = document.getElementById('logExport');
    if (exportBtn) exportBtn.addEventListener('click', function () {
      fetch('/v1/logs?tail=2000', { headers: { 'X-Log-Tail': '2000' } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var entries = (data && data.entries) || [];
          var blob = new Blob([JSON.stringify(entries, null, 2)], { type: 'application/json' });
          var a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = 'orbit-log-' + new Date().toISOString().slice(0, 10) + '.json';
          a.click();
          URL.revokeObjectURL(a.href);
        });
    });
    var mainBtn = document.getElementById('logMain');
    if (mainBtn) mainBtn.addEventListener('click', function () {
      filter.main = !filter.main;
      load();
    });

    // Poll every 2s (a capped tail fetch is cheap; the server filters on the path).
    setInterval(load, 2000);
    load();
  };

  // ── shared row builders ─────────────────────────────────────── */
  if (window.Chat && typeof window.Chat.renderPanel === 'function') {
    var _chatRenderPanel = window.Chat.renderPanel;
    window.Chat.renderPanel = function (name) {
      if (_ext[name]) return renderPanel(name);
      return _chatRenderPanel(name);
    };
  }

  /* ── shared row builders ─────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function host(url) {
    try { return new URL(url).hostname.replace(/^www\./, ''); } catch (e) { return url; }
  }
  function age(ts) {
    if (!ts) return '';
    var m = Math.round((Date.now() - ts) / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return m + 'm ago';
    var h = Math.floor(m / 60);
    if (h < 24) return h + 'h ago';
    return Math.floor(h / 24) + 'd ago';
  }
  function sectionLabel(t) {
    return '<div class="sbx-label">' + esc(t) + '</div>';
  }

  /* ── 2. Watches panel ────────────────────────────────────────── */
  var watchCache = [];
  function loadWatches() {
    try { watchCache = JSON.parse(localStorage.getItem('orbit-watches') || '[]') || []; }
    catch (e) { watchCache = []; }
    return watchCache;
  }
  function updateWatchBadge() {
    var badge = document.getElementById('railWatchBadge');
    if (!badge) return;
    var n = loadWatches().filter(function (w) { return (w.changes || 0) > 0; }).length;
    badge.textContent = n > 99 ? '99+' : String(n);
    badge.hidden = n === 0;
  }
  window.updateWatchBadge = updateWatchBadge;
  updateWatchBadge();

  function renderWatchesPanel() {
    var watches = loadWatches();
    var html = '<div class="panel-pad">';
    html += sectionLabel('Page watches — JARVIS watches for changes');
    if (!watches.length) {
      html += '<div class="sbx-empty">No watches armed yet.<br><br>';
      html += 'Ask JARVIS to watch a page ("watch this page for changes") or open ';
      html += '<a href="#" data-nav-watch="orbit://watch">orbit://watch</a> to manage them.</div>';
    } else {
      watches.forEach(function (w) {
        var changed = (w.changes || 0) > 0;
        html += '<div class="sbx-row watch' + (changed ? ' changed' : '') + '" data-url="' + esc(w.url) + '">';
        html += '<div class="sbx-row-main"><div class="sbx-title">' + esc(host(w.url)) + '</div>';
        html += '<div class="sbx-sub">' + (w.checks || 0) + ' checks · <b>' + (w.changes || 0) + '</b> changes';
        if (w.last_check) html += ' · ' + age(w.last_check * 1000);
        html += '</div></div>';
        html += (changed ? '<span class="sbx-dot on"></span>' : '<span class="sbx-dot"></span>');
        html += '</div>';
      });
      html += '<button class="sbx-link" id="sbxWatchAll">Open watch manager</button>';
    }
    html += '</div>';
    sbBody.innerHTML = html;
    sbBody.querySelectorAll('.sbx-row.watch').forEach(function (el) {
      el.addEventListener('click', function () { navigateTo(el.dataset.url); });
    });
    var mgr = document.getElementById('sbxWatchAll');
    if (mgr) mgr.addEventListener('click', function () { navigateTo('orbit://watch'); });
    var link = sbBody.querySelector('[data-nav-watch]');
    if (link) link.addEventListener('click', function (e) { e.preventDefault(); navigateTo('orbit://watch'); });
    updateWatchBadge();
  }

  /* ── 3. Flow panel (clock · notes · telemetry) ───────────────── */
  function renderFlowPanel() {
    var html = '<div class="panel-pad">';
    html += '<div class="sbx-clock"><span id="sbxFlowClock">--:--:--</span><span class="sbx-utc">UTC</span></div>';

    html += sectionLabel('Session');
    var mem = document.getElementById('telMem'), fps = document.getElementById('telFps');
    var tabsN = document.getElementById('telTabs'), up = document.getElementById('telUptime');
    html += '<div class="sbx-grid">';
    html += '<div class="sbx-cell"><span>TABS</span><b>' + esc(tabsN ? tabsN.textContent : '0') + '</b></div>';
    html += '<div class="sbx-cell"><span>MEM</span><b>' + esc(mem ? mem.textContent : '--') + '</b></div>';
    html += '<div class="sbx-cell"><span>FPS</span><b>' + esc(fps ? fps.textContent : '--') + '</b></div>';
    html += '<div class="sbx-cell"><span>UPTIME</span><b>' + esc(up ? up.textContent : '0:00') + '</b></div>';
    html += '</div>';

    html += sectionLabel('Quick note');
    var note = '';
    try { note = localStorage.getItem('orbit-notes') || ''; } catch (e) {}
    html += '<textarea id="sbxFlowNote" class="sbx-note" rows="4" placeholder="Scratch space — saved as you type…">' + esc(note) + '</textarea>';

    html += sectionLabel('Shortcuts');
    html += '<div class="sbx-kbd"><span>Command palette</span><span><kbd>Ctrl</kbd> <kbd>K</kbd></span></div>';
    html += '<div class="sbx-kbd"><span>Find in page</span><span><kbd>Ctrl</kbd> <kbd>F</kbd></span></div>';
    html += '<div class="sbx-kbd"><span>New tab</span><span><kbd>Ctrl</kbd> <kbd>T</kbd></span></div>';
    html += '</div>';
    sbBody.innerHTML = html;

    var clock = document.getElementById('sbxFlowClock');
    var t = setInterval(function () {
      if (!clock || !document.body.contains(clock)) { clearInterval(t); return; }
      clock.textContent = new Date().toISOString().slice(11, 19);
    }, 1000);

    var noteEl = document.getElementById('sbxFlowNote');
    if (noteEl) {
      var saved = null;
      noteEl.addEventListener('input', function () {
        clearTimeout(saved);
        saved = setTimeout(function () {
          try { localStorage.setItem('orbit-notes', noteEl.value); } catch (e) {}
        }, 400);
      });
    }
  }

  /* ── 4a. Bookmarks panel ─────────────────────────────────────── */
  function _liveBookmarks() {
    // localStorage is the source of truth (the `bookmarks` global is only
    // refreshed on some paths, e.g. star toggles — never on panel render).
    try { return JSON.parse(localStorage.getItem('orbit-bookmarks') || '[]') || []; }
    catch (e) { return (typeof bookmarks !== 'undefined') ? bookmarks : []; }
  }
  function renderBookmarksPanel() {
    var list = _liveBookmarks();
    var html = '<div class="panel-pad">';
    html += sectionLabel('Bookmarks — saved with the ★ star');
    if (!list.length) {
      html += '<div class="sbx-empty">No bookmarks yet.<br>Press the star in the address bar to save a page.</div>';
    } else {
      list.forEach(function (b, i) {
        html += '<div class="sbx-row" data-url="' + esc(b.url) + '" data-bm="' + i + '">';
        html += '<div class="sbx-fav">★</div><div class="sbx-row-main">';
        html += '<div class="sbx-title">' + esc(b.title || b.url) + '</div>';
        html += '<div class="sbx-sub">' + esc(host(b.url)) + '</div></div>';
        html += '<button class="sbx-x" data-del="' + i + '" title="Remove">×</button></div>';
      });
      html += '<button class="sbx-link" id="sbxOpenAll">Open all in tabs</button>';
    }
    html += '</div>';
    sbBody.innerHTML = html;

    sbBody.querySelectorAll('.sbx-row[data-url]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        if (e.target.closest('.sbx-x')) return;
        navigateTo(el.dataset.url);
      });
    });
    sbBody.querySelectorAll('.sbx-x').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var i = parseInt(btn.dataset.del, 10);
        list.splice(i, 1);
        localStorage.setItem('orbit-bookmarks', JSON.stringify(list));
        try { bookmarks.splice(0, bookmarks.length, list); } catch (e2) { /* global not writable */ }
        if (typeof renderBookmarkBar === 'function') renderBookmarkBar();
        renderBookmarksPanel();
        showToast('info', 'Bookmark removed', '');
      });
    });
    var openAll = document.getElementById('sbxOpenAll');
    if (openAll) openAll.addEventListener('click', function () {
      list.forEach(function (b) { createTab(b.url); });
      showToast('ok', 'Bookmarks opened', list.length + ' tabs');
    });
  }

  /* ── 4b. History panel ───────────────────────────────────────── */
  function renderHistoryPanelSide() {
    var list = (typeof getHistory === 'function') ? getHistory() : [];
    var html = '<div class="panel-pad">';
    html += sectionLabel('Recent history');
    if (!list.length) {
      html += '<div class="sbx-empty">No history yet — pages you visit appear here.</div>';
    } else {
      list.slice(0, 30).forEach(function (h, i) {
        html += '<div class="sbx-row" data-url="' + esc(h.url) + '" data-h="' + i + '">';
        html += '<div class="sbx-fav mono">' + esc(h.url.slice(0, 1).toUpperCase()) + '</div>';
        html += '<div class="sbx-row-main"><div class="sbx-title">' + esc(h.title || h.url) + '</div>';
        html += '<div class="sbx-sub">' + esc(host(h.url)) + ' · ' + age(h.ts) + '</div></div>';
        html += '<button class="sbx-x" data-hdel="' + i + '" title="Remove">×</button></div>';
      });
      html += '<button class="sbx-link" id="sbxHistAll">Open full history page</button>';
    }
    html += '</div>';
    sbBody.innerHTML = html;

    sbBody.querySelectorAll('.sbx-row[data-url]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        if (e.target.closest('.sbx-x')) return;
        navigateTo(el.dataset.url);
      });
    });
    sbBody.querySelectorAll('.sbx-x').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var h = getHistory();
        h.splice(parseInt(btn.dataset.hdel, 10), 1);
        localStorage.setItem('orbit-history', JSON.stringify(h));
        renderHistoryPanelSide();
      });
    });
    var full = document.getElementById('sbxHistAll');
    if (full) full.addEventListener('click', function () { navigateTo('orbit://history'); });
  }

  /* ── 4c. Downloads panel (mirror of pages.js render) ─────────── */
  function renderDownloadsPanel() {
    sbBody.innerHTML = '<div class="panel-pad">' + sectionLabel('Downloads') +
      '<div class="sbx-empty" id="sbxDlHost">Loading…</div></div>';
    var hostEl = document.getElementById('sbxDlHost');
    if (!window.orbit || !window.orbit.downloads || !window.orbit.downloads.list) {
      hostEl.innerHTML = 'Downloads land here. The downloads bridge is not available right now.';
      return;
    }
    window.orbit.downloads.list().then(function (list) {
      if (!hostEl || !document.body.contains(hostEl)) return;
      if (!list || !list.length) {
        hostEl.innerHTML = 'No downloads yet.<br>Files you download appear here.';
        return;
      }
      var html = '';
      list.slice(0, 20).forEach(function (d) {
        var pct = d.receivedBytes && d.totalBytes ? Math.round(100 * d.receivedBytes / d.totalBytes) : (d.state === 'completed' ? 100 : 0);
        var stateTxt = d.state === 'completed' ? (d.path || '').split(/[\\/]/).pop() : (d.state || 'active') + (pct ? ' · ' + pct + '%' : '');
        html += '<div class="sbx-row"><div class="sbx-fav mono">' + (d.state === 'completed' ? '✓' : '↓') + '</div>';
        html += '<div class="sbx-row-main"><div class="sbx-title">' + esc(d.filename || stateTxt) + '</div>';
        html += '<div class="sbx-sub">' + esc(stateTxt) + '</div></div></div>';
      });
      hostEl.className = 'sbx-list';
      hostEl.innerHTML = html;
      hostEl.insertAdjacentHTML('afterend', '<button class="sbx-link" id="sbxDlAll">Open downloads page</button>');
      var all = document.getElementById('sbxDlAll');
      if (all) all.addEventListener('click', function () { navigateTo('orbit://downloads'); });
    }).catch(function () {
      hostEl.textContent = 'Could not load downloads.';
    });
  }

  /* ── 5. NTP quick tiles — were never wired (dead buttons) ────── */
  (function wireNtpTiles() {
    var tiles = document.querySelectorAll('.nt-tile[data-url]');
    tiles.forEach(function (tile) {
      tile.addEventListener('click', function (e) {
        var url = tile.dataset.url;
        if (!url) return;
        if (e.ctrlKey || e.metaKey) createTab(url);
        else navigateTo(url);
      });
    });
  })();

  /* ── 6. Restore last active panel (after boot renders chat) ─── */
  (function restorePanel() {
    var last = null;
    try { last = localStorage.getItem('orbit-panel'); } catch (e) {}
    if (last && _ext[last]) {
      // Defer past renderer.js's boot Chat.renderPanel('jarvis') so the
      // restore wins without fighting the boot sequence.
      setTimeout(function () {
        try { renderPanel(last); } catch (e) { /* boot raced; ignore */ }
      }, 350);
    }
  })();

  /* ── 7. Live watch badge — poll the bridge, animate on change ── */
  (function watchBadgeLive() {
    var _lastChanges = null;
    function bridgeList() {
      try {
        if (window.orbitAPI && typeof window.orbitAPI.kernelRequest === 'function') {
          return window.orbitAPI.kernelRequest({ action: 'page.watch.list' });
        }
      } catch (e) { /* fall through */ }
      return Promise.resolve(null);
    }
    function ingest(state) {
      var watches = (state && state.watches) || null;
      if (!watches) return; // keep localStorage mirror from v2-watch.js
      try {
        localStorage.setItem('orbit-watches', JSON.stringify(watches.map(function (w) {
          return { url: w.url, checks: w.checks, changes: w.changes, last_check: w.last_check };
        })));
      } catch (e) {}
    }
    function tick() {
      var changed = loadWatches().reduce(function (n, w) { return n + (w.changes || 0); }, 0);
      if (_lastChanges !== null && changed > _lastChanges) {
        var badge = document.getElementById('railWatchBadge');
        if (badge) {
          badge.classList.remove('pulse');
          void badge.offsetWidth; // restart the animation
          badge.classList.add('pulse');
        }
      }
      _lastChanges = changed;
      updateWatchBadge();
    }
    setInterval(function () {
      bridgeList().then(function (state) {
        if (state) ingest(state);
        tick();
      }).catch(function () { tick(); });
    }, 30000);
    tick();
  })();

  /* ── 8. Collapse-to-rail mode (Opera GX FX) ─────────────────── */
  (function collapseMode() {
    var sidebar = document.getElementById('sidebar');
    var rail = document.getElementById('sbRail');
    if (!sidebar || !rail) return;

    var COLLAPSE_KEY = 'orbit-sidebar-collapsed';

    function setCollapsed(on, persist) {
      sidebar.classList.toggle('collapsed', !!on);
      if (persist !== false) {
        try { localStorage.setItem(COLLAPSE_KEY, on ? '1' : '0'); } catch (e) {}
      }
    }

    // Double-click the rail background (not a button) toggles collapse.
    rail.addEventListener('dblclick', function (e) {
      if (e.target.closest('button')) return;
      setCollapsed(!sidebar.classList.contains('collapsed'));
    });

    // In collapsed mode the panel becomes a hover flyout: pinning the rail
    // edge with the mouse opens it; leaving closes it. Clicks still route
    // panels through the normal renderPanel path (the flyout IS the panel).
    var flyoutTimer = null;
    sidebar.addEventListener('mouseenter', function (e) {
      if (!sidebar.classList.contains('collapsed')) return;
      clearTimeout(flyoutTimer);
      sidebar.classList.add('flyout');
    });
    sidebar.addEventListener('mouseleave', function (e) {
      if (!sidebar.classList.contains('collapsed')) return;
      clearTimeout(flyoutTimer);
      flyoutTimer = setTimeout(function () {
        sidebar.classList.remove('flyout');
      }, 220); // grace period so diagonal mouse paths don't flicker
    });

    // Restore persisted collapse state.
    try {
      if (localStorage.getItem(COLLAPSE_KEY) === '1') setCollapsed(true, false);
    } catch (e) {}
  })();
})();
