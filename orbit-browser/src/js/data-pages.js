/* data-pages - extracted from renderer.js by scripts/split_renderer.py.
 * Classic script, loads in the shared global scope before renderer.js.
 * Event bindings use closures so load order never matters.
 */
// ---------------------------------------------------------------------
// ── History (Chrome-style recent visits, recorded on navigate) ──
const HISTORY_KEY = "orbit-history";
function getHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); } catch (e) { return []; }
}
function recordHistory(url, title) {
  if (!url || url.startsWith("about:") || url.startsWith("orbit://") || url.startsWith("data:")) return;
  const h = getHistory();
  const now = Date.now();
  // Merge consecutive duplicates (same URL within a minute).
  if (h.length && h[0].url === url && (now - h[0].ts) < 60000) {
    h[0].title = title; h[0].ts = now;
  } else {
    h.unshift({ url: url, title: title || url, ts: now });
  }
  if (h.length > 400) h.length = 400;
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(h)); } catch (e) {}
}
// ── Boosts (Arc-style per-site custom CSS/JS) ──────────────
let _boosts = JSON.parse(localStorage.getItem('orbit-boosts') || '{}');

function getBoostForDomain(domain) {
  return _boosts[domain] || null;
}

function saveBoost(domain, boost) {
  if (boost.css || boost.js) {
    _boosts[domain] = boost;
  } else {
    delete _boosts[domain];
  }
  localStorage.setItem('orbit-boosts', JSON.stringify(_boosts));
}

function applyBoostToWebview(wv, url) {
  if (!wv || !url) return;
  try {
    var domain = new URL(url).hostname;
    var boost = getBoostForDomain(domain);
    if (!boost) return;
    if (boost.css) {
      wv.insertCSS(boost.css).catch(function() {});
    }
    if (boost.js) {
      wv.executeJavaScript(boost.js).catch(function() {});
    }
  } catch (e) {}
}

function createBoostUI() {
  var domain = '';
  try {
    var tab = tabs.get(activeTabId);
    if (tab && tab.url) domain = new URL(tab.url).hostname;
  } catch (e) {}
  if (!domain) { showToast('err', 'No site', 'Navigate to a site first'); return; }
  var existing = getBoostForDomain(domain);
  var css = prompt('Custom CSS for ' + domain + ':', existing ? existing.css || '' : '');
  if (css === null) return;
  var js = prompt('Custom JS for ' + domain + ':', existing ? existing.js || '' : '');
  if (js === null) return;
  saveBoost(domain, { css: css, js: js, created: Date.now() });
  showToast('ok', 'Boost saved', 'Applied to ' + domain);
  // Re-apply to current tab
  var tab = tabs.get(activeTabId);
  if (tab && tab.webview && tab.url && tab.url.includes(domain)) {
    applyBoostToWebview(tab.webview, tab.url);
  }
}

// ── Privacy Report Page (Safari-style) ────────────────────
let _privacyActivity = [];

function renderPrivacyPage() {
  // Update stats from security module via IPC
  if (window.orbit && window.orbit.perf && window.orbit.perf.stats) {
    window.orbit.perf.stats().then(function(stats) {
      var blocked = document.getElementById('privacyBlocked');
      if (blocked && stats) blocked.textContent = stats.adBlockStats ? stats.adBlockStats.blocked || 0 : 0;
    }).catch(function() {});
  }
  // Check shields config
  try {
    var shields = JSON.parse(localStorage.getItem('orbit-shields') || '{}');
    var toggleAdBlock = document.getElementById('toggleAdBlock');
    var toggleTrackerBlock = document.getElementById('toggleTrackerBlock');
    var toggleFingerprint = document.getElementById('toggleFingerprint');
    var toggleHttps = document.getElementById('toggleHttps');
    var toggleDnt = document.getElementById('toggleDnt');
    if (toggleAdBlock) toggleAdBlock.classList.toggle('on', shields.adBlocking !== false);
    if (toggleTrackerBlock) toggleTrackerBlock.classList.toggle('on', shields.trackerBlocking !== false);
    if (toggleFingerprint) toggleFingerprint.classList.toggle('on', shields.fingerprintProtection !== false);
    if (toggleHttps) toggleHttps.classList.toggle('on', shields.httpsUpgrade !== false);
    if (toggleDnt) toggleDnt.classList.toggle('on', shields.doNotTrack !== false);
  } catch (e) {}
  // Render activity
  var activityEl = document.getElementById('privacyActivity');
  if (activityEl) {
    if (_privacyActivity.length === 0) {
      activityEl.innerHTML = '<div class="empty-state">No tracker activity yet. Browsing will populate this list.</div>';
    } else {
      var html = '';
      _privacyActivity.slice(-20).reverse().forEach(function(item) {
        html += '<div class="privacy-activity-item">';
        html += '<div class="privacy-activity-dot ' + (item.blocked ? 'blocked' : 'allowed') + '"></div>';
        html += '<div class="privacy-activity-text">' + escapeHtml(item.url) + '</div>';
        html += '<div class="privacy-activity-time">' + item.type + '</div>';
        html += '</div>';
      });
      activityEl.innerHTML = html;
    }
  }
  // Wire shield toggles
  document.querySelectorAll('#shieldToggles .toggle').forEach(function(btn) {
    btn.onclick = function() {
      btn.classList.toggle('on');
      var shield = btn.dataset.shield;
      var shields = JSON.parse(localStorage.getItem('orbit-shields') || '{}');
      shields[shield] = btn.classList.contains('on');
      localStorage.setItem('orbit-shields', JSON.stringify(shields));
      showToast('ok', 'Shield Updated', shield + ' ' + (shields[shield] ? 'enabled' : 'disabled'));
    };
  });
}

function trackPrivacyEvent(url, type, blocked) {
  _privacyActivity.push({ url: url, type: type, blocked: blocked, time: Date.now() });
  if (_privacyActivity.length > 100) _privacyActivity.shift();
}

function renderHistoryPage() {
  const host = document.getElementById("historyPage");
  if (!host) return;
  let h = getHistory();
  const sheet = host.querySelector(".sheet");
  if (!sheet) return;
  const q = ((document.getElementById("histSearch") || {}).value || "").toLowerCase().trim();
  const dayLabel = (ts) => {
    const d = new Date(ts); const today = new Date();
    const sameDay = (a, b) => a.toDateString() === b.toDateString();
    if (sameDay(d, today)) return "Today";
    const yest = new Date(today); yest.setDate(today.getDate() - 1);
    if (sameDay(d, yest)) return "Yesterday";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  };
  const timeLabel = (ts) => new Date(ts).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  let html = '<div class="sheet"><h1>History</h1><p class="sheet-lede">Real visits from this device — recorded as you browse.</p>';
  html += '<input type="text" class="chat-search" id="histSearch" placeholder="Search history…" value="' + escapeHtml(q) + '" />';
  if (!h.length) {
    html += '<div class="group"><div class="empty-page">No history yet. Browse somewhere and it will appear here.</div></div>';
  } else {
    const filtered = q ? h.filter((e) => (e.title + " " + e.url).toLowerCase().indexOf(q) >= 0) : h;
    if (!filtered.length) {
      html += '<div class="group"><div class="empty-page">No entries match \u201c' + escapeHtml(q) + '\u201d</div></div>';
      html += '</div>';
      sheet.outerHTML = html;
      wireHistSearch();
      return;
    }
    h = filtered;
    let lastDay = "";
    h.forEach((e, i) => {
      const day = dayLabel(e.ts);
      if (day !== lastDay) { html += '<div class="group"><h2>' + day + '</h2>'; lastDay = day; }
      const fav = "<svg width='12' height='12' viewBox='0 0 12 12' fill='none'><circle cx='6' cy='6' r='4.5' stroke='currentColor'/></svg>";
      html += '<div class="row hist-row" data-url="' + escapeHtml(e.url) + '"><div class="hist-fav">' + fav + '</div><div class="hist-body"><div class="name">' + escapeHtml(e.title) + '</div><div class="sub">' + escapeHtml(e.url) + '</div></div><span class="meta">' + timeLabel(e.ts) + '</span><button class="hist-remove" data-remove="' + i + '" title="Remove">\u00d7</button></div>';
    });
    html += '</div>';
  }
  html += '<div class="hist-actions"><button class="chip-btn" id="histClear">Clear history</button></div></div>';
  sheet.outerHTML = html;
  function wireHistSearch() {
    const inp = document.getElementById("histSearch");
    if (inp) inp.addEventListener("input", () => renderHistoryPage());
  }
  wireHistSearch();
  const clearBtn = document.getElementById("histClear");
  if (clearBtn) clearBtn.addEventListener("click", () => {
    localStorage.removeItem(HISTORY_KEY);
    showToast("ok", "History Cleared", "All browsing history removed");
    renderHistoryPage();
  });
  host.querySelectorAll(".hist-remove").forEach((b) => {
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      const h2 = getHistory(); h2.splice(parseInt(b.dataset.remove, 10), 1);
      try { localStorage.setItem(HISTORY_KEY, JSON.stringify(h2)); } catch (err) {}
      renderHistoryPage();
    });
  });
  host.querySelectorAll(".hist-row").forEach((r) => {
    r.addEventListener("click", () => navigateTo(r.dataset.url));
  });
}
function renderBookmarksPage() {
  const host = document.getElementById("bookmarksPage");
  if (!host) return;
  const sheet = host.querySelector(".sheet");
  if (!sheet) return;
  let html = '<div class="sheet"><h1>Bookmarks</h1><p class="sheet-lede">Saved from the \u2605 star in the address bar.</p>';
  if (!bookmarks.length) {
    html += '<div class="group"><div class="empty-page">No bookmarks yet. Press the star in the address bar to save a page.</div></div>';
  } else {
    html += '<div class="group">';
    bookmarks.forEach((b, i) => {
      html += '<div class="row hist-row" data-url="' + escapeHtml(b.url) + '"><div class="hist-fav">\u2605</div><div class="hist-body"><div class="name">' + escapeHtml(b.title || b.url) + '</div><div class="sub">' + escapeHtml(b.url) + '</div></div><button class="hist-remove" data-remove="' + i + '" title="Remove">\u00d7</button></div>';
    });
    html += '</div><div class="hist-actions"><button class="chip-btn" id="bmOpenAll">Open all</button></div>';
  }
  html += '</div>';
  sheet.outerHTML = html;
  const openAll = document.getElementById("bmOpenAll");
  if (openAll) openAll.addEventListener("click", () => {
    bookmarks.forEach((b) => createTab(b.url));
    showToast("ok", "Bookmarks Opened", bookmarks.length + " tabs opened");
  });
  host.querySelectorAll(".hist-remove").forEach((b) => {
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      bookmarks.splice(parseInt(b.dataset.remove, 10), 1);
      localStorage.setItem("orbit-bookmarks", JSON.stringify(bookmarks));
      renderBookmarkBar(); renderBookmarksPage();
    });
  });
  host.querySelectorAll(".hist-row").forEach((r) => {
    r.addEventListener("click", () => navigateTo(r.dataset.url));
  });
}
