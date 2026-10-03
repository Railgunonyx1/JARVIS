/* Regression harness for orbit-browser/ipc-guard.js
 *
 * The main process cannot be launched in CI here, so the guard's trust
 * decision is factored into a pure, electron-free module and tested under
 * plain `node`. Run: node orbit-browser/test/ipc-guard.test.cjs
 *
 * What it pins down:
 *   - the chrome renderer and its DevTools are allowed
 *   - registered tab guests are allowed, by stable webContents.id
 *   - an UNREGISTERED webContents is refused -- the case that matters, since
 *     any webContents able to reach ipcRenderer can invoke any channel
 *   - refusals fail closed: handle() throws, on() drops silently
 *   - argument validation is NOT a substitute: a well-formed payload from an
 *     untrusted sender is still refused
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { classifySender, guardHandler, guardListener, BOOTSTRAP_CHANNELS } =
  require('../ipc-guard.js');

let checks = 0;
let failures = 0;

function ok(cond, label) {
  checks += 1;
  if (cond) console.log('  PASS  ' + label);
  else { failures += 1; console.log('  FAIL  ' + label); }
}

// ── Fixtures ────────────────────────────────────────────────────────────
const mainWC = { id: 1 };
mainWC.devToolsWebContents = { id: 2 };
const guestA = { id: 42 };
const guestB = { id: 43 };
const attacker = { id: 1337 };

function ctx(over) {
  return Object.assign({
    mainWebContents: mainWC,
    guestIds: [42, 43],
    isDevTools: true,
  }, over || {});
}

console.log('ipc-guard.js');

// ── Allow-list ──────────────────────────────────────────────────────────
ok(classifySender({ sender: mainWC }, ctx()).ok, 'chrome renderer is trusted');
ok(classifySender({ sender: mainWC.devToolsWebContents }, ctx()).ok,
  'DevTools of the main window is trusted');

ok(classifySender({ sender: guestA }, ctx()).ok, 'registered guest A is trusted');
ok(classifySender({ sender: guestB }, ctx()).ok, 'registered guest B is trusted');

// ── Refusal: the security case ──────────────────────────────────────────
const denied = classifySender({ sender: attacker }, ctx());
ok(!denied.ok, 'unregistered webContents is refused');
ok(/untrusted/.test(denied.reason || ''), 'refusal says why', denied.reason);
ok(/1337/.test(denied.reason || ''), 'refusal names the offending id', denied.reason);

ok(!classifySender({}, ctx()).ok, 'event with no sender is refused');
ok(!classifySender(null, ctx()).ok, 'null event is refused');
ok(!classifySender({ sender: {} }, ctx()).ok, 'sender with no id is refused');

// A newly window.open'd tab that has not been attached yet must NOT inherit
// trust just because it lives in the same process.
ok(!classifySender({ sender: { id: 999 } }, ctx()).ok,
  'unattached popup is refused');

// ── Window not ready ────────────────────────────────────────────────────
ok(!classifySender({ sender: attacker }, { mainWebContents: null, guestIds: [] }).ok,
  'refused while no window exists');
ok(classifySender({ sender: mainWC },
  { mainWebContents: null, guestIds: [], allowBootstrap: true }).ok,
  'bootstrap channel allowed before the window is stored');

// ── bootstrap is a RACE exemption, not a trust exemption ────────────────
// orbit:get-bridge-token hands out the secret that authenticates every JARVIS
// browser call. Treating the bootstrap set as "carries no capability" made
// ANY webContents able to read it -- caught by the runtime smoke test, where an
// unlisted second window came back holding the token.
ok(!classifySender({ sender: attacker }, ctx({ allowBootstrap: true })).ok,
  'allowBootstrap does NOT excuse an unknown sender when a window exists');
ok(!classifySender({ sender: { id: 999 } }, ctx({ allowBootstrap: true })).ok,
  'allowBootstrap does NOT excuse an unattached popup');

// ── Multiple chrome windows ─────────────────────────────────────────────
// createWindow() reassigns mainWindow, so trusting only that reference locks
// the first window out the moment a second one opens.
const windowA = { id: 1 };
const windowB = { id: 7 };
const twoCtx = { mainWebContents: windowB, chromeIds: [1, 7], guestIds: [], isDevTools: true };
ok(classifySender({ sender: windowA }, twoCtx).ok,
  'the older chrome window stays trusted after a second window opens');
ok(classifySender({ sender: windowB }, twoCtx).ok, 'the newest chrome window is trusted');
ok(!classifySender({ sender: attacker }, twoCtx).ok,
  'an unknown sender is still refused with two windows open');

// ── Guests added at runtime are picked up (context is read per message) ──
const growing = { mainWebContents: mainWC, guestIds: [42], isDevTools: true };
ok(!classifySender({ sender: guestB }, growing).ok, 'guest B refused before attach');
growing.guestIds = [42, 43];
ok(classifySender({ sender: guestB }, growing).ok, 'guest B trusted after attach');

// ── guardHandler: fail closed ───────────────────────────────────────────
(async function () {
  let reached = 0;
  const ctxFn = () => ctx();
  const rejected = [];
  const guarded = guardHandler(async (event, ...rest) => {
    reached += 1;
    return 'ok:' + rest.join(',');
  }, ctxFn, (reason) => rejected.push(reason));

  ok(await guarded({ sender: mainWC }, 'a', 'b') === 'ok:a,b',
    'trusted sender reaches the handler with its args intact');
  ok(reached === 1, 'handler ran exactly once for the trusted sender');

  let threw = false;
  try {
    await guarded({ sender: attacker }, 'https://evil.example');
  } catch (err) {
    threw = true;
    ok(/untrusted sender/.test(err.message), 'rejection message names the problem', err.message);
  }
  ok(threw, 'untrusted sender makes handle() reject, not silently succeed');
  ok(reached === 1, 'handler NEVER ran for the untrusted sender');
  ok(rejected.length === 1 && /1337/.test(rejected[0]), 'rejection is reported to the logger');

  // ── guardListener: drop, do not throw ──────────────────────────────────
  let ran = 0;
  const rejectedOn = [];
  const guardedOn = guardListener(() => { ran += 1; }, ctxFn, (r) => rejectedOn.push(r));
  guardedOn({ sender: mainWC });
  ok(ran === 1, 'trusted listener fires');
  let listenerThrew = false;
  try { guardedOn({ sender: attacker }); }
  catch (err) { listenerThrew = true; }
  ok(!listenerThrew, 'untrusted listener is dropped WITHOUT throwing into the sender');
  ok(ran === 1, 'untrusted listener never fired');
  ok(rejectedOn.length === 1, 'dropped listener is reported to the logger');

  // ── Bootstrap set is not a hole ───────────────────────────────────────
  ok(BOOTSTRAP_CHANNELS.size > 0, 'a bootstrap allow-list exists');
  ok([...BOOTSTRAP_CHANNELS].every((c) => typeof c === 'string' && c.length),
    'bootstrap entries are non-empty channel names');

  // ── The tested module must actually BE the thing main.js installs ──────
  // Otherwise this file tests a correct module that nothing uses, which is
  // the shape of a fix that silently does nothing.
  const mainSrc = fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8');
  ok(/ipcMain\.handle\s*=\s*\(channel,\s*fn\)\s*=>\s*_ipcHandle\(\s*channel,\s*guardHandler\(/.test(mainSrc),
    'main.js routes ipcMain.handle through guardHandler');
  ok(/ipcMain\.on\s*=\s*\(channel,\s*fn\)\s*=>\s*_ipcOn\(\s*channel,\s*guardListener\(/.test(mainSrc),
    'main.js routes ipcMain.on through guardListener');
  ok(/require\(['"]\.\/ipc-guard['"]\)/.test(mainSrc),
    'main.js imports the tested module');
  const rawHandles = (mainSrc.match(/ipcMain\.handle\(/g) || []).length;
  ok(rawHandles >= 50, `main.js still registers its privileged channels (${rawHandles})`);

  // Ordering matters as much as wiring. The wrappers *replace* ipcMain.handle
  // and ipcMain.on, so any channel registered above the replacement escapes
  // the guard. That regression already happened once: orbit:get-bridge-token
  // -- which hands out the secret that authenticates every JARVIS browser
  // call -- was registered first and therefore answered any sender.
  const guardInstall = mainSrc.indexOf('ipcMain.handle = (channel, fn)');
  const onInstall = mainSrc.indexOf('ipcMain.on = (channel, fn)');
  ok(guardInstall !== -1 && onInstall !== -1, 'the ipcMain wrappers are installed');
  const firstReg = mainSrc.search(/ipcMain\.(handle|on)\(\s*["']/);
  ok(firstReg > guardInstall && firstReg > onInstall,
    `no channel is registered before the guard is installed (first @${firstReg})`);

  // And the bootstrap set must only contain channels whose handler exists.
  for (const ch of BOOTSTRAP_CHANNELS) {
    ok(mainSrc.includes(`ipcMain.on("${ch}"`) || mainSrc.includes(`ipcMain.handle("${ch}"`),
      `bootstrap channel ${ch} is actually registered`);
  }

  console.log('\n' + (checks - failures) + '/' + checks + ' passed');
  process.exit(failures === 0 ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(1); });