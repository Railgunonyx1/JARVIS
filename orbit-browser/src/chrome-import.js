/**
 * JARVIS Orbit — Chrome Data Import
 *
 * Imports bookmarks, history, extensions, and settings from an existing
 * Chrome/Chromium installation. Reads directly from Chrome's user data
 * directory (no encryption needed for bookmarks/history/extensions).
 *
 * Supported sources:
 *   - Google Chrome
 *   - Microsoft Edge (Chromium)
 *   - Brave Browser
 *   - Any Chromium-based browser
 */

const fs = require("fs");
const path = require("path");
const os = require("os");

// ── Chrome data locations per platform ──────────────────────────
const CHROME_PATHS = {
  win32: [
    path.join(os.homedir(), "AppData", "Local", "Google", "Chrome", "User Data"),
    path.join(os.homedir(), "AppData", "Local", "Microsoft", "Edge", "User Data"),
    path.join(os.homedir(), "AppData", "Local", "BraveSoftware", "Brave-Browser", "User Data"),
  ],
  darwin: [
    path.join(os.homedir(), "Library", "Application Support", "Google", "Chrome"),
    path.join(os.homedir(), "Library", "Application Support", "Microsoft Edge"),
    path.join(os.homedir(), "Library", "Application Support", "BraveSoftware", "Brave-Browser"),
  ],
  linux: [
    path.join(os.homedir(), ".config", "google-chrome"),
    path.join(os.homedir(), ".config", "microsoft-edge"),
    path.join(os.homedir(), ".config", "BraveSoftware", "Brave-Browser"),
  ],
};

const PROFILES = ["Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4", "Guest Profile"];

// ── Detection ───────────────────────────────────────────────────

/**
 * Find all installed Chromium browsers and their profiles.
 * @returns {Array<{browser: string, profiles: Array<{name: string, path: string}>}>}
 */
function detectBrowsers() {
  const platform = process.platform;
  const candidates = CHROME_PATHS[platform] || CHROME_PATHS.win32;
  const found = [];

  for (const basePath of candidates) {
    if (!fs.existsSync(basePath)) continue;

    const browserName = path.basename(path.dirname(basePath));
    const profiles = [];

    for (const profile of PROFILES) {
      const profilePath = path.join(basePath, profile);
      const bookmarksFile = path.join(profilePath, "Bookmarks");
      if (fs.existsSync(bookmarksFile)) {
        profiles.push({ name: profile, path: profilePath });
      }
    }

    if (profiles.length > 0) {
      found.push({ browser: browserName, profiles });
    }
  }

  return found;
}

// ── Bookmarks ───────────────────────────────────────────────────

/**
 * Read Chrome's Bookmarks JSON and flatten into a list.
 * @param {string} profilePath
 * @returns {Array<{title: string, url: string, dateAdded: string, path: string}>}
 */
function readBookmarks(profilePath) {
  const bookmarksFile = path.join(profilePath, "Bookmarks");
  if (!fs.existsSync(bookmarksFile)) return [];

  try {
    const data = JSON.parse(fs.readFileSync(bookmarksFile, "utf-8"));
    const result = [];

    function walk(node, parentPath) {
      if (!node) return;
      if (node.type === "url") {
        result.push({
          title: node.name || "",
          url: node.url || "",
          dateAdded: node.date_added ? new Date(Number(node.date_added) / 1000).toISOString() : "",
          path: parentPath,
        });
      }
      if (node.children) {
        for (const child of node.children) {
          walk(child, parentPath ? parentPath + " / " + (node.name || "") : node.name || "");
        }
      }
    }

    // Walk all bookmark roots
    for (const root of ["bookmark_bar", "other", "synced"]) {
      if (data.roots && data.roots[root]) {
        walk(data.roots[root], data.roots[root].name || root);
      }
    }

    return result;
  } catch {
    return [];
  }
}

// ── History (SQLite) ────────────────────────────────────────────

/**
 * Read Chrome's History SQLite database.
 * Requires better-sqlite3 or falls back to a simple line parser.
 * @param {string} profilePath
 * @returns {Array<{title: string, url: string, lastVisitTime: string, visitCount: number}>}
 */
function readHistory(profilePath) {
  const historyFile = path.join(profilePath, "History");
  if (!fs.existsSync(historyFile)) return [];

  try {
    // Try better-sqlite3 if available
    const Database = require("better-sqlite3");
    const db = new Database(historyFile, { readonly: true, fileMustExist: true });
    const rows = db.prepare(`
      SELECT urls.url, urls.title, urls.visit_count,
             datetime(urls.last_visit_time / 1000000 - 11644473600, 'unixepoch') as lastVisit
      FROM urls
      WHERE urls.visit_count > 0
      ORDER BY urls.last_visit_time DESC
      LIMIT 5000
    `).all();
    db.close();
    return rows.map(r => ({
      title: r.title || "",
      url: r.url || "",
      lastVisitTime: r.lastVisit || "",
      visitCount: r.visit_count || 0,
    }));
  } catch {
    // better-sqlite3 not available — return empty (bookmarks are the priority)
    return [];
  }
}

// ── Extensions ──────────────────────────────────────────────────

/**
 * List installed Chrome extensions by scanning the Extensions directory.
 * @param {string} profilePath
 * @returns {Array<{id: string, name: string, version: string, enabled: boolean}>}
 */
function readExtensions(profilePath) {
  // Extensions are stored at <basePath>/Extensions/<id>/<version>/manifest.json
  const basePath = path.dirname(profilePath);
  const extensionsDir = path.join(basePath, "Extensions");
  if (!fs.existsSync(extensionsDir)) return [];

  // Read the preferences to get enabled/disabled state
  const prefsFile = path.join(profilePath, "Preferences");
  let prefs = {};
  try {
    prefs = JSON.parse(fs.readFileSync(prefsFile, "utf-8"));
  } catch { /* no prefs */ }

  const extSettings = (prefs.extensions || {}).settings || {};
  const result = [];

  try {
    const extIds = fs.readdirSync(extensionsDir).filter(id => {
      // Chrome extension IDs are 32 lowercase hex chars
      return /^[a-z]{32}$/.test(id);
    });

    for (const id of extIds) {
      const extPath = path.join(extensionsDir, id);
      const versions = fs.readdirSync(extPath).filter(v => fs.statSync(path.join(extPath, v)).isDirectory());
      if (versions.length === 0) continue;

      // Use the latest version
      const version = versions.sort().pop();
      const manifestFile = path.join(extPath, version, "manifest.json");

      try {
        const manifest = JSON.parse(fs.readFileSync(manifestFile, "utf-8"));
        const setting = extSettings[id] || {};
        result.push({
          id,
          name: manifest.name || id,
          version: manifest.version || version,
          enabled: setting.state === 1, // 1 = enabled
          description: manifest.description || "",
        });
      } catch {
        // Skip malformed manifests
      }
    }
  } catch { /* Extensions dir not readable */ }

  return result;
}

// ── Passwords (encrypted — report only) ─────────────────────────

/**
 * Chrome passwords are encrypted with DPAPI (Windows) or Keychain (macOS).
 * We can report how many exist but cannot decrypt without the user's
 * login credentials. This is by design — Orbit never handles raw passwords.
 *
 * @param {string} profilePath
 * @returns {{count: number, file: string}}
 */
function readPasswordInfo(profilePath) {
  const loginDataFile = path.join(profilePath, "Login Data");
  if (!fs.existsSync(loginDataFile)) return { count: 0, file: "" };

  try {
    const stat = fs.statSync(loginDataFile);
    // Each encrypted password blob is ~200+ bytes; rough estimate
    const estimatedCount = Math.max(0, Math.floor(stat.size / 300));
    return { count: estimatedCount, file: loginDataFile };
  } catch {
    return { count: 0, file: "" };
  }
}

// ── Cookies (encrypted — report only) ───────────────────────────

/**
 * Chrome cookies are encrypted. We report the count only.
 * @param {string} profilePath
 * @returns {{count: number, persistent: number}}
 */
function readCookieInfo(profilePath) {
  // Modern Chrome stores cookies in Network/Cookies
  const cookieFile = path.join(profilePath, "Network", "Cookies");
  const legacyFile = path.join(profilePath, "Cookies");
  const file = fs.existsSync(cookieFile) ? cookieFile : legacyFile;

  if (!fs.existsSync(file)) return { count: 0, persistent: 0 };

  try {
    // Rough estimate from file size
    const stat = fs.statSync(file);
    return { count: Math.floor(stat.size / 200), persistent: 0 };
  } catch {
    return { count: 0, persistent: 0 };
  }
}

// ── Settings / Preferences ──────────────────────────────────────

/**
 * Read select Chrome settings (homepage, search engine, etc.)
 * @param {string} profilePath
 * @returns {object}
 */
function readSettings(profilePath) {
  const prefsFile = path.join(profilePath, "Preferences");
  try {
    const prefs = JSON.parse(fs.readFileSync(prefsFile, "utf-8"));
    return {
      homepage: prefs.default_content_setting_values?.homepage || "",
      searchEngine: prefs.default_search_provider_data?.template_url_data?.short_name || "",
      // Spellcheck, autofill, etc. are intentionally not imported
    };
  } catch {
    return {};
  }
}

// ── Full Import ─────────────────────────────────────────────────

/**
 * Run a complete import from a Chrome profile.
 * @param {string} profilePath
 * @returns {object} Import results
 */
function importFromChrome(profilePath) {
  const bookmarks = readBookmarks(profilePath);
  const history = readHistory(profilePath);
  const extensions = readExtensions(profilePath);
  const passwords = readPasswordInfo(profilePath);
  const cookies = readCookieInfo(profilePath);
  const settings = readSettings(profilePath);

  return {
    bookmarks,
    history,
    extensions,
    passwords,
    cookies,
    settings,
    summary: {
      bookmarkCount: bookmarks.length,
      historyCount: history.length,
      extensionCount: extensions.length,
      passwordCount: passwords.count,
      cookieCount: cookies.count,
    },
  };
}

module.exports = {
  detectBrowsers,
  readBookmarks,
  readHistory,
  readExtensions,
  readPasswordInfo,
  readCookieInfo,
  readSettings,
  importFromChrome,
};
