/* sidebar - extracted from renderer.js by scripts/split_renderer.py.
 * Classic script, loads in the shared global scope before renderer.js.
 * Event bindings use closures so load order never matters.
 */
// ---------------------------------------------------------------------
// ── Sidebar Toggle / JARVIS Launch ────────────────────────────
var jarvisLaunchLabel = document.getElementById('jarvisLaunchLabel');

jarvisBtn.addEventListener("click", () => {
  // If JARVIS is offline, start it first
  if (!jarvisOnline) {
    startJarvis();
    return;
  }
  // If online, toggle sidebar
  sidebarOpen = !sidebarOpen;
  sidebar.classList.toggle("hidden", !sidebarOpen);
  jarvisBtn.classList.toggle("active", sidebarOpen);
  setMatrix(agentState);
});

// ── Private Window with PIN Protection (Safari-style) ──────
function openPrivateWindow() {
  // Check if PIN is required
  if (window.orbit && window.orbit.window && window.orbit.window.isLocked) {
    window.orbit.window.isLocked().then(function(locked) {
      if (locked) {
        // Show PIN prompt
        showPrivatePinPrompt();
      } else {
        window.orbit.window.createPrivate();
      }
    }).catch(function() {
      window.orbit.window.createPrivate();
    });
  } else {
    window.orbit?.window?.createPrivate?.();
  }
}

function showPrivatePinPrompt() {
  var overlay = document.createElement('div');
  overlay.className = 'shortcuts-overlay active';
  var h = '';
  h += '<div class="shortcuts-card" style="max-width:360px;text-align:center">';
  h += '<div style="font-size:32px;margin-bottom:12px">\u{1F512}</div>';
  h += '<h2 style="font-size:16px;color:var(--jb-paper);margin-bottom:4px">Private Window Locked</h2>';
  h += '<p style="font-size:12px;color:var(--jb-mute);margin-bottom:16px">Enter your PIN to open a private window</p>';
  h += '<input type="password" id="privatePinInput" maxlength="128" style="width:100%;padding:10px 14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.15);border-radius:8px;color:#fff;font-size:14px;text-align:center;letter-spacing:4px;outline:none;margin-bottom:12px" placeholder="Enter PIN" />';
  h += '<div id="privatePinError" style="font-size:11px;color:#f87171;margin-bottom:12px;display:none"></div>';
  h += '<div style="display:flex;gap:8px">';
  h += '<button id="privatePinCancel" style="flex:1;padding:8px;border-radius:6px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:var(--jb-mute);font-size:12px;cursor:pointer">Cancel</button>';
  h += '<button id="privatePinSubmit" style="flex:1;padding:8px;border-radius:6px;background:var(--jb-accent);border:none;color:#fff;font-size:12px;font-weight:500;cursor:pointer">Unlock</button>';
  h += '</div></div>';
  overlay.innerHTML = h;
  document.body.appendChild(overlay);
  var input = overlay.querySelector('#privatePinInput');
  var error = overlay.querySelector('#privatePinError');
  var cancelBtn = overlay.querySelector('#privatePinCancel');
  var submitBtn = overlay.querySelector('#privatePinSubmit');
  input.focus();
  function close() { overlay.remove(); }
  cancelBtn.onclick = function() { return close.apply(this, arguments); };
  overlay.onclick = function(e) { if (e.target === overlay) close(); };
  function submit() {
    var pin = input.value;
    if (!pin) { error.textContent = 'Please enter your PIN'; error.style.display = 'block'; return; }
    window.orbit.window.checkPin(pin).then(function(ok) {
      if (ok) { close(); window.orbit.window.createPrivate(); }
      else { error.textContent = 'Incorrect PIN. Try again.'; error.style.display = 'block'; input.value = ''; input.focus(); }
    }).catch(function() { error.textContent = 'Verification failed'; error.style.display = 'block'; });
  }
  submitBtn.onclick = function() { return submit.apply(this, arguments); };
  input.onkeydown = function(e) { if (e.key === 'Enter') submit(); if (e.key === 'Escape') close(); };
}

function startJarvis() {
  // Try to connect to JARVIS bridge
  if (window.orbit && window.orbit.jarvis) {
    showToast('info', 'Starting JARVIS', 'Connecting to JARVIS kernel...');
    setMatrix('thinking');
    window.orbit.jarvis.status().then(function(s) {
      if (s && s.ok) {
        jarvisOnline = true;
        updateJarvisStatusUI(true);
        // Open sidebar
        sidebarOpen = true;
        sidebar.classList.remove('hidden');
        jarvisBtn.classList.add('active');
        setMatrix('idle');
        showToast('ok', 'JARVIS Online', 'JARVIS is ready to use');
        Chat.append('system', 'JARVIS is now online. Ask me anything!');
      } else {
        // Bridge not running - offer Needle as fallback
        setMatrix('fail');
        showToast('warn', 'JARVIS Offline', 'Bridge not running. Using local Needle AI instead.');
        startNeedleMode();
      }
    }).catch(function() {
      // Bridge not running - offer Needle as fallback
      setMatrix('fail');
      showToast('info', 'Using Needle AI', 'Bridge not found. Starting local 14MB AI agent...');
      startNeedleMode();
    });
  } else {
    showToast('info', 'Using Needle AI', 'Starting local AI agent (no server needed)...');
    startNeedleMode();
  }
}

function startNeedleMode() {
  // Enable Needle local AI mode
  jarvisOnline = true;
  updateJarvisStatusUI(true);
  sidebarOpen = true;
  sidebar.classList.remove('hidden');
  jarvisBtn.classList.add('active');
  setMatrix('idle');
  Chat.append('jarvis', 'Needle AI is active (14MB local model). I can help you navigate, search, and interact with pages. No server required!');
  Chat.append('system', 'Tip: Type commands like "search for cats", "go to github.com", "read this page"');
}

function updateJarvisStatusUI(online) {
  var statusDot = document.getElementById('jarvisStatus');
  if (jarvisLaunchLabel) {
    jarvisLaunchLabel.textContent = online ? 'Online' : 'Start';
    jarvisLaunchLabel.classList.toggle('hidden', false);
  }
  jarvisBtn.classList.toggle('online', online);
  jarvisBtn.title = online ? 'JARVIS online — click to toggle sidebar' : 'Start JARVIS';
}

sbClose.addEventListener("click", () => {
  sidebarOpen = false;
  sidebar.classList.add("hidden");
  jarvisBtn.classList.remove("active");
  setMatrix(agentState);
});

// ── Jarvis Status Indicator ───────────────────────────────────
var jarvisStatusEl = document.getElementById('jarvisStatus');
if (window.orbit && window.orbit.jarvis && window.orbit.jarvis.onStatus) {
  window.orbit.jarvis.onStatus(function(status) {
    var isOnline = !!(status && status.ok);
    jarvisOnline = isOnline;
    if (jarvisStatusEl) {
      jarvisStatusEl.className = isOnline ? 'online' : 'offline';
      jarvisStatusEl.title = isOnline ? 'JARVIS online' : 'JARVIS offline';
    }
    updateJarvisStatusUI(isOnline);
    if (isOnline) setMatrix('idle');
  });
}

if (floatGlyph) floatGlyph.addEventListener("click", () => {
  sidebarOpen = true;
  sidebar.classList.remove("hidden");
  jarvisBtn.classList.add("active");
  setMatrix(agentState);
});

// ── Sidebar Navigation ────────────────────────────────────────
if (sbNav) sbNav.addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (btn?.dataset.panel) {
    sbNav.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === btn));
    renderPanel(btn.dataset.panel);
  }
});

function renderPanel(name) {
  // Delegate chat panels to Chat module
  if (name === "jarvis" || name === "chat-history" || name === "activity") {
    Chat.renderPanel(name);
    return;
  }
  if (name === "vision") { renderVisionPanel(); return; }
  if (name === "agents") {
    sbBody.innerHTML = '<div class="panel-pad"><div style="border:1px solid var(--jb-border);border-radius:12px;padding:12px;background:var(--jb-void);margin-bottom:8px"><div style="display:flex;align-items:center;gap:8px"><div class="sb-matrix" data-state="idle"></div><h3 style="font-size:13px;color:var(--jb-paper);font-weight:500">Main agent</h3></div><p style="color:var(--jb-mute);font-size:12px;margin-top:6px">No active task</p></div></div>';
    sbBody.querySelectorAll(".sb-matrix").forEach(initMatrix);
  } else if (name === "workspaces") {
    renderWorkspacesPanel();
  } else if (name === "companions") {
    renderCompanionsPanel();
  } else if (name === "tools") {
    renderToolsPanel();
  } else if (name === "memory") {
    sbBody.innerHTML = '<div class="panel-pad panel-muted">No saved memories yet.</div>';
  }
}

// ── AI Companions (Strawberry-style autonomous agents) ─────────
const _companions = [];
let _companionIdSeq = 0;

// ── Sidebar Tools Panel (Notes, Calculator, Dictionary) ──────
function renderToolsPanel() {
  const html = [];
  html.push('<div class="panel-pad">');
  html.push('<h3 style="font-size:13px;color:var(--jb-paper);font-weight:500;margin-bottom:12px">Tools</h3>');

  // Notes
  html.push('<div style="margin-bottom:16px">');
  html.push('<div style="font-size:11px;color:var(--jb-mute);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px">Notes</div>');
  html.push('<textarea id="sidebarNotes" style="width:100%;height:120px;background:var(--jb-void);border:1px solid var(--jb-border);border-radius:8px;padding:10px;color:var(--jb-paper);font-size:12px;resize:vertical;outline:none;font-family:inherit" placeholder="Quick notes...">' + escapeHtml(localStorage.getItem('orbit-notes') || '') + '</textarea>');
  html.push('<button id="saveNotes" style="margin-top:6px;padding:4px 12px;border-radius:6px;background:var(--jb-accent);color:#fff;border:none;font-size:11px;cursor:pointer">Save</button>');
  html.push('</div>');

  // Calculator
  html.push('<div style="margin-bottom:16px">');
  html.push('<div style="font-size:11px;color:var(--jb-mute);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px">Calculator</div>');
  html.push('<input type="text" id="calcInput" style="width:100%;background:var(--jb-void);border:1px solid var(--jb-border);border-radius:8px;padding:8px 10px;color:var(--jb-paper);font-size:13px;outline:none;font-family:monospace" placeholder="Enter expression...">');
  html.push('<div id="calcResult" style="margin-top:6px;font-size:18px;color:var(--jb-accent);font-family:monospace;min-height:24px"></div>');
  html.push('</div>');

  // Dictionary
  html.push('<div style="margin-bottom:16px">');
  html.push('<div style="font-size:11px;color:var(--jb-mute);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px">Dictionary</div>');
  html.push('<div style="display:flex;gap:6px">');
  html.push('<input type="text" id="dictInput" style="flex:1;background:var(--jb-void);border:1px solid var(--jb-border);border-radius:8px;padding:8px 10px;color:var(--jb-paper);font-size:12px;outline:none" placeholder="Look up word...">');
  html.push('<button id="dictLookup" style="padding:8px 12px;border-radius:6px;background:var(--jb-accent);color:#fff;border:none;font-size:11px;cursor:pointer">Go</button>');
  html.push('</div>');
  html.push('<div id="dictResult" style="margin-top:8px;font-size:12px;color:var(--jb-text);line-height:1.5"></div>');
  html.push('</div>');

  // Quick Links
  html.push('<div>');
  html.push('<div style="font-size:11px;color:var(--jb-mute);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px">Quick Links</div>');
  html.push('<div style="display:flex;flex-wrap:wrap;gap:6px">');
  var links = [
    { label: 'Gmail', url: 'https://mail.google.com' },
    { label: 'GitHub', url: 'https://github.com' },
    { label: 'YouTube', url: 'https://youtube.com' },
    { label: 'Reddit', url: 'https://reddit.com' },
    { label: 'Twitter', url: 'https://twitter.com' },
    { label: 'Docs', url: 'https://docs.google.com' },
  ];
  links.forEach(function(lnk) {
    html.push('<button class="sb-chip" onclick="navigateTo(\'' + lnk.url + '\')" style="font-size:11px">' + lnk.label + '</button>');
  });
  html.push('</div>');
  html.push('</div>');

  html.push('</div>');
  sbBody.innerHTML = html.join('');

  // Wire events
  var notesArea = document.getElementById('sidebarNotes');
  var saveBtn = document.getElementById('saveNotes');
  if (saveBtn && notesArea) {
    saveBtn.addEventListener('click', function() {
      localStorage.setItem('orbit-notes', notesArea.value);
      showToast('ok', 'Notes Saved', 'Stored locally');
    });
  }

  var calcInput = document.getElementById('calcInput');
  var calcResult = document.getElementById('calcResult');
  if (calcInput && calcResult) {
    calcInput.addEventListener('input', function() {
      try {
        var expr = calcInput.value.replace(/[^0-9+\-*/().% ]/g, '');
        if (expr.trim()) {
          var result = Function('"use strict"; return (' + expr + ')')();
          calcResult.textContent = '= ' + result;
        } else {
          calcResult.textContent = '';
        }
      } catch (e) {
        calcResult.textContent = 'Invalid expression';
      }
    });
  }

  var dictInput = document.getElementById('dictInput');
  var dictLookup = document.getElementById('dictLookup');
  var dictResult = document.getElementById('dictResult');
  if (dictLookup && dictInput && dictResult) {
    dictLookup.addEventListener('click', function() {
      var word = dictInput.value.trim();
      if (!word) return;
      dictResult.innerHTML = '<span style="color:var(--jb-mute)">Looking up...</span>';
      fetch('https://api.dictionaryapi.dev/api/v2/entries/en/' + encodeURIComponent(word))
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data && data[0] && data[0].meanings && data[0].meanings[0]) {
            var m = data[0].meanings[0];
            var def = m.definitions && m.definitions[0] ? m.definitions[0].definition : '';
            dictResult.innerHTML = '<div style="font-weight:500;color:var(--jb-paper);margin-bottom:4px">' + word + ' <span style="color:var(--jb-mute);font-size:11px">(' + m.partOfSpeech + ')</span></div>' +
              '<div>' + escapeHtml(def) + '</div>';
          } else {
            dictResult.innerHTML = '<span style="color:var(--jb-mute)">No definition found</span>';
          }
        })
        .catch(function() {
          dictResult.innerHTML = '<span style="color:var(--jb-mute)">Lookup failed</span>';
        });
    });
    dictInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') dictLookup.click();
    });
  }
}

// ── Workspaces Panel (Arc/Zen-style Spaces) ───────────────
var _workspaces = [
  { id: 'work', name: 'Work', icon: '\u{1F4BC}', color: '#8AA4C8', active: true },
  { id: 'personal', name: 'Personal', icon: '\u{1F3E0}', color: '#6F9B6A', active: false },
  { id: 'research', name: 'Research', icon: '\u{1F52C}', color: '#C9A227', active: false },
  { id: 'dev', name: 'Development', icon: '\u{1F4BB}', color: '#D71921', active: false },
];
var _activeWorkspaceId = 'work';

function renderWorkspacesPanel() {
  var html = [];
  html.push('<div class="panel-pad">');
  html.push('<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">');
  html.push('<h3 style="font-size:13px;color:var(--jb-paper);font-weight:500;margin:0">Spaces</h3>');
  html.push('<button id="wsCreate" style="background:var(--jb-accent);color:#fff;border:none;border-radius:8px;padding:4px 10px;font-size:11px;cursor:pointer;font-weight:500">+ New</button>');
  html.push('</div>');
  _workspaces.forEach(function(ws) {
    var isActive = ws.id === _activeWorkspaceId;
    html.push('<div class="ws-card' + (isActive ? ' active' : '') + '" data-wsid="' + ws.id + '" style="border:1px solid ' + (isActive ? ws.color : 'var(--jb-border)') + ';border-radius:10px;padding:10px;margin-bottom:8px;background:' + (isActive ? ws.color + '11' : 'var(--jb-void)') + ';cursor:pointer;transition:all .15s">');
    html.push('<div style="display:flex;align-items:center;gap:8px">');
    html.push('<span style="font-size:18px">' + ws.icon + '</span>');
    html.push('<span style="font-size:12px;font-weight:500;color:var(--jb-paper);flex:1">' + escapeHtml(ws.name) + '</span>');
    if (isActive) html.push('<span style="font-size:10px;color:' + ws.color + ';font-weight:500">Active</span>');
    html.push('</div>');
    html.push('</div>');
  });
  html.push('<div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--jb-border)">');
  html.push('<div style="font-size:11px;color:var(--jb-mute);margin-bottom:6px">Current space isolates cookies, storage, and tabs.</div>');
  html.push('<div style="font-size:11px;color:var(--jb-mute)">Switch spaces to separate work, personal, and research browsing.</div>');
  html.push('</div>');
  html.push('</div>');
  sbBody.innerHTML = html.join('');
  // Wire events
  sbBody.querySelectorAll('.ws-card').forEach(function(card) {
    card.addEventListener('click', function() {
      var wsid = card.dataset.wsid;
      switchWorkspace(wsid);
    });
  });
  var createBtn = document.getElementById('wsCreate');
  if (createBtn) createBtn.addEventListener('click', function() {
    var name = prompt('Space name:', '');
    if (!name) return;
    var icons = ['\u{1F3F0}', '\u{1F30A}', '\u{1F3AF}', '\u{1F4D6}', '\u{1F3B5}'];
    var colors = ['#8ab4f8', '#f28b82', '#81c995', '#fdd663', '#d7aefb'];
    _workspaces.push({
      id: 'ws-' + Date.now(),
      name: name,
      icon: icons[Math.floor(Math.random() * icons.length)],
      color: colors[Math.floor(Math.random() * colors.length)],
      active: false,
    });
    renderWorkspacesPanel();
  });
}

function switchWorkspace(wsid) {
  _activeWorkspaceId = wsid;
  _workspaces.forEach(function(ws) { ws.active = ws.id === wsid; });
  renderWorkspacesPanel();
  showToast('info', 'Space switched', 'Now browsing in: ' + _workspaces.find(function(w) { return w.id === wsid; }).name);
}

function renderCompanionsPanel() {
  const html = [];
  html.push('<div class="panel-pad">');
  html.push('<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">');
  html.push('<h3 style="font-size:13px;color:var(--jb-paper);font-weight:500;margin:0">Companions</h3>');
  html.push('<button id="companionCreate" style="background:var(--jb-accent);color:#fff;border:none;border-radius:8px;padding:4px 10px;font-size:11px;cursor:pointer;font-weight:500">+ New</button>');
  html.push('</div>');
  if (_companions.length === 0) {
    html.push('<div style="text-align:center;padding:24px 0;color:var(--jb-mute);font-size:12px">');
    html.push('<div style="font-size:28px;margin-bottom:8px">\u{1F916}</div>');
    html.push('No companions yet.<br>Create one to automate browsing tasks.');
    html.push('</div>');
  } else {
    _companions.forEach(function(c) {
      var statusColor = c.status === 'running' ? 'var(--jb-accent)' : c.status === 'done' ? '#4ade80' : c.status === 'error' ? '#f87171' : 'var(--jb-mute)';
      var statusLabel = c.status === 'running' ? 'Running' : c.status === 'done' ? 'Completed' : c.status === 'error' ? 'Failed' : 'Idle';
      html.push('<div class="companion-card" data-cid="' + c.id + '" style="border:1px solid var(--jb-border);border-radius:10px;padding:10px;margin-bottom:8px;background:var(--jb-void)">');
      html.push('<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">');
      html.push('<div style="width:8px;height:8px;border-radius:50%;background:' + statusColor + '"></div>');
      html.push('<span style="font-size:12px;font-weight:500;color:var(--jb-paper);flex:1">' + escapeHtml(c.name) + '</span>');
      html.push('<span style="font-size:10px;color:' + statusColor + '">' + statusLabel + '</span>');
      html.push('</div>');
      html.push('<div style="font-size:11px;color:var(--jb-mute);margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + escapeHtml(c.task) + '</div>');
      if (c.tabs && c.tabs.length > 0) {
        html.push('<div style="font-size:10px;color:var(--jb-mute);margin-bottom:6px">' + c.tabs.length + ' tab' + (c.tabs.length > 1 ? 's' : '') + ' open</div>');
      }
      html.push('<div style="display:flex;gap:4px">');
      if (c.status === 'idle') {
        html.push('<button class="companion-action" data-action="start" data-cid="' + c.id + '" style="flex:1;background:var(--jb-accent);color:#fff;border:none;border-radius:6px;padding:4px 0;font-size:10px;cursor:pointer">Start</button>');
      } else if (c.status === 'running') {
        html.push('<button class="companion-action" data-action="pause" data-cid="' + c.id + '" style="flex:1;background:var(--jb-muted);color:var(--jb-paper);border:none;border-radius:6px;padding:4px 0;font-size:10px;cursor:pointer">Pause</button>');
      } else if (c.status === 'paused') {
        html.push('<button class="companion-action" data-action="resume" data-cid="' + c.id + '" style="flex:1;background:var(--jb-accent);color:#fff;border:none;border-radius:6px;padding:4px 0;font-size:10px;cursor:pointer">Resume</button>');
      }
      html.push('<button class="companion-action" data-action="stop" data-cid="' + c.id + '" style="background:none;color:var(--jb-mute);border:1px solid var(--jb-border);border-radius:6px;padding:4px 8px;font-size:10px;cursor:pointer">Stop</button>');
      html.push('<button class="companion-action" data-action="remove" data-cid="' + c.id + '" style="background:none;color:#f87171;border:1px solid var(--jb-border);border-radius:6px;padding:4px 8px;font-size:10px;cursor:pointer">\u2715</button>');
      html.push('</div>');
      html.push('</div>');
    });
  }
  html.push('</div>');
  sbBody.innerHTML = html.join('');
  // Wire events
  var createBtn = document.getElementById('companionCreate');
  if (createBtn) createBtn.addEventListener('click', function() { return createCompanion.apply(this, arguments); });
  sbBody.querySelectorAll('.companion-action').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var action = btn.dataset.action;
      var cid = parseInt(btn.dataset.cid);
      if (action === 'start') startCompanion(cid);
      else if (action === 'pause') pauseCompanion(cid);
      else if (action === 'resume') resumeCompanion(cid);
      else if (action === 'stop') stopCompanion(cid);
      else if (action === 'remove') removeCompanion(cid);
    });
  });
}

function createCompanion() {
  var name = prompt('Companion name:', 'Research Agent ' + (_companionIdSeq + 1));
  if (!name) return;
  var task = prompt('What should this companion do?', '');
  if (!task) return;
  _companions.push({
    id: ++_companionIdSeq,
    name: name,
    task: task,
    status: 'idle',
    tabs: [],
    log: [],
    created: Date.now(),
  });
  renderCompanionsPanel();
}

function startCompanion(cid) {
  var c = _companions.find(function(x) { return x.id === cid; });
  if (!c || c.status !== 'idle') return;
  c.status = 'running';
  c.log.push({ time: Date.now(), msg: 'Started' });
  // Create a dedicated tab for this companion
  createTab('orbit://newtab');
  var newTabId = activeTabId;
  c.tabs.push(newTabId);
  // Register as agent-owned
  var tab = tabs.get(newTabId);
  if (tab) tab.agentOwned = true;
  _renderTabs();
  // Send task to JARVIS
  sendToJarvis({ type: 'companion_task', payload: { companionId: cid, name: c.name, task: c.task, tabId: newTabId } });
  showToast('Companion \"' + c.name + '\" started');
  renderCompanionsPanel();
}

function pauseCompanion(cid) {
  var c = _companions.find(function(x) { return x.id === cid; });
  if (!c || c.status !== 'running') return;
  c.status = 'paused';
  c.log.push({ time: Date.now(), msg: 'Paused' });
  showToast('Companion \"' + c.name + '\" paused');
  renderCompanionsPanel();
}

function resumeCompanion(cid) {
  var c = _companions.find(function(x) { return x.id === cid; });
  if (!c || c.status !== 'paused') return;
  c.status = 'running';
  c.log.push({ time: Date.now(), msg: 'Resumed' });
  sendToJarvis({ type: 'companion_resume', payload: { companionId: cid, task: c.task } });
  showToast('Companion \"' + c.name + '\" resumed');
  renderCompanionsPanel();
}

function stopCompanion(cid) {
  var c = _companions.find(function(x) { return x.id === cid; });
  if (!c) return;
  c.status = 'idle';
  c.log.push({ time: Date.now(), msg: 'Stopped' });
  sendToJarvis({ type: 'companion_stop', payload: { companionId: cid } });
  showToast('Companion \"' + c.name + '\" stopped');
  renderCompanionsPanel();
}

function removeCompanion(cid) {
  var idx = _companions.findIndex(function(x) { return x.id === cid; });
  if (idx < 0) return;
  var c = _companions[idx];
  // Close companion tabs
  c.tabs.forEach(function(tid) { closeTab(tid); });
  _companions.splice(idx, 1);
  showToast('Companion \"' + c.name + '\" removed');
  renderCompanionsPanel();
}
