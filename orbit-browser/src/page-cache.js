/**
 * JARVIS Orbit — Page Cache System
 * 
 * Intelligent caching for faster navigation:
 * - LRU cache with configurable size
 * - Prefetch prediction based on user patterns
 * - Cache invalidation strategies
 * - Memory-aware eviction
 * - DNS pre-resolution
 */

class PageCache {
  constructor(config = {}) {
    this.config = {
      maxEntries: config.maxEntries || 50,
      maxMemoryMB: config.maxMemoryMB || 100,
      ttl: config.ttl || 30 * 60 * 1000, // 30 minutes
      prefetchEnabled: config.prefetchEnabled !== false,
      prefetchThreshold: config.prefetchThreshold || 0.7, // 70% confidence
      dnsPreResolve: config.dnsPreResolve !== false,
      ...config,
    };
    
    this.cache = new Map();
    this.accessOrder = [];
    this.predictions = new Map();
    this.dnsCache = new Map();
    this.stats = {
      hits: 0,
      misses: 0,
      evictions: 0,
      prefetches: 0,
    };
    
    this.init();
  }

  init() {
    // Setup DNS pre-resolution
    if (this.config.dnsPreResolve) {
      this.setupDNSPreResolve();
    }
    
    // Cleanup expired entries periodically
    this.cleanupInterval = setInterval(() => {
      this.cleanup();
    }, 60000); // Every minute
    
    console.log('[CACHE] Page cache initialized');
  }

  // ── Cache Operations ────────────────────────────────────────────
  
  get(url) {
    const entry = this.cache.get(url);
    
    if (!entry) {
      this.stats.misses++;
      return null;
    }
    
    // Check TTL
    if (Date.now() - entry.timestamp > this.config.ttl) {
      this.cache.delete(url);
      this.removeFromAccessOrder(url);
      this.stats.misses++;
      return null;
    }
    
    // Update access order (move to end = most recently used)
    this.updateAccessOrder(url);
    
    this.stats.hits++;
    return entry;
  }

  set(url, data, metadata = {}) {
    // Check if we need to evict
    if (this.cache.size >= this.config.maxEntries) {
      this.evict();
    }
    
    const entry = {
      url,
      data,
      metadata: {
        title: metadata.title || '',
        favicon: metadata.favicon || '',
        scrollY: metadata.scrollY || 0,
        timestamp: Date.now(),
        size: this.estimateSize(data),
        accessCount: 1,
        lastAccess: Date.now(),
      },
    };
    
    this.cache.set(url, entry);
    this.updateAccessOrder(url);
    
    // Track memory usage
    this.checkMemoryLimit();
    
    return entry;
  }

  delete(url) {
    this.cache.delete(url);
    this.removeFromAccessOrder(url);
  }

  has(url) {
    const entry = this.cache.get(url);
    if (!entry) return false;
    
    // Check TTL
    if (Date.now() - entry.timestamp > this.config.ttl) {
      this.cache.delete(url);
      this.removeFromAccessOrder(url);
      return false;
    }
    
    return true;
  }

  // ── LRU Management ─────────────────────────────────────────────
  
  updateAccessOrder(url) {
    this.removeFromAccessOrder(url);
    this.accessOrder.push(url);
  }

  removeFromAccessOrder(url) {
    const index = this.accessOrder.indexOf(url);
    if (index !== -1) {
      this.accessOrder.splice(index, 1);
    }
  }

  evict() {
    // Evict least recently used
    if (this.accessOrder.length === 0) return;
    
    const oldestUrl = this.accessOrder[0];
    this.cache.delete(oldestUrl);
    this.accessOrder.shift();
    this.stats.evictions++;
  }

  evictByMemory(targetMB) {
    let freed = 0;
    
    // Sort by access time (oldest first)
    const sorted = [...this.accessOrder].sort((a, b) => {
      const entryA = this.cache.get(a);
      const entryB = this.cache.get(b);
      return (entryA?.metadata.lastAccess || 0) - (entryB?.metadata.lastAccess || 0);
    });
    
    for (const url of sorted) {
      if (freed >= targetMB) break;
      
      const entry = this.cache.get(url);
      if (entry) {
        freed += entry.metadata.size;
        this.delete(url);
      }
    }
    
    return freed;
  }

  // ── Memory Management ───────────────────────────────────────────
  
  estimateSize(data) {
    // Rough estimate in MB
    if (typeof data === 'string') {
      return data.length / (1024 * 1024);
    }
    return JSON.stringify(data).length / (1024 * 1024);
  }

  getTotalMemoryMB() {
    let total = 0;
    for (const entry of this.cache.values()) {
      total += entry.metadata.size;
    }
    return total;
  }

  checkMemoryLimit() {
    const totalMB = this.getTotalMemoryMB();
    if (totalMB > this.config.maxMemoryMB) {
      const target = totalMB - this.config.maxMemoryMB * 0.8; // Free 20%
      this.evictByMemory(target);
    }
  }

  // ── Prefetch System ─────────────────────────────────────────────
  
  recordAccess(url, referrer = null) {
    // Track access patterns for prefetch prediction
    const entry = this.cache.get(url);
    if (entry) {
      entry.metadata.accessCount++;
      entry.metadata.lastAccess = Date.now();
    }
    
    // Track referrer -> url patterns
    if (referrer) {
      const key = referrer;
      if (!this.predictions.has(key)) {
        this.predictions.set(key, new Map());
      }
      const referrerPredictions = this.predictions.get(key);
      const count = referrerPredictions.get(url) || 0;
      referrerPredictions.set(url, count + 1);
    }
  }

  predictNext(currentUrl) {
    const predictions = this.predictions.get(currentUrl);
    if (!predictions || predictions.size === 0) {
      return [];
    }
    
    // Sort by frequency
    return Array.from(predictions.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([url, count]) => ({
        url,
        confidence: count / (predictions.size * 2),
      }))
      .filter(p => p.confidence >= this.config.prefetchThreshold);
  }

  async prefetch(url) {
    if (!this.config.prefetchEnabled) return;
    if (this.has(url)) return;
    
    try {
      // Prefetch by loading into cache
      const response = await fetch(url, { 
        method: 'GET',
        credentials: 'same-origin',
      });
      
      if (response.ok) {
        const text = await response.text();
        this.set(url, text, {
          prefetched: true,
        });
        this.stats.prefetches++;
        console.log('[CACHE] Prefetched:', url);
      }
    } catch (error) {
      // Prefetch failures are silent
    }
  }

  async prefetchPredictions(currentUrl) {
    const predictions = this.predictNext(currentUrl);
    
    for (const prediction of predictions) {
      this.prefetch(prediction.url);
    }
  }

  // ── DNS Pre-resolution ──────────────────────────────────────────
  
  setupDNSPreResolve() {
    // Pre-resolve common domains
    const commonDomains = [
      'www.google.com',
      'github.com',
      'stackoverflow.com',
      'developer.mozilla.org',
    ];
    
    for (const domain of commonDomains) {
      this.preResolveDNS(domain);
    }
  }

  async preResolveDNS(domain) {
    if (this.dnsCache.has(domain)) return;
    
    try {
      // Use DNS-over-HTTPS if available
      const response = await fetch(`https://1.1.1.1/dns-query?name=${domain}`, {
        headers: { 'Accept': 'application/dns-json' },
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.Answer && data.Answer.length > 0) {
          const ip = data.Answer.find(a => a.type === 1)?.data;
          if (ip) {
            this.dnsCache.set(domain, {
              ip,
              timestamp: Date.now(),
            });
          }
        }
      }
    } catch (error) {
      // DNS pre-resolution failures are silent
    }
  }

  resolveDNS(domain) {
    return this.dnsCache.get(domain);
  }

  // ── Cleanup ─────────────────────────────────────────────────────
  
  cleanup() {
    const now = Date.now();
    
    for (const [url, entry] of this.cache) {
      if (now - entry.timestamp > this.config.ttl) {
        this.delete(url);
      }
    }
  }

  clear() {
    this.cache.clear();
    this.accessOrder = [];
  }

  // ── Statistics ──────────────────────────────────────────────────
  
  getStats() {
    const hitRate = this.stats.hits + this.stats.misses > 0
      ? this.stats.hits / (this.stats.hits + this.stats.misses)
      : 0;
    
    return {
      ...this.stats,
      hitRate: Math.round(hitRate * 100),
      totalEntries: this.cache.size,
      totalMemoryMB: Math.round(this.getTotalMemoryMB() * 100) / 100,
      maxEntries: this.config.maxEntries,
      maxMemoryMB: this.config.maxMemoryMB,
    };
  }

  // ── Export/Import ───────────────────────────────────────────────
  
  export() {
    const data = {};
    for (const [url, entry] of this.cache) {
      data[url] = entry;
    }
    return data;
  }

  import(data) {
    for (const [url, entry] of Object.entries(data)) {
      this.cache.set(url, entry);
      this.updateAccessOrder(url);
    }
  }
}

// Export
window.PageCache = PageCache;
window.pageCache = new PageCache();
