/**
 * JARVIS Orbit — Tab Tiling
 *
 * Side-by-side browsing: moves the active + MRU webviews into a grid
 * overlay on the content area. Webviews are MOVED, not recreated, so
 * each guest keeps its live page, scroll, and playback state. Exiting
 * returns every webview to the normal single-tab layout.
 *
 * Hook: renderer.js activateTab calls window.tilingUi.applyLayout()
 * when the module is present (single owner of per-activate visibility).
 *
 * Keys: Ctrl+Alt+T toggle | Esc exit.
 * Surface: window.tilingUi.
 */

(function () {
  const TILE_CSS =
    "#_orbitTileStage{position:absolute;inset:0;z-index:60;display:grid;" +
    "gap:4px;padding:4px;background:var(--jb-page,#161618);}" +
    "#_orbitTileStage .orbit-tile{position:relative;border:1px solid var(--jb-border,#2e2e32);" +
    "border-radius:8px;overflow:hidden;background:#101012;min-width:0;min-height:0;}" +
    "#_orbitTileStage .orbit-tile.active{border-color:var(--jb-accent,#4A90D9);" +
    "box-shadow:0 0 0 1px var(--jb-accent,#4A90D9);}" +
    "#_orbitTileStage .orbit-tile webview{position:absolute;inset:0;width:100%;height:100%;border:none;}" +
    "#_orbitTileStage .tile-head{position:absolute;top:0;left:0;right:0;z-index:3;display:flex;" +
    "align-items:center;gap:8px;padding:2px 8px;font-size:11px;background:rgba(16,16,18,.88);" +
    "backdrop-filter:blur(4px);color:var(--jb-ghost,#9aa);cursor:pointer;-webkit-user-select:none;}" +
    "#_orbitTileStage .tile-head:hover{color:var(--jb-paper,#eee);}" +
    "#_orbitTileStage .tile-title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}" +
    "#_orbitTileStage .tile-close{font-size:13px;opacity:.75;padding:0 4px;}" +
    "#_orbitTileStage .tile-close:hover{opacity:1;color:#e0655a;}" +
    "#_orbitTileStage .tile-ghost{position:absolute;inset:0;z-index:2;display:flex;align-items:center;" +
    "justify-content:center;background:rgba(16,16,18,.72);color:var(--jb-ghost,#9aa);font-size:12px;}";

  class TilingUi {
    constructor() {
      this.active = false;
      this.stage = null;
      this.staged = [];
      this._injectCss();
      this._bindKeys();
      window.addEventListener("beforeunload", () => this.exit(true));
    }

    targetTabs() {
      const fn = window._orbitTilingTargets;
      if (typeof fn !== "function") return [];
      return fn();
    }

    enter() {
      const targets = this.targetTabs();
      if (targets.length < 2 || this.active) return;
      tileMode = true;

      this.stage = document.createElement("div");
      this.stage.id = "_orbitTileStage";

      this.staged = [];
      for (const tab of targets) {
        if (!tab.webview) continue;

        if (tab.hibernated) {
          try {
            if (typeof wakeTab === "function") wakeTab(tab.id);
          } catch (_) {}
        }
        if (typeof loadURLSafely === "function") {
          try {
            const u = tab.webview.getURL ? tab.webview.getURL() : "";
            if (!u || u === "about:blank") loadURLSafely(tab.webview, tab.url);
          } catch (_) {}
        }

        const tile = document.createElement("div");
        tile.className = "orbit-tile" + (tab.id === activeTabId ? " active" : "");
        tile.dataset.tileId = tab.id;

        const head = document.createElement("div");
        head.className = "tile-head";
        head.innerHTML =
          `<span class="tile-title">${(tab.title || tab.url || "").replace(/&/g, "&amp;").replace(/</g, "&lt;")}</span>` +
          '<span class="tile-close" title="Close tab">✕</span>';
        head.addEventListener("click", () => this.activate(tab.id));
        head.querySelector(".tile-close").addEventListener("click", (e) => {
          e.stopPropagation();
          if (typeof closeTab === "function") closeTab(tab.id);
        });

        tile.appendChild(head);
        const ghost = document.createElement("div");
        ghost.className = "tile-ghost";
        ghost.textContent = tab.url || "";
        tile.appendChild(ghost);

        tab.webview.classList.remove("hidden");
        tile.appendChild(tab.webview);
        this.stage.appendChild(tile);
        this.staged.push({ id: tab.id, wv: tab.webview, tile, ghost });

        if (wc) {
          window.orbit?.tabs?.attach?.(tab.id, tab.url, tab.webview.getWebContentsId?.() || 0);
        }
      }
      if (!this.staged.length) {
        this.stage.remove();
        this.stage = null;
        return;
      }

      const area = contentArea || document.getElementById("contentArea");
      if (area) area.appendChild(this.stage);

      const n = this.staged.length;
      this.stage.style.gridTemplateColumns =
        n === 2 ? "1fr 1fr" : n === 3 ? "1fr 1fr 1fr" : "1fr 1fr";
      this.stage.style.gridTemplateRows = n > 2 ? "1fr 1fr" : "1fr";
      this.active = true;
      showToast("info", "Tiling", `${n} tabs side-by-side`);
    }

    activate(id) {
      if (typeof activateTab === "function") activateTab(id);
      if (this.stage) {
        this.stage.querySelectorAll(".orbit-tile").forEach((t) => {
          t.classList.toggle("active", t.dataset.tileId === String(id));
        });
      }
    }

    exit(silent) {
      if (!this.active || !this.stage) return;
      const n = this.staged.length;
      for (const s of this.staged) {
        const tab = tabs && tabs.get(s.id);
        try {
          if (s.wv && document.body.contains(s.wv) && tab) {
            const area = contentArea || document.getElementById("contentArea");
            if (area && !area.contains(s.wv)) area.appendChild(s.wv);
            s.wv.classList.toggle("hidden", tab.id !== activeTabId);
          }
        } catch (_) {}
      }
      try { this.stage.remove(); } catch (_) {}
      this.stage = null;
      this.staged = [];
      this.active = false;
      tileMode = false;
      if (typeof activateTab === "function") activateTab(activeTabId);
      if (!silent) showToast("info", "Tiling", "Exited tile view");
    }

    applyLayout() {
      if (this.active) return;
      for (const t of tabs.values()) {
        if (t.webview) t.webview.classList.toggle("hidden", t.id !== activeTabId);
      }
    }

    toggle() {
      if (this.active) this.exit();
      else this.enter();
    }

    _injectCss() {
      if (document.getElementById("_orbitTileCss")) return;
      const st = document.createElement("style");
      st.id = "_orbitTileCss";
      st.textContent = TILE_CSS;
      document.head.appendChild(st);
    }

    _bindKeys() {
      document.addEventListener("keydown", (e) => {
        if (e.ctrlKey && e.altKey && (e.key === "t" || e.key === "T")) {
          e.preventDefault();
          e.stopPropagation();
          this.toggle();
        } else if (e.key === "Escape" && this.active) {
          e.preventDefault();
          e.stopPropagation();
          this.exit();
        }
      }, true);
    }
  }

  window.tilingUi = new TilingUi();
})();