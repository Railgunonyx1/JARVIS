/**
 * JARVIS Orbit — Security Module
 *
 * Implements security features inspired by Brave Shields, Ungoogled Chromium,
 * and Edge Enhanced Security.
 *
 * Features:
 * - Ad/tracker blocking
 * - Fingerprint protection
 * - HTTPS upgrade
 * - Cookie controls
 * - Telemetry blocking
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

// ── Blocked Domains ───────────────────────────────────────────────
const BLOCKED_DOMAINS = [
  // Telemetry
  "clients1.google.com",
  "clients2.google.com",
  "www.google-analytics.com",
  "google-analytics.com",
  "analytics.google.com",
  "doubleclick.net",
  "ads.google.com",
  "pagead2.googlesyndication.com",

  // Trackers
  "facebook.com/tr",
  "connect.facebook.net",
  "platform.twitter.com",
  "syndication.twitter.com",
  "bat.bing.com",
  "clarity.ms",

  // Fingerprinting
  "fingerprint.com",
  "fpjs.io",
  "permsapi.com",
];

// ── Trackers Database ─────────────────────────────────────────────
const TRACKER_PATTERNS = [
  /google-analytics\.com/i,
  /googletagmanager\.com/i,
  /doubleclick\.net/i,
  /facebook\.com\/tr/i,
  /connect\.facebook\.net/i,
  /twitter\.com\/i\/adsct/i,
  /bat\.bing\.com/i,
  /clarity\.ms/i,
  /hotjar\.com/i,
  /mouseflow\.com/i,
  /heap\.io/i,
  /segment\.com/i,
  /amplitude\.com/i,
  /mixpanel\.com/i,
  /branch\.io/i,
  /adjust\.com/i,
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
   * Check if a URL should be blocked
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

      return false;
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

// ── Export ─────────────────────────────────────────────────────────
module.exports = { SecurityModule, SHIELDS_CONFIG, BLOCKED_DOMAINS };
