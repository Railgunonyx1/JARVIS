const http = require('http');
const WebSocket = require('ws');
function getJSON(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => { let d=''; res.on('data',(c)=>d+=c); res.on('end',()=>{try{resolve(JSON.parse(d));}catch(e){reject(e);}}); }).on('error', reject);
  });
}
(async () => {
  const targets = await getJSON('http://127.0.0.1:9333/json/list');
  const page = targets.find((t) => t.type === 'page' && !t.url.startsWith('devtools'));
  const ws = new WebSocket(page.webSocketDebuggerUrl, { maxPayload: 64*1024*1024 });
  let id = 0; const pending = new Map();
  const send = (method, params) => new Promise((res) => { const i=++id; pending.set(i,res); ws.send(JSON.stringify({id:i,method,params})); });
  ws.on('message', (m) => { const d=JSON.parse(m); if(d.id&&pending.has(d.id)){pending.get(d.id)(d.result);pending.delete(d.id);} });
  await new Promise((r)=>ws.on('open',r));
  const ev = async (expr, awaitPromise) => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: !!awaitPromise })).result.value;

  // 1. dshNative state
  const state = await ev(`(() => ({
    wired: window.__orbitDshWired,
    dsh: !!window.dshNative,
    status: window.dshNative && window.dshNative.status ? JSON.stringify(window.dshNative.status) : 'missing',
    selectedModel: window.dshNative && window.dshNative.selectedModel,
    listModels: !!window.dshNative && typeof window.dshNative.listModels,
  }))()`);
  console.log('DSH:', JSON.stringify(state));

  // 2. Is the chip visible
  const chip = await ev(`(() => ({
    chip: !!document.getElementById('sbModelChip'),
    visible: !!document.getElementById('sbModelChip') && document.getElementById('sbModelChip').style.display !== 'none',
    label: document.getElementById('sbModelName') ? document.getElementById('sbModelName').textContent : ''
  }))()`);
  console.log('CHIP:', JSON.stringify(chip));

  // 3. listModels can the browser actually call it
  try {
    const models = await ev(`window.dshNative.listModels().then(m => m.length).catch(e => 'ERR:' + e.message)`, true);
    console.log('LIST:', models);
  } catch (e) {
    console.log('LIST-ERR:', e.message);
  }
  process.exit(0);
})().catch((e)=>{console.error('FAIL', e.message); process.exit(1);});
