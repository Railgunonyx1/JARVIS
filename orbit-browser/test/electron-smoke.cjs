/* Runtime smoke test for the Electron 28 -> 44 migration.
 *
 * electron-compat.test.cjs can only reason about source. This one boots the
 * real Electron binary and exercises the parts the upgrade could plausibly
 * break: <webview> + webviewTag, the sandboxed preload, the sandboxed guest
 * preload behind its own partition session, the orbit:// custom protocol, and
 * -- the thing that had zero runtime coverage before -- the IPC sender guard
 * actually refusing a second, unlisted window.
 *
 * Run:  npx electron test/electron-smoke.cjs        (from orbit-browser/)
 * Exits 0 on success, 1 on the first failed check.
 */

const { app, BrowserWindow, ipcMain, net, protocol, session } = require('electron');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { guardHandler, guardListener, BOOTSTRAP_CHANNELS } = require('../ipc-guard.js');

const ROOT = path.join(__dirname, '..');
let checks = 0;
let failures = 0;

function ok(cond, label) {
  checks += 1;
  console.log((cond ? '  PASS  ' : '  FAIL  ') + label);
  if (!cond) failures += 1;
}

const deadline = (ms, what) => new Promise((_, rej) =>
  setTimeout(() => rej(new Error(`timeout waiting for ${what}`)), ms));

function once(emitter, event, ms = 15000) {
  return Promise.race([
    new Promise((res) => emitter.once(event, (...a) => res(a))),
    deadline(ms, event),
  ]);
}

// A preload for the untrusted window: it can reach ipcRenderer, which is
// exactly the capability the guard exists to constrain.
const UNTRUSTED_PRELOAD = `
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('probe', {
  invoke: (ch, ...a) => ipcRenderer.invoke(ch, ...a).then(
    (v) => ({ ok: true, value: v }),
    (e) => ({ ok: false, error: String(e && e.message || e) }),
  ),
  token: () => {
    try { return ipcRenderer.sendSync('orbit:get-bridge-token'); }
    catch (e) { return 'DENIED:' + String(e && e.message || e); }
  },
});
`;
const untrustedPreloadPath = path.join(__dirname, '.smoke-untrusted-preload.js');

async function main() {
  console.log('\nElectron runtime smoke');
  console.log('  electron=%s chromium=%s node=%s\n',
    process.versions.electron, process.versions.chrome, process.versions.node);

  // ── 1. Orbit's exact custom-protocol shape (Windows-safe since 33) ──────
  const orbitHandler = async (request) => {
    let host = 'newtab';
    try { host = new URL(request.url).hostname || 'newtab'; } catch (_) { /* default */ }
    const file = host === 'import' ? 'src/import.html' : 'src/newtab.html';
    try {
      return await net.fetch(pathToFileURL(path.join(ROOT, file)).toString());
    } catch (_) {
      return new Response('Not Found', { status: 404 });
    }
  };
  protocol.handle('orbit', orbitHandler);
  session.fromPartition('persist:orbit').protocol.handle('orbit', orbitHandler);
  ok(true, 'orbit:// handler registers on the default and persist:orbit sessions');

  // ── 2. The main window, with Orbit's real webPreferences ────────────────
  const win = new BrowserWindow({
    show: false,
    frame: false,
    webPreferences: {
      preload: path.join(ROOT, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webviewTag: true,
      spellcheck: false,
      additionalArguments: [
        '--orbit-partition=persist:orbit',
        '--orbit-guest-preload=' + path.join(ROOT, 'guest-preload.js'),
      ],
    },
  });
  ok(webContentsOf(win) !== null, 'BrowserWindow created with webviewTag + sandbox');

  await win.loadURL('orbit://newtab');
  ok(true, 'main window loaded orbit://newtab through protocol.handle');

  // The preload's contextBridge surface must exist and must NOT be Orbit's
  // quarantined agent API.
  const bridge = await win.webContents.executeJavaScript(
    'Object.keys(window.orbit || {}).sort().join(",")');
  ok(typeof bridge === 'string' && bridge.length > 0, `window.orbit exposed: ${bridge}`);
  ok(!bridge.split(',').includes('agent'), 'window.orbit has no `agent` surface');

  // The renderer must receive an ABSOLUTE guest preload path. A relative one
  // resolves against this document (src/index.html) and silently loads
  // nothing -- which is exactly what Orbit shipped until this was found.
  const guestPreloadArg = await win.webContents.executeJavaScript(
    'window.orbit && window.orbit.guestPreload');
  ok(typeof guestPreloadArg === 'string' && path.isAbsolute(guestPreloadArg || ''),
    `renderer receives an absolute guest preload path (${guestPreloadArg})`);
  ok(fs.existsSync(guestPreloadArg), 'that guest preload path exists on disk');

  // ── 3. A <webview> guest: attach, sandbox, guest preload ─────────────────
  const guestReady = win.webContents.executeJavaScript(`(async () => {
    const wv = document.createElement('webview');
    wv.setAttribute('src', 'about:blank');
    wv.setAttribute('partition', 'persist:orbit');
    wv.setAttribute('preload', ${JSON.stringify(path.join(ROOT, 'guest-preload.js'))});
    wv.setAttribute('webpreferences',
      'contextIsolation=yes,nodeIntegration=no,webSecurity=yes,spellcheck=false');
    document.body.appendChild(wv);
    await new Promise((res, rej) => {
      wv.addEventListener('did-attach', res, { once: true });
      wv.addEventListener('did-fail-load', (e) => rej(new Error('did-fail-load')), { once: true });
      setTimeout(() => rej(new Error('guest never attached')), 15000);
    });
    await new Promise((res) => wv.addEventListener('dom-ready', res, { once: true }));
    return {
      hardened: !!(wv.getWebContentsId && wv.getWebContentsId()),
      guestFlag: await wv.executeJavaScript('!!(window.__ORBIT_GUEST__ && window.__ORBIT_GUEST__.hardened)'),
      guestLeakedOrbit: await wv.executeJavaScript('!!window.orbit'),
      nodeInGuest: await wv.executeJavaScript('typeof require !== "undefined" || typeof process !== "undefined"'),
      url: wv.getURL(),
    };
  })()`);
  const g = await Promise.race([guestReady, deadline(20000, 'webview guest')]);
  ok(g.hardened, `webview guest attached (webContentsId=${g.hardened})`);
  ok(g.guestFlag === true,
    `guest preload ran and exposed __ORBIT_GUEST__.hardened (${g.guestFlag})`);
  ok(g.guestLeakedOrbit === false,
    'guest on about:blank gets NO orbit bridge (protocol gate holds for non-orbit pages)');
  ok(g.nodeInGuest === false, 'guest has no node (sandbox + nodeIntegration=no)');

  // The same guest, but on an orbit:// page: the first-party gate should open.
  const firstParty = await Promise.race([
    win.webContents.executeJavaScript(`(async () => {
      const wv = document.querySelector('webview');
      await new Promise((res) => {
        wv.addEventListener('dom-ready', () => res(true), { once: true });
        wv.loadURL('orbit://import');
      });
      return {
        url: wv.getURL(),
        hasChromeBridge: await wv.executeJavaScript('!!(window.orbit && window.orbit.chrome)'),
      };
    })()`),
    deadline(20000, 'orbit:// inside a guest'),
  ]);
  ok(firstParty.hasChromeBridge === true,
    `orbit:// page inside a guest gets the first-party bridge (url=${firstParty.url})`);

  // ── 4. The IPC sender guard, against a REAL second window ───────────────
  // This is the check that could not be made before: source-level tests can
  // only assert the wrapper exists, not that an unlisted webContents is
  // actually refused.
  fs.writeFileSync(untrustedPreloadPath, UNTRUSTED_PRELOAD);
  const ctx = () => ({
    mainWebContents: win.webContents,
    guestIds: [],
    isDevTools: true,
  });
  ipcMain.handle('smoke:ping', guardHandler(
    () => ({ pong: true }), ctx,
    (reason) => console.log('    (guard rejected: ' + reason + ')'),
  ));
  ipcMain.on('smoke:boot', guardListener(
    (event) => { event.returnValue = 'boot-ok'; }, ctx,
    () => {},
  ));
  // The real bootstrap channel, guarded exactly as main.js guards it. A
  // sendSync listener that returns without setting returnValue makes Electron
  // throw "reply was never sent" in the sender -- noisy, but still a denial,
  // which is what the untrusted window must get.
  const SECRET = 'test-bridge-token';
  ipcMain.on('orbit:get-bridge-token', guardListener(
    (event) => { event.returnValue = SECRET; },
    () => ({ ...ctx(), allowBootstrap: BOOTSTRAP_CHANNELS.has('orbit:get-bridge-token') }),
    () => {},
  ));
  ok(BOOTSTRAP_CHANNELS.size > 0, 'the guard module exports its bootstrap set');

  const intruder = new BrowserWindow({
    show: false,
    webPreferences: {
      preload: untrustedPreloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  // loadURL resolves at did-finish-load, so dom-ready has already fired by the
  // time we could attach a listener; awaiting it would hang forever.
  await intruder.loadURL('data:text/html,<title>intruder</title>');

  const trustedReply = await win.webContents.executeJavaScript(
    'window.orbit ? "has-bridge" : "no-bridge"');
  ok(trustedReply === 'has-bridge', 'the real preload bridge survived the upgrade');

  const intruderReply = await intruder.webContents.executeJavaScript(
    'window.probe.invoke("smoke:ping")');
  ok(intruderReply.ok === false,
    `an unlisted webContents is refused by the guard: ${intruderReply.error}`);
  ok(/untrusted sender/.test(String(intruderReply.error)),
    'the refusal names the sender, not the payload');

  const intruderSync = await intruder.webContents.executeJavaScript(
    'window.probe.token()');
  ok(intruderSync !== SECRET && String(intruderSync).indexOf(SECRET) === -1,
    `the bridge token is NOT returned to an unlisted sender (got ${JSON.stringify(intruderSync)})`);

  const trustedToken = await win.webContents.executeJavaScript(
    'window.orbit.getBridgeToken()');
  ok(trustedToken === SECRET,
    `the trusted renderer still receives its bootstrap token (${JSON.stringify(trustedToken)})`);

  // ── done ────────────────────────────────────────────────────────────────
  fs.unlinkSync(untrustedPreloadPath);
  console.log('\n' + (checks - failures) + '/' + checks + ' passed');
  app.exit(failures === 0 ? 0 : 1);
}

function webContentsOf(w) { return w.webContents; }

process.on('uncaughtException', (e) => {
  console.error('\nSMOKE ERROR: ' + (e && e.stack || e));
  try { fs.unlinkSync(untrustedPreloadPath); } catch (_) { /* ignore */ }
  app.exit(1);
});

app.whenReady().then(main).catch((e) => {
  console.error('\nSMOKE ERROR: ' + (e && e.stack || e));
  app.exit(1);
});