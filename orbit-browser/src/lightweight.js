/**
 * JARVIS Orbit — Lightweight Optimization Module
 *
 * Implements techniques from the world's lightest browsers:
 * - Min: Minimal DOM, efficient rendering, ad blocking
 * - Tauri: Memory efficiency, process optimization
 * - Firefox: Memory compression, efficient GC
 * - Edge: Sleeping tabs, efficiency mode
 *
 * Target: Make Orbit as light as Min while keeping JARVIS features
 */

// ── Configuration ─────────────────────────────────────────────────
const LIGHTWEIGHT_CONFIG = {
  // DOM Optimization
  dom: {
    maxElements: 1500, // Max DOM elements before warning
    virtualScrollThreshold: 100, // Use virtual scroll for lists > 100 items
    batchDOMUpdates: true, // Batch DOM changes
    useRequestAnimationFrame: true, // Use RAF for animations
  },

  // CSS Optimization
  css: {
    containLayout: true, // Use CSS containment
    willChangeElements: ['transform', 'opacity'], // Elements that animate
    avoidExpensiveProperties: ['box-shadow', 'filter', 'backdrop-filter'],
  },

  // JavaScript Optimization
  js: {
    debounceDelay: 100, // Default debounce delay
    throttleLimit: 16, // 60fps throttle
    maxEventListeners: 100, // Max listeners per element
    useWebWorkers: true, // Offload heavy computation
  },

  // Memory Optimization
  memory: {
    gcIntervalMs: 60000, // Force GC every 60 seconds
    maxCacheSize: 50 * 1024 * 1024, // 50MB max cache
    compressOldData: true, // Compress old cached data
  },

  // Ad/Tracker Blocking (from Min)
  blocking: {
    enabled: true,
    blockAds: true,
    blockTrackers: true,
    blockFingerprinting: true,
  },
};

// ── DOM Optimizer ─────────────────────────────────────────────────
class DOMOptimizer {
  constructor() {
    this.elementCount = 0;
    this.pendingUpdates = [];
    this.isUpdating = false;
  }

  /**
   * Count DOM elements
   */
  countElements() {
    this.elementCount = document.querySelectorAll('*').length;
    if (this.elementCount > LIGHTWEIGHT_CONFIG.dom.maxElements) {
      console.warn(`[LIGHT] DOM has ${this.elementCount} elements (max: ${LIGHTWEIGHT_CONFIG.dom.maxElements})`);
    }
    return this.elementCount;
  }

  /**
   * Batch DOM updates
   */
  batchUpdate(updateFn) {
    this.pendingUpdates.push(updateFn);

    if (!this.isUpdating) {
      this.isUpdating = true;
      requestAnimationFrame(() => {
        this.flushUpdates();
        this.isUpdating = false;
      });
    }
  }

  /**
   * Flush pending DOM updates
   */
  flushUpdates() {
    const fragment = document.createDocumentFragment();

    while (this.pendingUpdates.length > 0) {
      const update = this.pendingUpdates.shift();
      update(fragment);
    }

    // Single reflow
    document.body.appendChild(fragment);
  }

  /**
   * Create minimal element
   */
  createElement(tag, attrs = {}, text = '') {
    const el = document.createElement(tag);

    // Set attributes efficiently
    for (const [key, value] of Object.entries(attrs)) {
      if (key === 'className') {
        el.className = value;
      } else if (key === 'style' && typeof value === 'object') {
        Object.assign(el.style, value);
      } else if (key.startsWith('on')) {
        el.addEventListener(key.slice(2).toLowerCase(), value);
      } else {
        el.setAttribute(key, value);
      }
    }

    if (text) {
      el.textContent = text;
    }

    return el;
  }

  /**
   * Efficiently update text content
   */
  setText(element, text) {
    if (element.textContent !== text) {
      element.textContent = text;
    }
  }

  /**
   * Efficiently update class list
   */
  toggleClass(element, className, force) {
    element.classList.toggle(className, force);
  }

  /**
   * Remove element efficiently
   */
  removeElement(element) {
    if (element.parentNode) {
      element.parentNode.removeChild(element);
    }
  }
}

// ── CSS Optimizer ─────────────────────────────────────────────────
class CSSOptimizer {
  constructor() {
    this.optimizedElements = new WeakSet();
  }

  /**
   * Apply CSS containment to element
   */
  applyContainment(element) {
    if (this.optimizedElements.has(element)) return;

    element.style.contain = 'layout style paint';
    this.optimizedElements.add(element);
  }

  /**
   * Optimize element for animation
   */
  optimizeForAnimation(element) {
    element.style.willChange = 'transform, opacity';
    element.style.transform = 'translateZ(0)'; // Force GPU layer
  }

  /**
   * Remove animation optimization
   */
  removeAnimationOptimization(element) {
    element.style.willChange = 'auto';
    element.style.transform = '';
  }

  /**
   * Batch style changes
   */
  batchStyleChanges(element, changes) {
    // Save current state
    const computedStyle = getComputedStyle(element);
    const originalDisplay = computedStyle.display;

    // Temporarily detach from DOM for batch changes
    const parent = element.parentNode;
    if (parent) {
      parent.removeChild(element);
    }

    // Apply all changes at once
    Object.assign(element.style, changes);

    // Reattach to DOM
    if (parent) {
      parent.appendChild(element);
    }
  }
}

// ── JavaScript Optimizer ──────────────────────────────────────────
class JSOptimizer {
  constructor() {
    this.debounceTimers = new Map();
    this.throttleStates = new Map();
    this.workerPool = [];
  }

  /**
   * Debounce function
   */
  debounce(fn, delay = LIGHTWEIGHT_CONFIG.js.debounceDelay) {
    return (...args) => {
      const key = fn.toString();

      if (this.debounceTimers.has(key)) {
        clearTimeout(this.debounceTimers.get(key));
      }

      const timer = setTimeout(() => {
        fn.apply(this, args);
        this.debounceTimers.delete(key);
      }, delay);

      this.debounceTimers.set(key, timer);
    };
  }

  /**
   * Throttle function
   */
  throttle(fn, limit = LIGHTWEIGHT_CONFIG.js.throttleLimit) {
    return (...args) => {
      const key = fn.toString();
      const now = Date.now();

      if (!this.throttleStates.has(key)) {
        this.throttleStates.set(key, { lastCall: 0 });
      }

      const state = this.throttleStates.get(key);
      if (now - state.lastCall >= limit) {
        state.lastCall = now;
        fn.apply(this, args);
      }
    };
  }

  /**
   * Use requestAnimationFrame for animations
   */
  animate(fn) {
    return requestAnimationFrame(fn);
  }

  /**
   * Offload heavy computation to Web Worker
   */
  offloadToWorker(fn, data) {
    return new Promise((resolve, reject) => {
      const workerCode = `
        self.onmessage = function(e) {
          const result = (${fn.toString()})(e.data);
          self.postMessage(result);
        };
      `;

      const blob = new Blob([workerCode], { type: 'application/javascript' });
      const worker = new Worker(URL.createObjectURL(blob));

      worker.onmessage = (e) => {
        resolve(e.data);
        worker.terminate();
      };

      worker.onerror = (e) => {
        reject(e);
        worker.terminate();
      };

      worker.postMessage(data);
    });
  }
}

// ── Ad/Tracker Blocker (from Min) ─────────────────────────────────
class AdBlocker {
  constructor() {
    this.blockedDomains = new Set();
    this.blockedPatterns = [];
    this.stats = { blocked: 0, allowed: 0 };
  }

  /**
   * Initialize with blocked domains
   */
  init() {
    // Common ad/tracker domains
    const domains = [
      'google-analytics.com',
      'googletagmanager.com',
      'doubleclick.net',
      'facebook.com/tr',
      'connect.facebook.net',
      'twitter.com/i/adsct',
      'bat.bing.com',
      'clarity.ms',
      'hotjar.com',
      'segment.io',
      'amplitude.com',
      'mixpanel.com',
    ];

    domains.forEach(d => this.blockedDomains.add(d));

    // Pattern-based blocking
    this.blockedPatterns = [
      /google-analytics\.com/i,
      /googletagmanager\.com/i,
      /doubleclick\.net/i,
      /facebook\.com\/tr/i,
      /ads\./i,
      /tracking\./i,
      /analytics\./i,
    ];
  }

  /**
   * Check if URL should be blocked
   */
  shouldBlock(url) {
    if (!LIGHTWEIGHT_CONFIG.blocking.enabled) return false;

    try {
      const parsed = new URL(url);
      const hostname = parsed.hostname;

      // Check domain list
      if (this.blockedDomains.has(hostname)) {
        this.stats.blocked++;
        return true;
      }

      // Check patterns
      if (this.blockedPatterns.some(p => p.test(url))) {
        this.stats.blocked++;
        return true;
      }

      this.stats.allowed++;
      return false;
    } catch {
      return false;
    }
  }

  /**
   * Get blocking stats
   */
  getStats() {
    return { ...this.stats };
  }
}

// ── Virtual Scroll List ───────────────────────────────────────────
class VirtualList {
  constructor(container, options = {}) {
    this.container = container;
    this.itemHeight = options.itemHeight || 40;
    this.bufferSize = options.bufferSize || 10;
    this.items = [];
    this.renderFn = options.renderFn || (() => '');

    this.init();
  }

  init() {
    this.container.style.overflow = 'auto';
    this.container.addEventListener('scroll', this.onScroll.bind(this));
  }

  /**
   * Set items
   */
  setItems(items) {
    this.items = items;
    this.container.style.height = `${items.length * this.itemHeight}px`;
    this.render();
  }

  /**
   * Handle scroll
   */
  onScroll() {
    this.render();
  }

  /**
   * Render visible items
   */
  render() {
    const scrollTop = this.container.scrollTop;
    const viewportHeight = this.container.clientHeight;

    const startIndex = Math.max(0, Math.floor(scrollTop / this.itemHeight) - this.bufferSize);
    const endIndex = Math.min(
      this.items.length,
      Math.ceil((scrollTop + viewportHeight) / this.itemHeight) + this.bufferSize
    );

    // Clear and re-render only visible items
    this.container.innerHTML = '';

    const fragment = document.createDocumentFragment();

    for (let i = startIndex; i < endIndex; i++) {
      const item = this.items[i];
      const el = document.createElement('div');
      el.style.height = `${this.itemHeight}px`;
      el.style.position = 'absolute';
      el.style.top = `${i * this.itemHeight}px`;
      el.innerHTML = this.renderFn(item, i);
      fragment.appendChild(el);
    }

    this.container.appendChild(fragment);
  }
}

// ── Memory Compressor (from Firefox) ──────────────────────────────
class MemoryCompressor {
  constructor() {
    this.cache = new Map();
    this.maxSize = LIGHTWEIGHT_CONFIG.memory.maxCacheSize;
    this.currentSize = 0;
  }

  /**
   * Compress and store data
   */
  set(key, data) {
    const serialized = JSON.stringify(data);
    const size = new Blob([serialized]).size;

    // Check size limit
    if (this.currentSize + size > this.maxSize) {
      this.evictOldest();
    }

    this.cache.set(key, {
      data: serialized,
      size,
      timestamp: Date.now(),
      compressed: LIGHTWEIGHT_CONFIG.memory.compressOldData,
    });

    this.currentSize += size;
  }

  /**
   * Get data
   */
  get(key) {
    const entry = this.cache.get(key);
    if (!entry) return null;

    // Update timestamp
    entry.timestamp = Date.now();

    return JSON.parse(entry.data);
  }

  /**
   * Evict oldest entries
   */
  evictOldest() {
    const entries = Array.from(this.cache.entries());
    entries.sort((a, b) => a[1].timestamp - b[1].timestamp);

    // Remove oldest 25%
    const toRemove = Math.ceil(entries.length * 0.25);
    for (let i = 0; i < toRemove; i++) {
      const [key, entry] = entries[i];
      this.cache.delete(key);
      this.currentSize -= entry.size;
    }
  }

  /**
   * Get cache stats
   */
  getStats() {
    return {
      entries: this.cache.size,
      sizeBytes: this.currentSize,
      sizeMB: Math.round(this.currentSize / 1024 / 1024),
    };
  }
}

// ── Main Lightweight Optimizer ────────────────────────────────────
class LightweightOptimizer {
  constructor() {
    this.domOptimizer = new DOMOptimizer();
    this.cssOptimizer = new CSSOptimizer();
    this.jsOptimizer = new JSOptimizer();
    this.adBlocker = new AdBlocker();
    this.memoryCompressor = new MemoryCompressor();
    this.virtualLists = new Map();
  }

  /**
   * Initialize all optimizers
   */
  init() {
    this.adBlocker.init();
    this.monitorDOM();
    console.log('[LIGHT] Lightweight optimizer initialized');
  }

  /**
   * Monitor DOM size
   */
  monitorDOM() {
    setInterval(() => {
      this.domOptimizer.countElements();
    }, 30000); // Check every 30 seconds
  }

  /**
   * Optimize element
   */
  optimizeElement(element) {
    this.cssOptimizer.applyContainment(element);
    return element;
  }

  /**
   * Create virtual list
   */
  createVirtualList(container, options) {
    const list = new VirtualList(container, options);
    this.virtualLists.set(container.id, list);
    return list;
  }

  /**
   * Get optimization stats
   */
  getStats() {
    return {
      domElements: this.domOptimizer.elementCount,
      adBlockStats: this.adBlocker.getStats(),
      cacheStats: this.memoryCompressor.getStats(),
      virtualLists: this.virtualLists.size,
    };
  }
}

// ── Export ─────────────────────────────────────────────────────────
module.exports = {
  LightweightOptimizer,
  DOMOptimizer,
  CSSOptimizer,
  JSOptimizer,
  AdBlocker,
  VirtualList,
  MemoryCompressor,
  LIGHTWEIGHT_CONFIG,
};
