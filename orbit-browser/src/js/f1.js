/* f1.js — orbit://f1 workspace: live F1 monitoring via OpenF1 (free, no key).
 *
 * Data (all verified live from the Orbit renderer):
 *   /v1/sessions?session_key=latest   -> current session
 *   /v1/drivers?session_key=K         -> grid with team colours
 *   /v1/location?session_key=K&date>= -> GPS points (x,y,z + date) per car
 *   /v1/position?session_key=K        -> position snapshots (leaderboard)
 *
 * Track shape is drawn from the cars' own GPS points — no map assets.
 * Lifecycle + banner + ask come from workspace.js; this file owns data,
 * the adaptive rate-limit backoff, and drawing.
 */
(function () {
  'use strict';

  var BASE = 'https://api.openf1.org/v1';
  var REFRESH = { session: 5000, loc: 5000, pos: 20000 };
  var BACKOFF_MAX = 60000;
  var TICKS = { session: 0, loc: 0, pos: 0 };
  var backoff = { session: 5000, loc: 5000, pos: 20000 };
  var state = { session: null, drivers: {}, points: [], positions: [], lastPointDate: 0 };
  var canvas = null, ctx = null, W = 0, H = 0, bounds = null;
  var ws = null;

  function el(id) { return document.getElementById(id); }

  function fetchJSON(path, timeout) {
    return ws.fetchJSON(BASE + path, timeout);
  }

  function teamColor(num) {
    var d = state.drivers[num];
    return d && d.team_colour ? '#' + d.team_colour : '#888';
  }

  // ------------------------------------------------------------ data
  function loadSession() {
    return fetchJSON('/sessions?session_key=latest').then(function (s) {
      state.session = s[0] || null;
      good('session');
      renderInfo();
      if (!state.session) return;
      return fetchJSON('/drivers?session_key=' + state.session.session_key).then(function (ds) {
        state.drivers = {};
        ds.forEach(function (d) { state.drivers[d.driver_number] = d; });
        return pollPositions();
      });
    });
  }

  function isoMinutesAgo(min) {
    return new Date(Date.now() - min * 60000).toISOString().replace(/\.\d+Z$/, '+00:00');
  }

  function pollLocations() {
    if (!state.session) return Promise.resolve();
    var since = isoMinutesAgo(state.lastPointDate ? 0.2 : 3);
    return fetchJSON('/location?session_key=' + state.session.session_key +
        '&date>=' + encodeURIComponent(since))
      .then(function (pts) {
        pts.forEach(function (p) {
          var t = new Date(p.date).getTime();
          if (t > state.lastPointDate) state.lastPointDate = t;
          state.points.push(p);
        });
        if (state.points.length > 6000) state.points = state.points.slice(-4000);
        recomputeBounds();
        draw();
        good('loc');
      })
      .catch(function (e) { fail('loc', e); });
  }

  function pollPositions() {
    if (!state.session) return Promise.resolve();
    return fetchJSON('/position?session_key=' + state.session.session_key)
      .then(function (pos) {
        // Latest snapshot per driver = current running order.
        var latest = {};
        pos.forEach(function (p) {
          if (!latest[p.driver_number] || new Date(p.date) > new Date(latest[p.driver_number].date)) {
            latest[p.driver_number] = p;
          }
        });
        state.positions = Object.keys(latest)
          .map(function (k) { return latest[k]; })
          .filter(function (p) { return p.position != null; })
          .sort(function (a, b) { return a.position - b.position; });
        good('pos');
        renderLeaderboard();
      })
      .catch(function (e) { fail('pos', e); });
  }

  // Poll gate: TICKS advance on success AND failure, so cadence is always
  // backoff-driven — no retry storms during outages (verified by probe).
  function good(kind) {
    backoff[kind] = REFRESH[kind];
    TICKS[kind] = Date.now();
    if (kind === 'loc') {
      ws.setBanner('');
      detectStale();
    }
  }

  function fail(kind, e) {
    backoff[kind] = Math.min(BACKOFF_MAX, backoff[kind] * 2);
    TICKS[kind] = Date.now();
    if (String(e && e.message).indexOf('429') >= 0) {
      ws.setBanner('OpenF1 rate-limited — retrying in ' + Math.round(backoff[kind] / 1000) + 's');
    }
  }

  // Stale-data honesty: no cars for >10min shows a replay banner.
  function detectStale() {
    if (!state.lastPointDate) return;
    var age = Date.now() - state.lastPointDate;
    if (age > 10 * 60000) {
      ws.setBanner('No live cars right now — replaying the most recent session (' +
        new Date(state.lastPointDate).toLocaleTimeString() + ').');
    }
  }

  // ------------------------------------------------------------ drawing
  function recomputeBounds() {
    var xs = [], ys = [];
    state.points.forEach(function (p) { xs.push(p.x); ys.push(p.y); });
    if (!xs.length) return;
    var minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
    var minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
    var pad = Math.max(10, (maxX - minX) * 0.05, (maxY - minY) * 0.05);
    bounds = { minX: minX - pad, maxX: maxX + pad, minY: minY - pad, maxY: maxY + pad };
  }

  function project(x, y) {
    return {
      px: 20 + (x - bounds.minX) / (bounds.maxX - bounds.minX) * (W - 40),
      py: H - 20 - (y - bounds.minY) / (bounds.maxY - bounds.minY) * (H - 40),
    };
  }

  function draw() {
    if (!ctx || !bounds) return;
    ctx.fillStyle = '#050507';
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = '#1c1c1f';
    ctx.lineWidth = 1;
    for (var g = 1; g < 10; g++) {
      ctx.beginPath(); ctx.moveTo(0, H / 10 * g); ctx.lineTo(W, H / 10 * g); ctx.stroke();
    }
    // per-car trails from the GPS point stream
    var byCar = {};
    state.points.forEach(function (p) { (byCar[p.driver_number] = byCar[p.driver_number] || []).push(p); });
    Object.keys(byCar).forEach(function (num) {
      var pts = byCar[num];
      ctx.strokeStyle = teamColor(+num);
      ctx.lineWidth = 1.2;
      ctx.globalAlpha = 0.55;
      ctx.beginPath();
      pts.forEach(function (p, i) {
        var q = project(p.x, p.y);
        if (i === 0) ctx.moveTo(q.px, q.py); else ctx.lineTo(q.px, q.py);
      });
      ctx.stroke();
      ctx.globalAlpha = 1;
      var last = pts[pts.length - 1];
      var d = project(last.x, last.y);
      ctx.fillStyle = teamColor(+num);
      ctx.beginPath(); ctx.arc(d.px, d.py, 4.5, 0, Math.PI * 2); ctx.fill();
      var drv = state.drivers[+num];
      if (drv) {
        ctx.font = '10px monospace';
        ctx.fillStyle = '#d4d4d8';
        ctx.fillText(drv.name_acronym || drv.broadcast_name || num, d.px + 7, d.py + 3);
      }
    });
  }

  // ------------------------------------------------------------ UI bits
  function renderInfo() {
    var s = state.session;
    ws.setLive(s ? (s.session_name + ' · ' + (s.location || '') + ' · ' + (s.country_name || '') +
      ' · key ' + s.session_key) : 'No session data.');
  }

  function renderLeaderboard() {
    var lb = el('f1Leaderboard');
    if (!lb) return;
    lb.textContent = '';
    if (!state.positions.length) {
      var none = document.createElement('div');
      none.className = 'f1-lb-row';
      none.textContent = 'No position data (sessions before qualifying have no running order).';
      lb.appendChild(none);
      return;
    }
    state.positions.forEach(function (p) {
      var row = document.createElement('div');
      row.className = 'f1-lb-row';
      var pos = document.createElement('span');
      pos.className = 'f1-pos';
      pos.textContent = p.position;
      var chip = document.createElement('span');
      chip.className = 'f1-chip';
      chip.style.background = teamColor(p.driver_number);
      var name = document.createElement('span');
      name.className = 'f1-name';
      var drv = state.drivers[p.driver_number];
      name.textContent = (drv && (drv.full_name || drv.broadcast_name)) || ('Car ' + p.driver_number);
      row.appendChild(pos);
      row.appendChild(chip);
      row.appendChild(name);
      lb.appendChild(row);
    });
  }

  // ------------------------------------------------------------ lifecycle
  function buildAsk() {
    var s = state.session || {};
    var lead = state.positions.slice(0, 5).map(function (p) {
      var d = state.drivers[p.driver_number];
      return p.position + '. ' + (d ? d.full_name : p.driver_number);
    }).join(', ');
    return 'Live F1 session: ' + (s.session_name || 'unknown') + ' at ' + (s.location || 'unknown') +
      '. Running order: ' + (lead || 'not yet available') + '. User asks: ';
  }

  function tick() {
    var now = Date.now();
    if (!state.session) {
      // Session never loaded (e.g. rate limit at boot) — keep retrying on
      // the tick loop; pollLocations/pollPositions early-return meanwhile.
      if (now - TICKS.session >= backoff.session) {
        loadSession().catch(function (e) { fail('session', e); });
      }
      return;
    }
    if (now - TICKS.loc >= backoff.loc) pollLocations();
    if (now - TICKS.pos >= backoff.pos) pollPositions();
  }

  function start() {
    canvas = el('f1Track');
    if (!canvas || ws) return;
    ws = Workspace.create({
      name: 'F1',
      bannerId: 'f1Banner',
      liveId: 'f1Info',
      askBtnId: 'f1Ask',
      askInputId: 'f1Question',
      buildAsk: buildAsk,
      onTick: tick,
    });
    ctx = canvas.getContext('2d');
    // Same responsive backing store as God's Eye (fallback 1000x560).
    var r = canvas.getBoundingClientRect();
    W = canvas.width = Math.max(500, Math.round(r.width || 1000));
    H = canvas.height = Math.max(280, Math.round(r.height || 560));
    if (!start._resizeWired) {
      start._resizeWired = true;
      window.addEventListener('resize', function () {
        if (!canvas || !ws) return;
        var rr = canvas.getBoundingClientRect();
        if (rr.width > 50 && rr.height > 50) {
          W = canvas.width = Math.round(rr.width);
          H = canvas.height = Math.round(rr.height);
        }
      });
    }
    ws.start();
    loadSession()
      .then(function () { pollLocations(); })
      .catch(function (e) { fail('session', e); });
  }

  function stop() {
    if (ws) { ws.stop(); ws = null; }  // null so the next start() re-arms
  }

  window.OrbitF1 = {
    start: start,
    stop: stop,
    state: function () {
      return { session: state.session, positions: state.positions, cars: Object.keys(state.drivers).length };
    },
  };
})();
