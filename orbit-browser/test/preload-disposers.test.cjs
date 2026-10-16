/* Behavioural regression harness for preload.js event disposers.
 *
 * preload-surface.test.cjs parses preload.js textually (channel drift). This
 * one EXECUTES preload.js against a stubbed `electron` module to pin the
 * subscription lifecycle:
 *   - every listener method returns a disposer function
 *   - the disposer removes exactly its own wrapped listener
 *   - other subscriptions on the same channel keep firing after a dispose
 *   - a disposed callback never fires again (and double-dispose is safe)
 *
 * Run: ELECTRON_RUN_AS_NODE=1 electron orbit-browser/test/preload-disposers.test.cjs
 *      (or: node orbit-browser/test/preload-disposers.test.cjs)
 */

const Module = require('module');
const path = require('path');

let checks = 0;
let failures = 0;

function ok(cond, label) {
  checks += 1;
  if (cond) console.log('  PASS  ' + label);
  else { failures += 1; console.log('  FAIL  ' + label); }
}

// ── Stub `electron` and execute the real preload ──────────────────────
const handlers = new Map();

const fakeRenderer = {
  on(channel, listener) {
    if (!handlers.has(channel)) handlers.set(channel, new Set());
    handlers.get(channel).add(listener);
  },
  removeListener(channel, listener) {
    const set = handlers.get(channel);
    if (set) set.delete(listener);
  },
  invoke: async () => ({}),
  send: () => {},
  sendSync: () => 'token',
};

let exposed = null;
const fakeElectron = {
  contextBridge: {
    exposeInMainWorld(name, api) { exposed = { name, api }; },
  },
  ipcRenderer: fakeRenderer,
};

const originalLoad = Module._load;
Module._load = function (request, ...rest) {
  if (request === 'electron') return fakeElectron;
  return originalLoad.call(this, request, ...rest);
};
require(path.join(__dirname, '..', 'preload.js'));
Module._load = originalLoad;

function emit(channel, payload) {
  const set = handlers.get(channel);
  if (!set) return;
  for (const listener of [...set]) listener({}, payload);
}

console.log('preload-disposers');

const orbit = exposed && exposed.api;
ok(!!orbit, 'preload exposes the `orbit` surface via contextBridge');
ok(exposed && exposed.name === 'orbit', 'exposed under the name "orbit"');

// ── Every listener method returns a disposer ─────────────────────────
const LISTENERS = [
  [orbit.jarvis, 'onStatus'], [orbit.jarvis, 'onChat'],
  [orbit.jarvis, 'onAgentEvent'], [orbit.jarvis, 'onApproval'],
  [orbit.jarvis, 'onMessage'],
  [orbit.on, 'tabCreated'], [orbit.on, 'tabClosed'],
  [orbit.on, 'tabActivated'], [orbit.on, 'navigateTo'],
  [orbit.on, 'tabSleep'], [orbit.on, 'tabWake'],
  [orbit.on, 'spaceChanged'],
  [orbit.downloads, 'onUpdated'],
];

for (const [surface, method] of LISTENERS) {
  const dispose = surface[method](() => {});
  ok(typeof dispose === 'function', method + '() returns a disposer');
  dispose(); // probe subscription must not linger into later assertions
}

// ── Independent removal on the same channel ──────────────────────────
const seenA = [];
const seenB = [];
const disposeA = orbit.jarvis.onChat((p) => seenA.push(p));
const disposeB = orbit.jarvis.onChat((p) => seenB.push(p));

emit('jarvis-chat', 'm1');
disposeA();
disposeA(); // double-dispose must be safe
emit('jarvis-chat', 'm2');
disposeB();

ok(JSON.stringify(seenA) === JSON.stringify(['m1']),
  'disposed callback never fires again (A saw only its pre-dispose event)');
ok(JSON.stringify(seenB) === JSON.stringify(['m1', 'm2']),
  'sibling subscription on the same channel keeps firing after A is disposed');
ok(((handlers.get('jarvis-chat') || new Set()).size) === 0,
  'both wrapped listeners are gone from the channel');

// ── Disposer detaches exactly its own listener ───────────────────────
const seenNav = [];
const disposeNav = orbit.on.navigateTo((u) => seenNav.push(u));
emit('navigate-to', 'https://one');
disposeNav();
emit('navigate-to', 'https://two');
ok(JSON.stringify(seenNav) === JSON.stringify(['https://one']),
  'navigateTo disposer detaches only its own listener');

// ── Payload passthrough (downloads list arrives unwrapped) ───────────
const seenDl = [];
const disposeDl = orbit.downloads.onUpdated((list) => seenDl.push(list));
emit('downloads-updated', ['file-a']);
disposeDl();
ok(JSON.stringify(seenDl) === JSON.stringify([['file-a']]),
  'downloads.onUpdated delivers the payload and detaches on dispose');

console.log('\n' + (checks - failures) + '/' + checks + ' passed');
process.exit(failures === 0 ? 0 : 1);
