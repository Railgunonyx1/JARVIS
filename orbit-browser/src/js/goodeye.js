/* goodeye.js — orbit://goodeye workspace (God's Eye View integration).
 *
 * Live public signals on one world canvas — aircraft, earthquakes, the ISS.
 * All feeds verified CORS-open from the Orbit renderer; no keys, no proxies,
 * no third-party map tiles. Lifecycle + Ask-JARVIS + logging come from
 * workspace.js — this file owns only data and drawing.
 *
 * Exposes window.GoodEye: start/stop (router-driven), state()
 */
(function () {
  'use strict';

  var REFRESH = { iss: 3000, air: 15000, quakes: 60000 };
  var TICKS = { iss: 0, air: 0, quakes: 0 };
  var state = { iss: null, aircraft: [], quakes: [] };
  var world = null, wctx = null, W = 0, H = 0;
  var ws = null;

  function el(id) { return document.getElementById(id); }

  function draw() {
    if (!wctx || !window.WorldMap) return;
    var Wm = window.WorldMap;
    Wm.draw(wctx, W, H);
    // earthquakes: rings scaled by magnitude — meaningful events only (M3+);
    // plotting every M0.2 micro-quake was pure ring clutter.
    wctx.strokeStyle = '#d4d4d8';
    wctx.lineWidth = 1;
    state.quakes.forEach(function (q) {
      if (q.mag < 3) return;
      var p = Wm.project(q.lat, q.lon, W, H);
      wctx.beginPath();
      wctx.arc(p.x, p.y, Math.min(14, 2 + q.mag * 2), 0, Math.PI * 2);
      wctx.stroke();
    });
    // aircraft: 2.5px specks
    wctx.fillStyle = '#7d7d85';
    state.aircraft.forEach(function (a) {
      if (a.lat == null) return;
      var p = Wm.project(a.lat, a.lon, W, H);
      wctx.fillRect(p.x - 1, p.y - 1, 2.5, 2.5);
    });
    // ISS: crosshair + label
    if (state.iss) {
      var ip = Wm.project(state.iss.lat, state.iss.lon, W, H);
      wctx.strokeStyle = '#ffffff';
      wctx.lineWidth = 1.5;
      wctx.beginPath(); wctx.arc(ip.x, ip.y, 6, 0, Math.PI * 2); wctx.stroke();
      wctx.beginPath();
      wctx.moveTo(ip.x - 10, ip.y); wctx.lineTo(ip.x + 10, ip.y);
      wctx.moveTo(ip.x, ip.y - 10); wctx.lineTo(ip.x, ip.y + 10);
      wctx.stroke();
      wctx.font = '10px monospace';
      wctx.fillStyle = '#ffffff';
      wctx.fillText('ISS', ip.x + 12, ip.y - 8);
      ws.setLive('ISS ' + state.iss.lat.toFixed(1) + ', ' + state.iss.lon.toFixed(1) +
        ' · ' + Math.round(state.iss.alt) + 'km · ' + Math.round(state.iss.vel) + 'km/h');
    }
  }

  // ------------------------------------------------------------ feeds
  function pollIss() {
    return ws.fetchJSON('https://api.wheretheiss.at/v1/satellites/25544')
      .then(function (d) {
        state.iss = { lat: d.latitude, lon: d.longitude, alt: d.altitude, vel: d.velocity };
        TICKS.iss = Date.now();
        draw();
      });
    // errors propagate to fail() — no internal swallow
  }

  function pollAircraft() {
    // Bounded box keeps the response light; OpenSky tolerates anonymous GETs here.
    return ws.fetchJSON('https://opensky-network.org/api/states/all?lamin=35&lomin=-10&lamax=60&lomax=30')
      .then(function (d) {
        state.aircraft = (d.states || []).slice(0, 300).map(function (s) {
          return { icao: s[0], callsign: (s[1] || '').trim(), lat: s[6], lon: s[5], alt: s[7] || s[13] || 0, vel: s[9] || 0 };
        });
        TICKS.air = Date.now();
        draw();
      });
    // errors propagate to fail()
  }

  function pollQuakes() {
    return ws.fetchJSON('https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson')
      .then(function (d) {
        state.quakes = (d.features || []).map(function (f) {
          return { mag: f.properties.mag, place: f.properties.place,
                   lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] };
        }).filter(function (q) { return q.mag != null && q.mag >= 2.5; });
        TICKS.quakes = Date.now();
        draw();
      });
    // errors propagate to fail()
  }

  // What JARVIS sees when the user asks about the current picture.
  function buildAsk() {
    var top = state.quakes.slice().sort(function (a, b) { return b.mag - a.mag; })[0];
    var s = 'God\u2019s Eye live picture: ' + state.aircraft.length + ' aircraft tracked';
    if (top) s += '; strongest quake M' + top.mag + ' (' + (top.place || 'unknown') + ')';
    if (state.iss) s += '; ISS at ' + state.iss.lat.toFixed(1) + ',' + state.iss.lon.toFixed(1);
    return s + '. User asks: ';
  }

  // Per-feed adaptive backoff (F1's model): a 429ing feed doubles its next
  // attempt up to 60s instead of re-hitting the provider every 15s — the
  // OpenSky anonymous tier rate-limits fast and hammering it extends the ban.
  var backoff = { iss: REFRESH.iss, air: REFRESH.air, quakes: REFRESH.quakes };

  function good(kind) {
    backoff[kind] = REFRESH[kind];
    TICKS[kind] = Date.now();
  }

  function fail(kind, e) {
    backoff[kind] = Math.min(60000, backoff[kind] * 2);
    TICKS[kind] = Date.now();
    ws.log(kind + ' feed failed: ' + e.message + ' — retrying in ' +
      Math.round(backoff[kind] / 1000) + 's', true);
  }

  function tick() {
    var now = Date.now();
    // A-11: advance the next-attempt time BEFORE issuing the request, so a
    // slow/down feed cannot start a new request every tick while the old one
    // is still hanging (retry storm).
    if (now - TICKS.iss >= backoff.iss) { TICKS.iss = now; pollIss().then(function(){ good('iss'); }, function(e){ fail('iss', e); }); }
    if (now - TICKS.air >= backoff.air) { TICKS.air = now; pollAircraft().then(function(){ good('air'); }, function(e){ fail('air', e); }); }
    if (now - TICKS.quakes >= backoff.quakes) { TICKS.quakes = now; pollQuakes().then(function(){ good('quakes'); }, function(e){ fail('quakes', e); }); }
  }

  function start() {
    world = el('geWorld');
    if (!world || ws) return;
    ws = Workspace.create({
      name: "God's Eye",
      logId: 'geLog',
      liveId: 'geLive',
      askBtnId: 'geAsk',
      askInputId: 'geQuestion',
      buildAsk: buildAsk,
      onTick: tick,
    });
    wctx = world.getContext('2d');
    // Backing store follows the element's CSS box: crisp at any window size
    // and immune to first-show layout races (falls back to 1200x520).
    var r = world.getBoundingClientRect();
    W = world.width = Math.max(600, Math.round(r.width || 1200));
    H = world.height = Math.max(300, Math.round(r.height || 520));
    if (window.WorldMap) window.WorldMap.draw(wctx, W, H);
    if (!start._resizeWired) {
      start._resizeWired = true;
      window.addEventListener('resize', function () {
        if (!world || !ws) return;
        var rr = world.getBoundingClientRect();
        if (rr.width > 50 && rr.height > 50) {
          W = world.width = Math.round(rr.width);
          H = world.height = Math.round(rr.height);
          if (window.WorldMap) window.WorldMap.draw(wctx, W, H);
        }
      });
    }
    ws.start();
    tick();
    ws.log('God\u2019s Eye online — fusing public signals.');
  }

  function stop() {
    if (ws) { ws.stop(); ws = null; }  // null so the next start() re-arms
  }

  window.GoodEye = { start: start, stop: stop, state: function () { return state; } };
})();
