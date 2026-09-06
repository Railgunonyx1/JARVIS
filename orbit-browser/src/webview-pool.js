/**
 * JARVIS Orbit — Webview Pool
 * 
 * Manages webview instances for instant tab switching:
 * - Pre-creates webviews for faster tab creation
 * - Recycles unused webviews
 * - Memory-aware pooling
 * - Tab suspension/resume
 */

class WebviewPool {
  constructor(config = {}) {
    this.config = {
      minPoolSize: config.minPoolSize || 2,
      maxPoolSize: config.maxPoolSize || 10,
      recycleAfterMs: config.recycleAfterMs || 5 * 60 * 1000, // 5 minutes
      preloadCount: config.preloadCount || 2,
      ...config,
    };
    
    this.pool = [];
    this.active = new Map(); // tabId -> webview
    this.container = null;
    this.seedElement = null;
    
    this.init();
  }

  init() {
    // Find or create container
    this.container = document.getElementById('contentArea');
    this.seedElement = document.getElementById('webview');
    
    if (this.container) {
      // Pre-create webviews
      this.prefillPool();
      
      // Start recycle timer
      this.recycleTimer = setInterval(() => {
        this.recycleUnused();
      }, 60000); // Check every minute
      
      console.log('[POOL] Webview pool initialized');
    }
  }

  // ── Pool Management ─────────────────────────────────────────────
  
  prefillPool() {
    const toCreate = Math.min(
      this.config.preloadCount,
      this.config.maxPoolSize - this.pool.length
    );
    
    for (let i = 0; i < toCreate; i++) {
      const webview = this.createWebview();
      this.pool.push(webview);
    }
    
    console.log(`[POOL] Prefilled pool with ${toCreate} webviews`);
  }

  createWebview() {
    const webview = document.createElement('webview');
    webview.className = 'webview pooled';
    
    // Copy attributes from seed element
    if (this.seedElement) {
      webview.setAttribute('partition', this.seedElement.getAttribute('partition') || 'persist:orbit');
      webview.setAttribute('preload', this.seedElement.getAttribute('preload') || '');
      webview.setAttribute('webpreferences', this.seedElement.getAttribute('webpreferences') || '');
    }
    
    // Hide pooled webviews
    webview.style.display = 'none';
    
    // Add to container
    if (this.container) {
      this.container.appendChild(webview);
    }
    
    return webview;
  }

  acquire(tabId, url = null) {
    let webview;
    
    // Try to get from pool
    if (this.pool.length > 0) {
      webview = this.pool.pop();
      console.log(`[POOL] Acquired webview from pool (remaining: ${this.pool.length})`);
    } else if (this.pool.length < this.config.maxPoolSize) {
      // Create new if under limit
      webview = this.createWebview();
      console.log('[POOL] Created new webview');
    } else {
      // Pool is full, need to recycle
      webview = this.recycleOldest();
      console.log('[POOL] Recycled oldest webview');
    }
    
    // Setup webview
    webview.className = 'webview active';
    webview.style.display = '';
    webview.dataset.tabId = tabId;
    webview.dataset.lastActive = Date.now();
    
    // Track active webview
    this.active.set(tabId, webview);
    
    // Load URL if provided
    if (url) {
      this.loadURL(webview, url);
    }
    
    return webview;
  }

  release(tabId) {
    const webview = this.active.get(tabId);
    if (!webview) return;
    
    // Clean up webview
    webview.className = 'webview pooled';
    webview.style.display = 'none';
    webview.removeAttribute('data-tab-id');
    
    // Remove from active
    this.active.delete(tabId);
    
    // Add back to pool if under limit
    if (this.pool.length < this.config.maxPoolSize) {
      this.pool.push(webview);
      console.log(`[POOL] Released webview to pool (total: ${this.pool.length})`);
    } else {
      // Remove from DOM
      webview.remove();
      console.log('[POOL] Removed excess webview');
    }
  }

  // ── URL Loading ─────────────────────────────────────────────────
  
  async loadURL(webview, url) {
    // Check page cache first
    if (window.pageCache && window.pageCache.has(url)) {
      const cached = window.pageCache.get(url);
      if (cached && cached.data) {
        // Load from cache (for internal pages)
        console.log(`[POOL] Loading from cache: ${url}`);
        return;
      }
    }
    
    // Load URL
    try {
      await webview.loadURL(url);
      webview.dataset.url = url;
      webview.dataset.lastActive = Date.now();
    } catch (error) {
      console.error('[POOL] Failed to load URL:', error);
    }
  }

  // ── Tab Suspension ──────────────────────────────────────────────
  
  suspendTab(tabId) {
    const webview = this.active.get(tabId);
    if (!webview) return false;
    
    // Store state
    const state = {
      url: webview.getURL(),
      scrollY: webview.executeJavaScript('window.scrollY').catch(() => 0),
      timestamp: Date.now(),
    };
    
    webview.dataset.suspended = 'true';
    webview.dataset.state = JSON.stringify(state);
    
    // Hide webview
    webview.style.display = 'none';
    
    console.log(`[POOL] Suspended tab: ${tabId}`);
    return true;
  }

  async resumeTab(tabId) {
    const webview = this.active.get(tabId);
    if (!webview) return false;
    
    if (webview.dataset.suspended === 'true') {
      // Restore state
      try {
        const state = JSON.parse(webview.dataset.state || '{}');
        if (state.url) {
          await webview.loadURL(state.url);
        }
        if (state.scrollY) {
          webview.executeJavaScript(`window.scrollTo(0, ${state.scrollY})`);
        }
      } catch (error) {
        console.error('[POOL] Failed to resume tab:', error);
      }
      
      delete webview.dataset.suspended;
      delete webview.dataset.state;
      
      // Show webview
      webview.style.display = '';
      
      console.log(`[POOL] Resumed tab: ${tabId}`);
    }
    
    return true;
  }

  // ── Recycling ───────────────────────────────────────────────────
  
  recycleUnused() {
    const now = Date.now();
    const toRecycle = [];
    
    // Find inactive webviews
    for (const [tabId, webview] of this.active) {
      const lastActive = parseInt(webview.dataset.lastActive || '0');
      if (now - lastActive > this.config.recycleAfterMs) {
        toRecycle.push(tabId);
      }
    }
    
    // Recycle oldest
    for (const tabId of toRecycle.slice(0, 2)) { // Max 2 per cycle
      this.suspendTab(tabId);
    }
  }

  recycleOldest() {
    let oldest = null;
    let oldestTime = Infinity;
    
    for (const [tabId, webview] of this.active) {
      const lastActive = parseInt(webview.dataset.lastActive || '0');
      if (lastActive < oldestTime) {
        oldestTime = lastActive;
        oldest = tabId;
      }
    }
    
    if (oldest) {
      const webview = this.active.get(oldest);
      this.release(oldest);
      return webview;
    }
    
    // Fallback: create new
    return this.createWebview();
  }

  // ── Statistics ──────────────────────────────────────────────────
  
  getStats() {
    return {
      poolSize: this.pool.length,
      activeCount: this.active.size,
      maxPoolSize: this.config.maxPoolSize,
      suspendedCount: Array.from(this.active.values())
        .filter(w => w.dataset.suspended === 'true').length,
    };
  }

  // ── Cleanup ─────────────────────────────────────────────────────
  
  destroy() {
    if (this.recycleTimer) {
      clearInterval(this.recycleTimer);
    }
    
    // Release all active webviews
    for (const [tabId] of this.active) {
      this.release(tabId);
    }
    
    // Remove pooled webviews
    for (const webview of this.pool) {
      webview.remove();
    }
    
    this.pool = [];
    this.active.clear();
  }
}

// Export
window.WebviewPool = WebviewPool;
window.webviewPool = null; // Initialize after DOM ready
