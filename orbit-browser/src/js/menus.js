/* menus - extracted from renderer.js by scripts/split_renderer.py.
 * Classic script, loads in the shared global scope before renderer.js.
 * Event bindings use closures so load order never matters.
 */
// ---------------------------------------------------------------------
// ── Vision Panel ─────────────────────────────────────────────
function renderVisionPanel() {
  let html = '<div style="padding:16px;color:var(--jb-mute)">';
  
  html += '<div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--jb-ghost);margin-bottom:12px">Vision Agent</div>';
  
  html += '<div style="border:1px solid var(--jb-border);border-radius:12px;padding:12px;background:var(--jb-void);margin-bottom:12px">';
  html += '<div style="font-size:13px;color:var(--jb-paper);font-weight:500;margin-bottom:8px">Page Analysis</div>';
  html += '<p style="font-size:12px;color:var(--jb-mute);margin-bottom:10px">Capture screenshots and analyze page content with vision AI.</p>';
  html += '<button onclick="window.visionAgent && window.visionAgent.describePage().then(r => { if(r.success) alert(r.answer.slice(0,500)); else alert(r.error); })" style="padding:6px 12px;border:1px solid var(--jb-line-hard);border-radius:6px;background:var(--jb-surface);color:var(--jb-text);font-size:12px;cursor:pointer;margin-right:6px">Describe Page</button>';
  html += '<button onclick="window.readingMode && window.readingMode.toggle()" style="padding:6px 12px;border:1px solid var(--jb-line-hard);border-radius:6px;background:var(--jb-surface);color:var(--jb-text);font-size:12px;cursor:pointer">Reading Mode</button>';
  html += '</div>';
  
  html += '<div style="border:1px solid var(--jb-border);border-radius:12px;padding:12px;background:var(--jb-void);margin-bottom:12px">';
  html += '<div style="font-size:13px;color:var(--jb-paper);font-weight:500;margin-bottom:8px">Multi-Agent Planner</div>';
  html += '<p style="font-size:12px;color:var(--jb-mute);margin-bottom:10px">Decompose tasks into steps with planner + navigator architecture.</p>';
  html += '<textarea id="plannerInput" rows="2" placeholder="Describe a task..." style="width:100%;padding:8px;background:var(--jb-void);border:1px solid var(--jb-border);border-radius:6px;color:var(--jb-text);font-size:12px;resize:none;margin-bottom:8px"></textarea>';
  html += '<button id="plannerExecBtn" style="padding:6px 12px;border:1px solid var(--jb-line-hard);border-radius:6px;background:var(--jb-paper);color:var(--jb-void);font-size:12px;cursor:pointer;font-weight:500">Execute Task</button>';
  html += '</div>';
  
  html += '<div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--jb-ghost);margin-bottom:8px;margin-top:16px">Keyboard Shortcuts</div>';
  html += '<div style="font-size:12px;color:var(--jb-mute)">';
  html += '<div style="display:flex;justify-content:space-between;padding:4px 0"><span>Ctrl+Shift+D</span><span style="color:var(--jb-ghost)">Toggle reading mode</span></div>';
  html += '<div style="display:flex;justify-content:space-between;padding:4px 0"><span>Ctrl+Shift+V</span><span style="color:var(--jb-ghost)">Vision analysis</span></div>';
  html += '<div style="display:flex;justify-content:space-between;padding:4px 0"><span>Ctrl+K</span><span style="color:var(--jb-ghost)">Command palette</span></div>';
  html += '</div>';
  
  html += '</div>';
  sbBody.innerHTML = html;

  // Wire up planner button
  const plannerBtn = document.getElementById('plannerExecBtn');
  const plannerInput = document.getElementById('plannerInput');
  if (plannerBtn && plannerInput) {
    plannerBtn.addEventListener('click', function() {
      const task = plannerInput.value.trim();
      if (!task) return;
      if (window.multiAgentPlanner) {
        plannerBtn.textContent = 'Running...';
        plannerBtn.disabled = true;
        window.multiAgentPlanner.execute(task).then(function(r) {
          plannerBtn.textContent = 'Execute Task';
          plannerBtn.disabled = false;
          if (r.success) showToast('ok', 'Task Complete', r.result);
          else showToast('err', 'Task Failed', r.error);
        });
      }
    });
  }
}

// renderDshPanel removed — DSH is integrated into JARVIS (chat.js)

// ── Context Menu ──────────────────────────────────────────────
const tabContextMenu = $("#tabContextMenu");
let contextTabId = null;

if (tabStrip) tabStrip.addEventListener("contextmenu", (e) => {
  const tabEl = e.target.closest(".tab");
  if (!tabEl) return;
  e.preventDefault();
  contextTabId = tabEl.dataset.id;
  tabContextMenu.style.left = e.clientX + "px";
  tabContextMenu.style.top = e.clientY + "px";
  tabContextMenu.classList.add("on");
});

if (tabContextMenu) tabContextMenu.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  const action = btn.dataset.action;
  if (action === "newTab") createTab();
  if (action === "reopenTab") reopenClosedTab();
  if (action === "duplicate" && contextTabId) { const tab = tabs.get(contextTabId); if (tab) createTab(tab.url); }
  if (action === "closeTab" && contextTabId) closeTab(contextTabId);
  if (action === "closeOthers" && contextTabId) { for (const [id] of tabs) { if (id !== contextTabId) { ntpDrafts.delete(id); clearSleepTimer(id); clearHibernateTimer(id); tabs.delete(id); } } activateTab(contextTabId); renderTabs(); }
  if (action === "closeRight" && contextTabId) {
    const ids = Array.from(tabs.keys());
    const idx = ids.indexOf(contextTabId);
    for (let i = idx + 1; i < ids.length; i++) {
      clearSleepTimer(ids[i]); clearHibernateTimer(ids[i]); tabs.delete(ids[i]);
    }
    activateTab(contextTabId); renderTabs();
  }
  if (action === "reload") { try { const wv = activeWebview(); if (wv) wv.reload(); } catch (e) {} }
  if (action === "copyUrl" && contextTabId) { const tab = tabs.get(contextTabId); if (tab) navigator.clipboard.writeText(tab.url); }
  if (action === "muteTab" && contextTabId) { const tab = tabs.get(contextTabId); if (tab && tab.webview) { tab.muted = !tab.muted; try { tab.webview.setAudioMuted(tab.muted); } catch (err) {} renderTabs(); } }
  if (action === "pinTab" && contextTabId) { const tab = tabs.get(contextTabId); if (tab) { tab.pinned = !tab.pinned; renderTabs(); saveSession(); } }
  if (action === "groupTab" && contextTabId) groupTab(contextTabId);
  if (action === "ungroupTab" && contextTabId) ungroupTab(contextTabId);
  tabContextMenu.classList.remove("on");
});

// NOTE: tab strip click/drag handling is delegated once near renderTabs()
// (single listener for activate, close, group-dot, and drag reorder).

// ── Browser Menu ──────────────────────────────────────────────
const browserMenu = $("#browserMenu");
const menuBtn = $("#menuBtn");
if (menuBtn) menuBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  closeAllPopups();
  browserMenu.style.right = "10px";
  browserMenu.style.top = "84px";
  browserMenu.classList.toggle("on");
});

// ── About (browser menu) ──────────────────────────────────────
const aboutOrbit = document.getElementById("aboutOrbit");
if (aboutOrbit) aboutOrbit.addEventListener("click", (e) => {
  e.stopPropagation();
  closeAllPopups();
  showToast("info", "JARVIS Orbit 0.1.0", "Unbranded Chromium (Electron) \u00b7 DSH/1.0 \u00b7 Nothing Design System");
});

// ── Extension Popup ───────────────────────────────────────────
const extPopup = $("#extPopup");
const extBtn = $("#extBtn");
if (extBtn) extBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  closeAllPopups();
  renderExtPopup();
  extPopup.style.right = "50px";
  extPopup.style.top = "84px";
  extPopup.classList.toggle("on");
});

// ── Profile Popup ─────────────────────────────────────────────
const profilePopup = $("#profilePopup");
const profileBtn = $("#profileBtn");
if (profileBtn) profileBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  closeAllPopups();
  renderProfilePopup();
  profilePopup.style.right = "80px";
  profilePopup.style.top = "84px";
  profilePopup.classList.toggle("on");
});

// ── Profiles (Chrome-style multi-profile) ─────────────────────
const PROFILES_KEY = "orbit-profiles";
const PROFILE_COLORS = ["#8ab4f8", "#f28b82", "#81c995", "#fdd663", "#d7aefb", "#78d9ec", "#ff8bcb", "#9aa0a6"];
function getProfiles() {
  try {
    const p = JSON.parse(localStorage.getItem(PROFILES_KEY) || "[]");
    return (p && p.length) ? p : [{ id: "default", name: "Personal", color: "#9aa0a6", active: true }];
  } catch (e) { return [{ id: "default", name: "Personal", color: "#9aa0a6", active: true }]; }
}
function saveProfiles(p) { try { localStorage.setItem(PROFILES_KEY, JSON.stringify(p)); } catch (e) {} }
function activeProfile() { return getProfiles().find((x) => x.active) || getProfiles()[0]; }
function syncProfileAvatar() {
  const prof = activeProfile();
  const avatar = document.querySelector(".toolbar-avatar");
  if (avatar) {
    avatar.textContent = (prof.name || "P").charAt(0).toUpperCase();
    avatar.style.background = prof.color;
  }
}
function switchProfile(id) {
  const p = getProfiles();
  if (!p.some((x) => x.id === id)) return;
  p.forEach((x) => { x.active = (x.id === id); });
  saveProfiles(p);
  syncProfileAvatar();
  renderProfilePopup();
  const prof = activeProfile();
  showToast("ok", "Profile Switched", "Now using \"" + prof.name + "\"");
  closeAllPopups();
}
function addProfile() {
  const name = prompt("New profile name:", "");
  if (!name || !name.trim()) return;
  const p = getProfiles();
  p.push({ id: "p" + Date.now().toString(36), name: name.trim().slice(0, 24), color: PROFILE_COLORS[p.length % PROFILE_COLORS.length], active: false });
  saveProfiles(p);
  switchProfile(p[p.length - 1].id);
}
function toggleGuestMode() {
  const p = getProfiles();
  const active = activeProfile();
  if (active.id === "guest") {
    const fallback = p.find((x) => x.id !== "guest");
    if (fallback) switchProfile(fallback.id);
    return;
  }
  if (!p.some((x) => x.id === "guest")) {
    p.push({ id: "guest", name: "Guest", color: "#f28b82", active: false });
    saveProfiles(p);
  }
  switchProfile("guest");
  showToast("warn", "Guest Mode", "This session's data will not be saved");
}
function lockProfile() {
  localStorage.removeItem(HISTORY_KEY);
  localStorage.removeItem("orbit-bookmarks");
  localStorage.removeItem("orbit-session");
  bookmarks = [];
  closedTabs.length = 0;
  renderBookmarkBar();
  showToast("ok", "Profile Locked", "History and saved data cleared");
  renderProfilePopup();
}
function renderProfilePopup() {
  const popup = document.getElementById("profilePopup");
  if (!popup) return;
  const prof = activeProfile();
  const guest = prof.id === "guest";
  let html = '<div class="pop-header"><div class="profile-avatar" style="background:' + prof.color + '">' + escapeHtml(prof.name.charAt(0).toUpperCase()) + '</div><div><div class="pop-title">' + escapeHtml(prof.name) + '</div><div class="pop-sub">' + (guest ? "Guest \u00b7 not saved" : "Personal \u00b7 Sync on") + '</div></div></div>';
  getProfiles().forEach((p) => {
    html += '<button class="profile-item' + (p.active ? " on" : "") + '" data-profile="' + p.id + '"><span class="profile-avatar sm" style="background:' + p.color + '">' + escapeHtml(p.name.charAt(0).toUpperCase()) + '</span><span class="profile-name">' + escapeHtml(p.name) + '</span>' + (p.active ? '<span class="chip ok">Active</span>' : "") + '</button>';
  });
  html += '<div class="menu-sep"></div>';
  html += '<button class="menu-item" id="profileAdd">Add profile</button>';
  html += guest
    ? '<button class="menu-item" id="profileExitGuest">Exit guest mode</button>'
    : '<button class="menu-item" id="profileGuest">Guest mode</button>';
  html += '<button class="menu-item" id="profileLock">Lock profile</button>';
  html += '<div class="menu-sep"></div>';
  html += '<button class="menu-item" data-nav="orbit://settings">Profile settings</button>';
  popup.innerHTML = html;
  popup.querySelectorAll("[data-profile]").forEach((b) => b.addEventListener("click", () => switchProfile(b.dataset.profile)));
  const addBtn = document.getElementById("profileAdd");
  if (addBtn) addBtn.addEventListener("click", () => addProfile());
  const guestBtn = document.getElementById("profileGuest");
  if (guestBtn) guestBtn.addEventListener("click", () => toggleGuestMode());
  const exitBtn = document.getElementById("profileExitGuest");
  if (exitBtn) exitBtn.addEventListener("click", () => toggleGuestMode());
  const lockBtn = document.getElementById("profileLock");
  if (lockBtn) lockBtn.addEventListener("click", () => lockProfile());
}

// ── Extension Popup (interactive) ─────────────────────────────
const EXT_STATE_KEY = "orbit-ext-state";
const EXTENSIONS = [
  { id: "jarvis", name: "JARVIS", sub: "Built into Orbit", builtin: true },
  { id: "ublock", name: "uBlock Origin", sub: "Ad & tracker blocking" },
  { id: "bitwarden", name: "Bitwarden", sub: "Password manager" },
];
function getExtState() {
  try { return JSON.parse(localStorage.getItem(EXT_STATE_KEY) || "{}"); } catch (e) { return {}; }
}
function saveExtState(s) { try { localStorage.setItem(EXT_STATE_KEY, JSON.stringify(s)); } catch (e) {} }
function extStatus(id) { const s = getExtState()[id] || {}; return { pinned: !!s.pinned, enabled: s.enabled !== false }; }
function renderExtPopup() {
  const popup = document.getElementById("extPopup");
  if (!popup) return;
  let html = '<div class="pop-header"><span class="pop-title">Extensions</span></div>';
  EXTENSIONS.forEach((ext) => {
    const st = extStatus(ext.id);
    html += '<div class="ext-row' + (st.enabled ? "" : " disabled") + '"><div class="ext-icon">' + escapeHtml(ext.name.charAt(0).toUpperCase()) + '</div>' +
      '<div class="ext-info"><div class="ext-name">' + escapeHtml(ext.name) + '</div><div class="ext-sub">' + escapeHtml(ext.sub) + '</div></div>' +
      '<button class="chip ext-pin' + (st.pinned ? " ok" : "") + '" data-pin="' + ext.id + '" title="' + (st.pinned ? "Unpin from toolbar" : "Pin to toolbar") + '">' + (st.pinned ? "\u2713" : "Pin") + '</button>' +
      '<button class="ext-power' + (st.enabled ? " on" : "") + '" data-power="' + ext.id + '" title="' + (st.enabled ? "Disable extension" : "Enable extension") + '"></button>' +
      '</div>';
  });
  html += '<div class="menu-sep"></div>';
  html += '<button class="menu-item" data-nav="orbit://extensions">Manage extensions</button>';
  popup.innerHTML = html;
  popup.querySelectorAll("[data-pin]").forEach((b) => b.addEventListener("click", (e) => {
    e.stopPropagation();
    const s = getExtState(); const st = s[b.dataset.pin] || {};
    st.pinned = !st.pinned; s[b.dataset.pin] = st;
    saveExtState(s);
    renderExtPopup(); renderExtensionsPage();
  }));
  popup.querySelectorAll("[data-power]").forEach((b) => b.addEventListener("click", (e) => {
    e.stopPropagation();
    const s = getExtState(); const st = s[b.dataset.power] || {};
    st.enabled = st.enabled === false ? true : false; s[b.dataset.power] = st;
    saveExtState(s);
    renderExtPopup(); renderExtensionsPage();
  }));
}