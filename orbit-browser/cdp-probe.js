const http = require('http');
const fs = require('fs');
const WebSocket = require('ws');

function getJSON(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let d = '';
      res.on('data', (c) => d += c);
      res.on('end', () => {
        try { resolve(JSON.parse(d)); } catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

function wsCall(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    let id = 1;
    const pending = {};
    ws.on('message', (data) => {
      const msg = JSON.parse(data.toString());
      if (msg.id && pending[msg.id]) { pending[msg.id](msg); delete pending[msg.id]; }
    });
    ws.on('open', () => {
      const call = (method, params) => new Promise((res) => {
        const mid = id++;
        pending[mid] = res;
        ws.send(JSON.stringify({ id: mid, method, params }));
      });
      resolve({ ws, call });
    });
    ws.on('error', reject);
  });
}

(async () => {
  const mode = process.argv[2] || 'probe';
  let targets;
  try { targets = await getJSON('http://127.0.0.1:9333/json'); }
  catch (e) { console.log('NO_CDP: ' + e.message); process.exit(2); }
  const page = targets.find((t) => t.type === 'page' && !t.url.startsWith('devtools://'));
  if (!page) { console.log('NO_PAGE_TARGET'); process.exit(2); }
  const c = await wsCall(page.webSocketDebuggerUrl);
  const evalJs = async (expr, awaitPromise) => {
    const r = await c.call('Runtime.evaluate', { expression: expr, awaitPromise: !!awaitPromise, returnByValue: true });
    return r.result && r.result.result && r.result.result.value;
  };

  if (mode === 'close') {
    await evalJs('window.close(); true');
    console.log('CLOSE_SENT');
    c.ws.close();
    process.exit(0);
  }

  const shot = await c.call('Page.captureScreenshot', { format: 'png' });
  if (shot.result && shot.result.data) {
    fs.writeFileSync('shot.png', Buffer.from(shot.result.data, 'base64'));
    console.log('SHOT saved');
  }
  const ui = await evalJs(`({
    badge: document.querySelector('#statusLabel') ? document.querySelector('#statusLabel').textContent : null,
    dot: document.querySelector('#statusDot') ? document.querySelector('#statusDot').className : null,
    jarvisBtn: !!(document.querySelector('.jarvis-launch')),
    panelExists: !!(document.querySelector('.jarvis-panel, #jarvisPanel, .ai-panel, #chatPanel')),
    bodyText: document.body ? document.body.innerText.replace(/\\s+/g,' ').trim().substring(0, 150) : ''
  })`);
  console.log('UI=' + JSON.stringify(ui));
  const st = await evalJs(`window.orbit ? Promise.resolve(window.orbit.jarvis.status()).then(s => ({ ok: s.ok, kernel: s.kernel, engine: s.engine, reason: s.reason })).catch(e => ({ thrown: e.message })) : Promise.resolve(null)`, true);
  console.log('JARVIS_STATUS=' + JSON.stringify(st));
  c.ws.close();
  process.exit(0);
})().catch((e) => { console.log('ERR ' + e.message); process.exit(1); });