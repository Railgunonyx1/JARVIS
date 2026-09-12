/* Headless test of yt.js search + TTML parsing against the live Piped API. */
global.window = {};
require('./src/js/yt.js');
const YT = window.YT;
(async () => {
  // 1. TTML parser on hostile input
  const ttml = '<?xml version="1.0"?><tt><body><div>';
  ttml.concat ? null : null;
  const xml = '<tt><body><div><p t="1">&amp;hello &lt;world&gt;</p><p t="2"><span>second</span> line</p></div></body></tt>';
  const parsed = YT.parseTTML(xml);
  console.log('TTML:', JSON.stringify(parsed));
  if (parsed !== '&hello <world> second line') throw new Error('TTML parse mismatch: ' + parsed);

  // 2. Live search
  const results = await YT.search('python tutorial');
  console.log('SEARCH: n=' + results.length);
  if (!results.length) throw new Error('no results');
  const r = results[0];
  console.log('first:', JSON.stringify({ id: r.id, title: r.title.slice(0, 30), dur: YT.fmtDuration(r.duration), watch: r.watchUrl }));
  if (!r.id || !r.watchUrl.includes('youtube.com/watch')) throw new Error('bad shape');

  // 3. Transcript fetch (first result)
  const tr = await YT.transcript(r.id);
  console.log('TRANSCRIPT: title=' + tr.title.slice(0, 30) + ' chars=' + tr.text.length + (tr.note ? ' note=' + tr.note : ''));
  if (!tr.text) console.log('  (no captions — acceptable for this video)');
  else if (tr.text.length < 100) throw new Error('transcript suspiciously short');

  console.log('YT_HEADLESS_PASS');
  process.exit(0);
})().catch(e => { console.error('FAIL:', e.message); process.exit(1); });
