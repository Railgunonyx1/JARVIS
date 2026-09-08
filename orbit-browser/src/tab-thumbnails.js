/**
 * JARVIS Orbit — Tab Thumbnails
 * 
 * Shows visual tab previews on hover, similar to Edge/Chrome.
 * Captures webview screenshots and displays them in a tooltip.
 */

(function() {
  'use strict';

  const PREVIEW_WIDTH = 240;
  const PREVIEW_HEIGHT = 150;
  const HOVER_DELAY = 400; // ms before showing preview
  const CACHE_MAX = 20;

  class TabThumbnails {
    constructor() {
      this.cache = new Map();
      this.hoverTimer = null;
      this.previewEl = null;
      this.currentTabId = null;
      this._enabled = true;
      this._init();
    }

    _init() {
      // Create preview container
      this.previewEl = document.createElement('div');
      this.previewEl.className = 'tab-preview';
      this.previewEl.style.cssText = `
        display: none;
        position: fixed;
        z-index: 500;
        width: ${PREVIEW_WIDTH}px;
        height: ${PREVIEW_HEIGHT}px;
        background: #111;
        border: 1px solid #333;
        border-radius: 8px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.6);
        overflow: hidden;
        pointer-events: none;
        transition: opacity 0.15s;
      `;
      document.body.appendChild(this.previewEl);

      // Listen for tab hover events
      const tabStrip = document.getElementById('tabStrip');
      if (tabStrip) {
        tabStrip.addEventListener('mouseover', this._onTabHover.bind(this));
        tabStrip.addEventListener('mouseout', this._onTabLeave.bind(this));
      }
    }

    _onTabHover(e) {
      const tabEl = e.target.closest('.tab');
      if (!tabEl) return;

      const tabId = tabEl.dataset.id;
      if (!tabId || tabId === this.currentTabId) return;

      this.currentTabId = tabId;
      clearTimeout(this.hoverTimer);

      this.hoverTimer = setTimeout(() => {
        this._showPreview(tabId, tabEl);
      }, HOVER_DELAY);
    }

    _onTabLeave(e) {
      const tabEl = e.target.closest('.tab');
      if (!tabEl && !this.previewEl.contains(e.relatedTarget)) {
        clearTimeout(this.hoverTimer);
        this.currentTabId = null;
        this.previewEl.style.display = 'none';
      }
    }

    async _showPreview(tabId, tabEl) {
      if (!this._enabled) return;

      // Get cached screenshot or capture new one
      let screenshot = this.cache.get(tabId);
      if (!screenshot) {
        screenshot = await this._captureTab(tabId);
        if (screenshot) {
          this.cache.set(tabId, screenshot);
          // Evict old entries
          if (this.cache.size > CACHE_MAX) {
            const firstKey = this.cache.keys().next().value;
            this.cache.delete(firstKey);
          }
        }
      }

      if (!screenshot) return;

      // Position preview below the tab
      const rect = tabEl.getBoundingClientRect();
      const previewX = Math.max(8, Math.min(rect.left, window.innerWidth - PREVIEW_WIDTH - 8));
      const previewY = rect.bottom + 8;

      this.previewEl.innerHTML = `
        <img src="${screenshot}" style="width:100%;height:100%;object-fit:cover" />
      `;
      this.previewEl.style.display = 'block';
      this.previewEl.style.left = previewX + 'px';
      this.previewEl.style.top = previewY + 'px';
    }

    async _captureTab(tabId) {
      try {
        // Access the tab's webview through the renderer
        const tabs = window._orbitTabs;
        if (!tabs) return null;

        const tab = tabs.get(tabId);
        if (!tab || !tab.webview) return null;

        // Check if webview is ready
        if (tab.webview.classList.contains('hidden')) return null;

        const image = await tab.webview.capturePage();
        return image.toDataURL('image/jpeg', 0.6);
      } catch (error) {
        // Silently fail - thumbnails are nice-to-have
        return null;
      }
    }

    /**
     * Invalidate cache for a tab (call after navigation)
     */
    invalidate(tabId) {
      this.cache.delete(tabId);
    }

    /**
     * Clear all cached thumbnails
     */
    clearCache() {
      this.cache.clear();
    }

    /**
     * Enable/disable thumbnails
     */
    setEnabled(enabled) {
      this._enabled = enabled;
      if (!enabled) {
        this.previewEl.style.display = 'none';
      }
    }
  }

  // ── Expose to window ──────────────────────────────────────────
  window.tabThumbnails = new TabThumbnails();

  // Bridge: expose tabs map for thumbnail capture
  if (typeof window._orbitTabs === 'undefined') {
    // Will be set by renderer.js
    Object.defineProperty(window, '_orbitTabs', {
      get() { return window._tabsMap || null; },
      set(v) { window._tabsMap = v; },
    });
  }

  console.log('[THUMBS] Tab Thumbnails loaded — hover over tabs for previews');

})();
