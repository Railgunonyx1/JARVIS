/**
 * JARVIS Orbit — Enhanced Performance Module
 * 
 * Advanced performance optimizations inspired by:
 * - Chrome Memory Saver (tab discarding)
 * - Edge Efficiency Mode (CPU throttling)
 * - Thorium (compiler optimizations)
 * - Min Browser (minimal resource usage)
 * 
 * Features:
 * - Lazy webview loading
 * - Memory pressure monitoring
 * - Startup optimization
 * - Tab suspension with state preservation
 * - GPU acceleration management
 */

class EnhancedPerformance {
  constructor() {
    this.config = {
      // Lazy loading
      lazyLoad: {
        enabled: true,
        preloadAdjacent: 1, // Preload 1 tab on each side
        deferImages: true,
        deferIframes: true,
      },
      
      // Memory management
      memory: {
        monitorInterval: 30000, // 30 seconds
        warningThresholdMB: 512,
        criticalThresholdMB: 1024,
        autoSuspendThresholdMB: 768,
        maxTabCount: 100,
      },
      
      // Startup optimization
      startup: {
        preloadTabs: 2,
        preconnectHosts: ['www.google.com', 'fonts.googleapis.com'],
        deferNonCritical: true,
      },
      
      // Tab suspension
      suspension: {
        enabled: true,
        delayBeforeSuspend: 5 * 60 * 1000, // 5 minutes
        preserveState: true,
        excludePinned: true,
        excludePlaying: true,
      },
      
      // GPU acceleration
      gpu: {
        hardwareAcceleration: true,
        webgl: true,
        canvasAcceleration: true,
      },
    };
    
    this.tabs = new Map();
    this.memoryUsage = 0;
    this.monitorInterval = null;
    this.isLowMemory = false;
    this.startupTime = Date.now();
    
    this.init();
  }

  init() {
    // Start memory monitoring
    this.startMemoryMonitor();
    
    // Setup lazy loading
    if (this.config.lazyLoad.enabled) {
      this.setupLazyLoading();
    }
    
    // Setup startup optimization
    this.setupStartupOptimization();
    
    console.log('[PERF] Enhanced performance module initialized');
  }

  // ── Memory Monitoring ───────────────────────────────────────────
  
  startMemoryMonitor() {
    if (this.monitorInterval) return;
    
    this.monitorInterval = setInterval(() => {
      this.checkMemoryPressure();
    }, this.config.memory.monitorInterval);
    
    // Initial check
    this.checkMemoryPressure();
  }

  stopMemoryMonitor() {
    if (this.monitorInterval) {
      clearInterval(this.monitorInterval);
      this.monitorInterval = null;
    }
  }

  checkMemoryPressure() {
    // Get memory usage (Chrome-specific API)
    if (performance.memory) {
      this.memoryUsage = Math.round(performance.memory.usedJSHeapSize / 1048576);
      
      const { warningThresholdMB, criticalThresholdMB, autoSuspendThresholdMB } = this.config.memory;
      
      if (this.memoryUsage > criticalThresholdMB) {
        console.warn(`[PERF] Critical memory: ${this.memoryUsage}MB`);
        this.handleMemoryPressure('critical');
      } else if (this.memoryUsage > warningThresholdMB) {
        console.log(`[PERF] High memory: ${this.memoryUsage}MB`);
        this.handleMemoryPressure('warning');
      } else if (this.memoryUsage > autoSuspendThresholdMB) {
        this.handleMemoryPressure('suspend');
      } else {
        this.isLowMemory = false;
      }
    }
  }

  handleMemoryPressure(level) {
    this.isLowMemory = level !== 'normal';
    
    switch (level) {
      case 'critical':
        // Suspend all non-essential tabs
        this.suspendAllInactiveTabs();
        this.notify('memory-critical', { usage: this.memoryUsage });
        break;
        
      case 'warning':
        // Suspend oldest tabs
        this.suspendOldestTabs(3);
        this.notify('memory-warning', { usage: this.memoryUsage });
        break;
        
      case 'suspend':
        // Suspend one tab
        this.suspendOldestTabs(1);
        break;
    }
  }

  // ── Tab Management ──────────────────────────────────────────────
  
  registerTab(id, url) {
    const tab = {
      id,
      url,
      created: Date.now(),
      lastActive: Date.now(),
      isActive: false,
      isPinned: false,
      isSuspended: false,
      state: null, // For preserving scroll position, form data, etc.
    };
    
    this.tabs.set(id, tab);
    return tab;
  }

  unregisterTab(id) {
    this.tabs.delete(id);
  }

  markActive(id) {
    const tab = this.tabs.get(id);
    if (tab) {
      tab.lastActive = Date.now();
      tab.isActive = true;
      
      // Wake if suspended
      if (tab.isSuspended) {
        this.wakeTab(id);
      }
    }
  }

  markInactive(id) {
    const tab = this.tabs.get(id);
    if (tab) {
      tab.isActive = false;
    }
  }

  // ── Tab Suspension ──────────────────────────────────────────────
  
  suspendTab(id) {
    const tab = this.tabs.get(id);
    if (!tab || tab.isSuspended || tab.isPinned) return false;
    
    if (this.config.suspension.excludePlaying && tab.isPlaying) {
      return false;
    }
    
    // Preserve state before suspension
    if (this.config.suspension.preserveState) {
      tab.state = this.preserveTabState(id);
    }
    
    tab.isSuspended = true;
    this.notify('tab-suspended', { tabId: id, url: tab.url });
    
    return true;
  }

  wakeTab(id) {
    const tab = this.tabs.get(id);
    if (!tab || !tab.isSuspended) return false;
    
    tab.isSuspended = false;
    tab.lastActive = Date.now();
    
    // Restore state
    if (tab.state) {
      this.restoreTabState(id, tab.state);
      tab.state = null;
    }
    
    this.notify('tab-woken', { tabId: id, url: tab.url });
    
    return true;
  }

  suspendOldestTabs(count = 1) {
    const candidates = Array.from(this.tabs.values())
      .filter(t => !t.isActive && !t.isPinned && !t.isSuspended)
      .sort((a, b) => a.lastActive - b.lastActive);
    
    let suspended = 0;
    for (const tab of candidates) {
      if (suspended >= count) break;
      if (this.suspendTab(tab.id)) {
        suspended++;
      }
    }
    
    return suspended;
  }

  suspendAllInactiveTabs() {
    let suspended = 0;
    for (const [id, tab] of this.tabs) {
      if (!tab.isActive && !tab.isPinned && !tab.isSuspended) {
        if (this.suspendTab(id)) {
          suspended++;
        }
      }
    }
    return suspended;
  }

  preserveTabState(id) {
    // In a real implementation, this would capture:
    // - Scroll position
    // - Form data
    // - JavaScript state (if possible)
    return {
      timestamp: Date.now(),
      scrollY: window.scrollY,
    };
  }

  restoreTabState(id, state) {
    // Restore preserved state
    if (state.scrollY) {
      window.scrollTo(0, state.scrollY);
    }
  }

  // ── Lazy Loading ────────────────────────────────────────────────
  
  setupLazyLoading() {
    // Defer image loading
    if (this.config.lazyLoad.deferImages) {
      document.addEventListener('DOMContentLoaded', () => {
        const images = document.querySelectorAll('img[data-src]');
        const observer = new IntersectionObserver((entries) => {
          entries.forEach(entry => {
            if (entry.isIntersecting) {
              const img = entry.target;
              img.src = img.dataset.src;
              observer.unobserve(img);
            }
          });
        });
        
        images.forEach(img => observer.observe(img));
      });
    }
    
    // Defer iframe loading
    if (this.config.lazyLoad.deferIframes) {
      document.addEventListener('DOMContentLoaded', () => {
        const iframes = document.querySelectorAll('iframe[data-src]');
        const observer = new IntersectionObserver((entries) => {
          entries.forEach(entry => {
            if (entry.isIntersecting) {
              const iframe = entry.target;
              iframe.src = iframe.dataset.src;
              observer.unobserve(iframe);
            }
          });
        });
        
        iframes.forEach(iframe => observer.observe(iframe));
      });
    }
  }

  // ── Startup Optimization ────────────────────────────────────────
  
  setupStartupOptimization() {
    // Preconnect to critical hosts
    if (this.config.startup.preconnectHosts.length > 0) {
      const link = document.createElement('link');
      link.rel = 'preconnect';
      link.href = `https://${this.config.startup.preconnectHosts[0]}`;
      document.head.appendChild(link);
    }
    
    // Defer non-critical CSS
    if (this.config.startup.deferNonCritical) {
      const styles = document.querySelectorAll('link[rel="stylesheet"][data-defer]');
      styles.forEach(style => {
        style.media = 'print';
        window.onload = () => {
          style.media = 'all';
        };
      });
    }
    
    // Log startup time
    window.addEventListener('load', () => {
      const startupTime = Date.now() - this.startupTime;
      console.log(`[PERF] Startup time: ${startupTime}ms`);
      this.notify('startup-complete', { time: startupTime });
    });
  }

  // ── GPU Acceleration ────────────────────────────────────────────
  
  getGPUFlags() {
    const flags = [];
    
    if (this.config.gpu.hardwareAcceleration) {
      flags.push('--enable-gpu-rasterization');
      flags.push('--enable-zero-copy');
    }
    
    if (this.config.gpu.webgl) {
      flags.push('--enable-webgl');
      flags.push('--ignore-gpu-blocklist');
    }
    
    if (this.config.gpu.canvasAcceleration) {
      flags.push('--enable-accelerated-2d-canvas');
    }
    
    return flags;
  }

  // ── Notification System ─────────────────────────────────────────
  
  notify(type, data) {
    // Emit event for other modules to listen
    const event = new CustomEvent('performance-event', {
      detail: { type, data }
    });
    window.dispatchEvent(event);
    
    console.log(`[PERF] ${type}:`, data);
  }

  // ── Recommendations ─────────────────────────────────────────────
  
  getRecommendations() {
    const recommendations = [];
    
    // Memory recommendations
    if (this.memoryUsage > this.config.memory.warningThresholdMB) {
      recommendations.push({
        type: 'memory',
        severity: 'warning',
        message: `Memory usage is high (${this.memoryUsage}MB). Consider closing some tabs.`,
        action: 'close-tabs',
      });
    }
    
    // Tab count recommendations
    if (this.tabs.size > 20) {
      recommendations.push({
        type: 'tabs',
        severity: 'info',
        message: `You have ${this.tabs.size} tabs open. Consider using tab groups.`,
        action: 'organize-tabs',
      });
    }
    
    // Suspension recommendations
    const suspendedCount = Array.from(this.tabs.values()).filter(t => t.isSuspended).length;
    if (suspendedCount === 0 && this.tabs.size > 5) {
      recommendations.push({
        type: 'suspension',
        severity: 'info',
        message: 'No tabs are suspended. Enable automatic suspension to save memory.',
        action: 'enable-suspension',
      });
    }
    
    return recommendations;
  }

  // ── Status ──────────────────────────────────────────────────────
  
  getStatus() {
    const tabs = Array.from(this.tabs.values());
    const suspendedCount = tabs.filter(t => t.isSuspended).length;
    const activeCount = tabs.filter(t => t.isActive).length;
    
    return {
      memoryUsageMB: this.memoryUsage,
      isLowMemory: this.isLowMemory,
      totalTabs: this.tabs.size,
      activeTabs: activeCount,
      suspendedTabs: suspendedCount,
      recommendations: this.getRecommendations(),
      startupTime: Date.now() - this.startupTime,
    };
  }

  // ── Cleanup ─────────────────────────────────────────────────────
  
  destroy() {
    this.stopMemoryMonitor();
    this.tabs.clear();
  }
}

// Export
window.EnhancedPerformance = EnhancedPerformance;
window.enhancedPerformance = new EnhancedPerformance();
