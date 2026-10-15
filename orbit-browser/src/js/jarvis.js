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

// A-13: single consent-aware page-context collector. Every chat surface
// uses this one path: bounded innerText, source URL, freshness timestamp,
// and scheme-based exclusions (no page text is ever taken from internal
// or file origins — only http(s) guest pages).
async function collectPageContext(maxChars) {
  const tab = tabs.get(activeTabId);
  if (!tab) return null;
  const url = tab.url || "";
  const base = { url: url, title: tab.title || "" };
  if (!/^https?:/i.test(url)) return base; // internal/sensitive origins: metadata only
  const wv = activeWebview();
  if (!wv) return base;
  try {
    const text = await wv.executeJavaScript(
      '(document.body ? document.body.innerText.substring(0,' + (maxChars || 2000) + ') : "")', false);
    if (!text) return base;
    return { url: url, title: tab.title || "", text: String(text), capturedAt: Date.now() };
  } catch (_) {
    return base;
  }
}

// ── Plan / Build mode toggle (Freebuff-style) ─────────────────
// Plan: JARVIS proposes and explains before acting (tools are announced,
// not executed). Build: JARVIS acts — tool calls run immediately.
// Default is Build (a browser agent that can act); Plan is one click away.
window.orbitMode = localStorage.getItem("orbit-mode") || "build";
const sbModeToggle = document.getElementById("sbModeToggle");
function applyOrbitMode() {
  if (sbModeToggle) sbModeToggle.dataset.mode = window.orbitMode;
  sbModeToggle && sbModeToggle.setAttribute("aria-pressed", String(window.orbitMode === "plan"));
}
applyOrbitMode();
if (sbModeToggle) sbModeToggle.addEventListener("click", function (e) {
  e.stopPropagation();
  window.orbitMode = window.orbitMode === "plan" ? "build" : "plan";
  try { localStorage.setItem("orbit-mode", window.orbitMode); } catch (_) {}
  window.__pendingPlan = null; // a mode switch voids any open proposal
  applyOrbitMode();
  Chat.append("system", window.orbitMode === "plan"
    ? "Plan mode — JARVIS proposes before acting."
    : "Build mode — JARVIS can act directly.");
});

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
        var page = await collectPageContext();

    // Plan mode: JARVIS proposes, never acts. Skip the Needle fast-path
    // (which executes tools immediately) and ask the model for a plan.
    // The scaffold applies ONLY to actionable requests (imperatives:
    // "build X", "open Y", "clean Z"). Greetings are not requests, and
    // questions ("what is my name?") are answered, not planned — wrapping
    // either in the scaffold produced absurdities like "a plan for
    // responding to your hello" and "a plan to answer what your name is".
    const planMode = window.orbitMode === "plan";
    const trimmedText = text.trim();

    // ── Plan-confirmation lifecycle ──────────────────────────────────
    // Plan contract: propose → user confirms → EXECUTE. The confirm step
    // used to be impossible: nothing remembered the proposal, so "proceed"
    // was sent as ordinary text — got wrapped in the plan scaffold AGAIN
    // (it's short, not casual, not a question) — and the model proposed
    // the same plan a second time instead of acting.
    if (window.__pendingPlan) {
      const CONFIRM_RE = /^(proceed|go ahead|go ahead and (do|execute|run) it|do it( now)?|execute( it)?|run it|continue( with the plan)?|(yes|yep|yeah|sure|ok(ay)?)( please| pls)?|confirm(ed)?|approved?|sounds good|looks good|go)\b[!., ]*$/i;
      if (CONFIRM_RE.test(trimmedText)) {
        const task = window.__pendingPlan.task;
        window.__pendingPlan = null;
        Chat.append("system", "Plan approved — executing: " + task);
        setMatrix("running");
        runAgentTask(task); // real tool-execution path (/v1/agent stream)
        return;
      }
      // Any other message replaces the pending proposal (new intent wins).
      window.__pendingPlan = null;
    }

    const isCasual = /^(hi|hey|hello|yo|sup|thanks|thank you|thx|good (morning|afternoon|evening|night)|ok|okay|cool|nice|lol|bye|gn)\b[!., ]*$/i.test(trimmedText) || trimmedText.length <= 3;
    const isQuestion = trimmedText.endsWith("?") || /^(what|whats|what's|who|whos|who's|when|whens|where|why|how|which|is|are|was|were|do|does|did|can|could|should|would|will|am|may)\b/i.test(trimmedText);
    const isConfirmation = /^(proceed|go ahead|do it( now)?|execute( it)?|run it|continue( with the plan)?|yes( please| pls)?|yep|yeah|sure|ok(ay)?( please| pls)?|confirm(ed)?|approved?|sounds good|looks good|go)\b[!., ]*$/i.test(trimmedText);
    // A bare confirmation with no pending proposal is still never a task —
    // scaffolding it produced "a plan for proceeding".
    const neverScaffold = isCasual || isQuestion || (isConfirmation && !window.__pendingPlan);
    const wantsPlan = planMode && !neverScaffold;
    if (wantsPlan) {
      // Remember the task this proposal belongs to, so the next message
      // can confirm it into real execution (see __pendingPlan above).
      window.__pendingPlan = { task: text, at: Date.now() };
    }
    const prompt = wantsPlan
      ? "[PLAN MODE] Do not execute any tools. Propose a short step-by-step plan for this request and wait for my confirmation: " + text
      : text;

    // Needle parallel tool calling: when the local 14MB model recognizes a
    // concrete browser action (navigate/search/click/read/…), execute it
    // NOW via executeParallel and let the main model stream its reasoning
    // at the same time. Tool result lands sub-100ms; the model's answer
    // follows when ready. Pure Q&A skips the fast path entirely.
    var par = (!planMode && window.needleAgent && window.needleAgent.executeParallel)
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

    const streamResult = await window.dshNative.chat(prompt, {
      page,
      // Per-tab conversation threads: this tab's session + this tab's
      // history, so tabs don't bleed context into each other.
      sessionId: window.dshNative.sessionForTab
        ? window.dshNative.sessionForTab(activeTabId)
        : undefined,
      messages: (window.Chat && window.Chat.historyFor)
        ? window.Chat.historyFor(activeTabId, 12)
        : [],
    });
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
      runYTCommand(args);
      break;
    case "/new":
      // Fresh conversation: clear this tab's thread + rotate ITS session
      // (other tabs keep their threads).
      if (window.Chat && Chat.clearActive) Chat.clearActive();
      if (window.dshNative && typeof window.dshNative.forgetTabSession === "function") {
        window.dshNative.forgetTabSession(activeTabId);
      } else if (window.dshNative && typeof window.dshNative.rotateSession === "function") {
        window.dshNative.rotateSession();
      }
      send("system", "New conversation started. This tab's context is clear.");
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
  const page = await collectPageContext();
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

// /yt users the Piped front-end — deferred from boot; load on first use.
let _ytScriptLoading = false;
function runYTCommand(args) {
  if (window.YT) { window.YT.command(args); return; }
  if (_ytScriptLoading) return; // a queued load is already in flight
  _ytScriptLoading = true;
  Chat.append("system", "Loading private YouTube module...");
  const s = document.createElement("script");
  s.async = true;
  s.src = "js/yt.js";
  s.onload = function () {
    _ytScriptLoading = false;
    if (window.YT) window.YT.command(args);
    else Chat.append("error", "Private YouTube module failed to initialize.");
  };
  s.onerror = function () {
    _ytScriptLoading = false;
    Chat.append("error", "Failed to load the private YouTube module.");
  };
  document.head.appendChild(s);
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
    if (sbDot) sbDot.className = 'rail-status-dot ' + (jarvisOnline ? 'online' : 'offline');
    setMatrix(jarvisOnline ? 'idle' : 'offline');
    updatePerfHud();
    
    // Update JARVIS panel status if visible
    if (sbRail && sbRail.querySelector('[data-panel="jarvis"]')?.classList.contains('on')) {
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
        // Displayed in the persistent header chip — not as a chat message
        // after every reply.
        if (event.model) {
          const chip = document.getElementById('sbModelName');
          if (chip) {
            chip.textContent = event.model.split('/').pop().slice(0, 18);
            chip.title = 'Served by ' + event.model;
          }
        }
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

// ── Model selector (UI.Popup primitive — Escape/focus/ARIA handled) ──
let modelPopupHandle = null;

function _applyModelSelection(id) {
  if (window.dshNative) window.dshNative.selectedModel = id || null;
  updateModelChipLabel();
  Chat.append('system', id ? 'Model set to ' + id + '. New chats will use it.' : 'Model reset to router default.');
}

function _modelItemBtn(label, sub, id, sel, disabled) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'ui-menu-item';
  b.setAttribute('role', 'menuitemradio');
  b.setAttribute('aria-checked', String(sel === id));
  if (disabled) b.disabled = true;
  const lab = document.createElement('span');
  lab.className = 'ui-menu-item-label';
  lab.textContent = label;
  if (sub) {
    const s = document.createElement('span');
    s.className = 'ui-menu-item-sub';
    s.textContent = sub;
    lab.appendChild(s);
  }
  b.appendChild(lab);
  if (sel === id) {
    const chk = document.createElement('span');
    chk.className = 'ui-menu-item-check';
    chk.textContent = '\u2713';
    b.appendChild(chk);
  }
  b.addEventListener('click', function () {
    if (modelPopupHandle) modelPopupHandle.close();
    _applyModelSelection(id);
  });
  return b;
}

async function toggleModelPopup() {
  if (modelPopupHandle) { modelPopupHandle.close(); return; }
  const chip = document.getElementById('sbModelChip');
  const sel = window.dshNative?.selectedModel || null;
  const listWrap = document.createElement('div');
  listWrap.className = 'ui-menu';
  listWrap.appendChild(_modelItemBtn('Auto (router default)', 'fallback chain', '', sel, false));
  const loading = document.createElement('div');
  loading.className = 'ui-popup-hint';
  loading.style.padding = '10px 8px';
  loading.textContent = 'Loading models\u2026';
  listWrap.appendChild(loading);
  modelPopupHandle = UI.Popup.open({
    anchor: chip || null,
    title: 'Model',
    hint: sel ? 'custom' : 'router default',
    width: 264,
    items: [{ type: 'custom', el: listWrap }],
    onClose: function () { modelPopupHandle = null; },
  });
  let models = [];
  try {
    models = (window.dshNative ? await window.dshNative.listModels() : []) || [];
  } catch (_) { models = []; }
  if (!modelPopupHandle) return; // closed while loading
  loading.remove();
  if (!models.length) {
    loading.textContent = 'No models reported. The kernel may be offline.';
    loading.style.padding = '10px 8px';
    listWrap.appendChild(loading);
    return;
  }
  const current = window.dshNative?.selectedModel || null;
  models.forEach(function (m) {
    const id = m.id || (m.provider + '/' + m.model);
    listWrap.appendChild(_modelItemBtn(m.model || id, m.provider || '', id, current, !m.available));
  });
}

// Chip toggles the popup (chip may be re-created by page reloads;
// delegated listener survives that). Outside-click + Escape are owned
// by UI.Popup itself.
document.addEventListener('click', function (e) {
  const chip = e.target.closest ? e.target.closest('#sbModelChip') : null;
  if (chip) { e.stopPropagation(); toggleModelPopup(); }
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
// The legacy Electron-side agent loop is quarantined (see main.js A-04):
// main registers no agent-state / agent-tool / agent-*-result senders and
// answers agent:start with "disabled". The renderer listeners that used to
// consume them were therefore permanently dead — they registered handlers
// for events nothing emits, and advertised a second execution authority that
// does not exist. Browser capability now runs through the JARVIS kernel via
// dshNative/dshNative.runAgent, so there is nothing left to wire here.
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
    if (sbDot) sbDot.className = "rail-status-dot " + (jarvisOnline ? "online" : "offline");
    setMatrix(jarvisOnline ? "idle" : "offline");
    updatePerfHud();
  });  var _streamBuf = ""; // accumulated deltas for the in-flight reply
  window.orbit.jarvis.onChat((payload) => {
    if (payload.kind === "delta") {
      // Live token streaming: paint text as it arrives instead of a silent
      // spinner until done. First delta opens the streaming bubble.
      _streamBuf += payload.text;
      if (!Chat.isStreaming()) Chat.beginStream();
      Chat.updateStream(_streamBuf);
      setMatrix("running");
    }
    else if (payload.kind === "ack") {
      // Instant pickup signal while the model thinks — the next real delta
      // replaces it in the same bubble (updateStream swaps the full text).
      if (!Chat.isStreaming()) Chat.beginStream();
      Chat.updateStream(payload.text || "On it — working on that now…");
      setMatrix("running");
    }
    else if (payload.kind === "done") {
      Chat.endStream(payload.text || _streamBuf || "(no response)");
      _streamBuf = "";
      setMatrix("done");
      setTimeout(() => setMatrix("idle"), 2000);
    }
    else if (payload.kind === "error") {
      Chat.endStream("");
      _streamBuf = "";
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
      if (sbDot) sbDot.className = "rail-status-dot " + (jarvisOnline ? "online" : "offline");
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
  // Auto-hide: an empty bookmark bar is just a wasted 32px strip.
  bookmarkBar.classList.toggle("hidden", bookmarks.length === 0);
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
// ── New Tab telemetry strip (F1-style live readouts) ─────────
var _bootTime = Date.now();
var _telMemo = { mem: "--", sleep: 0, memAt: 0 };
function updateNtpTelemetry() {
  var up = document.getElementById('telUptime');
  if (up) {
    var s = Math.floor((Date.now() - _bootTime) / 1000);
    up.textContent = Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
  }
  var tabsEl = document.getElementById('telTabs');
  if (tabsEl) tabsEl.textContent = String(tabs.size);
  var fpsEl = document.getElementById('telFps');
  if (fpsEl) fpsEl.textContent = String(perfData.fps);
  var jEl = document.getElementById('telJarvis');
  if (jEl) {
    jEl.textContent = jarvisOnline ? "ON" : "OFF";
    jEl.classList.toggle("tel-live", jarvisOnline);
  }
  var st = document.getElementById('ntOsState');
  if (st) {
    st.textContent = jarvisOnline ? "ONLINE" : "OFFLINE";
  }
  var dot = document.getElementById('ntOsDot');
  if (dot) dot.classList.toggle("on", jarvisOnline);
  // Memory + sleeping tabs come from the main process (10s memo)
  if (Date.now() - _telMemo.memAt > 10000) {
    _telMemo.memAt = Date.now();
    try {
      window.orbit?.system?.performance?.status?.().then(function (st) {
        if (!st) return;
        _telMemo.mem = st.totalMemoryMB > 0 ? st.totalMemoryMB + " MB" : "--";
        _telMemo.sleep = st.sleepingTabs || 0;
        var m = document.getElementById('telMem');
        if (m) m.textContent = _telMemo.mem;
        var sl = document.getElementById('telSleep');
        if (sl) sl.textContent = String(_telMemo.sleep);
      }).catch(function () {});
    } catch (_) {}
  }
}
let _ntpPageEl = null;
setInterval(function () {
  // Cache the element; gate on visibility BEFORE any per-second work.
  // Hidden NTP (webview active) = zero DOM writes, zero layout.
  if (!_ntpPageEl) _ntpPageEl = document.getElementById('newtabPage');
  if (_ntpPageEl && _ntpPageEl.classList.contains("on") && _ntpPageEl.offsetParent !== null) updateNtpTelemetry();
}, 1000);

function renderSessionThumbnails() {
  const recentList = document.getElementById('ntRecentList');
  const sessionList = document.getElementById('ntSessionList');
  const recentSection = document.getElementById('ntRecent');
  const sessionSection = document.getElementById('ntSessions');
  updateNtpTelemetry();

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
