/* Playtest probe: careless-user flows through the real UI. Deleted after use. */
const http = require('http');
const WebSocket = require('ws');
function getJSON(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => { let d = ''; res.on('data', (c) => (d += c)); res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } }); }).on('error', reject);
  });
}
(async () => {
  const targets = await getJSON('http://127.0.0.1:9333/json');
  const page = targets.find((t) => t.type === 'page' && !t.url.startsWith('devtools://'));
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.on('open', res); ws.on('error', rej); });
  let mid = 0; const pending = {}; const consoleErrs = [];
  ws.on('message', (data) => {
    try {
      const m = JSON.parse(data.toString());
      if (m.id && pending[m.id]) { pending[m.id](m); delete pending[m.id]; }
      if (m.method === 'Runtime.consoleAPICalled' && (m.params.type === 'error' || m.params.type === 'assert')) {
        consoleErrs.push(m.params.args.map(a => a.value || a.description || '').join(' ').substring(0, 200));
      }
      if (m.method === 'Runtime.exceptionThrown') {
        consoleErrs.push('EXC: ' + JSON.stringify(m.params.exceptionDetails.exception || {}).substring(0, 200));
      }
    } catch (_) {}
  });
  const call = (method, params) => new Promise((res) => { const id = ++mid; pending[id] = res; ws.send(JSON.stringify({ id, method, params })); });
  const evalJs = async (expr, awaitPromise) => {
    const r = await call('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: !!awaitPromise });
    if (r.result && r.result.exceptionDetails) return { THROWN: (r.result.exceptionDetails.text || '') };
    return r.result && r.result.result ? r.result.result.value : undefined;
  };
  await call('Runtime.enable');
  const results = [];
  const test = (name, ok, detail) => { results.push({ name, ok, detail }); console.log((ok ? 'PASS' : 'FAIL') + ' | ' + name + (detail ? ' | ' + detail : '')); };

  await new Promise((r) => setTimeout(r, 2000));

  // ── T1: omnibox URL navigation ──
  await evalJs(`(function(){ const i = document.querySelector('#omniInput'); i.focus(); i.value = 'example.com'; i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); return document.querySelector('#omniInput').value; })()`);
  await new Promise((r) => setTimeout(r, 4000));
  const t1 = await evalJs(`(function(){ const t = tabs.get(activeTabId); return { url: t ? t.url : null, omni: document.querySelector('#omniInput').value }; })()`);
  test('T1 omnibox URL nav', !!t1 && String(t1.url || '').includes('example.com'), JSON.stringify(t1));

  // ── T2: omnibox search terms ──
  await evalJs(`(function(){ const i = document.querySelector('#omniInput'); i.focus(); i.value = 'hello world test'; i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); return true; })()`);
  await new Promise((r) => setTimeout(r, 3500));
  const t2 = await evalJs(`(function(){ const t = tabs.get(activeTabId); return { url: t ? t.url : null }; })()`);
  test('T2 omnibox search terms', !!t2 && String(t2.url || '').includes('google.com/search'), JSON.stringify(t2));

  // ── T3: omnibox empty Enter ──
  const t3 = await evalJs(`(function(){ const i = document.querySelector('#omniInput'); i.value = ''; const before = tabs.size; i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); return { before, after: tabs.size, omni: document.querySelector('#omniInput').value }; })()`);
  await new Promise((r) => setTimeout(r, 800));
  test('T3 omnibox empty Enter no-op', t3 && t3.before === t3.after && !t3.omni, JSON.stringify(t3));

  // ── T4: rapid new-tab clicks ──
  const t4 = await evalJs(`(function(){ const b = document.querySelector('#newTabBtn'); const before = tabs.size; for (let k = 0; k < 3; k++) b.click(); return { before, after: tabs.size }; })()`);
  await new Promise((r) => setTimeout(r, 1200));
  test('T4 rapid new-tab x3', t4 && t4.after === t4.before + 3, JSON.stringify(t4));

  // ── T5: fresh NTP is empty ──
  const t5 = await evalJs(`(function(){ const n = document.querySelector('#ntpSearch'); return { exists: !!n, value: n ? n.value : null }; })()`);
  test('T5 fresh NTP empty searchbox', !!t5 && t5.exists && t5.value === '', JSON.stringify(t5));

  // ── T6: JARVIS slash command ──
  const t6 = await evalJs(`(function(){ const i = document.querySelector('#sbInput'); i.value = '/help'; sendToJarvis(); return true; })()`);
  await new Promise((r) => setTimeout(r, 1500));
  const t6b = await evalJs(`(function(){ const msgs = Array.from(document.querySelectorAll('#sbBody .chat-msg')); return { n: msgs.length, last: msgs.length ? msgs[msgs.length-1].textContent.substring(0, 100) : null }; })()`);
  test('T6 /help renders output', !!t6b && t6b.n > 0 && /help|command|task/i.test(t6b.last || ''), JSON.stringify(t6b));

  // ── T7: JARVIS empty send no-op ──
  const t7 = await evalJs(`(function(){ const i = document.querySelector('#sbInput'); i.value = '   '; const before = document.querySelectorAll('#sbBody .chat-msg').length; sendToJarvis(); return { before, after: document.querySelectorAll('#sbBody .chat-msg').length }; })()`);
  test('T7 empty JARVIS send no-op', t7 && t7.after === t7.before, JSON.stringify(t7));

  // ── T8: close all tabs -> empty screen -> recover ──
  const t8 = await evalJs(`(async function(){ while (tabs.size > 0) { const id = Array.from(tabs.keys())[0]; closeTab(id); } return { size: tabs.size, emptyVisible: !document.querySelector('#emptyScreen')?.classList.contains('hidden') }; })()`);
  await new Promise((r) => setTimeout(r, 800));
  test('T8 all tabs closed -> empty screen', t8 && t8.size === 0, JSON.stringify(t8));
  const t8b = await evalJs(`(function(){ document.querySelector('#newTabBtn').click(); return { size: tabs.size }; })()`);
  await new Promise((r) => setTimeout(r, 800));
  test('T8b recover from empty state', t8b && t8b.size === 1, JSON.stringify(t8b));

  // ── T9: JARVIS chat still works after all that ──
  await evalJs(`(function(){ window.__evts = []; window.dshNative.on('message', (e) => window.__evts.push(e.type)); const i = document.querySelector('#sbInput'); i.value = 'Reply with exactly: PLAYTEST-OK'; sendToJarvis(); return true; })()`);
  let t9 = null;
  for (let i = 0; i < 30; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    t9 = await evalJs(`(function(){ const all = Array.from(document.querySelectorAll('#sbBody .chat-msg--jarvis:not(.chat-msg--streaming)')); const last = all[all.length-1]; return { txt: last ? (last.textContent||'').substring(0,120) : null, n: (window.__evts||[]).length }; })()`);
    if (t9 && t9.txt && t9.txt.includes('PLAYTEST-OK')) break;
  }
  test('T9 JARVIS chat after stress', !!t9 && !!(t9.txt || '').includes('PLAYTEST-OK'), JSON.stringify(t9));

  // ── T10: console error sweep ──
  test('T10 no console errors during playtest', consoleErrs.length === 0, consoleErrs.slice(0, 3).join(' || '));

  const fails = results.filter(r => !r.ok).length;
  console.log('SUMMARY: ' + (results.length - fails) + '/' + results.length + ' pass');
  ws.close(); process.exit(0);
})().catch((e) => { console.log('ERR ' + e.message); process.exit(1); });
