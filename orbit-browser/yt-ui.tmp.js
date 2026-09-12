/* Live UI test: /yt command through the real chat input, then check result cards. */
const http = require('http');
function getJSON(path) {
  return new Promise((resolve, reject) => {
    http.get({ host: '127.0.0.1', port: 9333, path }, (res) => {
      let d = ''; res.on('data', c => d += c);
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } });
    }).on('error', reject);
  });
}
async function evalInPage(expr) {
  const targets = await getJSON('/json/list');
  const page = targets.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
  const WebSocket = require('ws');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r => ws.on('open', r));
  const result = await new Promise((resolve, reject) => {
    const id = 7;
    const onMsg = (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch { return; }
      if (m.id === id) { ws.removeEventListener('message', onMsg); m.error ? reject(new Error(m.error.message)) : resolve(m.result); }
    };
    ws.addEventListener('message', onMsg);
    ws.send(JSON.stringify({ id, method: 'Runtime.evaluate', params: { expression: expr, returnByValue: true, awaitPromise: true } }));
  });
  ws.close();
  return result.result.value;
}
(async () => {
  const out = await evalInPage(`(async function(){
    // open the JARVIS sidebar if hidden
    const jarvisBtn = document.getElementById('jarvisBtn');
    if (jarvisBtn) jarvisBtn.click();
    await new Promise(r => setTimeout(r, 400));
    // drive the real input
    const input = document.getElementById('sbInput');
    if (!input) return { err: 'no sbInput' };
    input.value = '/yt lofi hip hop';
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await new Promise(r => setTimeout(r, 9000));
    const cards = document.querySelectorAll('.yt-card').length;
    const errs = Array.from(document.querySelectorAll('.chat-msg--error')).map(e => e.textContent.slice(0, 90));
    const msgs = Array.from(document.querySelectorAll('#sbBody > *')).slice(-4).map(e => e.className + ': ' + e.textContent.slice(0, 70));
    return { cards, errs, msgs };
  })()`);
  console.log(JSON.stringify(out, null, 1));
  process.exit(0);
})().catch(e => { console.error('PROBE FAIL:', e.message); process.exit(1); });
