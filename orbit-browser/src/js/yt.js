/* yt.js — Private YouTube via Piped/Invidious-style front-ends (Invidious integration).
 *
 * Public Invidious instances no longer serve open APIs (403/401/anti-bot), so this
 * module uses the Piped API — same extractor family, verified live, CORS enabled:
 *   GET /search?q=&filter=videos  -> { items: [{ url, title, uploaderName, duration, views, thumbnail, type }] }
 *   GET /streams/:id              -> { title, description, uploader, subtitles: [{ code, url, mimeType }] }
 *
 * Renderer-direct (no backend hop). Instance failover: on failure the next
 * instance is tried and remembered for subsequent calls.
 *
 * Exposes window.YT:
 *   YT.search(query)            -> [{ id, title, uploader, duration, views, thumb, watchUrl }]
 *   YT.transcript(videoId)      -> { title, uploader, text }
 *   YT.summarize(video)         -> streams a JARVIS summary into the sidebar
 *   YT.renderResults(items)     -> renders a result card list into the sidebar
 */
(function () {
  'use strict';

  // Verified-healthy instances (probed). Order = preference.
  var INSTANCES = [
    'https://api.piped.private.coffee',
    'https://pipedapi.ducks.party',
  ];
  var _preferred = 0;
  var SEARCH_TIMEOUT = 8000;
  var STREAM_TIMEOUT = 15000;
  var MAX_RESULTS = 6;
  var MAX_TRANSCRIPT_CHARS = 12000;

  // ---------------------------------------------------------------- helpers
  function fmtDuration(s) {
    if (!s && s !== 0) return '';
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return h > 0
      ? h + ':' + String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0')
      : m + ':' + String(sec).padStart(2, '0');
  }

  function fmtViews(n) {
    if (n == null) return '';
    if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B views';
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M views';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K views';
    return n + ' views';
  }

  function decodeEntities(s) {
    if (!s) return '';
    return s
      .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&apos;/g, "'")
      .replace(/&#(\d+);/g, function (_, d) { return String.fromCharCode(+d); });
  }

  // TTML/timedtext captions -> plain text.
  function parseTTML(xml) {
    var out = [];
    var re = /<p[^>]*>([\s\S]*?)<\/p>/g, m;
    while ((m = re.exec(xml)) !== null) {
      var text = decodeEntities(String(m[1]).replace(/<[^>]+>/g, '')).trim();
      if (text) out.push(text);
    }
    return out.join(' ').replace(/\s+/g, ' ').trim();
  }

  async function fetchJSON(url, timeoutMs) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(url, { signal: ctrl.signal });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return await res.json();
    } finally {
      clearTimeout(timer);
    }
  }

  // Try the preferred instance, fail over to the others.
  async function piped(path, timeoutMs) {
    var order = [];
    for (var i = 0; i < INSTANCES.length; i++) {
      order.push(INSTANCES[(_preferred + i) % INSTANCES.length]);
    }
    var lastErr = null;
    for (var j = 0; j < order.length; j++) {
      var base = order[j];
      try {
        var data = await fetchJSON(base + path, timeoutMs);
        _preferred = INSTANCES.indexOf(base); // remember the healthy one
        return data;
      } catch (e) {
        lastErr = e;
      }
    }
    throw new Error('All YouTube front-ends failed (last: ' + (lastErr ? lastErr.message : 'unknown') + ')');
  }

  // ----------------------------------------------------------------- search
  async function search(query) {
    const data = await piped('/search?q=' + encodeURIComponent(query) + '&filter=videos', SEARCH_TIMEOUT);
    var items = (data.items || []).filter(function (it) { return it.type === 'stream'; });
    return items.slice(0, MAX_RESULTS).map(function (it) {
      var v = it.url.match(/[?&]v=([\w-]{6,})/);
      return {
        id: v ? v[1] : '',
        title: it.title || '',
        uploader: it.uploaderName || '',
        duration: it.duration >= 0 ? it.duration : 0,
        views: it.views >= 0 ? it.views : null,
        thumb: it.thumbnail || '',
        watchUrl: 'https://www.youtube.com' + (it.url || ''),
      };
    });
  }

  // ------------------------------------------------------------- transcript
  // /streams extraction is per-video flaky on public instances (POT-token
  // gating), so: both instances, two rounds, then an honest failure.
  async function transcript(videoId) {
    var data = null, lastErr = null;
    for (var round = 0; round < 2 && !data; round++) {
      try {
        data = await piped('/streams/' + encodeURIComponent(videoId), STREAM_TIMEOUT);
      } catch (e) {
        lastErr = e;
        if (round === 0) await new Promise(r => setTimeout(r, 700));
      }
    }
    if (!data) {
      return {
        title: '', uploader: '', text: '',
        note: 'Caption extraction is unavailable for this video right now — ' +
              'YouTube is aggressively gating caption access and public front-end ' +
              'instances are rate-limited. Search and private playback still work.',
      };
    }
    var subs = data.subtitles || [];
    // Prefer manual English, then any English, then anything.
    var pick = subs.find(function (s) { return (s.code || '').indexOf('en') === 0 && (s.mimeType || '').indexOf('ttml') >= 0; }) ||
               subs.find(function (s) { return (s.code || '').indexOf('en') === 0; }) ||
               subs[0];
    if (!pick || !pick.url) {
      return { title: data.title || '', uploader: data.uploader || '', text: '', note: 'No captions available for this video.' };
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), STREAM_TIMEOUT);
    var xml = '';
    try {
      const res = await fetch(pick.url, { signal: ctrl.signal });
      xml = await res.text();
    } finally {
      clearTimeout(timer);
    }
    var text = parseTTML(xml);
    if (text.length > MAX_TRANSCRIPT_CHARS) text = text.slice(0, MAX_TRANSCRIPT_CHARS) + '…';
    return { title: data.title || '', uploader: data.uploader || '', text: text };
  }

  // --------------------------------------------------------------- summarize
  // Routes through the existing dshNative chat pipeline so the summary
  // streams into the sidebar like any JARVIS reply.
  async function summarize(video) {
    var status = document.querySelector('[data-yt-status]');
    if (status) status.textContent = 'Fetching transcript…';
    var tr;
    try {
      tr = await transcript(video.id);
    } catch (e) {
      if (window.Chat) Chat.append('error', 'Transcript failed: ' + e.message);
      return;
    }
    if (status) status.textContent = tr.note || 'Summarizing…';
    if (!tr.text) {
      if (window.Chat) Chat.append('jarvis', 'No captions for "' + tr.title + '" — nothing to summarize.');
      return;
    }
    if (window.dshNative && window.dshNative.status.connected) {
      const prompt =
        'Summarize this YouTube video transcript concisely (3-5 key points, then one takeaway line).\n' +
        'Title: ' + tr.title + '\nChannel: ' + tr.uploader + '\n\nTranscript:\n' + tr.text;
      const tab = (typeof tabs !== 'undefined') ? tabs.get(typeof activeTabId !== 'undefined' ? activeTabId : null) : null;
      await window.dshNative.chat(prompt, { page: tab ? { url: tab.url, title: tab.title } : null });
    } else {
      if (window.Chat) Chat.append('error', 'JARVIS backend is not connected — cannot summarize.');
    }
  }

  // -------------------------------------------------------------- render UI
  // All external strings go through textContent/attributes — no innerHTML
  // with untrusted data (XSS-safe DOM construction).
  function renderResults(items) {
    var body = document.getElementById('sbBody');
    if (!body) return;

    var wrap = document.createElement('div');
    wrap.className = 'yt-results';

    var head = document.createElement('div');
    head.className = 'yt-head';
    head.textContent = items.length + ' private results — tracking-free';
    wrap.appendChild(head);

    items.forEach(function (v) {
      var card = document.createElement('div');
      card.className = 'yt-card';

      if (v.thumb) {
        var img = document.createElement('img');
        img.className = 'yt-thumb';
        img.src = v.thumb;
        img.alt = '';
        img.loading = 'lazy';
        card.appendChild(img);
      }

      var info = document.createElement('div');
      info.className = 'yt-info';

      var title = document.createElement('div');
      title.className = 'yt-title';
      title.textContent = v.title;
      info.appendChild(title);

      var meta = document.createElement('div');
      meta.className = 'yt-meta';
      meta.textContent = v.uploader + (v.uploader ? ' · ' : '') +
        fmtDuration(v.duration) + (v.views != null ? ' · ' + fmtViews(v.views) : '');
      info.appendChild(meta);

      var actions = document.createElement('div');
      actions.className = 'yt-actions';

      function btn(label, fn) {
        var b = document.createElement('button');
        b.className = 'yt-btn';
        b.type = 'button';
        b.textContent = label;
        b.addEventListener('click', fn);
        return b;
      }

      actions.appendChild(btn('▶ Open', function () {
        if (typeof navigateTo === 'function') navigateTo(v.watchUrl);
      }));
      actions.appendChild(btn('🔒 Embed', function () {
        var frame = document.createElement('iframe');
        frame.className = 'yt-embed';
        frame.src = 'https://www.youtube-nocookie.com/embed/' + v.id;
        frame.allow = 'encrypted-media; picture-in-picture';
        frame.setAttribute('allowfullscreen', '');
        info.replaceWith(frame);
      }));
      actions.appendChild(btn('✨ Summarize', function () { summarize(v); }));

      info.appendChild(actions);
      card.appendChild(info);
      wrap.appendChild(card);
    });

    body.appendChild(wrap);
    body.scrollTop = body.scrollHeight;
  }

  // ------------------------------------------------------------------ wire
  window.YT = {
    search: search,
    transcript: transcript,
    summarize: summarize,
    renderResults: renderResults,
    fmtDuration: fmtDuration,
    parseTTML: parseTTML,
    instances: INSTANCES,
  };
})();
