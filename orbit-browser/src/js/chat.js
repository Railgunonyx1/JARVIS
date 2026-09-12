/**
 * JARVIS Orbit — Chat Module (per-tab conversations)
 *
 * Each browser tab has its own conversation.  Switching tabs swaps the
 * chat panel; new tabs start with a fresh (empty) conversation.
 *
 * Public API (window.Chat):
 *   Chat.init(bodyEl, navEl)           – wire DOM references
 *   Chat.setTab(tabId)                 – switch active conversation
 *   Chat.forgetTab(tabId)              – discard a tab's history
 *   Chat.pendingStreamTabId            – set before async send
 *   Chat.append(role, content)         – render + persist a message
 *   Chat.beginStream()                 – start a streaming bubble
 *   Chat.updateStream(fullText)        – update streaming text
 *   Chat.endStream(finalText)          – finalize + persist stream
 *   Chat.renderPanel(name)             – render sidebar panel
 *   Chat.isStreaming()                 – true while a stream is active
 *   Chat.clearActive()                 – wipe active tab's history
 *   Chat.clearAll()                    – wipe every tab's history
 *   Chat.showCmdPopup / hideCmdPopup
 *   Chat.COMMANDS
 */
;(function () {
  "use strict";

  const STORAGE_KEY = "orbit-chat-history";
  const MAX_MESSAGES = 500;
  const RESTORE_LIMIT = 80;
  const HISTORY_RENDER_LIMIT = 100;

  // ── Per-tab state ────────────────────────────────────────────
  let tabHistories = new Map();   // tabId → [{ role, content, time }]
  let activeTabId = null;         // currently visible tab
  let streamTabId = null;         // tab that owns the in-flight stream
  let _streamAttached = false;   // is streamingEl in the DOM right now?

  let bodyEl = null;   // #sbBody
  let navEl = null;    // #sbNav
  let streamingEl = null;
  let streamingText = "";
  let activePanel = "jarvis";

  // Set by renderer before async send so beginStream routes to the right tab
  let pendingStreamTabId = null;

  // ── Per-tab helpers ──────────────────────────────────────────
  function getTabHistory(tabId) {
    if (!tabHistories.has(tabId)) tabHistories.set(tabId, []);
    return tabHistories.get(tabId);
  }

  function pushToTab(tabId, role, content) {
    const hist = getTabHistory(tabId);
    hist.push({ role, content, time: Date.now() });
    if (hist.length > MAX_MESSAGES) {
      hist.splice(0, hist.length - MAX_MESSAGES);
    }
    persistAll();
  }

  function allMessages() {
    const out = [];
    for (const [, hist] of tabHistories) out.push(...hist);
    return out;
  }

  // ── Persistence ──────────────────────────────────────────────
  function loadHistory() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) { tabHistories = new Map(); return; }
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        tabHistories = new Map([["__legacy__", parsed]]);
      } else {
        tabHistories = new Map(Object.entries(parsed));
      }
    } catch (_) {
      tabHistories = new Map();
    }
  }

  function persistAll() {
    try {
      const obj = {};
      for (const [k, v] of tabHistories) obj[k] = v;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(obj));
    } catch (_) {
      for (const [k, v] of tabHistories) {
        tabHistories.set(k, v.slice(-Math.floor(MAX_MESSAGES / 2)));
      }
      try {
        const obj = {};
        for (const [k, v] of tabHistories) obj[k] = v;
        localStorage.setItem(STORAGE_KEY, JSON.stringify(obj));
      } catch (_) {}
    }
  }

  // ── Message Rendering ────────────────────────────────────────
  const LABELS = { user: "You", jarvis: "JARVIS", error: "Error", system: "System" };

  function messageHTML(role, content) {
    const label = LABELS[role] || role;
    const color = role === "user" ? "var(--jb-paper)" : "var(--jb-text)";
    return (
      '<div class="chat-label">' + label + "</div>" +
      '<div class="chat-content" style="color:' + color + '">' +
        escapeHtml(content) +
      "</div>"
    );
  }

  function createMessageEl(role, content) {
    const el = document.createElement("div");
    el.className = "chat-msg chat-msg--" + role;
    el.innerHTML = messageHTML(role, content);
    return el;
  }

  function appendMessage(role, content) {
    if (!bodyEl) return;
    // If a stream is in flight for a different tab, route system/error there
    var targetTab = (streamingEl && streamTabId && streamTabId !== activeTabId)
      ? streamTabId : activeTabId;
    if (targetTab && targetTab !== activeTabId) {
      if (role === "user" || role === "jarvis" || role === "error") {
        pushToTab(targetTab, role, content);
      }
      return;
    }
    bodyEl.appendChild(createMessageEl(role, content));
    bodyEl.scrollTop = bodyEl.scrollHeight;
    if (role === "user" || role === "jarvis" || role === "error") {
      pushToTab(activeTabId, role, content);
    }
  }

  // ── Streaming ────────────────────────────────────────────────
  function beginStream() {
    if (streamingEl) return;
    streamTabId = pendingStreamTabId || activeTabId;
    pendingStreamTabId = null;
    streamingEl = document.createElement("div");
    streamingEl.className = "chat-msg chat-msg--jarvis chat-msg--streaming";
    streamingEl.innerHTML =
      '<div class="chat-label">JARVIS</div>' +
      '<div class="chat-content streaming-text" style="color:var(--jb-text)"></div>';
    streamingText = "";

    if (streamTabId === activeTabId) {
      bodyEl.appendChild(streamingEl);
      _streamAttached = true;
    } else {
      _streamAttached = false;
    }
  }

  function updateStream(fullText) {
    if (!streamingEl) { beginStream(); return; }
    streamingText = fullText || "";
    const textEl = streamingEl.querySelector(".streaming-text");
    if (textEl) textEl.textContent = streamingText;
    if (_streamAttached) bodyEl.scrollTop = bodyEl.scrollHeight;
  }

  function endStream(finalText) {
    if (!streamingEl) {
      // Stream was detached by tab switch — finalize into the owning tab
      if (streamTabId && finalText) pushToTab(streamTabId, "jarvis", finalText);
      streamTabId = null;
      return;
    }
    const text = finalText || streamingText;
    const textEl = streamingEl.querySelector(".streaming-text");
    if (textEl) textEl.textContent = text;
    var targetTab = streamTabId || activeTabId;
    if (_streamAttached) {
      if (text) {
        // Swap the streaming bubble for the finalized message in place,
        // so the reply is visible without a panel re-render.
        bodyEl.replaceChild(createMessageEl("jarvis", text), streamingEl);
        bodyEl.scrollTop = bodyEl.scrollHeight;
      } else {
        bodyEl.removeChild(streamingEl);
      }
    }
    streamingEl = null;
    _streamAttached = false;
    streamingText = "";
    streamTabId = null;
    if (text) pushToTab(targetTab, "jarvis", text);
  }

  // ── Tab switching ────────────────────────────────────────────
  function setTab(tabId) {
    if (!tabId || activeTabId === tabId) return;

    // Detach in-flight stream from the old tab's DOM (keep it alive in JS)
    if (streamingEl && _streamAttached) {
      streamingEl.remove();
      _streamAttached = false;
    }

    activeTabId = tabId;
    restoreChat();

    // Re-attach if this tab owns the stream
    if (streamingEl && !_streamAttached && streamTabId === tabId) {
      bodyEl.appendChild(streamingEl);
      _streamAttached = true;
      bodyEl.scrollTop = bodyEl.scrollHeight;
    }
  }

  function forgetTab(tabId) {
    tabHistories.delete(tabId);
    persistAll();
  }

  // ── History Restore ──────────────────────────────────────────
  function restoreChat() {
    if (!bodyEl) return;
    if (streamingEl && _streamAttached) return; // stream live — don't destroy it
    bodyEl.innerHTML = "";
    var hist = getTabHistory(activeTabId);
    if (hist.length === 0) {
      var online = window._jarvisOnline;
      bodyEl.innerHTML =
        '<div class="chat-empty">' +
          '<div class="chat-empty-status">' + (online ? "READY" : "OFF") + "</div>" +
          '<div class="chat-empty-sub">' +
            (online
              ? "Ask me anything. I\u2019m always here."
              : "JARVIS is offline. Browse normally.") +
          "</div>" +
        "</div>";
      return;
    }
    var msgs = hist.slice(-RESTORE_LIMIT);
    var frag = document.createDocumentFragment();
    for (var i = 0; i < msgs.length; i++) {
      frag.appendChild(createMessageEl(msgs[i].role, msgs[i].content));
    }
    bodyEl.appendChild(frag);
    bodyEl.scrollTop = bodyEl.scrollHeight;
  }

  // ── Slash-Command Autocomplete ───────────────────────────────
  var COMMANDS = [
    { cmd: "/task",     desc: "Run an autonomous agent task" },
    { cmd: "/research", desc: "Research a topic" },
    { cmd: "/summarize",desc: "Summarize the current page" },
    { cmd: "/navigate", desc: "Navigate to a URL" },
    { cmd: "/read",     desc: "Read page content" },
    { cmd: "/screenshot",desc: "Capture the page" },
    { cmd: "/status",   desc: "Show JARVIS/DSH status" },
    { cmd: "/yt",       desc: "Private YouTube search (no tracking)" },
    { cmd: "/help",     desc: "Show available commands" },
  ];

  var cmdPopupEl = null;

  function ensureCmdPopup() {
    if (cmdPopupEl) return cmdPopupEl;
    cmdPopupEl = document.createElement("div");
    cmdPopupEl.className = "cmd-popup";
    cmdPopupEl.style.display = "none";
    var composer = bodyEl && bodyEl.closest(".sidebar");
    if (composer) composer.appendChild(cmdPopupEl);
    return cmdPopupEl;
  }

  function showCmdPopup(filter) {
    var popup = ensureCmdPopup();
    var q = (filter || "").toLowerCase();
    var matches = COMMANDS.filter(
      function (c) { return !q || c.cmd.includes(q) || c.desc.toLowerCase().includes(q); }
    );
    if (matches.length === 0) { popup.style.display = "none"; return; }
    popup.innerHTML = matches
      .map(function (c) {
        return '<div class="cmd-popup-item" data-cmd="' + c.cmd + '">' +
          '<span class="cmd-popup-cmd">' + c.cmd + "</span>" +
          '<span class="cmd-popup-desc">' + c.desc + "</span>" +
          "</div>";
      })
      .join("");
    popup.style.display = "block";
    popup.querySelectorAll(".cmd-popup-item").forEach(function (el) {
      el.addEventListener("mousedown", function (e) {
        e.preventDefault();
        var input = document.getElementById("sbInput");
        if (input) { input.value = el.dataset.cmd + " "; input.focus(); }
        popup.style.display = "none";
      });
    });
  }

  function hideCmdPopup() {
    if (cmdPopupEl) cmdPopupEl.style.display = "none";
  }

  // ── Panel Rendering ──────────────────────────────────────────
  function renderPanel(name) {
    activePanel = name;
    if (name === "jarvis") { restoreChat(); return; }
    if (name === "chat-history") { renderHistoryPanel(); return; }
    if (name === "activity") { renderActivityPanel(); return; }
    if (window._renderNonChatPanel) window._renderNonChatPanel(name);
  }

  function renderHistoryPanel() {
    if (!bodyEl) return;
    var msgs = allMessages();
    bodyEl.innerHTML =
      '<div class="panel-pad">' +
        '<input type="text" id="chatSearchInput" class="chat-search" placeholder="Search all conversations..." />' +
        '<div class="chat-history-meta">' +
          '<span class="chat-history-count">' + msgs.length + " messages across all tabs</span>" +
          '<button id="clearChatHistory" class="chat-history-clear">Clear all</button>' +
        "</div>" +
        '<div id="chatHistoryList" class="chat-history-list"></div>' +
      "</div>";

    renderHistoryList("");

    var searchInput = document.getElementById("chatSearchInput");
    if (searchInput) {
      var debounceTimer;
      searchInput.addEventListener("input", function () {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function () { renderHistoryList(searchInput.value); }, 120);
      });
      searchInput.focus();
    }

    var clearBtn = document.getElementById("clearChatHistory");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        if (confirm("Clear all chat history from every tab?")) {
          tabHistories.clear();
          localStorage.removeItem(STORAGE_KEY);
          renderHistoryList("");
          var countEl = bodyEl.querySelector(".chat-history-count");
          if (countEl) countEl.textContent = "0 messages across all tabs";
        }
      });
    }
  }

  function renderHistoryList(query) {
    var list = document.getElementById("chatHistoryList");
    if (!list) return;
    var msgs = allMessages();
    var filtered = msgs;
    if (query) {
      var q = query.toLowerCase();
      filtered = msgs.filter(function (m) { return (m.content || "").toLowerCase().includes(q); });
    }
    if (filtered.length === 0) {
      list.innerHTML =
        '<div class="chat-history-empty">' +
          (query ? "No matching messages" : "No messages yet") +
        "</div>";
      return;
    }
    var shown = filtered.slice(-HISTORY_RENDER_LIMIT).reverse();
    var html = "";
    var lastDay = "";
    for (var i = 0; i < shown.length; i++) {
      var entry = shown[i];
      var d = new Date(entry.time);
      var day = d.toLocaleDateString();
      if (day !== lastDay) {
        lastDay = day;
        html += '<div class="chat-history-date">' + day + "</div>";
      }
      var time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      var label = LABELS[entry.role] || entry.role;
      var preview = (entry.content || "").substring(0, 120);
      html +=
        '<div class="chat-history-item">' +
          '<div class="chat-history-item-header">' +
            '<span class="chat-history-item-label">' + label + "</span>" +
            '<span class="chat-history-item-time">' + time + "</span>" +
          "</div>" +
          '<div class="chat-history-item-preview">' + escapeHtml(preview) + "</div>" +
        "</div>";
    }
    list.innerHTML = html;
  }

  function renderActivityPanel() {
    if (!bodyEl) return;
    var msgs = allMessages();
    var recent = msgs.slice(-10).reverse();

    if (recent.length === 0) {
      bodyEl.innerHTML = '<div class="panel-pad panel-muted">No recent activity.</div>';
      return;
    }

    var html = '<div class="panel-pad"><div class="panel-section-label">Recent Activity</div>';
    for (var i = 0; i < recent.length; i++) {
      var entry = recent[i];
      var d = new Date(entry.time);
      var time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      var label = entry.role === "user" ? "You asked" : "JARVIS replied";
      var preview = (entry.content || "").substring(0, 80);
      html +=
        '<div class="activity-item">' +
          '<div class="activity-meta">' + time + " \u00b7 " + label + "</div>" +
          '<div class="activity-preview">' + escapeHtml(preview) + "</div>" +
        "</div>";
    }
    html += "</div>";
    bodyEl.innerHTML = html;
  }

  // ── Init ─────────────────────────────────────────────────────
  function init(body, nav) {
    bodyEl = body;
    navEl = nav;
    loadHistory();
  }

  // ── Public API ───────────────────────────────────────────────
  window.Chat = {
    init: init,
    append: appendMessage,
    beginStream: beginStream,
    updateStream: updateStream,
    endStream: endStream,
    renderPanel: renderPanel,
    setTab: setTab,
    forgetTab: forgetTab,
    isStreaming: function () { return !!streamingEl; },
    clearActive: function () {
      tabHistories.delete(activeTabId);
      persistAll();
      if (bodyEl) bodyEl.innerHTML = "";
    },
    clearAll: function () {
      tabHistories.clear();
      localStorage.removeItem(STORAGE_KEY);
      if (bodyEl) bodyEl.innerHTML = "";
    },
    showCmdPopup: showCmdPopup,
    hideCmdPopup: hideCmdPopup,
    COMMANDS: COMMANDS,
    set pendingStreamTabId(v) { pendingStreamTabId = v; },
  };
})();
