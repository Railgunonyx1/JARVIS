/* pages - extracted from renderer.js by scripts/split_renderer.py.
 * Classic script, loads in the shared global scope before renderer.js.
 * Event bindings use closures so load order never matters.
 */
// ---------------------------------------------------------------------
// ── Permissions Page (real allowlist) ────────────────────────
function renderPermissionsPage() {
  var listEl = document.getElementById('permissionsList');
  if (!listEl || !window.orbit?.permissions) return;
  window.orbit.permissions.list().then(function(perms) {
    if (!perms || perms.length === 0) {
      listEl.innerHTML = '<div class="panel-muted" style="padding:16px;text-align:center">No site permissions granted. Sites must ask, and you approve via the omnibox lock icon.</div>';
      return;
    }
    var html = '';
    perms.forEach(function(entry, idx) {
      var host = entry.origin || '';
      try { host = new URL(entry.origin).hostname; } catch (e) {}
      html += '<div class="row">';
      html += '<div style="flex:1"><div class="name">' + escapeHtml(host) + '</div><div class="sub">' + escapeHtml((entry.permissions || []).join(', ')) + '</div></div>';
      html += '<button class="chip-btn" data-perm-revoke="' + idx + '">Revoke</button>';
      html += '</div>';
    });
    listEl.innerHTML = html;
    listEl.querySelectorAll('[data-perm-revoke]').forEach(function(btn) {
      btn.onclick = function() {
        var entry = perms[parseInt(btn.dataset.permRevoke)];
        if (entry) {
          window.orbit.permissions.revoke(entry.origin).then(function() {
            showToast('ok', 'Permission Revoked', entry.origin);
            renderPermissionsPage();
          });
        }
      };
    });
  }).catch(function() {
    listEl.innerHTML = '<div class="panel-muted" style="padding:16px;text-align:center">Could not load permissions.</div>';
  });
}

// ── Downloads Page (real download tracking) ──────────────────
function renderDownloadsPage() {
  var page = document.getElementById('downloadsPage');
  if (!page) return;
  var group = page.querySelector('.group');
  if (!group) return;
  if (!window.orbit?.downloads) return;

  window.orbit.downloads.list().then(function(list) {
    if (!list || list.length === 0) {
      group.innerHTML = '<div class="panel-muted" style="padding:24px;text-align:center">No downloads yet. Files you download will appear here.</div>';
      return;
    }
    var html = '';
    list.forEach(function(d) {
      var pct = d.total > 0 ? Math.round((d.received / d.total) * 100) : 0;
      var size = d.total > 0 ? formatBytes(d.received) + ' / ' + formatBytes(d.total) : formatBytes(d.received);
      var chip = '';
      if (d.state === 'complete') chip = '<span class="chip ok">Complete</span>';
      else if (d.state === 'cancelled') chip = '<span class="chip bad">Cancelled</span>';
      else if (d.state === 'interrupted') chip = '<span class="chip warn">Interrupted</span>';
      else chip = '<span class="chip">' + pct + '%</span>';
      var actions = '';
      if (d.state === 'downloading') {
        actions = '<button class="chip-btn" data-dl-cancel="' + d.id + '">Cancel</button>';
      } else if (d.state === 'complete') {
        actions = '<button class="chip-btn" data-dl-show="' + d.id + '">Show</button>';
      }
      var progress = d.state === 'downloading' && d.total > 0
        ? '<div style="width:100%;height:2px;background:var(--jb-border);border-radius:1px;margin-top:6px"><div style="width:' + pct + '%;height:100%;background:var(--jb-accent);border-radius:1px"></div></div>'
        : '';
      html += '<div class="row" style="flex-wrap:wrap">';
      html += '<div style="flex:1;min-width:200px"><div class="name">' + escapeHtml(d.filename) + '</div><div class="sub">' + escapeHtml(truncateUrl(d.url)) + ' \u00b7 ' + size + '</div>' + progress + '</div>';
      html += chip + actions;
      html += '</div>';
    });
    group.innerHTML = html;
    group.querySelectorAll('[data-dl-cancel]').forEach(function(btn) {
      btn.onclick = function() { window.orbit.downloads.cancel(parseInt(btn.dataset.dlCancel)); };
    });
    group.querySelectorAll('[data-dl-show]').forEach(function(btn) {
      btn.onclick = function() { window.orbit.downloads.show(parseInt(btn.dataset.dlShow)); };
    });
  }).catch(function() {});
}

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B';
  var units = ['B', 'KB', 'MB', 'GB'];
  var i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
  return Math.round(bytes * 10) / 10 + ' ' + units[i];
}

function renderExtensionsPage() {
  const listEl = document.getElementById("extensionsList");
  if (!listEl) return;
  let html = '<div class="row"><div><div class="name">JARVIS</div><div class="sub">Built into Orbit \u00b7 native intelligence</div></div><span class="chip ok">Built in</span></div>';
  if (typeof EXTENSIONS !== "undefined") {
    EXTENSIONS.forEach((ext) => {
      const st = extStatus(ext.id);
      html += '<div class="row"><div><div class="name">' + escapeHtml(ext.name) + '</div><div class="sub">' + escapeHtml(ext.sub) + '</div></div>' +
        '<span class="chip' + (st.pinned ? " ok" : "") + '">' + (st.pinned ? "Pinned" : "Unpinned") + '</span>' +
        '<span class="chip ' + (st.enabled ? "ok" : "") + '">' + (st.enabled ? "Enabled" : "Disabled") + '</span></div>';
    });
  }
  listEl.innerHTML = html;
}

// ── Omnibox lock security state (Chrome-style) ──────────────
function updateOmniLock(url) {
  var lock = document.getElementById('omniLock');
  if (!lock) return;
  lock.classList.remove('insecure', 'internal');
  if (!url || url === 'about:blank' || url.startsWith('orbit://')) {
    lock.classList.add('internal');
    lock.title = 'Internal page';
    return;
  }
  try {
    var proto = new URL(url).protocol;
    if (proto === 'https:') {
      lock.title = 'Connection is secure';
    } else {
      lock.classList.add('insecure');
      lock.title = 'Not secure \u2014 connection is not encrypted';
    }
  } catch (e) {
    lock.classList.add('internal');
  }
}

// ── Floating JARVIS Chat Window (draggable + resizable) ──────
var jarvisFloat = document.getElementById('jarvisFloat');
var jarvisFloatHead = document.getElementById('jarvisFloatHead');
var jarvisFloatBody = document.getElementById('jarvisFloatBody');
var jarvisFloatInput = document.getElementById('jarvisFloatInput');
var jarvisFloatSend = document.getElementById('jarvisFloatSend');
var _floatMsgSeq = 0;

function toggleJarvisFloat(force) {
  if (!jarvisFloat) return;
  var show = (typeof force === 'boolean') ? force : !jarvisFloat.classList.contains('on');
  jarvisFloat.classList.toggle('on', show);
  jarvisFloat.classList.remove('minimized');
  if (show) {
    // Restore saved position if the window is still on-screen
    try {
      var pos = JSON.parse(localStorage.getItem('jarvis-float-pos') || 'null');
      if (pos && pos.left >= 0 && pos.top >= 0 && pos.left < window.innerWidth - 80 && pos.top < window.innerHeight - 60) {
        jarvisFloat.style.left = pos.left + 'px';
        jarvisFloat.style.top = pos.top + 'px';
        jarvisFloat.style.right = 'auto';
        jarvisFloat.style.bottom = 'auto';
      }
    } catch (e) {}
    if (jarvisFloatInput) setTimeout(function() { jarvisFloatInput.focus(); }, 60);
  }
}

function floatAppend(role, text) {
  if (!jarvisFloatBody) return;
  // Clear the welcome placeholder on first real message
  var ph = jarvisFloatBody.querySelector('.jarvis-float-welcome');
  if (ph) ph.remove();
  var wrap = document.createElement('div');
  wrap.className = 'jfm jfm--' + role;
  var time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  var labels = { user: 'YOU', jarvis: 'JARVIS', error: 'ERROR', system: 'SYS' };
  wrap.innerHTML =
    '<div class="jfm-head">' +
      '<span class="jfm-role"></span>' +
      '<span class="jfm-label">' + (labels[role] || role.toUpperCase()) + '</span>' +
      '<span class="jfm-time">' + time + '</span>' +
    '</div>';
  var body = document.createElement('div');
  body.className = 'jfm-text';
  body.textContent = text;
  wrap.appendChild(body);
  jarvisFloatBody.appendChild(wrap);
  jarvisFloatBody.scrollTop = jarvisFloatBody.scrollHeight;
}

async function floatSend() {
  var text = jarvisFloatInput.value.trim();
  if (!text) return;
  jarvisFloatInput.value = '';
  floatAppend('user', text);
  setMatrix('thinking');
  try {
    // Same brain as the sidebar: bridge first, Needle fallback
    if (window.dshNative && window.dshNative.status.connected) {
      // A-13: same consent-aware page-context collector as the sidebar
      var page = (typeof collectPageContext === 'function') ? await collectPageContext(1200) : null;
      // dshNative.chat() streams by default: it returns {streamId} at once
      // and the reply arrives on 'message' (done) / 'error' events. The old
      // code only inspected the return value, so successful replies were
      // silently dropped. Subscribe BEFORE sending, keyed by streamId so
      // concurrent sidebar replies never land in the float.
      var streamRef = null;
      var floatTimer = null;
      var resetMatrix = function() { setMatrix('idle'); };
      var cleanup = function() {
        window.dshNative.off('message', onMsg);
        window.dshNative.off('error', onErr);
        if (floatTimer) { clearTimeout(floatTimer); floatTimer = null; }
        resetMatrix();
      };
      var onMsg = function(ev) {
        if (streamRef && ev.streamId !== streamRef.streamId) return;
        if (ev.type === 'done') {
          floatAppend('jarvis', ev.text || '(no response)');
          cleanup();
        }
        // 'delta'/'start'/'meta' are handled by the sidebar pipeline.
      };
      var onErr = function(ev) {
        if (streamRef && ev.streamId !== streamRef.streamId) return;
        floatAppend('error', (ev && ev.message) || 'Chat error');
        cleanup();
      };
      floatTimer = setTimeout(function() {
        floatAppend('error', 'JARVIS did not respond in time.');
        cleanup();
      }, 45000);
      window.dshNative.on('message', onMsg);
      window.dshNative.on('error', onErr);
      var res = await window.dshNative.chat(text, { page: page });
      if (res && res.success === false) {
        // The request never started (HTTP/auth error) — no stream events.
        cleanup();
        floatAppend('error', res.error || 'Connection failed');
      } else if (res && res.streamId) {
        streamRef = res;
      } else if (res && res.success === true && typeof res.text === 'string') {
        // Non-streaming reply
        floatAppend('jarvis', res.text || '(empty reply)');
        cleanup();
      }
      return; // matrix reset happens in cleanup() when the reply lands
    } else if (window.orbit?.jarvis && !jarvisOnline) {
      window.orbit.jarvis.chat(text, "orbit-tab-" + (activeTabId || "float"));
      floatAppend('system', 'Sent to JARVIS bridge \u2014 the reply will appear in the JARVIS sidebar.');
    } else {
      // Needle parallel agent (fast path)
      var nr = window.needleAgent.route(text);
      var exec = await window.needleAgent.execute(nr);
      if (exec.done) floatAppend('jarvis', exec.result);
      else if (exec.success) floatAppend('jarvis', exec.result);
      else floatAppend('error', exec.result || 'Could not complete that.');
    }
  } catch (err) {
    floatAppend('error', err.message || 'Something went wrong.');
  }
  setMatrix('idle');
}

if (jarvisFloatHead) {
  // Drag by the header (pointer events work for mouse + touch)
  var _drag = null;
  jarvisFloatHead.addEventListener('pointerdown', function(e) {
    if (e.target.closest('.jarvis-float-btn')) return; // don't drag from buttons
    var rect = jarvisFloat.getBoundingClientRect();
    _drag = { dx: e.clientX - rect.left, dy: e.clientY - rect.top };
    jarvisFloatHead.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  jarvisFloatHead.addEventListener('pointermove', function(e) {
    if (!_drag) return;
    var x = e.clientX - _drag.dx;
    var y = e.clientY - _drag.dy;
    // Keep the window on-screen
    x = Math.max(0, Math.min(x, window.innerWidth - 60));
    y = Math.max(0, Math.min(y, window.innerHeight - 42));
    jarvisFloat.style.left = x + 'px';
    jarvisFloat.style.top = y + 'px';
    jarvisFloat.style.right = 'auto';
    jarvisFloat.style.bottom = 'auto';
  });
  jarvisFloatHead.addEventListener('pointerup', function() {
    if (!_drag) return;
    _drag = null;
    try {
      var rect = jarvisFloat.getBoundingClientRect();
      localStorage.setItem('jarvis-float-pos', JSON.stringify({ left: Math.round(rect.left), top: Math.round(rect.top) }));
    } catch (e) {}
  });

  // Resize from top-left corner
  var floatResizeHandle = document.getElementById('jarvisFloatResize');
  var _rz = null;
  if (floatResizeHandle) {
    floatResizeHandle.addEventListener('pointerdown', function(e) {
      var rect = jarvisFloat.getBoundingClientRect();
      _rz = { x: e.clientX, y: e.clientY, w: rect.width, h: rect.height };
      floatResizeHandle.setPointerCapture(e.pointerId);
      e.preventDefault();
      e.stopPropagation();
    });
    floatResizeHandle.addEventListener('pointermove', function(e) {
      if (!_rz) return;
      var w = Math.max(260, _rz.w - (e.clientX - _rz.x));
      var h = Math.max(300, _rz.h - (e.clientY - _rz.y));
      jarvisFloat.style.width = Math.min(w, window.innerWidth * 0.9) + 'px';
      jarvisFloat.style.height = Math.min(h, window.innerHeight * 0.8) + 'px';
    });
    floatResizeHandle.addEventListener('pointerup', function() { _rz = null; });
  }
}

if (document.getElementById('jarvisFloatClose')) {
  document.getElementById('jarvisFloatClose').addEventListener('click', function() { toggleJarvisFloat(false); });
}
if (document.getElementById('jarvisFloatMin')) {
  document.getElementById('jarvisFloatMin').addEventListener('click', function() {
    jarvisFloat.classList.toggle('minimized');
  });
}
var jarvisFloatBtn = document.getElementById('jarvisFloatBtn');
if (jarvisFloatBtn) jarvisFloatBtn.addEventListener('click', function() { toggleJarvisFloat(); });
if (jarvisFloatSend) jarvisFloatSend.addEventListener('click', function() { return floatSend.apply(this, arguments); });
if (jarvisFloatInput) {
  jarvisFloatInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); floatSend(); }
    if (e.key === 'Escape') toggleJarvisFloat(false);
  });
}
// Escape closes it globally when open and not typing
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape' && jarvisFloat && jarvisFloat.classList.contains('on') &&
      document.activeElement !== jarvisFloatInput) {
    toggleJarvisFloat(false);
  }
});

// Ctrl+Shift+K handled by the main keydown handler (see global shortcuts)
// Sync float matrix animation with global agent state
var _origSetMatrix = setMatrix;
setMatrix = function(state) {
  _origSetMatrix(state);
  var fm = document.getElementById('jarvisFloatMatrix');
  if (fm) fm.dataset.state = state;
};

// ── Tasks Page (real companion + agent task state) ───────────
function renderTasksPage() {
  var listEl = document.getElementById('tasksList');
  if (!listEl) return;
  var rows = '';
  // Companions are the real task runners
  var companions = (typeof _companions !== 'undefined') ? _companions : [];
  if (companions.length === 0) {
    listEl.innerHTML = '<div class="empty-state"><div class="empty-state-icon">\u2699</div>No tasks yet.<br>Create a Companion in the JARVIS sidebar to run autonomous browsing tasks.</div>';
    return;
  }
  companions.forEach(function(c) {
    var chip = '';
    if (c.status === 'running') chip = '<span class="chip ask">Running</span>';
    else if (c.status === 'paused') chip = '<span class="chip warn">Paused</span>';
    else if (c.status === 'done') chip = '<span class="chip ok">Done</span>';
    else if (c.status === 'error') chip = '<span class="chip bad">Failed</span>';
    else chip = '<span class="chip">Idle</span>';
    var elapsed = c.created ? Math.max(1, Math.round((Date.now() - c.created) / 60000)) + 'm' : '';
    rows += '<div class="row">';
    rows += '<div style="flex:1"><div class="name">' + escapeHtml(c.task || c.name) + '</div><div class="sub">' + escapeHtml(c.name) + (c.tabs && c.tabs.length ? ' \u00b7 ' + c.tabs.length + ' tab(s)' : '') + '</div></div>';
    rows += chip + '<span class="meta">' + elapsed + '</span>';
    rows += '</div>';
  });
  listEl.innerHTML = rows;
}

// ── Memory Page (real saved memories) ─────────────────────────
let _memories = JSON.parse(localStorage.getItem('orbit-memories') || '[]');

function renderMemoryPage() {
  var listEl = document.getElementById('memoryList');
  if (!listEl) return;
  if (_memories.length === 0) {
    listEl.innerHTML = '<div class="empty-state"><div class="empty-state-icon">\u{1F9E0}</div>No saved memories yet.<br>JARVIS remembers facts you save here across sessions.</div>';
  } else {
    var html = '';
    _memories.forEach(function(m, idx) {
      var date = new Date(m.time).toLocaleDateString();
      html += '<div class="row">';
      html += '<div style="flex:1"><div class="name">' + escapeHtml(m.text) + '</div><div class="sub">Saved \u00b7 ' + date + '</div></div>';
      html += '<span class="chip">Saved</span><button class="chip-btn" data-mem-del="' + idx + '">Forget</button>';
      html += '</div>';
    });
    listEl.innerHTML = html;
    listEl.querySelectorAll('[data-mem-del]').forEach(function(btn) {
      btn.onclick = function() {
        var idx = parseInt(btn.dataset.memDel);
        var removed = _memories.splice(idx, 1);
        localStorage.setItem('orbit-memories', JSON.stringify(_memories));
        showToast('info', 'Forgotten', removed[0] ? removed[0].text.substring(0, 40) : '');
        renderMemoryPage();
      };
    });
  }
  // Wire save input
  var input = document.getElementById('memoryInput');
  var saveBtn = document.getElementById('memorySaveBtn');
  if (input && saveBtn && !saveBtn.dataset.wired) {
    saveBtn.dataset.wired = '1';
    function saveMemory() {
      var text = input.value.trim();
      if (!text) return;
      _memories.push({ text: text, time: Date.now() });
      localStorage.setItem('orbit-memories', JSON.stringify(_memories));
      input.value = '';
      showToast('ok', 'Memory Saved', text.substring(0, 40));
      renderMemoryPage();
    }
    saveBtn.onclick = function() { return saveMemory.apply(this, arguments); };
    input.onkeydown = function(e) { if (e.key === 'Enter') saveMemory(); };
  }
}

// ── Site Settings Popup (lock icon — Chrome-style) ───────────
const sitePopup = $("#sitePopup");
const omniLock = $("#omniLock");
function renderSitePopup() {
  if (!sitePopup) return;
  const tab = tabs.get(activeTabId);
  let host = "—", origin = "";
  try {
    const u = new URL(tab ? tab.url : "");
    if (u.protocol === "https:" || u.protocol === "http:") {
      host = u.hostname;
      origin = u.origin;
    }
  } catch (e) {}
  const hostEl = document.getElementById("siteHost");
  if (hostEl) hostEl.textContent = host;
  const connEl = document.getElementById("siteConn");
  if (connEl) connEl.textContent = host === "—" ? "Not on a web page" : (origin.startsWith("https") ? "Secure connection" : "Not secure — HTTP");
  const permEl = document.getElementById("sitePerms");
  if (permEl && window.orbit?.system?.permissions?.list) {
    window.orbit.system.permissions.list().then((list) => {
      if (!permEl) return;
      const mine = (Array.isArray(list) ? list : []).filter((p) => p.origin === origin);
      if (!mine.length) {
        permEl.innerHTML = '<div class="site-perm-row"><span>Permissions</span><span class="meta">Default (ask)</span></div>';
        return;
      }
      permEl.innerHTML = '<div class="site-perm-row"><span>Permissions</span><span class="chip ok">' + escapeHtml(mine.length) + " granted</span></div>" + mine.map((p) => '<div class="site-perm-row sub"><span>' + escapeHtml(String(p.permissions || []).slice(0, 40)) + '</span><span class="chip ok">Allowed</span></div>').join("");
    }).catch(() => {});
  }
  const clearBtn = document.getElementById("siteClearData");
  if (clearBtn) clearBtn.dataset.origin = origin;
}
if (omniLock) omniLock.addEventListener("click", (e) => {
  e.stopPropagation();
  closeAllPopups();
  renderSitePopup();
  sitePopup.style.left = "240px";
  sitePopup.style.top = "84px";
  sitePopup.classList.toggle("on");
});
const siteClearBtn = document.getElementById("siteClearData");
if (siteClearBtn) siteClearBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const origin = siteClearBtn.dataset.origin || "";
  if (!origin) { showToast("info", "No site data", "Open a web page first"); return; }
  if (!confirm("Clear cookies and stored data for " + origin + "? This will sign you out of that site.")) return;
  window.orbit?.system?.session?.clearSiteData(origin).then((r) => {
    showToast(r && r.ok ? "ok" : "err", "Site Data", r && r.ok ? "Cleared for " + origin : "Failed to clear");
    renderSitePopup();
  });
});
