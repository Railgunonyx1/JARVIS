/* jarvis - extracted from renderer.js by scripts/split_renderer.py.
 * Classic script, loads in the shared global scope before renderer.js.
 * Event bindings use closures so load order never matters.
 */
// ---------------------------------------------------------------------
// ── Composer (DSH Native Integration) ──────────────────────────
if (sbSend) sbSend.addEventListener("click", function() { return sendToJarvis.apply(this, arguments); });
if (sbInput) {
  sbInput.addEventListener("keydown", (e) => {
    // Slash-command popup keyboard navigation
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      const popup = document.querySelector(".cmd-popup");
      if (popup && popup.style.display !== "none") {
        e.preventDefault();
        const items = popup.querySelectorAll(".cmd-popup-item");
        if (!items.length) return;
        let idx = Array.from(items).findIndex((el) => el.classList.contains("active"));
        if (e.key === "ArrowDown") idx = (idx + 1) % items.length;
        else idx = (idx - 1 + items.length) % items.length;
        items.forEach((el) => el.classList.remove("active"));
        items[idx].classList.add("active");
        items[idx].scrollIntoView({ block: "nearest" });
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      // If a slash-command item is highlighted, fill it instead of sending
      const active = document.querySelector(".cmd-popup-item.active");
      if (active) {
        e.preventDefault();
        sbInput.value = active.dataset.cmd + " ";
        Chat.hideCmdPopup();
        sbInput.focus();
        return;
      }
      e.preventDefault(); sendToJarvis();
    }
    // Escape closes command popup
    if (e.key === "Escape") Chat.hideCmdPopup();
  });
  // Slash-command autocomplete
  sbInput.addEventListener("input", () => {
    const val = sbInput.value;
    if (val.startsWith("/")) {
      Chat.showCmdPopup(val.substring(1));
    } else {
      Chat.hideCmdPopup();
    }
  });
}

async function sendToJarvis() {
  const text = sbInput.value.trim();
  if (!text) return;
  sbInput.value = "";
  Chat.hideCmdPopup();
  if (window.Chat) Chat.pendingStreamTabId = activeTabId;
  Chat.append("user", text);

  // Slash commands
  if (text.startsWith("/")) {
    handleDshCommand(text);
    return;
  }

  // DSH native (direct kernel HTTP stream). Note: streams resolve as soon as
  // the SSE reader starts; the reply renders via dshNative's 'message' events
  // (start/delta/done handled in the wiring block below).
  if (window.dshNative && window.dshNative.status.connected) {
    setMatrix("thinking");
    const tab = tabs.get(activeTabId);
    const page = tab ? { url: tab.url, title: tab.title } : null;

    // Needle parallel tool calling: when the local 14MB model recognizes a
    // concrete browser action (navigate/search/click/read/…), execute it
    // NOW via executeParallel and let the main model stream its reasoning
    // at the same time. Tool result lands sub-100ms; the model's answer
    // follows when ready. Pure Q&A skips the fast path entirely.
    var par = window.needleAgent && window.needleAgent.executeParallel
      ? window.needleAgent.executeParallel(text, {
          onFast: function (fast) {
            var conf = Math.round(fast.confidence * 100);
            Chat.append("system", "\u26A1 Needle: " + fast.tool + " (" + conf + "%)");
            if (fast.result && fast.result.success === false) {
              Chat.append("error", fast.result.result || (fast.tool + " failed"));
            } else if (fast.result && fast.result.done) {
              Chat.append("jarvis", fast.result.result);
            } else {
              Chat.append("jarvis", (fast.result && fast.result.result) || ("Executed: " + fast.tool));
            }
          },
          onMain: function () {
            Chat.append("system", "\u26A1 Needle fast-path armed \u2014 main model reasoning in parallel…");
          },
        })
      : { parallel: false };

    const streamResult = await window.dshNative.chat(text, { page });
    if (streamResult && streamResult.success === false) {
      Chat.append("error", streamResult.error || "Connection failed");
      setMatrix("fail");
      setTimeout(() => setMatrix("idle"), 2000);
    }
    // streamId case: events render the reply; nothing more to do here.
  } else if (window.orbit?.jarvis) {
    setMatrix("thinking");
    window.orbit.jarvis.chat(text, "orbit-tab-" + activeTabId);
  } else if (jarvisOnline) {
    // Parallel mode: Needle (fast) + Main Model (reasoning)
    setMatrix("thinking");
    try {
      var needleResult = window.needleAgent.route(text);
      var conf = Math.round(needleResult.confidence * 100);
      if (needleResult.confidence >= 0.8) {
        // High confidence: execute immediately (fast path)
        Chat.append("system", "\u26A1 Needle: " + needleResult.tool + " (" + conf + "%)");
        var execResult = await window.needleAgent.execute(needleResult);
        if (execResult.done) {
          Chat.append("jarvis", execResult.result);
          setMatrix("done");
          setTimeout(() => setMatrix("idle"), 2000);
        } else {
          Chat.append("jarvis", execResult.result);
          setMatrix("idle");
        }
      } else {
        // Low confidence: run both in parallel
        Chat.append("system", "\u26A1 Needle: " + needleResult.tool + " (" + conf + "%) | Main model: reasoning...");
        var execResult = await window.needleAgent.execute(needleResult);
        Chat.append("jarvis", execResult.result || 'Tool executed: ' + needleResult.tool);
        setMatrix("idle");
      }
    } catch (err) {
      Chat.append("error", "Agent error: " + err.message);
      setMatrix("fail");
      setTimeout(() => setMatrix("idle"), 2000);
    }
  } else {
    Chat.append("jarvis", "Click the JARVIS button to start the AI agent.\n\n\u2022 Navigate: type a URL or search\n\u2022 Tabs: Ctrl+T / Ctrl+W\n\u2022 Find: Ctrl+F\n\u2022 Commands: Ctrl+K\n\u2022 Zoom: Ctrl+/-\n\u2022 Bookmarks: Ctrl+D\n\u2022 Screenshot: Ctrl+Shift+S");
    setMatrix("idle");
  }
}

function handleDshCommand(text) {
  const parts = text.split(" ");
  const cmd = parts[0].toLowerCase();
  const args = parts.slice(1).join(" ");
  const send = (role, msg) => Chat.append(role, msg);

  switch (cmd) {
    case "/task":
      runAgentTask(args);
      break;
    case "/research":
      runAgentTask("Research: " + args);
      break;
    case "/summarize":
      runAgentTask("Summarize this page");
      break;
    case "/navigate":
      if (args) navigateTo(args);
      break;
    case "/read":
      readPage();
      break;
    case "/screenshot":
      takeScreenshot();
      break;
    case "/yt":
      if (window.YT) window.YT.command(args);
      break;
    case "/status":
      showDshStatus();
      break;
    case "/model":
      if (args) {
        const choice = args.trim();
        if (choice.toLowerCase() === "auto" || choice === "none") {
          window.dshNative.selectedModel = null;
          updateModelChipLabel();
          send("system", "Model reset to router default (fallback chain).");
        } else {
          window.dshNative.selectedModel = choice;
          updateModelChipLabel();
          send("system", "Model set to " + choice + ". New chats will use it.\nType /model to list available models.");
        }
      } else {
        showModelsCommand();
      }
      break;
    case "/help":
      send("jarvis", "Available commands:\n" +
        Chat.COMMANDS.map((c) => "  " + c.cmd + " \u2014 " + c.desc).join("\n"));
      break;
    default:
      send("error", "Unknown command: " + cmd + ". Type /help for available commands.");
  }
}

async function runAgentTask(task) {
  if (!window.dshNative || !window.dshNative.status.connected) {
    Chat.append("error", "JARVIS backend is not connected.");
    return;
  }
  setMatrix("running");
  Chat.append("system", "Starting agent task: " + task);
  const tab = tabs.get(activeTabId);
  const page = tab ? { url: tab.url, title: tab.title } : null;
  const result = await window.dshNative.runAgent(task, { page });
  if (result.streamId) {
  } else if (result.success === false) {
    Chat.append("error", result.error || "Agent task failed");
    setMatrix("fail");
    setTimeout(() => setMatrix("idle"), 2000);
  }
}

async function readPage() {
  if (!window.dshNative || !window.dshNative.status.connected) {
    Chat.append("error", "JARVIS backend is not connected.");
    return;
  }
  setMatrix("thinking");
  const result = await window.dshNative.read();
  if (result.success) {
    Chat.append("jarvis", result.text || "Page content retrieved");
    setMatrix("done");
    setTimeout(() => setMatrix("idle"), 2000);
  } else {
    Chat.append("error", result.error || "Failed to read page");
    setMatrix("fail");
    setTimeout(() => setMatrix("idle"), 2000);
  }
}

function showDshStatus() {
  if (!window.dshNative) {
    Chat.append("error", "JARVIS module not loaded.");
    return;
  }
  const s = window.dshNative.getStatus();
  Chat.append("system", [
    "JARVIS Status:",
    "  Connected: " + (s.connected ? "Yes" : "No"),
    "  Kernel: " + s.kernel,
    "  Last check: " + (s.lastCheck ? new Date(s.lastCheck).toLocaleTimeString() : "Never"),
    "  Sessions: " + s.activeSessions,
    "  Streams: " + s.activeStreams,
    "  Queued: " + s.queuedMessages,
  ].join("\n"));
}

// ── Chat module: all persistence/rendering in src/js/chat.js ──
// Chat.append(), Chat.beginStream(), Chat.updateStream(),
// Chat.endStream(), Chat.renderPanel(), Chat.COMMANDS

// Expose jarvisOnline for Chat module
window._jarvisOnline = false;
function syncJarvisOnline(val) {
  jarvisOnline = val;
  window._jarvisOnline = val;
}

// ── DSH Native Events ──────────────────────────────────────────
// dsh-native.js is lazy-loaded AFTER this file (index.html critical-module
// loader), so window.dshNative does not exist at parse time. Wire as soon
// as it appears: bounded poll, handlers attach exactly once.
function wireDshNative() {
  const dsh = window.dshNative;
  if (!dsh || dsh.__orbitWired) return !!dsh;
  dsh.__orbitWired = true;
  window.__orbitDshWired = true;
  // Status updates
  dsh.on('status', (status) => {
    syncJarvisOnline(status.connected && status.kernel === 'online');
    if (statusDot) statusDot.className = 'status-dot ' + (jarvisOnline ? 'online' : 'offline');
    if (statusLabel) statusLabel.textContent = jarvisOnline ? 'ONLINE' : 'OFF';
    if (sbDot) sbDot.className = 'sb-dot ' + (jarvisOnline ? 'online' : 'offline');
    setMatrix(jarvisOnline ? 'idle' : 'offline');
    updatePerfHud();
    
    // Update JARVIS panel status if visible
    if (sbNav && sbNav.querySelector('[data-panel="jarvis"]')?.classList.contains('on')) {
      // Refresh the JARVIS panel header with new status
      const jarvisPanel = sbBody.querySelector('.jarvis-status-header');
      if (jarvisPanel) {
        jarvisPanel.textContent = jarvisOnline ? 'READY' : 'OFF';
      }
    }
  });
  
  // Chat messages — all persistence handled by Chat.endStream()
  dsh.on('message', (event) => {
    switch (event.type) {
      case 'start':
        setMatrix('thinking');
        Chat.beginStream();
        break;
      case 'delta':
        updateStreamingMessage(event.text, event.fullText);
        break;
      case 'meta':
        // Which provider/model actually served this reply (post-fallback).
        if (event.model) Chat.append('system', '\u26A1 served by ' + event.model);
        break;
      case 'done':
        finalizeStreamingMessage(event.text || '(no response)');
        setMatrix('done');
        setTimeout(() => setMatrix('idle'), 2000);
        break;
    }
  });
  
  // Agent events
  dsh.on('agent', (event) => {
    switch (event.type) {
      case 'start':
        setMatrix('running');
        Chat.append('system', 'Agent started: ' + (event.task || 'Unknown task'));
        break;
      case 'step':
        if (event.step) Chat.append('system', 'Step: ' + JSON.stringify(event.step));
        break;
      case 'done':
        if (event.text) Chat.append('jarvis', event.text);
        setMatrix('done');
        setTimeout(() => setMatrix('idle'), 2000);
        break;
    }
  });
  
  // Errors
  dsh.on('error', (event) => {
    Chat.append('error', event.message || 'JARVIS error');
    setMatrix('fail');
    setTimeout(() => setMatrix('idle'), 2000);
  });
  // Model picker: show the chip once connected, refresh when it changes
  dsh.on('status', () => {
    const chip = document.getElementById('sbModelChip');
    if (chip) chip.style.display = jarvisOnline ? 'flex' : 'none';
    if (jarvisOnline) updateModelChipLabel();
  });
  dsh.on('model', () => updateModelChipLabel());
  updateModelChipLabel();
  return true;
}

// ── Model Picker ────────────────────────────────────────────────
function updateModelChipLabel() {
  const name = document.getElementById('sbModelName');
  if (!name) return;
  const sel = (window.dshNative && window.dshNative.selectedModel) || null;
  name.textContent = sel ? (sel.split('/').pop() || sel).slice(0, 18) : 'AUTO';
}

async function toggleModelPopup() {
  let popup = document.getElementById('modelPopup');
  if (popup && popup.classList.contains('open')) {
    popup.classList.remove('open');
    return;
  }
  if (!popup) {
    popup = document.createElement('div');
    popup.id = 'modelPopup';
    popup.className = 'model-popup';
    document.body.appendChild(popup);
  }
  const chip = document.getElementById('sbModelChip');
  if (chip) {
    const r = chip.getBoundingClientRect();
    popup.style.top = Math.round(r.bottom + 6) + 'px';
    popup.style.right = Math.round(window.innerWidth - r.right) + 'px';
    popup.style.left = 'auto';
  }
  popup.innerHTML = '<div class="model-popup-header"><span class="model-popup-title">Model</span>' +
    '<span class="model-popup-hint">' + (window.dshNative?.selectedModel ? 'custom' : 'router default') + '</span></div>' +
    '<div class="model-popup-list"><div class="model-popup-hint" style="padding:12px">Loading models…</div></div>';
  popup.classList.add('open');
  const models = (window.dshNative ? await window.dshNative.listModels() : []) || [];
  if (!popup.classList.contains('open')) return; // closed while loading
  const sel = window.dshNative?.selectedModel || null;
  const list = models.length ? models.map(function (m) {
    const id = m.id || (m.provider + '/' + m.model);
    const active = sel ? sel === id : false;
    return '<button class="model-item' + (active ? ' active' : '') + (m.available ? '' : ' unavailable') + '" data-mid="' + escapeHtml(id) + '">' +
      '<span class="mi-main"><span class="mi-model">' + escapeHtml(m.model || id) + '</span>' +
      '<span class="mi-provider">' + escapeHtml(m.provider || '') + '</span></span>' +
      (m.kind ? '<span class="mi-kind ' + escapeHtml(m.kind) + '">' + escapeHtml(m.kind) + '</span>' : '') +
      (active ? '<span class="mi-check">\u2713</span>' : '') +
      '</button>';
  }).join('') : '<div class="model-popup-hint" style="padding:12px">No models reported. The kernel may be offline.</div>';
  const auto = '<button class="model-item' + (sel ? '' : ' active') + '" data-mid="">' +
    '<span class="mi-main"><span class="mi-model">Auto (router default)</span>' +
    '<span class="mi-provider">fallback chain</span></span>' +
    (sel ? '' : '<span class="mi-check">\u2713</span>') + '</button>';
  popup.innerHTML = '<div class="model-popup-header"><span class="model-popup-title">Model</span>' +
    '<span class="model-popup-hint">' + (sel ? 'custom' : 'router default') + '</span></div>' +
    auto + '<div class="model-popup-list">' + list + '</div>';
  popup.querySelectorAll('.model-item').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const id = btn.getAttribute('data-mid') || '';
      if (window.dshNative) window.dshNative.selectedModel = id || null;
      updateModelChipLabel();
      popup.classList.remove('open');
      Chat.append('system', id ? 'Model set to ' + id + '. New chats will use it.' : 'Model reset to router default.');
    });
  });
}

// Chip + outside-click dismissal (chip may be re-created by page reloads;
// delegated listener survives that)
document.addEventListener('click', function (e) {
  const chip = e.target.closest ? e.target.closest('#sbModelChip') : null;
  if (chip) { e.stopPropagation(); toggleModelPopup(); return; }
  const inside = e.target.closest ? e.target.closest('#modelPopup') : null;
  const popup = document.getElementById('modelPopup');
  if (popup && popup.classList.contains('open') && !inside) popup.classList.remove('open');
});

async function showModelsCommand() {
  const models = (window.dshNative ? await window.dshNative.listModels() : []) || [];
  if (!models.length) {
    Chat.append('system', 'No models reported. Is the JARVIS kernel online?');
    return;
  }
  const sel = window.dshNative?.selectedModel || null;
  const lines = models.map(function (m) {
    const id = m.id || (m.provider + '/' + m.model);
    const mark = sel === id ? ' \u25c0 current' : (m.available ? '' : ' (offline)');
    return '  ' + id + mark;
  });
  Chat.append('system', 'Available models (pick with /model <id>, or the chip in the header):\n' + lines.join('\n'));
}
(function waitForDshNative(attempts) {
  if (wireDshNative()) return;
  if (attempts > 100) { console.warn('[ORBIT] dsh-native.js never appeared; JARVIS UI disabled'); return; }
  setTimeout(function () { waitForDshNative(attempts + 1); }, 100);
})(0);

// ── Streaming — delegates to Chat module ────────────────────────
function updateStreamingMessage(delta, fullText) {
  Chat.updateStream(fullText);
}

function finalizeStreamingMessage(fullText) {
  Chat.endStream(fullText);
}

// ── Legacy JARVIS Events (Fallback) ──────────────────────────────
// ── Headless Agent Loop tool round-trips ───────────────────────
// main.js registers browser.read/click/type tools that ping the renderer
// and await a result IPC; without these handlers every call hit its timeout.
if (window.orbit?.on?.navigateTo) {
  window.orbit.on.navigateTo((url) => {
    if (url && /^https?:/i.test(url)) createTab(url);
  });
}
if (window.orbit?.agent) {
  window.orbit.agent.onState(function(state) {
    if (state === 'thinking' || state === 'executing') setMatrix('thinking');
    else if (state === 'completed') { setMatrix('done'); setTimeout(function() { setMatrix('idle'); }, 2000); }
    else if (state === 'failed') { setMatrix('fail'); setTimeout(function() { setMatrix('idle'); }, 2000); }
  });
  window.orbit.agent.onTool(function(info) {
    Chat.append('system', '\u2699 ' + (info && info.name ? info.name : 'tool'));
  });
}
if (window.orbit?.agent?.sendReadResult) {
  window.orbit.on && window.orbit.on.agentRead && window.orbit.on.agentRead(async function() {
    try {
      const wv = activeWebview();
      if (!wv) { window.orbit.agent.sendReadResult('No active page'); return; }
      const text = await wv.executeJavaScript('document.body ? document.body.innerText.substring(0, 8000) : ""', false);
      window.orbit.agent.sendReadResult(text || '(empty page)');
    } catch (e) {
      window.orbit.agent.sendReadResult('Read error: ' + e.message);
    }
  });
  window.orbit.on && window.orbit.on.agentClick && window.orbit.on.agentClick(async function(args) {
    try {
      const wv = activeWebview();
      if (!wv) { window.orbit.agent.sendClickResult('No active page'); return; }
      const sel = (args && args.selector) || 'body';
      const r = await wv.executeJavaScript(
        '(function(){var el=document.querySelector(' + JSON.stringify(sel) + ');' +
        'if(!el)return "Not found";el.scrollIntoView({block:"center"});el.click();return "Clicked";})()', false);
      window.orbit.agent.sendClickResult(r || 'Click failed');
    } catch (e) {
      window.orbit.agent.sendClickResult('Click error: ' + e.message);
    }
  });
  window.orbit.on && window.orbit.on.agentType && window.orbit.on.agentType(async function(args) {
    try {
      const wv = activeWebview();
      if (!wv) { window.orbit.agent.sendTypeResult('No active page'); return; }
      const sel = (args && args.selector) || 'input';
      const text = (args && args.text) || '';
      const r = await wv.executeJavaScript(
        '(function(){var el=document.querySelector(' + JSON.stringify(sel) + ');' +
        'if(!el)return "Input not found";el.focus();el.value=' + JSON.stringify(text) + ';' +
        'el.dispatchEvent(new Event("input",{bubbles:true}));return "Typed";})()', false);
      window.orbit.agent.sendTypeResult(r || 'Type failed');
    } catch (e) {
      window.orbit.agent.sendTypeResult('Type error: ' + e.message);
    }
  });
}
if (window.orbit?.on?.navigateTo) {
  window.orbit.on.navigateTo((url) => {
    if (url && /^https?:/i.test(url)) createTab(url);
  });
}
if (window.orbit?.on?.tabCreated) {
  window.orbit.on.tabCreated((tab) => {
    const id = tab && tab.id;
    if (!id || tabs.has(id) || !tab.url) return;
    if (bootTabId && !bootReplaced && tabs.has(bootTabId)) {
      bootReplaced = true;
      navigateTo(tab.url);
      return;
    }
    createTab(tab.url);
  });
}
if (window.orbit?.on?.tabSleep) {
  window.orbit.on.tabSleep((id) => {
    const tab = tabs.get(id);
    if (tab && !tab.hibernated) {
      tab.sleeping = true;
      if (id !== activeTabId) renderTabs();
    }
  });
  window.orbit.on.tabWake((id) => {
    const tab = tabs.get(id);
    if (tab) {
      tab.sleeping = false;
      clearSleepTimer(id);
      if (id === activeTabId) renderTabs();
    }
  });
}
if (window.orbit?.jarvis && !window.dshNative?.status.connected) {
  window.orbit.jarvis.onStatus((status) => {
    syncJarvisOnline(status.ok && status.kernel === "online");
    if (statusDot) statusDot.className = "status-dot " + (jarvisOnline ? "online" : "offline");
    if (statusLabel) statusLabel.textContent = jarvisOnline ? "ONLINE" : "OFF";
    if (sbDot) sbDot.className = "sb-dot " + (jarvisOnline ? "online" : "offline");
    setMatrix(jarvisOnline ? "idle" : "offline");
    updatePerfHud();
  });
  window.orbit.jarvis.onChat((payload) => {
    if (payload.kind === "delta") { /* Stream response */ }
    else if (payload.kind === "done") {
      Chat.append("jarvis", payload.text || "(no response)");
      setMatrix("done");
      setTimeout(() => setMatrix("idle"), 2000);
    } else if (payload.kind === "error") {
      Chat.append("error", payload.error?.message || "JARVIS error");
      setMatrix("fail");
      setTimeout(() => setMatrix("idle"), 2000);
    }
  });
  window.orbit.jarvis.onAgentEvent((event) => { if (event.state) setMatrix(event.state); });
  window.orbit.jarvis.onApproval((request) => { showApprovalModal(request); });

  // Seed the status badge from the main-process state: the connection may have
  // opened before the renderer subscribed, and main only pushes on change, so
  // without this pull the badge would stay OFF until the next reconnect.
  window.orbit.jarvis.status().then(function(s) {
    if (s) syncJarvisOnline(!!(s.ok && s.kernel === "online"));
    if (s && s.ok) {
      if (statusDot) statusDot.className = "status-dot " + (jarvisOnline ? "online" : "offline");
      if (statusLabel) statusLabel.textContent = jarvisOnline ? "ONLINE" : "OFF";
      if (sbDot) sbDot.className = "sb-dot " + (jarvisOnline ? "online" : "offline");
    }
  }).catch(function() {});
}

// ── Approval Modal ────────────────────────────────────────────
function showApprovalModal(request) {
  setMatrix("ask");
  modalBg.classList.add("on");
  const title = $("#modalTitle");
  const desc = $("#modalDesc");
  const kv = $("#modalKv");
  if (title) title.textContent = request.title || "JARVIS wants to take an action";
  if (desc) desc.textContent = request.description || "This action requires your approval.";
  if (kv) {
    kv.innerHTML = "";
    if (request.details) {
      for (const [key, value] of Object.entries(request.details)) {
        kv.innerHTML += "<dt>" + escapeHtml(key) + "</dt><dd>" + escapeHtml(value) + "</dd>";
      }
    }
  }
}

if (modalDeny) modalDeny.addEventListener("click", () => { modalBg.classList.remove("on"); setMatrix("done"); setTimeout(() => setMatrix("idle"), 2000); });
if (modalAllowOnce) modalAllowOnce.addEventListener("click", () => { modalBg.classList.remove("on"); setMatrix("running"); });
if (modalAllowSite) modalAllowSite.addEventListener("click", () => { modalBg.classList.remove("on"); setMatrix("running"); });
if (modalBg) modalBg.addEventListener("click", (e) => { if (e.target === modalBg) modalBg.classList.remove("on"); });

// ── Bookmark System ───────────────────────────────────────────
function renderBookmarkBar() {
  if (!bookmarkBar) return;
  const addBtn = bookmarkBar.querySelector(".bm-add");
  const sep = bookmarkBar.querySelector(".bm-sep");
  bookmarkBar.innerHTML = "";
  if (addBtn) bookmarkBar.appendChild(addBtn);
  if (sep) bookmarkBar.appendChild(sep);
  bookmarks.forEach(function(bm, i) {
    const el = document.createElement("button");
    el.className = "bm-item";
    el.innerHTML = '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4.5" stroke="currentColor"/></svg>' + escapeHtml(bm.title);
    el.title = bm.url;
    el.addEventListener("click", function() { navigateTo(bm.url); });
    el.addEventListener("contextmenu", function(e) {
      e.preventDefault();
      if (confirm("Remove: " + bm.title + "?")) {
        bookmarks.splice(i, 1);
        localStorage.setItem("orbit-bookmarks", JSON.stringify(bookmarks));
        renderBookmarkBar();
      }
    });
    bookmarkBar.appendChild(el);
  });
}

function addBookmark() {
  const tab = tabs.get(activeTabId);
  if (!tab) return;
  const title = prompt("Bookmark name:", tab.title);
  if (!title) return;
  bookmarks.push({ title: title, url: tab.url });
  localStorage.setItem("orbit-bookmarks", JSON.stringify(bookmarks));
  renderBookmarkBar();
  updateStarIcon(tab.url);
  showToast("ok", "Bookmark Added", title);
}

function updateStarIcon(url) {
  if (!omniStar) return;
  const isBookmarked = bookmarks.some(b => b.url === url);
  omniStar.classList.toggle("bookmarked", isBookmarked);
}

if (omniStar) omniStar.addEventListener("click", function() { return addBookmark.apply(this, arguments); });
if ($("#bmAddBtn")) $("#bmAddBtn").addEventListener("click", function() { return addBookmark.apply(this, arguments); });

// ── Session Management ────────────────────────────────────────
function saveSession() {
  const s = [];
  tabs.forEach(function(tab, id) {
    s.push({ id: id, url: tab.url, title: tab.title, agentOwned: tab.agentOwned });
  });
  localStorage.setItem("orbit-session", JSON.stringify({ tabs: s, activeTabId: activeTabId, savedAt: Date.now() }));
}

// ── Session Thumbnails (New Tab Page) ────────────────────────
function renderSessionThumbnails() {
  const recentList = document.getElementById('ntRecentList');
  const sessionList = document.getElementById('ntSessionList');
  const recentSection = document.getElementById('ntRecent');
  const sessionSection = document.getElementById('ntSessions');

  // Recently closed tabs
  if (recentList && closedTabs.length > 0) {
    recentSection.style.display = 'block';
    recentList.innerHTML = '';
    closedTabs.slice(-8).reverse().forEach(function(tab) {
      const thumb = document.createElement('div');
      thumb.className = 'nt-thumb';
      thumb.innerHTML = '<div class="nt-thumb-icon">\u{1F5D9}</div>' +
        '<div class="nt-thumb-title">' + escapeHtml(tab.title || 'Untitled') + '</div>' +
        '<div class="nt-thumb-url">' + escapeHtml(truncateUrl(tab.url)) + '</div>';
      thumb.addEventListener('click', function() {
        createTab(tab.url);
      });
      recentList.appendChild(thumb);
    });
  } else if (recentSection) {
    recentSection.style.display = 'none';
  }

  // Previous session
  if (sessionList) {
    try {
      const data = JSON.parse(localStorage.getItem('orbit-session'));
      if (data && data.tabs && data.tabs.length > 0) {
        sessionSection.style.display = 'block';
        sessionList.innerHTML = '';
        data.tabs.slice(0, 8).forEach(function(tab) {
          if (!tab.url || tab.url.startsWith('orbit://')) return;
          const thumb = document.createElement('div');
          thumb.className = 'nt-thumb';
          const domain = tryGetDomain(tab.url);
          thumb.innerHTML = '<div class="nt-thumb-icon">' + (domain ? domain.charAt(0).toUpperCase() : '\u{1F310}') + '</div>' +
            '<div class="nt-thumb-title">' + escapeHtml(tab.title || 'Untitled') + '</div>' +
            '<div class="nt-thumb-url">' + escapeHtml(truncateUrl(tab.url)) + '</div>';
          thumb.addEventListener('click', function() {
            createTab(tab.url);
          });
          sessionList.appendChild(thumb);
        });
      } else if (sessionSection) {
        sessionSection.style.display = 'none';
      }
    } catch (e) {
      if (sessionSection) sessionSection.style.display = 'none';
    }
  }
}

function truncateUrl(url) {
  try {
    var u = new URL(url);
    return u.hostname + u.pathname.substring(0, 30);
  } catch (e) {
    return url.substring(0, 40);
  }
}

function tryGetDomain(url) {
  try {
    return new URL(url).hostname;
  } catch (e) {
    return '';
  }
}

function restoreSession() {
  try {
    const data = JSON.parse(localStorage.getItem("orbit-session"));
    if (!data || !data.tabs || !data.tabs.length) return false;
    // createTab generates new IDs, so track which index was active
    let activeIdx = 0;
    if (data.activeTabId) {
      activeIdx = data.tabs.findIndex((t) => t.id === data.activeTabId);
      if (activeIdx < 0) activeIdx = 0;
    }
    let restoredId = null;
    const ids = Array.from(tabs.keys());
    data.tabs.forEach((t) => { restoredId = createTab(t.url); });
    // Activate the tab that corresponds to the previously active one
    const allIds = Array.from(tabs.keys());
    if (allIds.length > ids.length) {
      const newIds = allIds.slice(ids.length);
      activateTab(newIds[Math.min(activeIdx, newIds.length - 1)]);
    }
    showToast("ok", "Session Restored", data.tabs.length + " tabs recovered");
    return true;
  } catch (e) { return false; }
}
