/* ORBIT v2 — page.watch manager (orbit://watch).
 * changedetection.io concept: the browser exposes the agent's armed page
 * watches in a dedicated internal page. Additive module — safe if the kernel
 * or a page element is missing.
 *
 * Data source: kernel bridge `page.watch.list` action (falls back to an
 * empty state with instructions when the bridge lacks the endpoint).
 *
 * v2.1: the fetched state is also mirrored to localStorage ("orbit-watches")
 * so the Opera GX sidebar "Watches" rail panel (v2-sidebar.js) can show the
 * same data without a second bridge call.
 */
(function () {
  'use strict';

  function safe(fn, tag) {
    return function () {
      try { fn.apply(null, arguments); }
      catch (e) { if (window.__ORBIT_DEBUG__) console.warn('[v2-watch:' + tag + ']', e); }
    };
  }

  var REGISTERED = false;

  (safe(function initWatchPage() {
    var page = document.getElementById('watchPage');
    if (!page) return;

    var listEl = document.getElementById('watchList');
    var emptyEl = document.getElementById('watchEmpty');
    var urlEl = document.getElementById('watchNewUrl');
    var armBtn = document.getElementById('watchArmBtn');
    var refreshBtn = document.getElementById('watchRefreshBtn');

    function bridgeCall(action, extra) {
      // Kernel bridge via the preload API when present (Electron), else a
      // plain fetch against the dev bridge port.
      try {
        if (window.orbitAPI && typeof window.orbitAPI.kernelRequest === 'function') {
          return window.orbitAPI.kernelRequest({ action: action }).then(function (r) { return r; });
        }
      } catch (e) { /* fall through */ }
      return Promise.resolve(null);
    }

    function esc(s) {
      var d = document.createElement('div');
      d.textContent = String(s == null ? '' : s);
      return d.innerHTML;
    }

    function row(w) {
      var el = document.createElement('div');
      el.className = 'watch-row';
      var url = esc(w.url || '(unknown)');
      var checks = Number(w.checks || 0);
      var changes = Number(w.changes || 0);
      var lastMin = w.last_check ? Math.max(0, Math.round((Date.now() / 1000 - w.last_check) / 60)) : null;
      el.innerHTML =
        '<div class="watch-row-main">' +
        '<div class="watch-url" title="' + url + '">' + url + '</div>' +
        '<div class="watch-meta telemetry">' +
        'checks ' + checks + ' · changes <b class="' + (changes ? 'has-changes' : '') + '">' + changes + '</b>' +
        (lastMin != null ? ' · checked ' + (lastMin < 1 ? 'just now' : lastMin + 'm ago') : '') +
        '</div></div>';
      var rm = document.createElement('button');
      rm.className = 'tool-btn watch-remove';
      rm.textContent = 'Remove';
      rm.addEventListener('click', safe(function () {
        bridgeCall('page.watch.remove', { url: w.url });
        el.remove();
        if (!listEl.children.length && emptyEl) emptyEl.style.display = '';
      }, 'rm'));
      el.appendChild(rm);
      return el;
    }

    function render(state) {
      if (!listEl) return;
      listEl.innerHTML = '';
      var watches = (state && state.watches) || [];
      // Mirror to localStorage for the sidebar Watches panel (best effort).
      try {
        var compact = watches.map(function (w) {
          return { url: w.url, checks: w.checks, changes: w.changes, last_check: w.last_check };
        });
        localStorage.setItem('orbit-watches', JSON.stringify(compact));
        if (typeof updateWatchBadge === 'function') updateWatchBadge();
      } catch (e) { /* private mode etc. */ }
      if (!watches.length) {
        if (emptyEl) emptyEl.style.display = '';
        return;
      }
      if (emptyEl) emptyEl.style.display = 'none';
      watches.forEach(function (w) { listEl.appendChild(row(w)); });
    }

    function refresh() {
      bridgeCall('page.watch.list').then(function (state) {
        render(state);
      }).catch(safe(function () { render(null); }, 'refresh'));
    }

    function arm() {
      var url = urlEl && urlEl.value.trim();
      if (!url) return;
      bridgeCall('page.watch.arm', { url: url }).then(function (res) {
        if (urlEl) urlEl.value = '';
        refresh();
      }).catch(safe(function () {}, 'arm'));
    }

    if (armBtn) armBtn.addEventListener('click', safe(arm, 'arm-click'));
    if (urlEl) urlEl.addEventListener('keydown', safe(function (e) {
      if (e.key === 'Enter') arm();
    }, 'arm-key'));
    if (refreshBtn) refreshBtn.addEventListener('click', safe(refresh, 'refresh-click'));

    // Register internal page id in tabs.js's map (defensive: if tabs.js is
    // missing the entry, patch it at runtime so orbit://watch routes).
    try {
      if (typeof INTERNAL_PAGES !== 'undefined' && !INTERNAL_PAGES['orbit://watch']) {
        INTERNAL_PAGES['orbit://watch'] = 'watchPage';
      }
    } catch (e) { /* INTERNAL_PAGES may be scoped; tabs.js has the entry */ }

    REGISTERED = true;
    if (REGISTERED) refresh(); // initial paint
  }, 'v2-watch-page'))();
})();
