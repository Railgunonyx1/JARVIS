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

  // Coarse continent outlines for the equirectangular canvas (tiny, offline).
  var LAND = [
    // North America
    [[-168,66],[-140,70],[-125,72],[-95,74],[-80,73],[-70,62],[-55,52],[-65,45],[-75,40],[-80,32],[-82,25],[-90,18],[-95,15],[-105,20],[-115,30],[-125,40],[-130,52],[-145,60],[-168,66]],
    // Eurasia
    [[-10,36],[0,44],[10,45],[25,40],[28,36],[35,36],[45,40],[60,45],[90,48],[135,50],[145,60],[160,62],[170,66],[178,70],[160,70],[140,72],[110,74],[90,72],[70,70],[60,68],[45,66],[30,60],[20,55],[15,50],[5,48],[-5,44],[-10,36]],
    // Africa
    [[-8,44],[0,40],[8,38],[15,40],[22,38],[28,36],[32,31],[35,28],[40,20],[43,12],[51,12],[48,-2],[42,-12],[40,-20],[35,-25],[28,-33],[20,-35],[15,-28],[12,-18],[9,-6],[10,2],[0,4],[-8,4],[-8,44]],
    // South Asia
    [[72,20],[80,15],[88,22],[92,22],[95,16],[100,14],[104,10],[102,2],[110,2],[118,5],[122,12],[110,20],[100,22],[90,25],[80,22],[72,20]],
    // Australia
    [[115,-22],[125,-16],[135,-13],[142,-12],[148,-20],[153,-28],[150,-37],[145,-39],[138,-36],[130,-32],[122,-34],[115,-34],[113,-26],[115,-22]],
    // Japan
    [[130,32],[135,35],[140,40],[143,44],[140,43],[137,38],[132,34],[130,32]],
    // South America
    [[-84,10],[-76,8],[-70,12],[-62,10],[-55,5],[-52,0],[-60,-4],[-70,-8],[-76,-12],[-80,-6],[-82,0],[-84,10]],
  ];

  function project(lat, lon) {
    return { x: (lon + 180) / 360 * W, y: (90 - lat) / 180 * H };
  }

  function drawWorld() {
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
    // earthquakes: rings scaled by magnitude
    wctx.strokeStyle = '#d4d4d8';
    wctx.lineWidth = 1;
    state.quakes.forEach(function (q) {
      var p = project(q.lat, q.lon);
      wctx.beginPath();
      wctx.arc(p.x, p.y, Math.min(14, 2 + q.mag * 2), 0, Math.PI * 2);
      wctx.stroke();
    });
    // aircraft: 2.5px specks
    wctx.fillStyle = '#7d7d85';
    state.aircraft.forEach(function (a) {
      if (a.lat == null) return;
      var p = project(a.lat, a.lon);
      wctx.fillRect(p.x - 1, p.y - 1, 2.5, 2.5);
    });
    // ISS: crosshair + label
    if (state.iss) {
      var ip = project(state.iss.lat, state.iss.lon);
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
      })
      .catch(function (e) { ws.log('ISS feed failed: ' + e.message, true); });
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
      })
      .catch(function (e) { ws.log('Aircraft feed failed: ' + e.message, true); });
  }

  function pollQuakes() {
    return ws.fetchJSON('https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson')
      .then(function (d) {
        state.quakes = (d.features || []).map(function (f) {
          return { mag: f.properties.mag, place: f.properties.place,
                   lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] };
        }).filter(function (q) { return q.mag != null; });
        TICKS.quakes = Date.now();
        draw();
      })
      .catch(function (e) { ws.log('Quake feed failed: ' + e.message, true); });
  }

  // What JARVIS sees when the user asks about the current picture.
  function buildAsk() {
    var top = state.quakes.slice().sort(function (a, b) { return b.mag - a.mag; })[0];
    var s = 'God\u2019s Eye live picture: ' + state.aircraft.length + ' aircraft tracked';
    if (top) s += '; strongest quake M' + top.mag + ' (' + (top.place || 'unknown') + ')';
    if (state.iss) s += '; ISS at ' + state.iss.lat.toFixed(1) + ',' + state.iss.lon.toFixed(1);
    return s + '. User asks: ';
  }

  function tick() {
    var now = Date.now();
    if (now - TICKS.iss >= REFRESH.iss) pollIss();
    if (now - TICKS.air >= REFRESH.air) pollAircraft();
    if (now - TICKS.quakes >= REFRESH.quakes) pollQuakes();
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
    ws.log('God\u2019s Eye online — fusing public signals.');
  }

  function stop() {
    if (ws) { ws.stop(); ws = null; }  // null so the next start() re-arms
  }

  window.GoodEye = { start: start, stop: stop, state: function () { return state; } };
})();
