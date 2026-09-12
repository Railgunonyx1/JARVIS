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

  // Coarse continent outlines (same offline dataset as God's Eye).
  var LAND = [
    [[-168,66],[-140,70],[-125,72],[-95,74],[-80,73],[-70,62],[-55,52],[-65,45],[-75,40],[-80,32],[-82,25],[-90,18],[-95,15],[-105,20],[-115,30],[-125,40],[-130,52],[-145,60],[-168,66]],
    [[-10,36],[0,44],[10,45],[25,40],[28,36],[35,36],[45,40],[60,45],[90,48],[135,50],[145,60],[160,62],[170,66],[178,70],[160,70],[140,72],[110,74],[90,72],[70,70],[60,68],[45,66],[30,60],[20,55],[15,50],[5,48],[-5,44],[-10,36]],
    [[-8,44],[0,40],[8,38],[15,40],[22,38],[28,36],[32,31],[35,28],[40,20],[43,12],[51,12],[48,-2],[42,-12],[40,-20],[35,-25],[28,-33],[20,-35],[15,-28],[12,-18],[9,-6],[10,2],[0,4],[-8,4],[-8,44]],
    [[72,20],[80,15],[88,22],[92,22],[95,16],[100,14],[104,10],[102,2],[110,2],[118,5],[122,12],[110,20],[100,22],[90,25],[80,22],[72,20]],
    [[115,-22],[125,-16],[135,-13],[142,-12],[148,-20],[153,-28],[150,-37],[145,-39],[138,-36],[130,-32],[122,-34],[115,-34],[113,-26],[115,-22]],
    [[130,32],[135,35],[140,40],[143,44],[140,43],[137,38],[132,34],[130,32]],
    [[-84,10],[-76,8],[-70,12],[-62,10],[-55,5],[-52,0],[-60,-4],[-70,-8],[-76,-12],[-80,-6],[-82,0],[-84,10]]
  ];

  function project(lat, lon) {
    return { x: (lon + 180) / 360 * W, y: (90 - lat) / 180 * H };
  }

  function drawWorld() {
    if (!wctx) return;
    wctx.fillStyle = '#050507';
    wctx.fillRect(0, 0, W, H);
    wctx.strokeStyle = '#1c1c1f';
    wctx.lineWidth = 1;
    for (var gx = 0; gx <= 360; gx += 30) {
      var p = project(0, gx - 180);
      wctx.beginPath(); wctx.moveTo(p.x, 0); wctx.lineTo(p.x, H); wctx.stroke();
    }
    for (var gy = 0; gy <= 180; gy += 30) {
      var q = project(gy - 90, 0);
      wctx.beginPath(); wctx.moveTo(0, q.y); wctx.lineTo(W, q.y); wctx.stroke();
    }
    wctx.fillStyle = '#2a2a2e';
    LAND.forEach(function (poly) {
      wctx.beginPath();
      poly.forEach(function (pt, i) {
        var r = project(pt[0], pt[1]);
        if (i === 0) wctx.moveTo(r.x, r.y); else wctx.lineTo(r.x, r.y);
      });
      wctx.closePath();
      wctx.fill();
    });
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
    if (now - TICKS.quakes >= REFRESH.quakes) pollQuakes();
    if (now - TICKS.iss >= REFRESH.iss) pollIss();
    if (now - TICKS.wx >= REFRESH.wx) pollWeather();
    if (now - TICKS.mkt >= REFRESH.mkt) pollMarket();
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
