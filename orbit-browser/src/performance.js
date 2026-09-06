/**
 * JARVIS Orbit — Performance Module
 *
 * Implements performance optimizations inspired by Edge Efficiency Mode,
 * Thorium, and Chrome's tab discarding.
 *
 * Features:
 * - Sleeping tabs (suspend inactive tabs)
 * - Efficiency mode (reduce CPU usage)
 * - Memory management
 * - Startup optimization
 */

// ── Configuration ─────────────────────────────────────────────────
const PERFORMANCE_CONFIG = {
  // Sleeping tabs
  sleepingTabs: {
    enabled: true,
    delayBeforeSleep: 30 * 60 * 1000, // 30 minutes
    excludePinned: true,
    excludeAudible: true,
    excludeActive: true,
  },

  // Efficiency mode
  efficiencyMode: {
    enabled: false, // Disabled by default
    throttleCPU: 0.5, // 50% CPU limit when enabled
    reduceAnimations: true,
  },

  // Memory management
  memory: {
    maxTabCount: 100,
    discardThresholdMB: 1024, // Discard tabs when memory exceeds 1GB
    prioritizeActive: true,
  },

  // Startup
  startup: {
    preload: true,
    preloadTabs: 3, // Preload first 3 tabs
    lazyLoad: true, // Lazy load offscreen content
  },
};

// ── Tab State ─────────────────────────────────────────────────────
class TabState {
  constructor(id, url) {
    this.id = id;
    this.url = url;
    this.lastActive = Date.now();
    this.isSleeping = false;
    this.isPinned = false;
    this.isAudible = false;
    this.memoryUsage = 0;
    this.cpuUsage = 0;
  }

  touch() {
    this.lastActive = Date.now();
    this.isSleeping = false;
  }

  sleep() {
    this.isSleeping = true;
  }

  wake() {
    this.isSleeping = false;
    this.touch();
  }
}

// ── Performance Class ─────────────────────────────────────────────
class PerformanceModule {
  constructor() {
    this.config = { ...PERFORMANCE_CONFIG };
    this.tabs = new Map();
    this.totalMemory = 0;
    this.sleepCheckInterval = null;
    this.activeTabId = null;
  }

  /**
   * Register a tab for tracking
   */
  registerTab(id, url) {
    const tab = new TabState(id, url);
    this.tabs.set(id, tab);
    return tab;
  }

  /**
   * Unregister a tab
   */
  unregisterTab(id) {
    this.tabs.delete(id);
  }

  /**
   * Mark a tab as the active tab (never slept while active)
   */
  markActive(id) {
    this.activeTabId = id;
    const tab = this.tabs.get(id);
    if (tab) {
      tab.touch();
    }
  }

  /**
   * Mark a tab as active
   */
  activateTab(id) {
    const tab = this.tabs.get(id);
    if (tab) {
      tab.touch();
    }
  }

  /**
   * Check if a tab should be sleeping
   */
  shouldSleep(id) {
    const tab = this.tabs.get(id);
    if (!tab) return false;

    const config = this.config.sleepingTabs;
    if (!config.enabled) return false;
    if (config.excludePinned && tab.isPinned) return false;
    if (config.excludeAudible && tab.isAudible) return false;
    if (config.excludeActive && tab.id === this.activeTabId) return false;

    const timeSinceActive = Date.now() - tab.lastActive;
    return timeSinceActive > config.delayBeforeSleep;
  }

  /**
   * Get all sleeping tabs
   */
  getSleepingTabs() {
    const sleeping = [];
    for (const [id, tab] of this.tabs) {
      if (tab.isSleeping) {
        sleeping.push(id);
      }
    }
    return sleeping;
  }

  /**
   * Get tab memory usage
   */
  getTabMemory(id) {
    const tab = this.tabs.get(id);
    return tab ? tab.memoryUsage : 0;
  }

  /**
   * Update tab memory usage
   */
  updateTabMemory(id, memoryMB) {
    const tab = this.tabs.get(id);
    if (tab) {
      this.totalMemory -= tab.memoryUsage;
      tab.memoryUsage = memoryMB;
      this.totalMemory += memoryMB;
    }
  }

  /**
   * Check if memory threshold is exceeded
   */
  isMemoryExceeded() {
    return this.totalMemory > this.config.memory.discardThresholdMB;
  }

  /**
   * Get tabs to discard (oldest, least used)
   */
  getTabsToDiscard(count = 1) {
    const candidates = [];
    for (const [id, tab] of this.tabs) {
      if (!tab.isPinned && !tab.isSleeping) {
        candidates.push({
          id,
          score: tab.lastActive + (tab.memoryUsage * 1000),
        });
      }
    }

    // Sort by score (oldest + most memory = first to discard)
    candidates.sort((a, b) => a.score - b.score);

    return candidates.slice(0, count).map(c => c.id);
  }

  /**
   * Toggle efficiency mode
   */
  toggleEfficiencyMode(enabled) {
    this.config.efficiencyMode.enabled = enabled;
    return this.config.efficiencyMode;
  }

  /**
   * Get efficiency recommendations
   */
  getRecommendations() {
    const recommendations = [];
    const sleepingCount = this.getSleepingTabs().length;
    const totalCount = this.tabs.size;

    if (sleepingCount < totalCount * 0.3) {
      recommendations.push({
        type: "sleeping_tabs",
        message: `${totalCount - sleepingCount} tabs are active. Consider sleeping inactive tabs.`,
        impact: "medium",
      });
    }

    if (this.totalMemory > this.config.memory.discardThresholdMB * 0.8) {
      recommendations.push({
        type: "memory",
        message: `Memory usage is ${Math.round(this.totalMemory)}MB. Consider closing some tabs.`,
        impact: "high",
      });
    }

    if (!this.config.efficiencyMode.enabled) {
      recommendations.push({
        type: "efficiency",
        message: "Efficiency mode is disabled. Enable it to reduce CPU usage.",
        impact: "low",
      });
    }

    return recommendations;
  }

  /**
   * Get performance status
   */
  getStatus() {
    const sleeping = this.getSleepingTabs().length;
    const active = this.tabs.size - sleeping;

    return {
      totalTabs: this.tabs.size,
      activeTabs: active,
      sleepingTabs: sleeping,
      totalMemoryMB: Math.round(this.totalMemory),
      efficiencyMode: this.config.efficiencyMode.enabled,
      recommendations: this.getRecommendations(),
    };
  }

  /**
   * Start automatic sleep checking
   */
  startSleepCheck(intervalMs = 60000) {
    this.stopSleepCheck();

    this.sleepCheckInterval = setInterval(() => {
      for (const [id, tab] of this.tabs) {
        if (this.shouldSleep(id) && !tab.isSleeping) {
          tab.sleep();
          // Emit event: tab should be suspended
          console.log(`[PERF] Tab ${id} sleeping after inactivity`);
        }
      }
    }, intervalMs);
  }

  /**
   * Stop automatic sleep checking
   */
  stopSleepCheck() {
    if (this.sleepCheckInterval) {
      clearInterval(this.sleepCheckInterval);
      this.sleepCheckInterval = null;
    }
  }
}

// ── Export ─────────────────────────────────────────────────────────
module.exports = { PerformanceModule, PERFORMANCE_CONFIG };
