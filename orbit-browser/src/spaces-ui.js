/**
 * JARVIS Orbit — Spaces UI
 *
 * Real workspace isolation: every space maps to its own persistent
 * session partition (cookies/storage), patched into webview creation
 * via window.__orbitPartition. On switch, all tab webviews are rebuilt
 * against the new partition so each space is cookie-isolated.
 *
 * Surface: window.spacesUi (auto-instantiated).
 */

class SpacesUi {
  constructor() {
    this.partition = "persist:orbit";
    this.button = null;
    this.popup = null;
    window.__orbitPartition = this.partition;
    this.bind();
    if (window.orbit?.on?.spaceChanged) {
      window.orbit.on.spaceChanged((payload) => this.onSpaceChanged(payload));
    }
  }

  bind() {
    const bar = document.getElementById("toolbar");
    if (!bar) return;
    const btn = document.createElement("button");
    btn.className = "nav-btn spaces-btn";
    btn.title = "Spaces — separate cookies & storage per space";
    btn.textContent = "◧";
    btn.style.fontSize = "14px";
    btn.addEventListener("click", () => this.toggle());
    bar.appendChild(btn);
    this.button = btn;
  }

  toggle() {
    if (this.popup && document.body.contains(this.popup)) {
      this.close();
      return;
    }
    const status = window.orbit?.system?.spaces?.list;
    if (!status) return;
    status().then((s) => this.render(s)).catch(() => {});
  }

  render(status) {
    this.close();
    const pop = document.createElement("div");
    pop.className = "spaces-popup";
    pop.style.cssText =
      "position:fixed;top:44px;left:8px;z-index:2000;background:var(--bg,#fff);" +
      "border:1px solid var(--border,#ddd);border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.18);" +
      "min-width:200px;padding:6px;font-size:13px;";
    const title = document.createElement("div");
    title.textContent = "Spaces";
    title.style.cssText = "font-weight:600;padding:4px 8px;opacity:.7;font-size:11px;letter-spacing:.08em;text-transform:uppercase;";
    pop.appendChild(title);
    const spaces = (status && status.spaces) || [];
    for (const sp of spaces) {
      const row = document.createElement("button");
      row.style.cssText =
        "display:flex;align-items:center;gap:8px;width:100%;text-align:left;padding:6px 8px;" +
        "border:none;background:transparent;border-radius:6px;cursor:pointer;color:var(--text,#222);";
      row.innerHTML =
        `<span style="width:14px;text-align:center;">${sp.icon || ""}</span>` +
        `<span style="flex:1;">${sp.name}</span>` +
        (sp.isActive ? '<span style="opacity:.6">●</span>' : "");
      row.onmouseover = () => { row.style.background = "var(--hover,#f0f0f0)"; };
      row.onmouseout = () => { row.style.background = "transparent"; };
      row.addEventListener("click", () => this.switchTo(sp.id));
      pop.appendChild(row);
    }
    document.body.appendChild(pop);
    this.popup = pop;
  }

  close() {
    if (this.popup && document.body.contains(this.popup)) document.body.removeChild(this.popup);
    this.popup = null;
  }

  async switchTo(id) {
    this.close();
    try {
      await window.orbit.spaces.switch(id);
    } catch (e) {
      console.error("[Spaces] switch failed:", e);
    }
  }

  onSpaceChanged(payload) {
    if (!payload || !payload.partition || !payload.space) return;
    window.__orbitPartition = payload.partition;
    this.partition = payload.partition;
    this.rebuildTabs(payload.space);
  }

  rebuildTabs(spaceId) {
    const snapshot = [];
    for (const [id, tab] of tabs) {
      let url = (tab && tab.url) || "";
      try {
        if (tab.webview && typeof tab.webview.getURL === "function" && tab.webview.getURL()) {
          url = tab.webview.getURL();
        }
      } catch (_) {}
      snapshot.push({ id, url });
    }
    if (!snapshot.length) return;
    for (const s of snapshot) {
      const tab = tabs.get(s.id);
      if (!tab) continue;
      try {
        if (tab.webview && typeof tab.webview.remove === "function") {
          tab.webview.remove();
        }
      } catch (_) {}
      const wv = createWebview();
      tab.webview = wv;
      attachWebviewEvents(wv);
      const url = s.url;
      if (url && !/^orbit:\/\//i.test(url)) {
        wv.addEventListener("did-attach", function onAttach() {
          wv.removeEventListener("did-attach", onAttach);
          try { wv.loadURL(url); } catch (_) {}
        });
      }
    }
    renderTabs();
    const cur = tabs.get(activeTabId);
    if (cur && cur.webview) cur.webview.classList.remove("hidden");
    console.log(`[Spaces] switched to "${spaceId}" — ${snapshot.length} tab(s) rebuilt on partition ${this.partition}`);
  }
}

window.SpacesUi = SpacesUi;
window.spacesUi = new SpacesUi();