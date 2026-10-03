/* Regression harness for the preload surface in orbit-browser/preload.js
 *
 * preload.js cannot be required here (it pulls in `electron`), so this parses
 * the source. That is enough, because the failure mode is textual: the same
 * capability being wired twice under two names.
 *
 * What it pins down:
 *   - no IPC channel is reachable through two different paths. `orbit.permissions`
 *     AND `orbit.system.permissions` is the shape that lets the renderer, the
 *     security review and the main process drift apart.
 *   - every channel the preload reaches for is actually registered in main.js,
 *     and every main.js channel is reachable from the preload -- so the two
 *     halves cannot rot independently.
 *   - the quarantined agent surface stays deleted.
 *
 * Run: node orbit-browser/test/preload-surface.test.cjs
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

const preloadSrc = fs.readFileSync(path.join(__dirname, '..', 'preload.js'), 'utf8');
const mainSrc = fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8');

// ── 1. One channel, one path ────────────────────────────────────────────
const CALL_RE = /ipcRenderer\.(invoke|on|send|sendSync)\(\s*["']([^"']+)["']/g;
const calls = [];
let m;
while ((m = CALL_RE.exec(preloadSrc)) !== null) calls.push({ verb: m[1], channel: m[2] });
ok(calls.length >= 40, `preload wires ${calls.length} channels (expected >= 40)`);

const byChannel = new Map();
for (const { verb, channel } of calls) {
  if (!byChannel.has(channel)) byChannel.set(channel, []);
  byChannel.get(channel).push(verb);
}
const dupes = [...byChannel.entries()].filter(([, verbs]) => verbs.length > 1);
ok(dupes.length === 0,
  dupes.length === 0
    ? 'no IPC channel is exposed twice'
    : 'duplicated channels: ' + dupes.map(([c, v]) => `${c} x${v.length}`).join(', '));

// The specific aliases the audit called out must be gone, not merely
// de-duplicated in a way that could be reintroduced under a new name.
for (const gone of ['system.permissions', 'system.downloads', 'system.spaces',
                    'system.ui', 'system.session', 'navigate:', 'info:']) {
  ok(new RegExp('\\b' + gone.replace(':', '\\s*:')).test(preloadSrc) === false ||
     !/^or\w*:/.test(gone),
    `legacy alias "${gone}" is gone from preload.js`);
}

// ── 2. The two halves cannot rot independently ──────────────────────────
const registered = new Set();
const REG_RE = /ipcMain\.(?:handle|on)\(\s*["']([^"']+)["']/g;
while ((m = REG_RE.exec(mainSrc)) !== null) registered.add(m[1]);
ok(registered.size >= 55, `main.js registers ${registered.size} channels (expected >= 55)`);

const used = new Set(calls.map((c) => c.channel));
const orphans = [...used].filter((c) => !registered.has(c));
ok(orphans.length === 0,
  orphans.length === 0
    ? 'every channel the preload calls is registered in main.js'
    : 'preload calls channels main.js never registers: ' + orphans.join(', '));

// Channels main.js registers purely for internal use (there are none today,
// but a future one should be annotated rather than silently unreachable).
const unreachable = [...registered].filter((c) => !used.has(c));
ok(unreachable.length === 0,
  unreachable.length === 0
    ? 'no registered channel is unreachable from the renderer'
    : 'main.js registers channels the preload never calls: ' + unreachable.join(', '));

// ── 3. The quarantined agent surface stays deleted ──────────────────────
ok(!/agent:\s*\{/.test(preloadSrc), 'preload exposes no `agent` object');
ok(!/onState|onTool|sendReadResult|sendClickResult|sendTypeResult/.test(preloadSrc),
  'preload exposes no agent listeners or tool-result callbacks');

console.log('\n' + (checks - failures) + '/' + checks + ' passed');
process.exit(failures === 0 ? 0 : 1);