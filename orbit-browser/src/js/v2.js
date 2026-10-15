/* ORBIT v2 — Fugu skin behaviors.
 * Independent, additive module: nothing here is required by core; every
 * feature degrades silently if its element is missing.
 *
 * 1. OrbV2   — thinking-orbs-inspired canvas agent states (concept from
 *              github.com/Jakubantalik/thinking-orbs, MIT; this is a
 *              vanilla re-implementation mapped to Orbit's setMatrix verbs)
 * 2. Footer  — always-on telemetry strip (glances/uptime-kuma concept)
 * 3. NTP     — live UTC clock + contextual session card
 * 4. Tools   — orbit://tools utilities (it-tools/CyberChef concept)
 * 5. Looks   — settings accent/density/motion wiring (persisted)
 */
(function () {
  'use strict';
  var safe = window.safe || function (fn) { return fn; };

  /* ── 1. OrbV2: canvas agent states ───────────────────────────── */
  var ORB_MAP = {
    idle: 'breathing', thinking: 'working', planning: 'composing',
    running: 'searching', ask: 'listening', done: 'solved',
    fail: 'fail', offline: 'offline', link: 'connecting',
  };
  var REDUCED = false;
  try { REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) {}

  function orbInk(el) {
    var accent = getComputedStyle(document.documentElement)
      .getPropertyValue('--jb-accent').trim() || '#00f5ff';
    var s = el.dataset.state || 'idle';
    if (s === 'offline' || s === 'idle') return 'rgba(132,148,149,0.75)';
    if (s === 'fail') return 'rgba(255,138,122,0.9)';
    return accent;
  }

  function drawOrb(ctx, size, t, verb, ink) {
    ctx.clearRect(0, 0, size, size);
    var c = size / 2;
    ctx.fillStyle = ink;
    var dot = function (x, y, r, a) {
      ctx.globalAlpha = a == null ? 1 : a;
      ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.fill();
    };
    var r = size * 0.36;
    if (verb === 'working') {           // particles on tilted orbits
      var tilt = 0.5;
      for (var k = 0; k < 2; k++) {
        for (var i = 0; i < 8; i++) {
          var a = t * (1.6 + k * 0.7) + i * (Math.PI / 4) + k * 0.4;
          var x = Math.cos(a) * r;
          var y = Math.sin(a) * r * tilt * (k ? 0.55 : 1);
          dot(c + x, c + y, size * 0.045, 0.35 + 0.65 * Math.abs(Math.cos(a)));
        }
      }
    } else if (verb === 'searching') {  // scan meridian sweeps a dotted globe
      for (var g = 0; g < 26; g++) {
        var th = (g / 26) * Math.PI - Math.PI / 2;
        for (var p = 0; p < 3; p++) {
          var ph = p * Math.PI / 3 + Math.PI / 6;
          var x3 = Math.cos(th) * Math.cos(ph) * r;
          var y3 = Math.sin(th) * r;
          var z = Math.sin(th) * Math.sin(ph);
          var sweep = Math.cos(t * 2.2);
          var lit = z * sweep > 0.55;
          if (!lit && p !== 1) continue;
          dot(c + x3, c + y3, size * 0.03, lit ? 0.95 : 0.22);
        }
      }
    } else if (verb === 'composing') {  // undulating multi-band sash
      for (var b = 0; b < 3; b++) {
        for (var i2 = 0; i2 < 9; i2++) {
          var x2 = (i2 / 8) * 2 * r - r;
          var y2 = Math.sin(t * 3 + i2 * 0.9 + b * 1.4) * r * 0.22 + (b - 1) * r * 0.3;
          dot(c + x2, c + y2, size * 0.04, 0.85 - Math.abs(x2) / (r * 2));
        }
      }
    } else if (verb === 'listening') {  // waveform rolls through the rings
      for (var w = 0; w < 11; w++) {
        var xw = (w / 10) * 2 * r - r;
        var amp = Math.sin(t * 5 + w * 0.8);
        var yw = amp * r * 0.34;
        dot(c + xw, c + yw, size * 0.045, 0.45 + 0.5 * Math.abs(amp));
      }
    } else if (verb === 'connecting') { // constellation wires itself
      var pts = [[-0.5, -0.3], [0.4, -0.45], [0.55, 0.35], [-0.35, 0.45], [0, 0.05]];
      var n = 2 + Math.floor((Math.sin(t * 1.8) * 0.5 + 0.5) * 4);
      ctx.strokeStyle = ink; ctx.lineWidth = 1; ctx.globalAlpha = 0.5;
      for (var e = 1; e < n; e++) {
        ctx.beginPath();
        ctx.moveTo(c + pts[e - 1][0] * r, c + pts[e - 1][1] * r);
        ctx.lineTo(c + pts[e][0] * r, c + pts[e][1] * r);
        ctx.stroke();
      }
      for (var q = 0; q < pts.length; q++) {
        dot(c + pts[q][0] * r, c + pts[q][1] * r, size * 0.05, q < n ? 0.95 : 0.3);
      }
    } else if (verb === 'solved') {     // bands click back solved
      var click = Math.max(0, Math.sin(t * 2));
      for (var s3 = 0; s3 < 3; s3++) {
        for (var i3 = 0; i3 < 9; i3++) {
          var x3b = (i3 / 8) * 2 * r - r;
          var y3b = (s3 - 1) * r * 0.3 + Math.sin(i3 * 1.2 + s3) * r * 0.12 * (1 - click);
          dot(c + x3b, c + y3b, size * 0.04, 0.9 - s3 * 0.18);
        }
      }
    } else if (verb === 'fail') {       // static dim X
      ctx.strokeStyle = ink; ctx.lineWidth = size * 0.07; ctx.globalAlpha = 0.85;
      ctx.beginPath();
      ctx.moveTo(c - r * 0.7, c - r * 0.7); ctx.lineTo(c + r * 0.7, c + r * 0.7);
      ctx.moveTo(c + r * 0.7, c - r * 0.7); ctx.lineTo(c - r * 0.7, c + r * 0.7);
      ctx.stroke();
    } else if (verb === 'offline') {    // static dim ring
      for (var o = 0; o < 10; o++) {
        var ao = (o / 10) * 6.2832;
        dot(c + Math.cos(ao) * r, c + Math.sin(ao) * r, size * 0.035, 0.4);
      }
    } else {                            // breathing: morphing ring
      var rr = r * (0.86 + 0.14 * Math.sin(t * 1.4));
      for (var br = 0; br < 12; br++) {
        var ab = (br / 12) * 6.2832;
        dot(c + Math.cos(ab) * rr, c + Math.sin(ab) * rr, size * 0.04, 0.35 + 0.4 * Math.abs(Math.sin(t * 1.4)));
      }
    }
    ctx.globalAlpha = 1;
  }

  var orbs = [];
  function mountOrb(el) {
    if (!el || el.dataset.orbMounted) return;
    el.dataset.orbMounted = '1';
    var size = Math.max(18, el.clientWidth || 22);
    var canvas = document.createElement('canvas');
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = size * dpr; canvas.height = size * dpr;
    canvas.style.width = size + 'px'; canvas.style.height = size + 'px';
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'JARVIS agent state');
    el.textContent = '';
    el.appendChild(canvas);
    var ctx = canvas.getContext('2d');
    var orb = {
      el: el, ctx: ctx, size: size, dpr: dpr, t: Math.random() * 10,
      verb: function () { return ORB_MAP[el.dataset.state] || 'breathing'; },
    };
    orbs.push(orb);
    drawOrbFrame(orb);
  }
  function drawOrbFrame(orb) {
    var dpr = orb.dpr;
    orb.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var verb = orb.verb();
    var static_ = REDUCED || verb === 'fail' || verb === 'offline';
    if (static_) {
      // Static verb: the frame is identical every tick — draw once, then
      // stop repainting until the state changes (lastVerb differs).
      if (orb.lastVerb !== verb) { orb.lastVerb = verb; drawOrb(orb.ctx, orb.size, orb.t, verb, orbInk(orb.el)); }
      return;
    }
    orb.lastVerb = verb;
    orb.t += 0.016;
    drawOrb(orb.ctx, orb.size, orb.t, verb, orbInk(orb.el));
  }
  function orbLoop() {
    if (!document.hidden) {
      var live = false;
      for (var i = 0; i < orbs.length; i++) {
        drawOrbFrame(orbs[i]);
        // Keep the rAF chain alive only while at least one orb animates.
        var v = orbs[i].verb();
        if (!(REDUCED || v === 'fail' || v === 'offline')) live = true;
      }
      if (!live) { orbLoopRunning = false; return; }  // fully idle: park the loop
    }
    requestAnimationFrame(orbLoop);
  }
  var orbLoopRunning = false;
  // Restart hook: setMatrix flips a state -> if the loop parked itself and an
  // animated verb is now present, spin it back up.
  function kickOrbLoop() {
    if (orbLoopRunning) return;
    for (var i = 0; i < orbs.length; i++) {
      var v = orbs[i].verb();
      if (!(REDUCED || v === 'fail' || v === 'offline')) {
        orbLoopRunning = true;
        requestAnimationFrame(orbLoop);
        return;
      }
    }
  }
  document.addEventListener('visibilitychange', function () { if (!document.hidden) kickOrbLoop(); });
  window.kickOrbLoop = kickOrbLoop;  // core.setMatrix revives the loop on state change

  (safe(function initOrbs() {
    var slots = document.querySelectorAll('.sb-matrix, #jarvisFloatMatrix, #floatMatrix');
    for (var i = 0; i < slots.length; i++) mountOrb(slots[i]);
    kickOrbLoop();  // starts the loop only if any orb is animated
    // Late-mounted floats: catch them once the DOM settles.
    setTimeout(function () {
      var late = document.querySelectorAll('.sb-matrix, #jarvisFloatMatrix, #floatMatrix');
      for (var j = 0; j < late.length; j++) mountOrb(late[j]);
      kickOrbLoop();
    }, 1500);
  }, 'orbv2-init'))();

  /* ── 2. NTP clock + contextual card ───────────────────────────── */
  (safe(function initNtp() {
    var clock = document.getElementById('ntClock');
    var greeting = document.getElementById('ntGreeting');
    function tick() {
      // Visible-only: skip DOM writes when the NTP page isn't showing
      // (clock element exists but is display:none inside a hidden page).
      if (clock && clock.offsetParent !== null) {
        clock.textContent = new Date().toISOString().slice(11, 19) + ' UTC';
      }
      if (greeting && greeting.offsetParent !== null) {
        var h = new Date().getHours();
        greeting.textContent = (h < 5 ? 'Good night' : h < 12 ? 'Good morning' :
          h < 18 ? 'Good afternoon' : 'Good evening') + ', Commander.';
      }
    }
    setInterval(tick, 1000);
    tick();

    var card = document.getElementById('ntContextCard');
    var banner = document.getElementById('sessionBanner');
    if (card && banner) {
      new MutationObserver(function () {
        card.classList.toggle('show', banner.classList.contains('show') ||
          banner.style.display !== 'none' && getComputedStyle(banner).display !== 'none' &&
          banner.classList.contains('visible'));
      }).observe(banner, { attributes: true, attributeFilter: ['class', 'style'] });
      var resume = document.getElementById('ntContextResume');
      if (resume) resume.addEventListener('click', function (e) {
        e.stopPropagation();
        var restore = document.getElementById('sessionRestore');
        if (restore) restore.click();
        if (card) card.classList.remove('show');
      });
    }
  }, 'v2-ntp'))();

  /* ── 4. Tools page (orbit://tools) ────────────────────────────── */
  (safe(function initTools() {
    var page = document.getElementById('toolsPage');
    if (!page) return;

    function out(id, text, isErr) {
      var el = document.getElementById(id);
      if (!el) return;
      el.textContent = text;
      el.classList.toggle('tool-err', !!isErr);
    }
    function bind(id, fn) {
      var btn = document.getElementById(id);
      if (btn) btn.addEventListener('click', safe(fn, id));
    }

    // JSON format / minify / query
    function jsonVal() {
      try { return JSON.parse(document.getElementById('toolJsonIn').value); }
      catch (e) { out('toolJsonOut', 'JSON error: ' + e.message, true); return undefined; }
    }
    bind('toolJsonFmt', function () {
      var v = jsonVal(); if (v === undefined) return;
      out('toolJsonOut', JSON.stringify(v, null, 2));
    });
    bind('toolJsonMin', function () {
      var v = jsonVal(); if (v === undefined) return;
      out('toolJsonOut', JSON.stringify(v));
    });
    bind('toolJsonQuery', function () {
      var v = jsonVal(); if (v === undefined) return;
      var q = document.getElementById('toolJsonQ').value.trim();
      if (!q) { out('toolJsonOut', 'Enter a dot path, e.g. a.b[0].c', true); return; }
      var cur = v;
      var parts = q.replace(/\[(\d+)\]/g, '.$1').split('.').filter(Boolean);
      for (var i = 0; i < parts.length; i++) {
        if (cur == null || !(parts[i] in Object(cur))) {
          out('toolJsonOut', 'Missing key: ' + parts[i], true); return;
        }
        cur = cur[parts[i]];
      }
      out('toolJsonOut', JSON.stringify(cur, null, 2));
    });

    // Base64
    bind('toolB64Enc', function () {
      var v = document.getElementById('toolB64In').value;
      out('toolB64Out', btoa(unescape(encodeURIComponent(v))));
    });
    bind('toolB64Dec', function () {
      var v = document.getElementById('toolB64In').value;
      try { out('toolB64Out', decodeURIComponent(escape(atob(v.trim())))); }
      catch (e) { out('toolB64Out', 'Invalid base64', true); }
    });

    // URL codec
    bind('toolUrlEnc', function () {
      out('toolUrlOut', encodeURIComponent(document.getElementById('toolUrlIn').value));
    });
    bind('toolUrlDec', function () {
      var v = document.getElementById('toolUrlIn').value;
      try { out('toolUrlOut', decodeURIComponent(v.replace(/\+/g, ' '))); }
      catch (e) { out('toolUrlOut', 'Invalid encoding', true); }
    });

    // UUID
    bind('toolUuid', function () {
      var u = crypto.randomUUID ? crypto.randomUUID() :
        'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
          var r = Math.random() * 16 | 0;
          return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
      out('toolUuidOut', u);
    });

    // Timestamp
    function tsSync() {
      var now = Date.now();
      out('toolTsNow', String(now) + '  (' + new Date().toISOString() + ')');
    }
    bind('toolTsToDate', function () {
      var v = parseInt(document.getElementById('toolTsIn').value, 10);
      if (!v) { out('toolTsOut', 'Enter a unix timestamp (s or ms)', true); return; }
      if (v < 1e12) v *= 1000;
      out('toolTsOut', new Date(v).toISOString());
    });
    bind('toolTsNowBtn', tsSync);
    tsSync(); setInterval(tsSync, 30000);

    // SHA-256 (async)
    bind('toolSha', function () {
      var v = document.getElementById('toolShaIn').value;
      var data = new TextEncoder().encode(v);
      crypto.subtle.digest('SHA-256', data).then(function (h) {
        var hex = Array.from(new Uint8Array(h)).map(function (b) {
          return b.toString(16).padStart(2, '0');
        }).join('');
        out('toolShaOut', hex);
      }, function () { out('toolShaOut', 'Hash failed (insecure context?)', true); });
    });
  }, 'v2-tools'))();

  /* ── 5. Settings appearance wiring ────────────────────────────── */
  (safe(function initLooks() {
    function apply(key, value) {
      try { localStorage.setItem('orbit-v2-' + key, value); } catch (e) {}
      if (key === 'accent') document.documentElement.dataset.accent = value;
      if (key === 'density') document.documentElement.dataset.density = value;
      if (key === 'motion') document.documentElement.dataset.motion = value;
    }
    ['accent', 'density', 'motion'].forEach(function (key) {
      var saved;
      try { saved = localStorage.getItem('orbit-v2-' + key); } catch (e) {}
      if (saved) apply(key, saved);
      document.querySelectorAll('[data-v2-' + key + ']').forEach(function (btn) {
        if (btn.dataset.v2Applied) return;
        btn.dataset.v2Applied = '1';
        btn.addEventListener('click', function () { apply(key, btn.dataset['v2' + key[0].toUpperCase() + key.slice(1)] || btn.getAttribute('data-v2-' + key)); });
      });
    });
  }, 'v2-looks'))();
})();
