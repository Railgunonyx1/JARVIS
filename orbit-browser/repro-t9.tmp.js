/* Repro T9: close-all -> new tab -> chat, with full event + state instrumentation. */
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
  let mid = 0; const pending = {};
  ws.on('message', (data) => { try { const m = JSON.parse(data.toString()); if (m.id && pending[m.id]) { pending[m.id](m); delete pending[m.id]; } } catch (_) {} });
  const call = (method, params) => new Promise((res) => { const id = ++mid; pending[id] = res; ws.send(JSON.stringify({ id, method, params })); });
  const evalJs = async (expr, awaitPromise) => {
    const r = await call('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: !!awaitPromise });
    if (r.result && r.result.exceptionDetails) return { THROWN: (r.result.exceptionDetails.text || '') };
    return r.result && r.result.result ? r.result.result.value : undefined;
  };
  await new Promise((r) => setTimeout(r, 1500));

  // Recreate T8 exactly: close all tabs -> new tab
  const pre = await evalJs(`(async function(){ while (tabs.size > 0) { closeTab(Array.from(tabs.keys())[0]); } document.querySelector('#newTabBtn').click(); return { size: tabs.size, activeTabId }; })()`);
  console.log('SETUP=' + JSON.stringify(pre));
  await new Promise((r) => setTimeout(r, 1500));

  // Instrument: log every message event with state
  await evalJs(`(function(){
    window.__log = [];
    window.dshNative.on('message', (e) => {
      const streamingEl = document.querySelector('#sbBody .chat-msg--streaming');
      window.__log.push({
        t: e.type,
        len: (e.text || e.fullText || '').length,
        chatStreaming: (typeof Chat !== 'undefined') ? Chat.isStreaming() : null,
        domStreaming: !!streamingEl,
        domLen: streamingEl && streamingEl.querySelector('.streaming-text') ? streamingEl.querySelector('.streaming-text').textContent.length : 0
      });
    });
    return true;
  })()`);

  // Send
  const sent = await evalJs(`(function(){ const i = document.querySelector('#sbInput'); i.value = 'Reply with exactly: REPRO-OK'; sendToJarvis(); return { activeTabId }; })()`);
  console.log('SENT=' + JSON.stringify(sent));

  // Poll state for up to 45s
  let final = null;
  for (let i = 0; i < 22; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const st = await evalJs(`(function(){
      const jarvis = Array.from(document.querySelectorAll('#sbBody .chat-msg--jarvis:not(.chat-msg--streaming)'));
      const log = window.__log || [];
      return {
        n: log.length,
        types: log.map(x => x.t).join(''),
        lastState: log.length ? log[log.length-1] : null,
        nJarvis: jarvis.length,
        jarvisTxt: jarvis.length ? jarvis[jarvis.length-1].textContent.substring(0, 100) : null
      };
    })()`);
    if (i % 5 === 4) console.log('t+' + ((i+1)*2) + 's ' + JSON.stringify(st));
    if (st && st.jarvisTxt && st.jarvisTxt.includes('REPRO-OK')) { final = st; break; }
    if (st && st.n > 0 && st.types.indexOf('done') !== -1 && i > 8) { final = st; break; }
  }
  console.log('FINAL=' + JSON.stringify(final));

  // Key discriminator: where did the reply land in persisted history?
  const hist = await evalJs(`(function(){
    const raw = localStorage.getItem('orbit-chat-history');
    if (!raw) return { none: true };
    const obj = JSON.parse(raw);
    const out = {};
    for (const [k, v] of Object.entries(obj)) {
      const hits = (v || []).filter(m => (m.content || '').includes('REPRO-OK')).length;
      if (hits || v.length) out[k.substring(0, 24)] = { n: v.length, reproHits: hits, lastRole: v.length ? v[v.length-1].role : null, lastText: v.length ? (v[v.length-1].content || '').substring(0, 80) : null };
    }
    return out;
  })()`);
  console.log('HISTORY=' + JSON.stringify(hist, null, 1));
  ws.close(); process.exit(0);
})().catch((e) => { console.log('ERR ' + e.message); process.exit(1); });
