/**
 * JARVIS Orbit — Chat Module
 *
 * Single owner of ALL chat state: persistence, message rendering,
 * streaming, history search, activity feed, slash-command discoverability.
 *
 * Public API (window.Chat):
 *   Chat.init(bodyEl, navEl)           – wire DOM references
 *   Chat.append(role, content)         – render + persist a message
 *   Chat.beginStream()                 – start a streaming bubble
 *   Chat.updateStream(fullText)        – update streaming text
 *   Chat.endStream(finalText)          – finalize + persist stream
 *   Chat.renderPanel(name)             – render sidebar panel
 *   Chat.isStreaming()                 – true while a stream is active
 *   Chat.clear()                       – wipe history
 */
;(function () {
  "use strict";

  // ── State ─────────────────────────────────────────────────────
  const STORAGE_KEY = "orbit-chat-history";
  const MAX_MESSAGES = 500;
  const RESTORE_LIMIT = 80;
  const HISTORY_RENDER_LIMIT = 100;

  let history = [];
  let bodyEl = null;     // #sbBody
  let navEl = null;      // #sbNav
  let streamingEl = null;
  let streamingText = "";
  let activePanel = "jarvis";

  // ── Persistence ───────────────────────────────────────────────
  function loadHistory() {
    try {
      history = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    } catch (_) {
      history = [];
    }
  }

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
    } catch (_) {
      // localStorage full — trim oldest
      history = history.slice(-Math.floor(MAX_MESSAGES / 2));
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(history)); } catch (_) {}
    }
  }

  function pushMessage(role, content) {
    history.push({ role, content, time: Date.now() });
    if (history.length > MAX_MESSAGES) history = history.slice(-MAX_MESSAGES);
    persist();
  }

  // ── Message Rendering ─────────────────────────────────────────
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
    bodyEl.appendChild(createMessageEl(role, content));
    bodyEl.scrollTop = bodyEl.scrollHeight;
    // Persist user/jarvis/error (not system — ephemeral)
    if (role === "user" || role === "jarvis" || role === "error") {
      pushMessage(role, content);
    }
  }

  // ── Streaming ─────────────────────────────────────────────────
  function beginStream() {
    if (!bodyEl) return;
    // Don't create a second stream
    if (streamingEl) return;
    streamingEl = document.createElement("div");
    streamingEl.className = "chat-msg chat-msg--jarvis chat-msg--streaming";
    streamingEl.innerHTML =
      '<div class="chat-label">JARVIS</div>' +
      '<div class="chat-content streaming-text" style="color:var(--jb-text)"></div>';
    bodyEl.appendChild(streamingEl);
    streamingText = "";
  }

  function updateStream(fullText) {
    if (!streamingEl) beginStream();
    streamingText = fullText || "";
    const textEl = streamingEl.querySelector(".streaming-text");
    if (textEl) textEl.textContent = streamingText;
    bodyEl.scrollTop = bodyEl.scrollHeight;
  }

  function endStream(finalText) {
    if (!streamingEl) return;
    const text = finalText || streamingText;
    const textEl = streamingEl.querySelector(".streaming-text");
    if (textEl) textEl.textContent = text;
    // Transition from streaming to permanent message
    streamingEl.className = "chat-msg chat-msg--jarvis";
    streamingEl = null;
    streamingText = "";
    // Persist the completed response
    if (text) pushMessage("jarvis", text);
  }

  // ── History Restore ───────────────────────────────────────────
  function restoreChat() {
    if (!bodyEl) return;
    // If a stream is active, don't destroy it
    if (streamingEl) return;
    bodyEl.innerHTML = "";
    if (history.length === 0) {
      const online = window._jarvisOnline;
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
    const msgs = history.slice(-RESTORE_LIMIT);
    const frag = document.createDocumentFragment();
    for (const entry of msgs) {
      frag.appendChild(createMessageEl(entry.role, entry.content));
    }
    bodyEl.appendChild(frag);
    bodyEl.scrollTop = bodyEl.scrollHeight;
  }

  // ── Slash-Command Autocomplete ────────────────────────────────
  const COMMANDS = [
    { cmd: "/task",     desc: "Run an autonomous agent task" },
    { cmd: "/research", desc: "Research a topic" },
    { cmd: "/summarize",desc: "Summarize the current page" },
    { cmd: "/navigate", desc: "Navigate to a URL" },
    { cmd: "/read",     desc: "Read page content" },
    { cmd: "/screenshot",desc: "Capture the page" },
    { cmd: "/status",   desc: "Show JARVIS/DSH status" },
    { cmd: "/help",     desc: "Show available commands" },
  ];

  let cmdPopupEl = null;

  function ensureCmdPopup() {
    if (cmdPopupEl) return cmdPopupEl;
    cmdPopupEl = document.createElement("div");
    cmdPopupEl.className = "cmd-popup";
    cmdPopupEl.style.display = "none";
    // Insert after the composer
    const composer = bodyEl && bodyEl.closest(".sidebar");
    if (composer) composer.appendChild(cmdPopupEl);
    return cmdPopupEl;
  }

  function showCmdPopup(filter) {
    const popup = ensureCmdPopup();
    const q = (filter || "").toLowerCase();
    const matches = COMMANDS.filter(
      (c) => !q || c.cmd.includes(q) || c.desc.toLowerCase().includes(q)
    );
    if (matches.length === 0) {
      popup.style.display = "none";
      return;
    }
    popup.innerHTML = matches
      .map(
        (c) =>
          '<div class="cmd-popup-item" data-cmd="' + c.cmd + '">' +
            '<span class="cmd-popup-cmd">' + c.cmd + "</span>" +
            '<span class="cmd-popup-desc">' + c.desc + "</span>" +
          "</div>"
      )
      .join("");
    popup.style.display = "block";
    // Wire click handlers
    popup.querySelectorAll(".cmd-popup-item").forEach((el) => {
      el.addEventListener("mousedown", (e) => {
        e.preventDefault();
        const input = document.getElementById("sbInput");
        if (input) {
          input.value = el.dataset.cmd + " ";
          input.focus();
        }
        popup.style.display = "none";
      });
    });
  }

  function hideCmdPopup() {
    if (cmdPopupEl) cmdPopupEl.style.display = "none";
  }

  // ── Panel Rendering ───────────────────────────────────────────
  function renderPanel(name) {
    activePanel = name;
    if (name === "jarvis") {
      restoreChat();
      return;
    }
    if (name === "chat-history") {
      renderHistoryPanel();
      return;
    }
    if (name === "activity") {
      renderActivityPanel();
      return;
    }
    // Non-chat panels: signal renderer.js to handle (vision, agents, memory)
    if (window._renderNonChatPanel) window._renderNonChatPanel(name);
  }

  function renderHistoryPanel() {
    if (!bodyEl) return;
    bodyEl.innerHTML =
      '<div class="panel-pad">' +
        '<input type="text" id="chatSearchInput" class="chat-search" placeholder="Search chat history..." />' +
        '<div class="chat-history-meta">' +
          '<span class="chat-history-count">' + history.length + " messages</span>" +
          '<button id="clearChatHistory" class="chat-history-clear">Clear all</button>' +
        "</div>" +
        '<div id="chatHistoryList" class="chat-history-list"></div>' +
      "</div>";

    renderHistoryList("");

    const searchInput = document.getElementById("chatSearchInput");
    if (searchInput) {
      let debounceTimer;
      searchInput.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => renderHistoryList(searchInput.value), 120);
      });
      searchInput.focus();
    }

    const clearBtn = document.getElementById("clearChatHistory");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        if (confirm("Clear all chat history?")) {
          history = [];
          localStorage.removeItem(STORAGE_KEY);
          renderHistoryList("");
          const countEl = bodyEl.querySelector(".chat-history-count");
          if (countEl) countEl.textContent = "0 messages";
        }
      });
    }
  }

  function renderHistoryList(query) {
    const list = document.getElementById("chatHistoryList");
    if (!list) return;

    let filtered = history;
    if (query) {
      const q = query.toLowerCase();
      filtered = history.filter((m) => (m.content || "").toLowerCase().includes(q));
    }

    if (filtered.length === 0) {
      list.innerHTML =
        '<div class="chat-history-empty">' +
          (query ? "No matching messages" : "No messages yet") +
        "</div>";
      return;
    }

    const shown = filtered.slice(-HISTORY_RENDER_LIMIT).reverse();
    let html = "";
    let lastDay = "";

    for (const entry of shown) {
      const d = new Date(entry.time);
      const day = d.toLocaleDateString();
      if (day !== lastDay) {
        lastDay = day;
        html += '<div class="chat-history-date">' + day + "</div>";
      }
      const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const label = LABELS[entry.role] || entry.role;
      const preview = (entry.content || "").substring(0, 120);
      html +=
        '<div class="chat-history-item" data-idx="' + history.indexOf(entry) + '">' +
          '<div class="chat-history-item-header">' +
            '<span class="chat-history-item-label">' + label + "</span>" +
            '<span class="chat-history-item-time">' + time + "</span>" +
          "</div>" +
          '<div class="chat-history-item-preview">' + escapeHtml(preview) + "</div>" +
        "</div>";
    }

    list.innerHTML = html;

    // Click: switch to JARVIS panel and scroll to message
    list.querySelectorAll(".chat-history-item").forEach((el) => {
      el.addEventListener("click", () => {
        // Switch nav to JARVIS
        if (navEl) {
          navEl.querySelectorAll("button").forEach((b) => {
            b.classList.toggle("on", b.dataset.panel === "jarvis");
          });
        }
        activePanel = "jarvis";
        restoreChat();
        // Scroll to the corresponding message
        const idx = parseInt(el.dataset.idx, 10);
        if (!isNaN(idx) && bodyEl) {
          const msgs = bodyEl.querySelectorAll(".chat-msg");
          // The restored messages start at history.length - RESTORE_LIMIT
          const offset = idx - (history.length - Math.min(history.length, RESTORE_LIMIT));
          if (offset >= 0 && offset < msgs.length) {
            msgs[offset].scrollIntoView({ behavior: "smooth", block: "center" });
            msgs[offset].classList.add("chat-msg--highlight");
            setTimeout(() => msgs[offset].classList.remove("chat-msg--highlight"), 2000);
          }
        }
      });
    });
  }

  function renderActivityPanel() {
    if (!bodyEl) return;
    const recent = history.slice(-10).reverse();

    if (recent.length === 0) {
      bodyEl.innerHTML = '<div class="panel-pad panel-muted">No recent activity.</div>';
      return;
    }

    let html = '<div class="panel-pad"><div class="panel-section-label">Recent Activity</div>';
    for (const entry of recent) {
      const d = new Date(entry.time);
      const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const label = entry.role === "user" ? "You asked" : "JARVIS replied";
      const preview = (entry.content || "").substring(0, 80);
      html +=
        '<div class="activity-item">' +
          '<div class="activity-meta">' + time + " \u00b7 " + label + "</div>" +
          '<div class="activity-preview">' + escapeHtml(preview) + "</div>" +
        "</div>";
    }
    html += "</div>";
    bodyEl.innerHTML = html;
  }

  // ── Init ──────────────────────────────────────────────────────
  function init(body, nav) {
    bodyEl = body;
    navEl = nav;
    loadHistory();
  }

  // ── Public API ────────────────────────────────────────────────
  window.Chat = {
    init,
    append: appendMessage,
    beginStream,
    updateStream,
    endStream,
    renderPanel,
    isStreaming: () => !!streamingEl,
    clear: () => {
      history = [];
      localStorage.removeItem(STORAGE_KEY);
      if (bodyEl) bodyEl.innerHTML = "";
    },
    showCmdPopup,
    hideCmdPopup,
    COMMANDS,
  };
})();
