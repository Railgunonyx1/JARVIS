/* shell.js — wires the Arc/Zen shell (index.html) to the browser engine.
 * The shell markup (#rail / #sidebar / .toolbar / #assistant / newtab) was
 * introduced without JS bindings, so its controls did nothing: the legacy
 * renderer only knew the old ids. This module is the single place that maps
 * shell affordances onto the existing engine functions (navigateTo, createTab,
 * openCmdPalette, toggleSplitView, UI.prompt, ...). It also defines the four
 * keydown helpers that settings-ux.js calls but were never implemented
 * (toggleCompactMode, toggleSidebar, toggleAssistantDrawer, openCommandPalette).
 * Must load AFTER core/tabs/nav-tools/ui.
 */
(function () {
  'use strict';

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  function bind(el, evt, fn) {
    if (!el) return;
    if (typeof window.on === 'function') window.on(el, evt, fn);
    else el.addEventListener(evt, fn);
  }
  function toast(type, title, msg) {
    if (typeof window.showToast === 'function') { try { window.showToast(type, title, msg); } catch (_) {} }
  }

  // ── Helpers the keydown handler expects ─────────────────────────────
  function toggleCompactMode() {
    var html = document.documentElement;
    var compact = html.dataset.density === 'compact';
    if (compact) html.removeAttribute('data-density');
    else html.dataset.density = 'compact';
    try { localStorage.setItem('orbit-density', compact ? '' : 'compact'); } catch (_) {}
    toast('info', 'Density', compact ? 'Comfortable' : 'Compact');
  }

  function toggleSidebar(force) {
    var app = $('.app');
    if (!app) return;
    var collapsed = force != null ? !force : !app.classList.contains('sidebar-collapsed');
    app.classList.toggle('sidebar-collapsed', collapsed);
    try { localStorage.setItem('orbit-sidebar-collapsed', collapsed ? '1' : ''); } catch (_) {}
  }

  function toggleAssistant(force) {
    var el = $('#assistant');
    if (!el) return;
    var open = force != null ? !!force : !el.classList.contains('open');
    el.classList.toggle('open', open);
    el.setAttribute('aria-hidden', open ? 'false' : 'true');
    if (open) { var inp = $('#assistantInput'); if (inp) setTimeout(function () { try { inp.focus(); } catch (_) {} }, 60); }
  }

  function toggleAssistantDrawer() { toggleAssistant(); }
  function openCommandPalette() { if (typeof window.openCmdPalette === 'function') window.openCmdPalette(); }

  window.toggleCompactMode = toggleCompactMode;
  window.toggleSidebar = toggleSidebar;
  window.toggleAssistant = toggleAssistant;
  window.toggleAssistantDrawer = toggleAssistantDrawer;
  window.openCommandPalette = openCommandPalette;

  // Restore persisted chrome prefs.
  try {
    var theme = localStorage.getItem('orbit-theme');
    if (theme) document.documentElement.dataset.theme = theme;
    if (localStorage.getItem('orbit-density') === 'compact') document.documentElement.dataset.density = 'compact';
    if (localStorage.getItem('orbit-sidebar-collapsed') === '1') { var app0 = $('.app'); if (app0) app0.classList.add('sidebar-collapsed'); }
  } catch (_) {}

  // ── Rail ────────────────────────────────────────────────────────────
  var THEMES = ['dark', 'light', 'minimal'];
  bind($('#themeButton'), 'click', function () {
    var html = document.documentElement;
    var cur = html.dataset.theme || 'dark';
    var next = THEMES[(THEMES.indexOf(cur) + 1) % THEMES.length];
    html.dataset.theme = next;
    try { localStorage.setItem('orbit-theme', next); } catch (_) {}
    toast('info', 'Theme', 'Switched to ' + next);
  });
  bind($('#compactButton'), 'click', function () { toggleCompactMode(); });
  bind($('#settingsRailBtn'), 'click', function () {
    if (typeof window.navigateTo === 'function') window.navigateTo('orbit://settings');
  });
  $$('.rail-nav .space').forEach(function (btn) {
    bind(btn, 'click', function () {
      $$('.rail-nav .space').forEach(function (b) { b.classList.toggle('active', b === btn); });
      var name = btn.dataset.space || (btn.textContent || '').trim();
      try { localStorage.setItem('orbit-space', name); } catch (_) {}
      toast('info', 'Space', 'Switched to ' + name);
    });
  });
  try {
    var sp = localStorage.getItem('orbit-space');
    if (sp) $$('.rail-nav .space').forEach(function (b) { b.classList.toggle('active', b.dataset.space === sp); });
  } catch (_) {}

  // ── Sidebar ─────────────────────────────────────────────────────────
  bind($('#searchButton'), 'click', openCommandPalette);
  bind($('#sidebarMenuBtn'), 'click', function () { var mb = $('#menuBtn'); if (mb) mb.click(); });

  var PINNED = { goodeye: 'orbit://goodeye', f1: 'orbit://f1', worldmon: 'orbit://worldmon', tasks: 'orbit://tasks', memory: 'orbit://memory' };
  $$('.pinned-item[data-action]').forEach(function (el) {
    bind(el, 'click', function () { var u = PINNED[el.dataset.action]; if (u && typeof window.navigateTo === 'function') window.navigateTo(u); });
  });
  var LIB = { bookmarks: 'orbit://bookmarks', history: 'orbit://history', downloads: 'orbit://downloads' };
  $$('.lib-item[data-action]').forEach(function (el) {
    bind(el, 'click', function () { var u = LIB[el.dataset.action]; if (u && typeof window.navigateTo === 'function') window.navigateTo(u); });
  });

  // ── Toolbar ─────────────────────────────────────────────────────────
  bind($('.address'), 'click', function (e) {
    if (e.target && e.target.closest && e.target.closest('#omniStar')) return;
    openCommandPalette();
  });
  bind($('#splitViewBtn'), 'click', function () { if (typeof window.toggleSplitView === 'function') window.toggleSplitView(); });
  bind($('#aiTrigger'), 'click', function () { toggleAssistant(); });

  // ── Address display ─────────────────────────────────────────────────
  // The shell address is display-only (navigation goes through the palette),
  // but it was never updated, so it always read "New Tab". Mirror the active
  // tab's title/URL on every tab change.
  function syncAddress() {
    var el = $('#addressTitle');
    if (!el) return;
    var tab = null;
    try { if (typeof tabs !== 'undefined' && activeTabId != null) tab = tabs.get(activeTabId); } catch (_) {}
    if (!tab) { el.textContent = 'New Tab'; el.title = ''; if (typeof window.updateStarIcon === 'function') window.updateStarIcon(''); return; }
    el.textContent = tab.title || tab.url || 'New Tab';
    el.title = tab.url || '';
    if (typeof window.updateStarIcon === 'function') window.updateStarIcon(tab.url);
  }
  window.syncAddress = syncAddress;
  ['navigateTo', 'activateTab', 'closeTab', 'createTab', 'reopenClosedTab'].forEach(function (fn) {
    var orig = window[fn];
    if (typeof orig !== 'function') return;
    window[fn] = function () { var r = orig.apply(this, arguments); setTimeout(syncAddress, 0); return r; };
  });
  var tabListEl = $('#tabList');
  if (tabListEl && typeof MutationObserver === 'function') {
    var syncTimer = null;
    new MutationObserver(function () { clearTimeout(syncTimer); syncTimer = setTimeout(syncAddress, 50); })
      .observe(tabListEl, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
  }
  setTimeout(syncAddress, 120);

  // ── Assistant drawer ────────────────────────────────────────────────
  bind($('#closeAssistant'), 'click', function () { toggleAssistant(false); });

  function appendMsg(role, text) {
    var thread = $('#assistantThread');
    if (!thread) return null;
    var el = document.createElement('div');
    el.className = 'assistant-msg ' + role;
    el.textContent = text;
    thread.appendChild(el);
    thread.scrollTop = thread.scrollHeight;
    return el;
  }
  function setState(text) { var s = $('#assistantState'); if (s) s.textContent = '\u25cf ' + text; }

  function assistantSend() {
    var input = $('#assistantInput');
    if (!input) return;
    var text = (input.value || '').trim();
    if (!text) return;
    input.value = '';
    appendMsg('user', text);
    setState('Thinking\u2026');
    var finish = function (reply) { appendMsg('assistant', reply || '(no reply)'); setState('Ready'); };
    try {
      if (window.dshNative && typeof window.dshNative.chat === 'function') {
        Promise.resolve(window.dshNative.chat(text, {})).then(function (res) {
          if (res && typeof res.text === 'string' && res.text) finish(res.text);
          else if (res && res.streamId) finish('(streaming \u2014 reply appears in the chat panel)');
          else if (res && res.success === false) finish('Error: ' + (res.error || 'request failed'));
          else finish(res && res.text);
        }).catch(function (e) { finish('Error: ' + ((e && e.message) || e)); });
        return;
      }
      if (window.orbit && window.orbit.jarvis && typeof window.orbit.jarvis.chat === 'function') {
        Promise.resolve(window.orbit.jarvis.chat(text)).then(function (res) {
          finish(res && (res.text || res.message));
        }).catch(function (e) { finish('Error: ' + ((e && e.message) || e)); });
        return;
      }
      finish('JARVIS is offline \u2014 start the JARVIS bridge to chat.');
    } catch (e) {
      finish('Error: ' + ((e && e.message) || e));
    }
  }
  var aInput = $('#assistantInput');
  bind(aInput, 'keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); assistantSend(); }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      var el = $('#assistant');
      if (el && el.classList.contains('open')) toggleAssistant(false);
    }
  });
})();
