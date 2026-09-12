global.window = {};
require('./src/js/yt.js');
const YT = window.YT;
(async () => {
  const results = await YT.search('lofi hip hop');
  console.log('SEARCH n=' + results.length);
  if (!results.length) throw new Error('no results');
  const tr = await YT.transcript(results[0].id);
  console.log('TRANSCRIPT chars=' + tr.text.length + (tr.note ? ' note=yes' : ''));
  console.log('YT_PASS');
  process.exit(0);
})().catch(e => { console.error('FAIL:', e.message); process.exit(1); });
