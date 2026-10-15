/**
 * JARVIS Orbit — Security Module
 *
 * Implements security features inspired by Brave Shields, Ungoogled Chromium,
 * and Edge Enhanced Security.
 *
 * Features:
 * - Ad/tracker blocking (EasyList-inspired comprehensive filter patterns)
 * - Fingerprint protection
 * - HTTPS upgrade
 * - Cookie controls
 * - Telemetry blocking
 * - VPN extension management
 * - Extension store integration
 */

// ── Shields Configuration ─────────────────────────────────────────
const SHIELDS_CONFIG = {
  // Ad/tracker blocking
  adBlocking: true,
  trackerBlocking: true,
  fingerprintProtection: true,

  // HTTPS
  httpsUpgrade: true,
  httpsOnlyMode: false,

  // Cookies
  thirdPartyCookies: "block", // "allow" | "block" | "session"
  firstPartyCookies: "allow",

  // Privacy
  doNotTrack: true,
  referrerPolicy: "no-referrer-when-downgrade",

  // Telemetry blocking
  blockTelemetry: true,
  blockGoogleServices: true,
};

// ── Blocked Domains (Brave Shields comprehensive list) ──────────
const BLOCKED_DOMAINS = [
  // Google Ads & Analytics
  "clients1.google.com",
  "clients2.google.com",
  "www.google-analytics.com",
  "google-analytics.com",
  "analytics.google.com",
  "doubleclick.net",
  "ads.google.com",
  "pagead2.googlesyndication.com",
  "adservice.google.com",
  "tpc.googlesyndication.com",
  "googlesyndication.com",
  "googleadservices.com",
  "www.googleadservices.com",
  "adservice.google.com",
  "stat.clickvwant.com",

  // Facebook / Meta trackers
  "facebook.com/tr",
  "connect.facebook.net",
  "pixel.facebook.com",
  "analytics.facebook.com",
  "www.facebook.com/tr",

  // Twitter / X trackers
  "platform.twitter.com",
  "syndication.twitter.com",
  "analytics.twitter.com",
  "t.co",

  // Microsoft trackers
  "bat.bing.com",
  "clarity.ms",
  "c.bing.com",
  "adnxs.com",

  // Amazon ads
  "assoc-amazon.com",
  "fls-na.amazon.com",

  // Common ad networks
  "adnxs.com",
  "adsrvr.org",
  "advertising.com",
  "criteo.com",
  "criteo.net",
  "demdex.net",
  "doubleverify.com",
  "everesttech.net",
  "exelator.com",
  "chartbeat.com",
  "chartbeat.net",
  "scoresense.com",
  "liadm.com",
  "sail-horizon.com",
  "rubiconproject.com",
  "pubmatic.com",
  "openx.net",
  "sharethrough.com",
  "outbrain.com",
  "taboola.com",
  "ligatus.com",
  "mathtag.com",
  "moatads.com",
  "nativo.com",
  "spotxchange.com",
  "yieldmo.com",

  // Analytics platforms
  "hotjar.com",
  "mouseflow.com",
  "heap.io",
  "segment.com",
  "amplitude.com",
  "mixpanel.com",
  "branch.io",
  "adjust.com",
  "instapage.com",
  "optimizely.com",
  "fullstory.com",
  "logrocket.com",
  "sentry.io",
  "newrelic.com",
  "nr-data.net",
  "pardot.com",
  "marketo.com",
  "hubspot.com",
  "intercom.io",
  "drift.com",
  "crisp.chat",
  "tawk.to",
  "zendesk.com",

  // Fingerprinting
  "fingerprint.com",
  "fpjs.io",
  "permsapi.com",
  "infocaptcha.net",
  "whiteboxdigital.com",

  // Crypto miners
  "coinhive.com",
  "coin-hive.com",
  "jsecoin.com",
  "crypto-loot.com",
  "authedmine.com",
  "minero.cc",
  "ppoi.org",
  "webmine.cz",

  // Telemetry / data collection
  "telemetry.microsoft.com",
  "vortex.data.microsoft.com",
  "settings-win.data.microsoft.com",
  "v10.events.data.microsoft.com",
  "self.events.data.microsoft.com",
  "browser.events.data.msn.com",

  // More ad networks (Brave-level coverage)
  "media.net",
  "zedo.com",
  "adroll.com",
  "turn.com",
  "mathtag.com",
  "bidswitch.net",
  "brightroll.com",
  "contextweb.com",
  "sonobi.com",
  "lijit.com",
  "sovrn.com",
  "undertone.com",
  "teads.tv",
  "connatix.com",
  "confiant-integrations.net",
  "permutive.com",
  "bluekai.com",
  "agkn.com",
  "acuityplatform.com",
  "bidvertiser.com",

  // A/B testing & session replay
  "heap.io",
  "fullstory.com",
  "logrocket.com",
  "hotjar.com",
  "crazyegg.com",
  "luckyorange.com",
  "mouseflow.com",
  "clicktale.com",
  "kissmetrics.com",
  "qllick.com",
  "inspectlet.com",
  "bingbot.com",

  // Malware / phishing (known)
  "bit.do",
  "tinyurl.com",
  "goo.gl",
  "t.co",
];

// ── Trackers Database (EasyList-inspired URL patterns) ─────────
const TRACKER_PATTERNS = [
  // Google
  /google-analytics\.com/i,
  /googletagmanager\.com/i,
  /googleadservices\.com/i,
  /googlesyndication\.com/i,
  /doubleclick\.net/i,
  /adservice\.google/i,
  /pagead\.google/i,

  // Facebook
  /facebook\.com\/tr/i,
  /connect\.facebook\.net/i,
  /pixel\.facebook/i,
  /analytics\.facebook/i,

  // Twitter
  /twitter\.com\/i\/adsct/i,
  /platform\.twitter/i,
  /analytics\.twitter/i,

  // Microsoft
  /bat\.bing\.com/i,
  /clarity\.ms/i,
  /c\.bing\.com/i,

  // Ad networks
  /adnxs\.com/i,
  /adsrvr\.org/i,
  /criteo\.(com|net)/i,
  /demdex\.net/i,
  /everesttech\.net/i,
  /exelator\.com/i,
  /rubiconproject\.com/i,
  /pubmatic\.com/i,
  /openx\.net/i,
  /sharethrough\.com/i,
  /outbrain\.com/i,
  /taboola\.com/i,
  /moatads\.com/i,
  /doubleverify\.com/i,
  /chartbeat\.(com|net)/i,
  /yieldmo\.com/i,
  /sail-horizon\.com/i,
  /nativo\.com/i,
  /spotxchange\.com/i,

  // Analytics
  /hotjar\.com/i,
  /mouseflow\.com/i,
  /heap\.io/i,
  /segment\.com/i,
  /amplitude\.com/i,
  /mixpanel\.com/i,
  /branch\.io/i,
  /adjust\.com/i,
  /optimizely\.com/i,
  /fullstory\.com/i,
  /logrocket\.com/i,
  /sentry\.io/i,
  /newrelic\.com/i,
  /nr-data\.net/i,

  // Crypto miners
  /coinhive\.com/i,
  /coin-hive\.com/i,
  /jsecoin\.com/i,
  /crypto-loot\.com/i,
  /authedmine\.com/i,

  // Generic ad/tracking patterns
  /\/ads?\/[?&]/i,
  /\/track\/[?&]/i,
  /\/beacon\//i,
  /\/pixel\//i,
  /\/imp\.gif/i,
  /\/tracking\//i,
];

// ── Security Class ────────────────────────────────────────────────
class SecurityModule {
  constructor() {
    this.config = { ...SHIELDS_CONFIG };
    this.blockedRequests = 0;
    this.upgradedConnections = 0;
    this.fingerprintAttempts = 0;
  }

  /**
   * Check if a URL should be blocked.
   * Returns true for URLs matching blocked domains, tracker patterns,
   * or EasyList-style filter rules.
   */
  shouldBlock(url) {
    if (!this.config.adBlocking && !this.config.trackerBlocking) {
      return false;
    }

    try {
      const parsed = new URL(url);
      const hostname = parsed.hostname;

      // Check blocked domains
      if (BLOCKED_DOMAINS.some(d => hostname.includes(d))) {
        this.blockedRequests++;
        return true;
      }

      // Check tracker patterns
      if (this.config.trackerBlocking) {
        if (TRACKER_PATTERNS.some(p => p.test(url))) {
          this.blockedRequests++;
          return true;
        }
      }

      // Check custom filter rules (EasyList-style)
      if (this._customFilters && this._customFilters.length > 0) {
        if (this._customFilters.some(rule => this._matchesFilter(url, rule))) {
          this.blockedRequests++;
          return true;
        }
      }

      return false;
    } catch {
      return false;
    }
  }

  /**
   * Add a custom filter rule (EasyList-style).
   * Supported formats:
   *   - Domain pattern: ||example.com^  (block all requests to domain)
   *   - URL pattern: ||example.com/path*  (block matching URLs)
   *   - CSS selector: ##.ad-banner  (hide matching elements via injection)
   */
  addFilter(rule) {
    if (!this._customFilters) this._customFilters = [];
    if (!this._customFilters.includes(rule)) {
      this._customFilters.push(rule);
    }
  }

  /**
   * Remove a custom filter rule
   */
  removeFilter(rule) {
    if (!this._customFilters) return;
    const idx = this._customFilters.indexOf(rule);
    if (idx >= 0) this._customFilters.splice(idx, 1);
  }

  /**
   * Get all custom filter rules
   */
  getFilters() {
    return this._customFilters ? [...this._customFilters] : [];
  }

  /**
   * Get CSS selectors for element hiding (EasyList ## rules)
   */
  getCssHideSelectors() {
    if (!this._customFilters) return [];
    return this._customFilters
      .filter(r => r.includes('##'))
      .map(r => r.split('##')[1])
      .filter(Boolean);
  }

  /**
   * Check if a URL matches a filter rule
   */
  _matchesFilter(url, rule) {
    // Skip CSS selector rules (handled by getCssHideSelectors)
    if (rule.includes('##')) return false;

    // Domain pattern: ||example.com^
    if (rule.startsWith('||')) {
      const domain = rule.slice(2).replace(/\^$/, '');
      try {
        const hostname = new URL(url).hostname;
        return hostname === domain || hostname.endsWith('.' + domain);
      } catch {
        return false;
      }
    }

    // URL pattern (simple substring match)
    return url.includes(rule);
  }

  /**
   * True when the URL belongs to a known ad/tracker host. Used by the main
   * process to scope cookie filtering to trackers ONLY (Brave-standard mode)
   * so SSO/OAuth/iframe logins — which set cookies cross-site — keep working
   * and the user stays logged in.
   */
  isTracker(url) {
    try {
      const parsed = new URL(url);
      const hostname = parsed.hostname;
      if (BLOCKED_DOMAINS.some(d => hostname.includes(d))) return true;
      return TRACKER_PATTERNS.some(p => p.test(url));
    } catch {
      return false;
    }
  }

  /**
   * Upgrade HTTP to HTTPS
   */
  upgradeToHttps(url) {
    if (!this.config.httpsUpgrade) return url;

    if (url.startsWith("http://")) {
      this.upgradedConnections++;
      return url.replace("http://", "https://");
    }
    return url;
  }

  /**
   * Get security headers for requests
   */
  getSecurityHeaders() {
    const headers = {};

    if (this.config.doNotTrack) {
      headers["DNT"] = "1";
    }

    if (this.config.referrerPolicy) {
      headers["Referer"] = this.config.referrerPolicy;
    }

    return headers;
  }

  /**
   * Check if cookies should be allowed
   */
  shouldAllowCookies(domain, isThirdParty) {
    if (isThirdParty) {
      return this.config.thirdPartyCookies !== "block";
    }
    return this.config.firstPartyCookies === "allow";
  }

  /**
   * Get fingerprint protection data
   */
  getFingerprintProtection() {
    if (!this.config.fingerprintProtection) return null;

    return {
      // Randomize canvas fingerprint
      canvas: {
        noise: true,
        noiseLevel: 0.1,
      },
      // Randomize WebGL fingerprint
      webgl: {
        noise: true,
        vendor: "Google Inc. (Intel)",
        renderer: "ANGLE (Intel, Intel(R) UHD Graphics 630, OpenGL 4.5)",
      },
      // Randomize audio context
      audio: {
        noise: true,
        noiseLevel: 0.01,
      },
      // Spoof screen resolution
      screen: {
        width: 1920,
        height: 1080,
        colorDepth: 24,
      },
      // Spoof timezone
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    };
  }

  /**
   * Get security status
   */
  getStatus() {
    return {
      shields: this.config.adBlocking || this.config.trackerBlocking,
      adBlocking: this.config.adBlocking,
      trackerBlocking: this.config.trackerBlocking,
      fingerprintProtection: this.config.fingerprintProtection,
      httpsUpgrade: this.config.httpsUpgrade,
      blockedRequests: this.blockedRequests,
      upgradedConnections: this.upgradedConnections,
      fingerprintAttempts: this.fingerprintAttempts,
    };
  }

  /**
   * Toggle shields
   */
  toggleShields(enabled) {
    this.config.adBlocking = enabled;
    this.config.trackerBlocking = enabled;
    this.config.fingerprintProtection = enabled;
  }
}

// ── VPN Extension Manager ───────────────────────────────────────
// Manages VPN extensions installed in the browser. Supports installing,
// enabling, disabling, and removing VPN extensions.
const VPN_EXTENSIONS = {
  "windscribe-vpn": {
    id: "hnfanknocfeofodojlnbnckbeaicjodhm",
    name: "Windscribe VPN",
    description: "Free VPN with ad blocker. 10GB/month free.",
    chromeWebStore: "https://chrome.google.com/webstore/detail/windscribe-vpn/hnfanknocfeofodojlnbnckbeaicjodhm",
    icon: "🛡️",
    free: true,
    dataLimit: "10GB/month",
  },
  "proton-vpn": {
    id: "jplgfhpmjbgbjoffpmmnmfanmmdpdodo",
    name: "Proton VPN",
    description: "Free unlimited VPN from Proton. No ads, no logs.",
    chromeWebStore: "https://chrome.google.com/webstore/detail/proton-vpn/jplgfhpmjbgbjoffpmmnmfanmmdpdodo",
    icon: "🔒",
    free: true,
    dataLimit: "Unlimited",
  },
  "planet-vpn": {
    id: "hipncndjamdcmphkgngojegjblibadbe",
    name: "Planet VPN",
    description: "Free VPN with ad blocker. No signup required.",
    chromeWebStore: "https://chrome.google.com/webstore/detail/free-vpn-for-chrome-ad-bl/hipncndjamdcmphkgngojegjblibadbe",
    icon: "🌍",
    free: true,
    dataLimit: "Unlimited",
  },
  "browsec-vpn": {
    id: "epkoonefibelfhlmkbmclhgfiidhpnl",
    name: "Browsec VPN",
    description: "Free VPN for Chrome. Encrypt your traffic.",
    chromeWebStore: "https://chrome.google.com/webstore/detail/browsec-vpn/epkoonefibelfhlmkbmclhgfiidhpnl",
    icon: "🔐",
    free: true,
    dataLimit: "Unlimited",
  },
  "urban-vpn": {
    id: "fhcgjolkccmbidfldomjliifgaodjagh",
    name: "Urban VPN",
    description: "Free VPN with ad blocker. Fast and unlimited.",
    chromeWebStore: "https://chrome.google.com/webstore/detail/urban-vpn/fhcgjolkccmbidfldomjliifgaodjagh",
    icon: "🏙️",
    free: true,
    dataLimit: "Unlimited",
  },
};

// ── Adblocker Extensions ────────────────────────────────────────
const ADBLOCKER_EXTENSIONS = {
  "ublock-origin": {
    id: "cjpalhdlnbpafiamejdnhcphjbkeiagm",
    name: "uBlock Origin",
    description: "The best ad blocker. Efficient, lightweight, extensive.",
    chromeWebStore: "https://chrome.google.com/webstore/detail/ublock-origin/cjpalhdlnbpafiamejdnhcphjbkeiagm",
    icon: "🛡️",
    openSource: true,
  },
  "adblock-plus": {
    id: "cfhdojbkjhnklbfkdaibbbddcgncdjnd",
    name: "Adblock Plus",
    description: "The most popular ad blocker. Acceptable Ads enabled by default.",
    chromeWebStore: "https://chrome.google.com/webstore/detail/adblock-plus/cfhdojbkjhnklbfkdaibbbddcgncdjnd",
    icon: "🚫",
    openSource: false,
  },
  "adguard-adblocker": {
    id: "bgnkhhnnamicmpeenaelnjfhikgbkllg",
    name: "AdGuard AdBlocker",
    description: "Block ads, trackers, malware. Comprehensive protection.",
    chromeWebStore: "https://chrome.google.com/webstore/detail/adguard-adblocker/bgnkhhnnamicmpeenaelnjfhikgbkllg",
    icon: "🛡️",
    openSource: true,
  },
  "ghostery": {
    id: "mlomiejdfkolichcflejclcbmpeaniij",
    name: "Ghostery",
    description: "Block ads, stop trackers, speed up websites.",
    chromeWebStore: "https://chrome.google.com/webstore/detail/ghostery/mlomiejdfkolichcflejclcbmpeaniij",
    icon: "👻",
    openSource: false,
  },
  "brave-adblock": {
    id: "nomnklagpcmgamjmaoidigdcockkkonm",
    name: "Brave Ad Blocker",
    description: "Brave's built-in ad blocker as a Chrome extension.",
    chromeWebStore: "https://chrome.google.com/webstore/detail/brave-ad-blocker/nomnklagpcmgamjmaoidigdcockkkonm",
    icon: "🦁",
    openSource: true,
  },
};

// ── Extension Store ──────────────────────────────────────────────
// Provides a unified view of all available extensions (VPN + adblockers)
// and manages their installation state.
class ExtensionStore {
  constructor() {
    this._installed = new Map(); // extensionId -> { enabled, pinned }
  }

  /**
   * Get all available extensions (VPN + adblockers)
   */
  getAll() {
    const extensions = [];
    for (const [key, ext] of Object.entries(ADBLOCKER_EXTENSIONS)) {
      extensions.push({ ...ext, type: "adblocker", key });
    }
    for (const [key, ext] of Object.entries(VPN_EXTENSIONS)) {
      extensions.push({ ...ext, type: "vpn", key });
    }
    return extensions;
  }

  /**
   * Get VPN extensions only
   */
  getVPN() {
    return Object.entries(VPN_EXTENSIONS).map(([key, ext]) => ({
      ...ext, type: "vpn", key,
      installed: this._installed.has(ext.id),
      enabled: this._installed.get(ext.id)?.enabled ?? false,
    }));
  }

  /**
   * Get adblocker extensions only
   */
  getAdblockers() {
    return Object.entries(ADBLOCKER_EXTENSIONS).map(([key, ext]) => ({
      ...ext, type: "adblocker", key,
      installed: this._installed.has(ext.id),
      enabled: this._installed.get(ext.id)?.enabled ?? false,
    }));
  }

  /**
   * Mark an extension as installed
   */
  markInstalled(extensionId, enabled = true) {
    this._installed.set(extensionId, { enabled, pinned: false, installedAt: Date.now() });
  }

  /**
   * Toggle extension enabled state
   */
  toggle(extensionId) {
    const state = this._installed.get(extensionId);
    if (state) {
      state.enabled = !state.enabled;
      return state.enabled;
    }
    return false;
  }

  /**
   * Remove an extension
   */
  remove(extensionId) {
    this._installed.delete(extensionId);
  }

  /**
   * Get the Chrome Web Store install URL for an extension
   */
  getInstallUrl(key) {
    const all = { ...ADBLOCKER_EXTENSIONS, ...VPN_EXTENSIONS };
    for (const ext of Object.values(all)) {
      if (ext.id === key || key.includes(ext.id)) return ext.chromeWebStore;
    }
    return null;
  }
}

// ── Export ─────────────────────────────────────────────────────────
module.exports = {
  SecurityModule,
  ExtensionStore,
  SHIELDS_CONFIG,
  BLOCKED_DOMAINS,
  VPN_EXTENSIONS,
  ADBLOCKER_EXTENSIONS,
};
