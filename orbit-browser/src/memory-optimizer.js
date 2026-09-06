/**
 * JARVIS Orbit — Memory Optimizer
 *
 * Implements memory optimization techniques from the lightest browsers:
 * - Tab discarding (Chrome Memory Saver)
 * - Memory monitoring per tab
 * - Lazy loading for images/iframes
 * - Virtual scrolling for large lists
 * - Debounce/throttle utilities
 *
 * Target: 50% memory reduction at 50 tabs
 */

// ── Configuration ─────────────────────────────────────────────────
const MEMORY_CONFIG = {
  // Tab discarding (Chrome Memory Saver style)
  tabDiscarding: {
    enabled: true,
    memoryThresholdMB: 1024, // Discard when total exceeds 1GB
    inactiveTimeoutMs: 5 * 60 * 1000, // 5 minutes
    maxDiscardedTabs: 20,
    preserveTabState: true, // Keep scroll position, form data
  },

  // Memory monitoring
  monitoring: {
    enabled: true,
    intervalMs: 30000, // Check every 30 seconds
    warningThresholdMB: 512,
    criticalThresholdMB: 1024,
  },

  // Lazy loading
  lazyLoading: {
    images: true,
    iframes: true,
    scripts: true,
    threshold: 100, // pixels before loading
  },

  // Virtual scrolling
  virtualScrolling: {
    enabled: true,
    itemHeight: 40, // pixels per item
    bufferItems: 10, // extra items above/below viewport
  },
};

// ── Utility Functions ─────────────────────────────────────────────
/**
 * Debounce function calls
 */
function debounce(fn, delay = 100) {
  let timeoutId;
  return function (...args) {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn.apply(this, args), delay);
  };
}

/**
 * Throttle function calls
 */
function throttle(fn, limit = 16) {
  let inThrottle = false;
  return function (...args) {
    if (!inThrottle) {
      fn.apply(this, args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
}

/**
 * Format bytes to human readable
 */
function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

// ── Tab State Manager ─────────────────────────────────────────────
class TabStateManager {
  constructor() {
    this.tabs = new Map();
    this.discardedTabs = new Map();
  }

  /**
   * Register a tab
   */
  register(tabId, webview) {
    this.tabs.set(tabId, {
      id: tabId,
      webview,
      lastActive: Date.now(),
      memoryUsage: 0,
      isDiscarded: false,
      scrollPosition: 0,
      formData: null,
      url: webview?.getURL() || "",
    });
  }

  /**
   * Unregister a tab
   */
  unregister(tabId) {
    this.tabs.delete(tabId);
    this.discardedTabs.delete(tabId);
  }

  /**
   * Mark tab as active
   */
  activate(tabId) {
    const tab = this.tabs.get(tabId);
    if (tab) {
      tab.lastActive = Date.now();
      tab.isDiscarded = false;
    }
  }

  /**
   * Get inactive tabs (candidates for discarding)
   */
  getInactiveTabs(timeoutMs = MEMORY_CONFIG.tabDiscarding.inactiveTimeoutMs) {
    const now = Date.now();
    const inactive = [];

    for (const [tabId, tab] of this.tabs) {
      if (!tab.isDiscarded && (now - tab.lastActive) > timeoutMs) {
        inactive.push(tabId);
      }
    }

    return inactive;
  }

  /**
   * Save tab state before discarding
   */
  saveState(tabId) {
    const tab = this.tabs.get(tabId);
    if (!tab || !tab.webview) return;

    try {
      // Save scroll position
      tab.scrollPosition = tab.webview.executeJavaScript("window.scrollY") || 0;

      // Save form data (simplified - in production, serialize all form fields)
      tab.formData = null;

      // Save URL
      tab.url = tab.webview.getURL();
    } catch (e) {
      console.error(`[MEMORY] Failed to save state for tab ${tabId}:`, e);
    }
  }

  /**
   * Restore tab state after restoring
   */
  restoreState(tabId) {
    const tab = this.tabs.get(tabId);
    if (!tab || !tab.webview) return;

    try {
      // Restore scroll position
      if (tab.scrollPosition > 0) {
        tab.webview.executeJavaScript(`window.scrollTo(0, ${tab.scrollPosition})`);
      }

      // Restore form data (simplified)
      // In production, iterate through saved form fields
    } catch (e) {
      console.error(`[MEMORY] Failed to restore state for tab ${tabId}:`, e);
    }
  }

  /**
   * Discard a tab (suspend renderer)
   */
  discard(tabId) {
    const tab = this.tabs.get(tabId);
    if (!tab || tab.isDiscarded) return false;

    // Save state first
    this.saveState(tabId);

    // Suspend the webview
    if (tab.webview) {
      try {
        // Execute JavaScript to suspend the page
        tab.webview.executeJavaScript(`
          // Pause animations
          document.querySelectorAll('*').forEach(el => {
            el.style.animationPlayState = 'paused';
          });

          // Pause videos
          document.querySelectorAll('video').forEach(v => v.pause());

          // Clear non-essential timers
          // (This is a simplified version - production would be more thorough)
        `);
      } catch (e) {
        // Tab might be crashed or unavailable
      }
    }

    tab.isDiscarded = true;
    this.discardedTabs.set(tabId, {
      url: tab.url,
      savedAt: Date.now(),
    });

    return true;
  }

  /**
   * Restore a discarded tab
   */
  restore(tabId) {
    const tab = this.tabs.get(tabId);
    if (!tab || !tab.isDiscarded) return false;

    // Restore the webview
    if (tab.webview && tab.url) {
      try {
        tab.webview.loadURL(tab.url);
      } catch (e) {
        console.error(`[MEMORY] Failed to restore tab ${tabId}:`, e);
      }
    }

    tab.isDiscarded = false;
    this.discardedTabs.delete(tabId);

    // Restore state
    this.restoreState(tabId);

    return true;
  }

  /**
   * Get memory usage for all tabs
   */
  getMemoryUsage() {
    let total = 0;
    const perTab = {};

    for (const [tabId, tab] of this.tabs) {
      perTab[tabId] = tab.memoryUsage;
      total += tab.memoryUsage;
    }

    return { total, perTab };
  }
}

// ── Memory Monitor ────────────────────────────────────────────────
class MemoryMonitor {
  constructor() {
    this.config = MEMORY_CONFIG.monitoring;
    this.history = [];
    this.interval = null;
    this.onWarning = null;
    this.onCritical = null;
  }

  /**
   * Start monitoring
   */
  start(tabStateManager) {
    if (this.interval) return;

    this.interval = setInterval(() => {
      this.check(tabStateManager);
    }, this.config.intervalMs);
  }

  /**
   * Stop monitoring
   */
  stop() {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
  }

  /**
   * Check memory usage
   */
  check(tabStateManager) {
    const usage = tabStateManager.getMemoryUsage();
    const entry = {
      timestamp: Date.now(),
      total: usage.total,
      perTab: { ...usage.perTab },
    };

    this.history.push(entry);

    // Keep only last 100 entries
    if (this.history.length > 100) {
      this.history.shift();
    }

    // Check thresholds
    if (usage.total > this.config.criticalThresholdMB) {
      this.onCritical?.(usage);
    } else if (usage.total > this.config.warningThresholdMB) {
      this.onWarning?.(usage);
    }

    return entry;
  }

  /**
   * Get memory trend
   */
  getTrend() {
    if (this.history.length < 2) return "stable";

    const recent = this.history.slice(-10);
    const avg = recent.reduce((sum, e) => sum + e.total, 0) / recent.length;
    const last = recent[recent.length - 1].total;

    if (last > avg * 1.2) return "increasing";
    if (last < avg * 0.8) return "decreasing";
    return "stable";
  }
}

// ── Lazy Loader ───────────────────────────────────────────────────
class LazyLoader {
  constructor() {
    this.config = MEMORY_CONFIG.lazyLoading;
  }

  /**
   * Inject lazy loading into a webview
   */
  inject(webview) {
    if (!webview) return;

    const script = `
      (function() {
        // Lazy load images
        if (${this.config.images}) {
          document.querySelectorAll('img:not([loading])').forEach(img => {
            img.loading = 'lazy';
          });
        }

        // Lazy load iframes
        if (${this.config.iframes}) {
          document.querySelectorAll('iframe:not([loading])').forEach(iframe => {
            iframe.loading = 'lazy';
          });
        }

        // Add intersection observer for dynamic content
        const observer = new IntersectionObserver((entries) => {
          entries.forEach(entry => {
            if (entry.isIntersecting) {
              const el = entry.target;
              if (el.dataset.src) {
                el.src = el.dataset.src;
                el.removeAttribute('data-src');
              }
              if (el.dataset.srcset) {
                el.srcset = el.dataset.srcset;
                el.removeAttribute('data-srcset');
              }
              observer.unobserve(el);
            }
          });
        }, {
          rootMargin: '${this.config.threshold}px'
        });

        // Observe lazy elements
        document.querySelectorAll('[data-src], [data-srcset]').forEach(el => {
          observer.observe(el);
        });
      })();
    `;

    try {
      webview.executeJavaScript(script);
    } catch (e) {
      // Tab might be crashed
    }
  }
}

// ── Virtual Scroller ──────────────────────────────────────────────
class VirtualScroller {
  constructor(container, options = {}) {
    this.container = container;
    this.config = { ...MEMORY_CONFIG.virtualScrolling, ...options };
    this.items = [];
    this.visibleItems = [];
    this.startIndex = 0;
    this.endIndex = 0;

    this.init();
  }

  init() {
    this.container.style.overflow = 'auto';
    this.container.addEventListener('scroll', throttle(() => this.update(), 16));
  }

  /**
   * Set items to display
   */
  setItems(items) {
    this.items = items;
    this.container.style.height = `${items.length * this.config.itemHeight}px`;
    this.update();
  }

  /**
   * Update visible items based on scroll position
   */
  update() {
    const scrollTop = this.container.scrollTop;
    const viewportHeight = this.container.clientHeight;

    this.startIndex = Math.max(0, Math.floor(scrollTop / this.config.itemHeight) - this.config.bufferItems);
    this.endIndex = Math.min(
      this.items.length,
      Math.ceil((scrollTop + viewportHeight) / this.config.itemHeight) + this.config.bufferItems
    );

    this.visibleItems = this.items.slice(this.startIndex, this.endIndex);
    this.render();
  }

  /**
   * Render visible items
   */
  render() {
    // Override this method to render items
    // This is a base class - implement your own render logic
  }
}

// ── Main Memory Optimizer ─────────────────────────────────────────
class MemoryOptimizer {
  constructor() {
    this.config = MEMORY_CONFIG;
    this.tabStateManager = new TabStateManager();
    this.memoryMonitor = new MemoryMonitor();
    this.lazyLoader = new LazyLoader();
    this.optimizations = {
      discardedTabs: 0,
      memorySavedMB: 0,
      lazyLoadedResources: 0,
    };
  }

  /**
   * Initialize the optimizer
   */
  init() {
    this.memoryMonitor.start(this.tabStateManager);

    // Set up warning handlers
    this.memoryMonitor.onWarning = (usage) => {
      console.warn(`[MEMORY] Warning: ${formatBytes(usage.total * 1024 * 1024)} used`);
      this.suggestDiscard();
    };

    this.memoryMonitor.onCritical = (usage) => {
      console.error(`[MEMORY] Critical: ${formatBytes(usage.total * 1024 * 1024)} used`);
      this.forceDiscard();
    };

    console.log("[MEMORY] Optimizer initialized");
  }

  /**
   * Register a tab
   */
  registerTab(tabId, webview) {
    this.tabStateManager.register(tabId, webview);
  }

  /**
   * Unregister a tab
   */
  unregisterTab(tabId) {
    this.tabStateManager.unregister(tabId);
  }

  /**
   * Activate a tab
   */
  activateTab(tabId) {
    this.tabStateManager.activate(tabId);

    // Restore if discarded
    const tab = this.tabStateManager.tabs.get(tabId);
    if (tab?.isDiscarded) {
      this.tabStateManager.restore(tabId);
    }
  }

  /**
   * Suggest discarding tabs
   */
  suggestDiscard() {
    const inactive = this.tabStateManager.getInactiveTabs();
    if (inactive.length > 0) {
      console.log(`[MEMORY] Suggesting discard of ${inactive.length} inactive tabs`);
    }
  }

  /**
   * Force discard tabs
   */
  forceDiscard() {
    const inactive = this.tabStateManager.getInactiveTabs();
    const toDiscard = inactive.slice(0, 5); // Discard up to 5 tabs

    toDiscard.forEach(tabId => {
      if (this.tabStateManager.discard(tabId)) {
        this.optimizations.discardedTabs++;
        console.log(`[MEMORY] Discarded tab ${tabId}`);
      }
    });
  }

  /**
   * Inject lazy loading into a webview
   */
  injectLazyLoading(webview) {
    this.lazyLoader.inject(webview);
    this.optimizations.lazyLoadedResources++;
  }

  /**
   * Get optimization stats
   */
  getStats() {
    const memory = this.tabStateManager.getMemoryUsage();
    return {
      totalMemoryMB: Math.round(memory.total),
      tabCount: this.tabStateManager.tabs.size,
      discardedCount: this.tabStateManager.discardedTabs.size,
      memoryTrend: this.memoryMonitor.getTrend(),
      optimizations: { ...this.optimizations },
    };
  }

  /**
   * Get recommendations
   */
  getRecommendations() {
    const stats = this.getStats();
    const recommendations = [];

    if (stats.totalMemoryMB > this.config.monitoring.warningThresholdMB) {
      recommendations.push({
        type: "memory",
        message: `Memory usage is high (${stats.totalMemoryMB}MB). Consider closing tabs.`,
        impact: "high",
      });
    }

    if (stats.tabCount > 20) {
      recommendations.push({
        type: "tabs",
        message: `You have ${stats.tabCount} tabs open. Consider using Spaces to organize.`,
        impact: "medium",
      });
    }

    if (stats.memoryTrend === "increasing") {
      recommendations.push({
        type: "trend",
        message: "Memory usage is increasing. Check for memory leaks.",
        impact: "medium",
      });
    }

    return recommendations;
  }

  /**
   * Cleanup
   */
  cleanup() {
    this.memoryMonitor.stop();
  }
}

// ── Export ─────────────────────────────────────────────────────────
module.exports = {
  MemoryOptimizer,
  TabStateManager,
  MemoryMonitor,
  LazyLoader,
  VirtualScroller,
  debounce,
  throttle,
  formatBytes,
  MEMORY_CONFIG,
};
