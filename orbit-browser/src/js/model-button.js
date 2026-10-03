/* JARVIS chat-model selector — the AI drawer composer control.
 *
 * The sidebar chip (jarvis.js) and the `/model` slash command already own
 * model selection through `window.dshNative.selectedModel`. This module wires
 * the composer button (#modelButton / #modelMenu) to that SAME selection so the
 * drawer is not a dead control with hardcoded "1B Fast / 3B Balanced" rows that
 * match nothing the bridge actually reports.
 *
 *   GET /v1/models  ->  [{id, provider, model, kind, available}]
 *   selectedModel   ->  persisted in localStorage as "orbit-model"
 *
 * Writing the selection goes through dshNative so the sidebar chip, the
 * /model command, and this button can never drift apart: one setter, one
 * localStorage key, one 'model' event.
 */
(function () {
  'use strict';

  var STORE_KEY = 'orbit-model';

  // ── State ────────────────────────────────────────────────────────────
  var menuOpen = false;
  var loading = false;
  var models = [];
  var populatedFor = null;   // signature of the model list currently rendered
  var wired = false;

  function _bridge() {
    return (window.dshNative && window.dshNative.config && window.dshNative.config.baseUrl)
      || 'http://127.0.0.1:8170';
  }

  function _token() {
    try {
      if (window.dshNative && window.dshNative.config && window.dshNative.config.authToken) {
        return window.dshNative.config.authToken;
      }
      if (window.orbit && typeof window.orbit.getBridgeToken === 'function') {
        return window.orbit.getBridgeToken();
      }
    } catch (e) { /* preload boundary unavailable */ }
    return null;
  }

  function currentId() {
    if (window.dshNative) {
      try { return window.dshNative.selectedModel || null; } catch (e) { /* fall through */ }
    }
    try { return localStorage.getItem(STORE_KEY) || null; } catch (e) { return null; }
  }

  /** Single writer for the selection — never touch localStorage directly. */
  function select(id) {
    var next = id || null;
    if (window.dshNative) {
      window.dshNative.selectedModel = next;   // persists + emits 'model'
      return;
    }
    try {
      if (next) localStorage.setItem(STORE_KEY, next);
      else localStorage.removeItem(STORE_KEY);
    } catch (e) { /* storage unavailable */ }
    render();
  }

  function label(id) {
    if (!id) return 'Auto';
    var parts = String(id).split('/');
    return parts[parts.length - 1] || id;
  }

  // ── Fetch ───────────────────────────────────────────────────────────
  async function fetchModels() {
    if (window.dshNative && typeof window.dshNative.listModels === 'function') {
      try {
        var viaNative = await window.dshNative.listModels();
        if (Array.isArray(viaNative)) return viaNative;
      } catch (e) { /* fall through to a direct fetch */ }
    }
    // dsh-native not injected yet (or it threw): hit the bridge directly so
    // the button still works in a plain browser tab.
    var headers = {};
    var tok = _token();
    if (tok) headers['Authorization'] = 'Bearer ' + tok;
    try {
      var res = await fetch(_bridge() + '/v1/models', {
        method: 'GET',
        headers: headers,
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) return [];
      var body = await res.json();
      return Array.isArray(body && body.models) ? body.models : [];
    } catch (e) {
      return [];
    }
  }

  // ── Render ──────────────────────────────────────────────────────────
  function render() {
    var btn = document.getElementById('modelButton');
    var name = document.getElementById('modelName');
    var menu = document.getElementById('modelMenu');
    if (!btn || !menu) return;

    if (name) name.textContent = label(currentId());
    btn.setAttribute('aria-expanded', String(menuOpen));
    btn.title = currentId() ? 'Model: ' + currentId() : 'Model: auto (router default)';

    // The menu animates off `.open` (see orbit.css); `hidden` is kept in sync
    // so assistive tech and any UA `display:none` agree with the visual state.
    menu.classList.toggle('open', menuOpen);
    menu.hidden = !menuOpen;
    if (!menuOpen) return;

    var sel = currentId();
    var frag = document.createDocumentFragment();

    // "Auto" is always the first row — it means "no pin, use the router chain".
    frag.appendChild(row({ id: null, model: 'Auto', provider: 'router default' }, sel));

    if (loading) {
      var hint = document.createElement('button');
      hint.type = 'button';
      hint.className = 'model-option';
      hint.disabled = true;
      hint.textContent = 'Loading models...';
      frag.appendChild(hint);
    } else if (!models.length) {
      var none = document.createElement('button');
      none.type = 'button';
      none.className = 'model-option';
      none.disabled = true;
      none.textContent = 'No models reported - kernel offline?';
      frag.appendChild(none);
    } else {
      models.forEach(function (m) { frag.appendChild(row(m, sel)); });
    }

    menu.textContent = '';
    menu.appendChild(frag);
  }

  function row(m, sel) {
    var id = m.id || (m.provider ? m.provider + '/' + m.model : m.model);
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'model-option';
    b.dataset.model = id || '';
    b.setAttribute('role', 'menuitemradio');
    b.setAttribute('aria-checked', String((sel || null) === (id || null)));
    if ((sel || null) === (id || null)) b.classList.add('active');
    // An offline provider is still listed (so the user can see it exists) but
    // cannot be pinned — picking it would just burn a fallback hop.
    if (m.available === false) b.disabled = true;

    var lab = document.createElement('span');
    lab.className = 'model-option-label';
    lab.textContent = label(id);
    b.appendChild(lab);

    if (m.provider) {
      var sub = document.createElement('span');
      sub.className = 'model-option-sub';
      sub.textContent = m.available === false ? m.provider + ' (offline)' : m.provider;
      b.appendChild(sub);
    }

    b.addEventListener('click', function () {
      if (b.disabled) return;
      setMenuOpen(false);
      select(id || null);
    });
    return b;
  }

  function setMenuOpen(open) {
    menuOpen = !!open;
    render();
  }

  // ── Population ──────────────────────────────────────────────────────
  // A second refresh() while one is in flight joins the first rather than
  // returning early, so `await refresh()` always means "the list is current".
  var inFlight = null;

  function refresh() {
    if (inFlight) return inFlight;
    var btn = document.getElementById('modelButton');
    if (!btn) return Promise.resolve([]);
    loading = true;
    if (menuOpen) render();
    inFlight = fetchModels().then(function (next) {
      loading = false;
      inFlight = null;
      models = next || [];
      populatedFor = signature(models);
      render();
      return models;
    }, function () {
      loading = false;
      inFlight = null;
      render();
      return models;
    });
    return inFlight;
  }

  function signature(list) {
    return list.map(function (m) { return (m.id || m.model || '') + (m.available ? '1' : '0'); }).join('|');
  }

  // ── Wiring ──────────────────────────────────────────────────────────
  function wire() {
    if (wired) return;
    var btn = document.getElementById('modelButton');
    var menu = document.getElementById('modelMenu');
    if (!btn || !menu) return false;
    wired = true;

    btn.setAttribute('aria-haspopup', 'menu');
    btn.setAttribute('aria-expanded', 'false');
    menu.setAttribute('role', 'menu');

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var opening = !menuOpen;
      setMenuOpen(opening);
      if (opening) {
        // Re-fetch only when the fleet could have changed since last paint.
        var sig = signature(models);
        if (!models.length || populatedFor !== sig) refresh(true);
      }
    });

    document.addEventListener('click', function (e) {
      if (!menuOpen) return;
      if (e.target.closest && e.target.closest('#modelMenu')) return;
      if (e.target.closest && e.target.closest('#modelButton')) return;
      setMenuOpen(false);
    });

    document.addEventListener('keydown', function (e) {
      if (menuOpen && e.key === 'Escape') {
        setMenuOpen(false);
        btn.focus();
      }
    });

    // Any other surface that changes the model (sidebar chip, /model command)
    // must repaint this button too — they share one localStorage key.
    if (window.dshNative && typeof window.dshNative.on === 'function') {
      window.dshNative.on('model', render);
      window.dshNative.on('status', function () { refresh(); });
    }

    render();
    refresh();
    return true;
  }

  function boot(attempts) {
    if (wire()) return;
    if (attempts > 100) return;   // composer markup absent (different shell)
    setTimeout(function () { boot(attempts + 1); }, 100);
  }

  // Small surface for the rest of the UI (and for tests) to reuse.
  window.OrbitModelButton = {
    get: currentId,
    select: select,
    refresh: refresh,
    models: function () { return models.slice(); },
    open: function () { setMenuOpen(true); },
    close: function () { setMenuOpen(false); },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { boot(0); });
  } else {
    boot(0);
  }
})();