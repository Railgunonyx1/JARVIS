/**
 * JARVIS Orbit — Advanced Optimizations
 * 
 * Based on research from Chrome, Firefox, Brave, Edge, Thorium, and others.
 * 
 * Features:
 * - Intelligent tab discarding (Chrome Memory Saver style)
 * - Memory pressure detection (Edge Efficiency Mode)
 * - Fingerprint farbling (Brave Shields)
 * - DNS pre-resolution (Chrome)
 * - Lazy loading (Firefox Quantum)
 * - Startup optimization (Thorium)
 * - Energy saver mode (Chrome Energy Saver)
 */

class AdvancedOptimizations {
  constructor(config = {}) {
    this.config = {
      // Tab Discarding (Chrome Memory Saver)
      tabDiscarding: {
        enabled: true,
        memoryThreshold: 0.8, // 80% memory usage triggers discard
        minActiveTabs: 3,
        preservePinned: true,
        preservePlaying: true,
        preservePinnedTabs: true,
        discardTimeout: 5 * 60 * 1000, // 5 minutes
        useMLPrediction: true, // Chrome 140+ style
      },

      // Memory Pressure (Edge Efficiency Mode)
      memoryPressure: {
        enabled: true,
        warningThreshold: 0.7, // 70%
        criticalThreshold: 0.9, // 90%
        suspendThreshold: 0.85, // 85%
        checkInterval: 30000, // 30 seconds
      },

      // Fingerprint Protection (Brave Shields)
      fingerprintProtection: {
        enabled: true,
        canvas: true,
        webgl: true,
        audio: true,
        screen: true,
        fonts: true,
        timezone: true,
        hardware: true,
        noiseLevel: 0.1,
      },

      // DNS Pre-resolution
      dnsPreResolve: {
        enabled: true,
        commonDomains: [
          'www.google.com',
          'github.com',
          'stackoverflow.com',
          'developer.mozilla.org',
          'www.youtube.com',
          'twitter.com',
          'reddit.com',
        ],
        cacheSize: 100,
      },

      // Lazy Loading
      lazyLoading: {
        enabled: true,
        images: true,
        iframes: true,
        videos: true,
        threshold: 100, // pixels before viewport
      },

      // Startup Optimization
      startup: {
        preloadTabs: 2,
        preconnect: true,
        deferCSS: true,
        deferImages: true,
        dnsPrefetch: true,
      },

      // Energy Saver (Chrome Energy Saver)
      energySaver: {
        enabled: true,
        reduceAnimations: true,
        throttleTimers: true,
        limitFPS: 30, // When on battery
        batteryThreshold: 0.2, // 20% battery
      },

      // Performance Monitoring
      monitoring: {
        enabled: true,
        fpsTarget: 60,
        memoryWarningMB: 512,
        memoryCriticalMB: 1024,
        logPerformance: true,
      },

      ...config,
    };

    this.state = {
      memoryUsage: 0,
      memoryPressure: 'normal', // normal, warning, critical
      batteryLevel: 1,
      isCharging: true,
      fps: 60,
      tabCount: 0,
      suspendedTabs: 0,
      discardedTabs: 0,
    };

    this.tabs = new Map();
    this.dnsCache = new Map();
    this.performanceObserver = null;
    this.batteryAPI = null;

    this.init();
  }

  async init() {
    // Setup memory monitoring
    this.startMemoryMonitoring();

    // Setup FPS monitoring
    this.startFPSMonitoring();

    // Setup battery monitoring
    await this.setupBatteryMonitoring();

    // Setup DNS pre-resolution
    if (this.config.dnsPreResolve.enabled) {
      this.setupDNSPreResolution();
    }

    // Setup lazy loading
    if (this.config.lazyLoading.enabled) {
      this.setupLazyLoading();
    }

    // Setup fingerprint protection
    if (this.config.fingerprintProtection.enabled) {
      this.setupFingerprintProtection();
    }

    console.log('[OPT] Advanced optimizations initialized');
  }

  // ── Tab Discarding (Chrome Memory Saver) ────────────────────────

  registerTab(id, webview, options = {}) {
    const tab = {
      id,
      webview,
      url: options.url || '',
      title: options.title || '',
      lastActive: Date.now(),
      isActive: false,
      isPinned: options.isPinned || false,
      isPlaying: options.isPlaying || false,
      isSuspended: false,
      isDiscarded: false,
      scrollY: 0,
      state: null,
      importance: this.calculateImportance(options),
    };

    this.tabs.set(id, tab);
    this.state.tabCount = this.tabs.size;

    return tab;
  }

  unregisterTab(id) {
    this.tabs.delete(id);
    this.state.tabCount = this.tabs.size;
  }

  calculateImportance(options) {
    let score = 0;

    // Recent activity increases importance
    if (options.lastActive) {
      const age = Date.now() - options.lastActive;
      score += Math.max(0, 100 - age / 60000); // Decays over 100 minutes
    }

    // Pinned tabs are important
    if (options.isPinned) score += 50;

    // Playing tabs are important
    if (options.isPlaying) score += 40;

    // Audio playing is important
    if (options.isAudible) score += 30;

    // User-created tabs are important
    if (options.isUserCreated) score += 20;

    return score;
  }

  shouldDiscardTab(tab) {
    if (!this.config.tabDiscarding.enabled) return false;
    if (tab.isPinned && this.config.tabDiscarding.preservePinned) return false;
    if (tab.isPlaying && this.config.tabDiscarding.preservePlaying) return false;
    if (tab.isActive) return false;
    if (tab.isDiscarded) return false;

    // Check memory pressure
    if (this.state.memoryPressure === 'critical') return true;
    if (this.state.memoryPressure === 'warning') {
      // Only discard low-importance tabs
      if (tab.importance < 30) return true;
    }

    // Check time since last active
    const timeSinceActive = Date.now() - tab.lastActive;
    return timeSinceActive > this.config.tabDiscarding.discardTimeout;
  }

  discardTab(tab) {
    if (tab.isDiscarded) return false;

    // Save state before discarding
    tab.state = {
      url: tab.url,
      scrollY: tab.scrollY,
      timestamp: Date.now(),
    };

    // Hide webview
    if (tab.webview) {
      tab.webview.style.display = 'none';
    }

    tab.isDiscarded = true;
    this.state.discardedTabs++;

    console.log(`[OPT] Discarded tab: ${tab.id}`);
    return true;
  }

  restoreTab(tab) {
    if (!tab.isDiscarded) return false;

    // Show webview
    if (tab.webview) {
      tab.webview.style.display = '';
    }

    // Reload if needed
    if (tab.state && tab.state.url) {
      tab.webview.loadURL(tab.state.url);
    }

    tab.isDiscarded = false;
    tab.lastActive = Date.now();
    this.state.discardedTabs--;

    console.log(`[OPT] Restored tab: ${tab.id}`);
    return true;
  }

  // ── Memory Pressure (Edge Efficiency Mode) ──────────────────────

  startMemoryMonitoring() {
    this.memoryCheckInterval = setInterval(() => {
      this.checkMemoryPressure();
    }, this.config.memoryPressure.checkInterval);
  }

  checkMemoryPressure() {
    if (!performance.memory) return;

    const used = performance.memory.usedJSHeapSize;
    const limit = performance.memory.jsHeapSizeLimit;
    const usage = used / limit;

    this.state.memoryUsage = Math.round(used / (1024 * 1024));

    if (usage > this.config.memoryPressure.criticalThreshold) {
      this.state.memoryPressure = 'critical';
      this.handleMemoryPressure('critical');
    } else if (usage > this.config.memoryPressure.suspendThreshold) {
      this.state.memoryPressure = 'warning';
      this.handleMemoryPressure('warning');
    } else if (usage > this.config.memoryPressure.warningThreshold) {
      this.state.memoryPressure = 'normal';
    } else {
      this.state.memoryPressure = 'normal';
    }
  }

  handleMemoryPressure(level) {
    switch (level) {
      case 'critical':
        // Discard oldest, least important tabs
        this.discardOldestTabs(3);
        break;
      case 'warning':
        // Suspend some tabs
        this.suspendOldestTabs(2);
        break;
    }
  }

  discardOldestTabs(count) {
    const candidates = Array.from(this.tabs.values())
      .filter(t => !t.isPinned && !t.isActive && !t.isDiscarded)
      .sort((a, b) => a.importance - b.importance || a.lastActive - b.lastActive);

    let discarded = 0;
    for (const tab of candidates) {
      if (discarded >= count) break;
      if (this.discardTab(tab)) {
        discarded++;
      }
    }
  }

  suspendOldestTabs(count) {
    const candidates = Array.from(this.tabs.values())
      .filter(t => !t.isPinned && !t.isActive && !t.isSuspended)
      .sort((a, b) => a.lastActive - b.lastActive);

    let suspended = 0;
    for (const tab of candidates) {
      if (suspended >= count) break;
      if (this.suspendTab(tab)) {
        suspended++;
      }
    }
  }

  suspendTab(tab) {
    if (tab.isSuspended) return false;

    // Save state
    tab.state = {
      url: tab.url,
      scrollY: tab.scrollY,
      timestamp: Date.now(),
    };

    tab.isSuspended = true;
    this.state.suspendedTabs++;

    console.log(`[OPT] Suspended tab: ${tab.id}`);
    return true;
  }

  resumeTab(tab) {
    if (!tab.isSuspended) return false;

    tab.isSuspended = false;
    tab.lastActive = Date.now();
    this.state.suspendedTabs--;

    console.log(`[OPT] Resumed tab: ${tab.id}`);
    return true;
  }

  // ── FPS Monitoring ──────────────────────────────────────────────

  startFPSMonitoring() {
    let lastTime = performance.now();
    let frames = 0;

    const measureFPS = () => {
      frames++;
      const now = performance.now();
      if (now - lastTime >= 1000) {
        this.state.fps = frames;
        frames = 0;
        lastTime = now;

        // Check FPS and adjust
        if (this.state.fps < 30 && this.config.energySaver.enabled) {
          this.enableEnergySaver();
        }
      }
      requestAnimationFrame(measureFPS);
    };

    requestAnimationFrame(measureFPS);
  }

  enableEnergySaver() {
    // Reduce animations
    document.documentElement.classList.add('energy-saver');

    // Throttle timers
    if (this.config.energySaver.throttleTimers) {
      this.throttleTimers();
    }
  }

  throttleTimers() {
    // Override setTimeout to throttle long timers
    const originalSetTimeout = window.setTimeout;
    window.setTimeout = (fn, delay, ...args) => {
      if (delay > 100) {
        delay = Math.min(delay, 1000); // Cap at 1 second
      }
      return originalSetTimeout(fn, delay, ...args);
    };
  }

  // ── Battery Monitoring ──────────────────────────────────────────

  async setupBatteryMonitoring() {
    try {
      if ('getBattery' in navigator) {
        this.batteryAPI = await navigator.getBattery();
        this.updateBatteryState();

        this.batteryAPI.addEventListener('chargingchange', () => {
          this.updateBatteryState();
        });

        this.batteryAPI.addEventListener('levelchange', () => {
          this.updateBatteryState();
        });
      }
    } catch (error) {
      console.log('[OPT] Battery API not available');
    }
  }

  updateBatteryState() {
    if (!this.batteryAPI) return;

    this.state.batteryLevel = this.batteryAPI.level;
    this.state.isCharging = this.batteryAPI.charging;

    // Enable energy saver when battery is low and not charging
    if (!this.state.isCharging && 
        this.state.batteryLevel < this.config.energySaver.batteryThreshold) {
      this.enableEnergySaver();
    }
  }

  // ── DNS Pre-resolution ──────────────────────────────────────────

  setupDNSPreResolution() {
    // Pre-resolve common domains
    for (const domain of this.config.dnsPreResolve.commonDomains) {
      this.preResolveDNS(domain);
    }

    // Pre-resolve on page load
    document.addEventListener('DOMContentLoaded', () => {
      this.prefetchDNSFromPage();
    });
  }

  async preResolveDNS(domain) {
    if (this.dnsCache.has(domain)) return;

    try {
      const response = await fetch(`https://1.1.1.1/dns-query?name=${domain}`, {
        headers: { 'Accept': 'application/dns-json' },
      });

      if (response.ok) {
        const data = await response.json();
        if (data.Answer) {
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
      // Silent fail
    }
  }

  prefetchDNSFromPage() {
    const links = document.querySelectorAll('a[href]');
    const domains = new Set();

    links.forEach(link => {
      try {
        const url = new URL(link.href);
        if (url.hostname && !url.hostname.includes(window.location.hostname)) {
          domains.add(url.hostname);
        }
      } catch (e) {}
    });

    // Pre-resolve top 10 unique domains
    Array.from(domains).slice(0, 10).forEach(domain => {
      this.preResolveDNS(domain);
    });
  }

  // ── Lazy Loading ────────────────────────────────────────────────

  setupLazyLoading() {
    // Lazy load images
    if (this.config.lazyLoading.images) {
      this.setupLazyImages();
    }

    // Lazy load iframes
    if (this.config.lazyLoading.iframes) {
      this.setupLazyIframes();
    }

    // Lazy load videos
    if (this.config.lazyLoading.videos) {
      this.setupLazyVideos();
    }
  }

  setupLazyImages() {
    const images = document.querySelectorAll('img[data-src]');
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const img = entry.target;
          img.src = img.dataset.src;
          img.removeAttribute('data-src');
          observer.unobserve(img);
        }
      });
    }, {
      rootMargin: `${this.config.lazyLoading.threshold}px`,
    });

    images.forEach(img => observer.observe(img));
  }

  setupLazyIframes() {
    const iframes = document.querySelectorAll('iframe[data-src]');
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const iframe = entry.target;
          iframe.src = iframe.dataset.src;
          iframe.removeAttribute('data-src');
          observer.unobserve(iframe);
        }
      });
    }, {
      rootMargin: `${this.config.lazyLoading.threshold}px`,
    });

    iframes.forEach(iframe => observer.observe(iframe));
  }

  setupLazyVideos() {
    const videos = document.querySelectorAll('video[data-src]');
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const video = entry.target;
          video.src = video.dataset.src;
          video.removeAttribute('data-src');
          observer.unobserve(video);
        }
      });
    }, {
      rootMargin: `${this.config.lazyLoading.threshold}px`,
    });

    videos.forEach(video => observer.observe(video));
  }

  // ── Fingerprint Protection (Brave Shields) ──────────────────────

  setupFingerprintProtection() {
    if (this.config.fingerprintProtection.canvas) {
      this.protectCanvas();
    }

    if (this.config.fingerprintProtection.webgl) {
      this.protectWebGL();
    }

    if (this.config.fingerprintProtection.audio) {
      this.protectAudio();
    }

    if (this.config.fingerprintProtection.screen) {
      this.protectScreen();
    }

    if (this.config.fingerprintProtection.fonts) {
      this.protectFonts();
    }

    if (this.config.fingerprintProtection.timezone) {
      this.protectTimezone();
    }

    console.log('[OPT] Fingerprint protection enabled');
  }

  protectCanvas() {
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const originalToBlob = HTMLCanvasElement.prototype.toBlob;
    const noiseLevel = this.config.fingerprintProtection.noiseLevel;

    HTMLCanvasElement.prototype.toDataURL = function (...args) {
      const ctx = this.getContext('2d');
      if (ctx) {
        const imageData = ctx.getImageData(0, 0, this.width, this.height);
        const data = imageData.data;

        // Add subtle noise
        for (let i = 0; i < data.length; i += 4) {
          data[i] ^= Math.floor(Math.random() * noiseLevel * 10);
          data[i + 1] ^= Math.floor(Math.random() * noiseLevel * 10);
          data[i + 2] ^= Math.floor(Math.random() * noiseLevel * 10);
        }

        ctx.putImageData(imageData, 0, 0);
      }
      return originalToDataURL.apply(this, args);
    };

    HTMLCanvasElement.prototype.toBlob = function (callback, type, quality) {
      const ctx = this.getContext('2d');
      if (ctx) {
        const imageData = ctx.getImageData(0, 0, this.width, this.height);
        const data = imageData.data;

        // Add subtle noise
        for (let i = 0; i < data.length; i += 4) {
          data[i] ^= Math.floor(Math.random() * noiseLevel * 10);
          data[i + 1] ^= Math.floor(Math.random() * noiseLevel * 10);
          data[i + 2] ^= Math.floor(Math.random() * noiseLevel * 10);
        }

        ctx.putImageData(imageData, 0, 0);
      }
      return originalToBlob.apply(this, arguments);
    };
  }

  protectWebGL() {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    const getParameter2 = WebGL2RenderingContext.prototype.getParameter;

    WebGLRenderingContext.prototype.getParameter = function (param) {
      // Spoof vendor and renderer
      if (param === 37445) return 'Intel Inc.';
      if (param === 37446) return 'Intel Iris OpenGL Engine';
      return getParameter.call(this, param);
    };

    if (typeof WebGL2RenderingContext !== 'undefined') {
      WebGL2RenderingContext.prototype.getParameter = function (param) {
        if (param === 37445) return 'Intel Inc.';
        if (param === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter2.call(this, param);
      };
    }
  }

  protectAudio() {
    if (!window.AudioContext && !window.webkitAudioContext) return;

    const AudioContext = window.AudioContext || window.webkitAudioContext;
    const originalGetChannelData = AudioContext.prototype.getChannelData;

    AudioContext.prototype.getChannelData = function (...args) {
      const data = originalGetChannelData.apply(this, args);

      // Add subtle noise
      for (let i = 0; i < data.length; i++) {
        data[i] += (Math.random() - 0.5) * 0.0001;
      }

      return data;
    };
  }

  protectScreen() {
    Object.defineProperty(screen, 'availWidth', { get: () => 1920 });
    Object.defineProperty(screen, 'availHeight', { get: () => 1040 });
    Object.defineProperty(screen, 'width', { get: () => 1920 });
    Object.defineProperty(screen, 'height', { get: () => 1080 });
    Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
    Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
  }

  protectFonts() {
    const originalCheck = document.fonts.check;
    const commonFonts = [
      'Arial', 'Verdana', 'Helvetica', 'Times New Roman', 'Georgia',
      'Courier New', 'monospace', 'sans-serif', 'serif',
    ];

    document.fonts.check = function (font, text) {
      // Always return true for common fonts
      if (commonFonts.some(f => font.toLowerCase().includes(f.toLowerCase()))) {
        return true;
      }
      return originalCheck.call(this, font, text);
    };
  }

  protectTimezone() {
    const originalResolvedOptions = Intl.DateTimeFormat.prototype.resolvedOptions;
    Intl.DateTimeFormat.prototype.resolvedOptions = function (...args) {
      const options = originalResolvedOptions.apply(this, args);
      options.timeZone = 'UTC';
      return options;
    };
  }

  // ── Status ──────────────────────────────────────────────────────

  getStatus() {
    return {
      ...this.state,
      config: this.config,
      tabDiscarding: {
        enabled: this.config.tabDiscarding.enabled,
        discardedTabs: this.state.discardedTabs,
      },
      memoryPressure: {
        enabled: this.config.memoryPressure.enabled,
        level: this.state.memoryPressure,
        usageMB: this.state.memoryUsage,
      },
      fingerprintProtection: {
        enabled: this.config.fingerprintProtection.enabled,
      },
      dnsCache: this.dnsCache.size,
      energySaver: {
        enabled: this.config.energySaver.enabled,
        batteryLevel: this.state.batteryLevel,
        isCharging: this.state.isCharging,
      },
    };
  }

  // ── Cleanup ─────────────────────────────────────────────────────

  destroy() {
    if (this.memoryCheckInterval) {
      clearInterval(this.memoryCheckInterval);
    }
    this.tabs.clear();
    this.dnsCache.clear();
  }
}

// Export
window.AdvancedOptimizations = AdvancedOptimizations;
window.advancedOptimizations = new AdvancedOptimizations();
