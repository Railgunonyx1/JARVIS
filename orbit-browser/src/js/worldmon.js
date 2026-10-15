/* worldmon.js — orbit://worldmon workspace (WorldMonitor-inspired).
 *
 * A live global-intelligence board in the spirit of github.com/koala73/worldmonitor,
 * rebuilt for Orbit's Nothing design system: worldwide seismic events on a world
 * canvas, ISS position, weather for world capitals, and a market ticker.
 * All feeds are CORS-open and key-free (verified live from the renderer):
 *   USGS 4.5+ week  · wheretheiss.at  · open-meteo.com  · coinbase.com
 * Lifecycle + Ask-JARVIS + logging come from workspace.js; this file owns
 * only data and drawing.
 *
 * Exposes window.WorldMon: start/stop (router-driven), state()
 */
(function () {
  'use strict';

  var REFRESH = { quakes: 60000, iss: 5000, wx: 900000, mkt: 120000 };
  var TICKS = { quakes: 0, iss: 0, wx: 0, mkt: 0 };
  var state = { quakes: [], iss: null, wx: {}, btc: null };
  var world = null, wctx = null, W = 0, H = 0;
  var ws = null;

  function el(id) { return document.getElementById(id); }

  // World capitals: [name, lat, lon] — one Open-Meteo call each, 15-min TTL.
  var CAPITALS = [
    ['London', 51.5, -0.12], ['Paris', 48.85, 2.35], ['Berlin', 52.52, 13.4],
    ['Kyiv', 50.45, 30.52], ['Washington', 38.9, -77.04], ['Tokyo', 35.68, 139.69],
    ['Beijing', 39.9, 116.4], ['New Delhi', 28.61, 77.21], ['Moscow', 55.76, 37.62],
  ];

  function project(lat, lon) {
    if (!window.WorldMap) return { x: 0, y: 0 };
    return window.WorldMap.project(lat, lon, W, H);
  }

  function drawWorld() {
    if (!wctx || !window.WorldMap) return;
    window.WorldMap.draw(wctx, W, H);
  }

  function draw() {
    if (!wctx) return;
    drawWorld();
    // Quakes: filled dots, radius ~ magnitude, brighter = shallower.
    state.quakes.forEach(function (q) {
      var p = project(q.lat, q.lon);
      var rad = 2 + Math.min(9, (q.mag - 4) * 3);
      wctx.beginPath();
      wctx.arc(p.x, p.y, rad, 0, Math.PI * 2);
      wctx.fillStyle = 'rgba(224,224,228,' + Math.min(0.9, 0.3 + q.mag / 12) + ')';
      wctx.fill();
      wctx.strokeStyle = '#3a3a40';
      wctx.stroke();
    });
    // ISS: crosshair marker.
    if (state.iss) {
      var p = project(state.iss.latitude, state.iss.longitude);
      wctx.strokeStyle = '#e8e8e8';
      wctx.lineWidth = 1.4;
      wctx.beginPath();
      wctx.moveTo(p.x - 7, p.y); wctx.lineTo(p.x + 7, p.y);
      wctx.moveTo(p.x, p.y - 7); wctx.lineTo(p.x, p.y + 7);
      wctx.stroke();
      wctx.beginPath();
      wctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
      wctx.stroke();
    }
  }

  // ------------------------------------------------------------ data
  function pollQuakes() {
    return ws.fetchJSON('https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson')
      .then(function (j) {
        state.quakes = (j.features || []).map(function (f) {
          return { lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0],
                   mag: f.properties.mag || 0, place: f.properties.place || '' };
        }).sort(function (a, b) { return b.mag - a.mag; }).slice(0, 80);
        TICKS.quakes = Date.now();
        draw();
        renderQuakeList();
        ws.setLive(state.quakes.length + ' quakes M4.5+ / 7d');
      })
      .catch(function (e) { ws.log('quakes: ' + e.message, true); });
  }

  function pollIss() {
    return ws.fetchJSON('https://api.wheretheiss.at/v1/satellites/25544', 6000)
      .then(function (s) {
        state.iss = s;
        TICKS.iss = Date.now();
        draw();
        var iss = el('wmIss');
        if (iss) iss.textContent = 'ISS ' + s.latitude.toFixed(1) + '\u00b0, ' + s.longitude.toFixed(1) + '\u00b0 · alt ' + Math.round(s.altitude) + ' km';
      })
      .catch(function () { /* next tick retries */ });
  }

  function pollWeather() {
    TICKS.wx = Date.now();
    CAPITALS.forEach(function (c) {
      ws.fetchJSON('https://api.open-meteo.com/v1/forecast?latitude=' + c[1] +
                   '&longitude=' + c[2] + '&current=temperature_2m,weather_code', 8000)
        .then(function (w) {
          state.wx[c[0]] = { t: Math.round(w.current.temperature_2m), code: w.current.weather_code };
          renderWx();
        })
        .catch(function () { /* keep last */ });
    });
  }

  function pollMarket() {
    return ws.fetchJSON('https://api.coinbase.com/v2/prices/BTC-USD/spot', 6000)
      .then(function (j) {
        state.btc = parseFloat(j.data.amount);
        TICKS.mkt = Date.now();
        var m = el('wmBtc');
        if (m && state.btc) m.textContent = 'BTC $' + state.btc.toLocaleString('en-US', { maximumFractionDigits: 0 });
      })
      .catch(function () { /* next tick retries */ });
  }

  // ------------------------------------------------------------ render
  function renderQuakeList() {
    var list = el('wmQuakes');
    if (!list) return;
    list.textContent = '';
    state.quakes.slice(0, 12).forEach(function (q) {
      var row = document.createElement('div');
      row.className = 'wm-qrow';
      var mag = document.createElement('span');
      mag.className = 'wm-qmag';
      mag.textContent = 'M' + q.mag.toFixed(1);
      var place = document.createElement('span');
      place.className = 'wm-qplace';
      place.textContent = q.place || '—';
      row.appendChild(mag); row.appendChild(place);
      list.appendChild(row);
    });
  }

  function renderWx() {
    var grid = el('wmWx');
    if (!grid) return;
    grid.textContent = '';
    CAPITALS.forEach(function (c) {
      var d = state.wx[c[0]];
      if (!d) return;
      var cell = document.createElement('div');
      cell.className = 'wm-wxcell';
      var name = document.createElement('span');
      name.className = 'wm-wxname';
      name.textContent = c[0];
      var temp = document.createElement('span');
      temp.className = 'wm-wxtemp';
      temp.textContent = d.t + '\u00b0C';
      cell.appendChild(name); cell.appendChild(temp);
      grid.appendChild(cell);
    });
  }

  function buildAsk() {
    var top = state.quakes.slice(0, 5).map(function (q) {
      return 'M' + q.mag.toFixed(1) + ' — ' + q.place;
    }).join('; ');
    return 'World Monitor snapshot. Strongest quakes this week: ' + (top || 'none listed') +
      '. BTC: $' + (state.btc || '?') + '. ';
  }

  function tick() {
    var now = Date.now();
    // A-11: advance next-attempt time before issuing (retry-storm guard).
    if (now - TICKS.quakes >= REFRESH.quakes) { TICKS.quakes = now; pollQuakes(); }
    if (now - TICKS.iss >= REFRESH.iss) { TICKS.iss = now; pollIss(); }
    if (now - TICKS.wx >= REFRESH.wx) { TICKS.wx = now; pollWeather(); }
    if (now - TICKS.mkt >= REFRESH.mkt) { TICKS.mkt = now; pollMarket(); }
  }

  function start() {
    world = el('wmWorld');
    if (!world || ws) return;
    ws = Workspace.create({
      name: 'World Monitor',
      logId: 'wmLog',
      liveId: 'wmLive',
      askBtnId: 'wmAsk',
      askInputId: 'wmQuestion',
      buildAsk: buildAsk,
      onTick: tick,
    });
    wctx = world.getContext('2d');
    var r = world.getBoundingClientRect();
    W = world.width = Math.max(500, Math.round(r.width || 900));
    H = world.height = Math.max(280, Math.round(r.height || 460));
    drawWorld();
    if (!start._resizeWired) {
      start._resizeWired = true;
      window.addEventListener('resize', function () {
        if (!world || !ws) return;
        var rr = world.getBoundingClientRect();
        if (rr.width > 50 && rr.height > 50) {
          W = world.width = Math.round(rr.width);
          H = world.height = Math.round(rr.height);
          drawWorld();
        }
      });
    }
    ws.start();
    tick();
    ws.log('World Monitor online — public signals, no keys.');
  }

  function stop() {
    if (ws) { ws.stop(); ws = null; }  // null so the next start() re-arms
  }

  window.WorldMon = { start: start, stop: stop, state: function () { return state; } };
})();
