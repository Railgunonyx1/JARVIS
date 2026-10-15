/* Electron version compatibility gate for orbit-browser.
 *
 * Orbit was pinned to Electron 28 (Chromium 120, Dec 2023). Electron supports
 * only the latest three majors, so 28 is end-of-life by many majors -- not
 * acceptable for a browser that renders untrusted web content on every tab.
 * This gate exists because the jump to 44 CANNOT be verified here: the main
 * process needs a display, so CI in this environment can only reason about
 * the source. It encodes Electron's published breaking-change list as a
 * denylist so the upgrade cannot silently rot back.
 *
 * Sources: electronjs.org/docs/latest/breaking-changes (v29 through v44).
 *
 * Run: node orbit-browser/test/electron-compat.test.cjs
 */

const fs = require('fs');
const path = require('path');

let checks = 0;
let failures = 0;

function ok(cond, label) {
  checks += 1;
  if (cond) console.log('  PASS  ' + label);
  else { failures += 1; console.log('  FAIL  ' + label); }
}

const root = path.join(__dirname, '..');
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));

// ── Walk the app's own sources (never node_modules, never this test) ───
// The denylist below lives in this file, so scanning it would report every
// removed API as a hit -- the gate would fail on its own source text.
const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', 'out', 'build', 'test']);
function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP_DIRS.has(entry.name)) continue;
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(p, out);
    else if (/\.(js|cjs|mjs|html)$/.test(entry.name)) out.push(p);
  }
  return out;
}
const files = walk(root);
ok(files.length >= 30, `scanned ${files.length} app source files`);
const sources = files.map((f) => ({ file: path.relative(root, f).split(path.sep).join('/'), text: fs.readFileSync(f, 'utf8') }));

function hits(re) {
  const out = [];
  for (const { file, text } of sources) {
    const re2 = new RegExp(re.source, re.flags.includes('g') ? re.flags : re.flags + 'g');
    let m;
    while ((m = re2.exec(text)) !== null) {
      const line = text.slice(0, m.index).split('\n').length;
      out.push(`${file}:${line} ${m[0].trim()}`);
      if (out.length >= 4) return out;
    }
  }
  return out;
}

// ── 1. The version pin itself ────────────────────────────────────────────
const spec = (pkg.devDependencies || {}).electron || '';
ok(/^\d+\.\d+\.\d+$/.test(spec),
  `electron is pinned to an exact version (${spec || 'MISSING'})`);
const major = parseInt(String(spec).replace(/^[^\d]*/, ''), 10);
ok(Number.isFinite(major) && major >= 44,
  `electron major >= 44 (Chromium 152) — got ${spec}`);
ok(String((pkg.devDependencies || {})['electron-builder'] || '').match(/^\D*(\d+)/)?.[1] >= 26
   ? true : Number((pkg.devDependencies || {})['electron-builder'] || '').replace(/[^\d].*$/, '') >= 26,
  'electron-builder >= 26 (required since Electron 42 downloads its binary on demand)');

// Electron can only be exercised here as far as "the binary launches".
const installedPath = path.join(root, 'node_modules', 'electron', 'package.json');
if (fs.existsSync(installedPath)) {
  const installed = JSON.parse(fs.readFileSync(installedPath, 'utf8')).version;
  ok(installed === spec, `installed electron matches the pin (${installed} vs ${spec})`);
} else {
  ok(false, 'node_modules/electron is installed and matches the pin');
}

// ── 2. APIs removed between 28 and 44 ────────────────────────────────────
// Each entry: [removedIn, human label, regex that finds the removed usage].
const REMOVED = [
  [29, "webContents/webview 'crashed' event", /['"]crashed['"]/],
  [29, "app 'renderer-process-crashed' event", /['"]renderer-process-crashed['"]/],
  [29, "app 'gpu-process-crashed' event", /['"]gpu-process-crashed['"]/],
  [28, 'BrowserWindow.setTrafficLightPosition', /\.setTrafficLightPosition\s*\(/],
  [28, 'BrowserWindow.getTrafficLightPosition', /\.getTrafficLightPosition\s*\(/],
  [28, 'ipcRenderer.sendTo', /\.sendTo\s*\(/],
  [28, 'app.runningUnderRosettaTranslation', /runningUnderRosettaTranslation/],
  [30, 'process.getIOCounters', /\.getIOCounters\s*\(/],
  [31, 'WebSQL openDatabase', /\.openDatabase\s*\(/],
  [32, 'File.path (use webUtils.getPathForFile)', /\.files\s*\[\s*0\s*\]\s*\.path\b/],
  [36, 'systemPreferences.isAeroGlassEnabled', /isAeroGlassEnabled/],
  [36, 'session.loadExtension (moved to session.extensions)', /\.loadExtension\s*\(/],
  [36, 'session.removeExtension (moved to session.extensions)', /\.removeExtension\s*\(/],
  [36, 'session.getAllExtensions (moved to session.extensions)', /\.getAllExtensions\s*\(/],
  [36, 'PrinterInfo.isDefault / .status', /\.isDefault\b/],
  [36, 'clearStorageData quota type "syncable"', /['"]syncable['"]/],
  [35, 'session.setPreloads (use registerPreloadScript)', /\.setPreloads\s*\(/],
  [38, "webContents 'plugin-crashed' event", /['"]plugin-crashed['"]/],
  [44, 'app.isUnityRunning', /\.isUnityRunning\s*\(/],
  // Deprecated in 32 and still callable, but every use is a future error and
  // a deprecation warning in the console.
  [32, 'webContents navigation methods (use navigationHistory)',
    /(?:webContents|\.webContents)\.(?:canGoBack|canGoForward|goBack|goForward|goToIndex|goToOffset|canGoToOffset|clearHistory)\s*\(/],
];

for (const [since, label, re] of REMOVED) {
  const found = hits(re);
  ok(found.length === 0,
    found.length === 0
      ? `no use of ${label} (removed/deprecated in Electron ${since})`
      : `${label} is gone in ${since}+:\n         ${found.join('\n         ')}`);
}

// ── 3. Electron 44 removals that need context, not a regex ───────────────
// The electron `clipboard` module is no longer exposed to renderer processes
// (removed in 44). navigator.clipboard is the supported replacement and is
// fine; `clipboard.writeText(...)` reached through `require('electron')` in a
// preload is not.
const RENDERER_FILES = /^(preload\.js|guest-preload\.js|src\/.*)$/;
const clipboardHits = [];
for (const { file, text } of sources) {
  if (!RENDERER_FILES.test(file)) continue;
  const re = /(?<!navigator\.)\bclipboard\.(?:readText|writeText|read|write|has|clear)\s*\(/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    clipboardHits.push(`${file}: ${text.slice(0, m.index).split('\n').length} ${m[0]}`);
  }
}
ok(clipboardHits.length === 0,
  clipboardHits.length === 0
    ? 'no renderer-side use of the electron clipboard module (removed in 44)'
    : 'electron clipboard module used from renderer:\n         ' + clipboardHits.join('\n         '));

// console-message gained a structured Event argument in 35; the old
// (event, level, message, line, sourceId) signature silently reads undefined.
for (const { file, text } of sources) {
  const re = /['"]console-message['"]\s*,\s*(?:async\s*)?\(([^)]*)\)/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const params = m[1].split(',').map((s) => s.trim()).filter(Boolean);
    ok(params.length <= 2,
      `console-message handler in ${file} uses the v35+ event signature`);
  }
}

// ── 4. Positive expectations for the 28 -> 44 migration ──────────────────
const mainSrc = fs.readFileSync(path.join(root, 'main.js'), 'utf8');
ok(!/protocol\.register(?:File|Buffer|String|Http)Protocol/.test(mainSrc),
  'custom protocol uses protocol.handle + net.fetch (Windows path-safe since 33)');
ok(/net\.fetch\(\s*pathToFileURL/.test(mainSrc),
  'orbit:// is served through net.fetch(pathToFileURL(...)), the 33+ safe form');
ok(/['"]render-process-gone['"]/.test(mainSrc),
  'tab crash capture uses render-process-gone (the crashed event is gone in 29)');
ok(/setWindowOpenHandler/.test(mainSrc),
  'guest window.open policy goes through setWindowOpenHandler');

// Every top-level runtime module main.js requires must be inside the
// electron-builder `files` globs, or the packaged app throws MODULE_NOT_FOUND
// on first launch and the build still "succeeds".
const buildFiles = (pkg.build && pkg.build.files) || [];
const globCovers = (mod) => buildFiles.some((g) =>
  g === '*.js' || g === mod ||
  (g.endsWith('/**/*') && mod.startsWith(g.slice(0, -5))) ||
  (g.endsWith('/*') && mod.startsWith(g.slice(0, -2))));
// Extensionless relative requires resolve to <name>.js; catch both spellings
// or this check silently passes on zero matches.
const requiredTop = [...mainSrc.matchAll(/require\(['"]\.\/([A-Za-z0-9._-]+?)(?:\.js)?['"]\)/g)]
  .map((m) => m[1] + '.js');
ok(requiredTop.length > 0, `found ${requiredTop.length} relative requires in main.js`);
const uncovered = requiredTop.filter((mod) => !globCovers(mod));
ok(uncovered.length === 0,
  uncovered.length === 0
    ? `all ${requiredTop.length} modules main.js requires are packaged`
    : 'these required modules are NOT in electron-builder files[]: ' + uncovered.join(', '));

// The seeded <webview> resolves its guest preload by relative path, so that
// file must ship too even though main.js never requires it.
ok(globCovers('guest-preload.js'), 'guest-preload.js is inside the packaged files[]');

console.log('\n' + (checks - failures) + '/' + checks + ' passed');
process.exit(failures === 0 ? 0 : 1);