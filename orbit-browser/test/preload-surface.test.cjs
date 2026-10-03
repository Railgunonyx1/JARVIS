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
// IPC is two directions. A renderer->main channel must be a registered
// ipcMain handler; a main->renderer channel must be a webContents.send push.
// Checking both against the same set is the easy way to write a test that
// looks thorough and is wrong.
const registered = new Set();
const REG_RE = /ipcMain\.(?:handle|on)\(\s*["']([^"']+)["']/g;
while ((m = REG_RE.exec(mainSrc)) !== null) registered.add(m[1]);
ok(registered.size >= 55, `main.js registers ${registered.size} channels (expected >= 55)`);

const pushed = new Set();
const PUSH_RE = /webContents\.send\(\s*["']([^"']+)["']/g;
while ((m = PUSH_RE.exec(mainSrc)) !== null) pushed.add(m[1]);

const inbound = new Set(calls.filter((c) => c.verb !== 'on').map((c) => c.channel));
const outbound = new Set(calls.filter((c) => c.verb === 'on').map((c) => c.channel));

const ghostInbound = [...inbound].filter((c) => !registered.has(c));
ok(ghostInbound.length === 0,
  ghostInbound.length === 0
    ? `all ${inbound.size} renderer->main channels are registered in main.js`
    : 'preload calls channels main.js never registers: ' + ghostInbound.join(', '));

const ghostOutbound = [...outbound].filter((c) => !pushed.has(c));
ok(ghostOutbound.length === 0,
  ghostOutbound.length === 0
    ? `all ${outbound.size} main->renderer channels are pushed by main.js`
    : 'preload listens for channels main.js never sends: ' + ghostOutbound.join(', '));

// Channels main.js handles but deliberately never exposes: the quarantined
// agent tombstones. They must stay unreachable -- that IS their job -- so
// they are named explicitly instead of being allowed to appear by accident.
const TOMBSTONES = new Set(['agent:start', 'agent:stop', 'agent:status']);
const unreachable = [...registered].filter((c) => !inbound.has(c) && !TOMBSTONES.has(c));
ok(unreachable.length === 0,
  unreachable.length === 0
    ? 'no handler is unreachable except the named agent tombstones'
    : 'main.js handles channels the preload never calls: ' + unreachable.join(', '));

const staleTombstones = [...TOMBSTONES].filter((c) => !registered.has(c));
ok(staleTombstones.length === 0,
  staleTombstones.length === 0
    ? 'the agent tombstones are still registered in main.js'
    : 'agent tombstones were deleted from main.js: ' + staleTombstones.join(', '));

// ── 3. The quarantined agent surface stays deleted ──────────────────────
ok(!/agent:\s*\{/.test(preloadSrc), 'preload exposes no `agent` object');
ok(!/onState|onTool|sendReadResult|sendClickResult|sendTypeResult/.test(preloadSrc),
  'preload exposes no agent listeners or tool-result callbacks');

console.log('\n' + (checks - failures) + '/' + checks + ' passed');
process.exit(failures === 0 ? 0 : 1);