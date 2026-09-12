/* workspace.js — shared base for orbit:// workspace pages (God's Eye, F1).
 *
 * One owner for the machinery every workspace needs, so each workspace
 * module only implements its own data + drawing:
 *
 *   var ws = Workspace.create({
 *     name:      "God's Eye",            // for ask prompts / banners
 *     logId:     "geLog",                // optional signal log
 *     bannerId:  "f1Banner",             // optional honest-state banner
 *     liveId:    "geLive",               // optional telemetry chip (LIVE LED is CSS)
 *     askBtnId:  "geAsk", askInputId: "geQuestion",   // optional Ask-JARVIS pair
 *     buildAsk:  function () { return "context string"; },
 *     onTick:    function () {},         // called ~1/s while visible
 *   });
 *
 *   ws.fetchJSON(url, ms)   — fetch with timeout; throws Error("HTTP n")
 *   ws.setBanner(msg|""), ws.setLive(text), ws.log(msg, isErr)
 *   ws.start() / ws.stop()  — idempotent lifecycle (router calls these)
 *   ws.alive()
 */
(function () {
  'use strict';

  function create(opts) {
    var alive = false;
    var timer = null;
    var api = {};

    api.alive = function () { return alive; };

    api.setBanner = function (msg) {
      var b = opts.bannerId && document.getElementById(opts.bannerId);
      if (!b) return;
      b.textContent = msg || '';
      b.style.display = msg ? 'block' : 'none';
    };

    api.setLive = function (text) {
      var el = opts.liveId && document.getElementById(opts.liveId);
      if (el) el.textContent = text;
    };

    api.log = function (msg, isErr) {
      var log = opts.logId && document.getElementById(opts.logId);
      if (!log) return;
      var div = document.createElement('div');
      div.className = 'ge-log' + (isErr ? ' ge-log-err' : '');
      div.textContent = new Date().toLocaleTimeString() + '  ' + msg;
      log.insertBefore(div, log.firstChild);
      while (log.children.length > 60) log.removeChild(log.lastChild);
    };

    api.fetchJSON = function (url, timeoutMs) {
      return fetch(url, { signal: AbortSignal.timeout(timeoutMs || 8000) })
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        });
    };

    // Ask-JARVIS: buildAsk() supplies the workspace context; the reply
    // streams into the sidebar via the standard dshNative pipeline.
    function wireAsk() {
      var btn = opts.askBtnId && document.getElementById(opts.askBtnId);
      if (!btn || btn.dataset.wsWired) return;
      btn.dataset.wsWired = '1';
      btn.addEventListener('click', function () {
        if (!window.dshNative || !window.dshNative.status.connected) {
          api.setBanner('JARVIS is not connected.');
          return;
        }
        var input = opts.askInputId && document.getElementById(opts.askInputId);
        var q = (input && input.value.trim()) || '';
        api.setBanner('');
        window.dshNative.chat(opts.buildAsk() + (q || 'What stands out?'), {});
        api.log('JARVIS analyzing: ' + (q || 'current picture'));
      });
    }

    function loop() {
      if (!alive) return;
      try { opts.onTick(); } catch (e) { /* keep the loop alive */ }
      timer = setTimeout(loop, 1000);
    }

    api.start = function () {
      if (alive) return;
      alive = true;
      wireAsk();
      loop();
    };

    api.stop = function () {
      alive = false;
      if (timer) { clearTimeout(timer); timer = null; }
    };

    return api;
  }

  window.Workspace = { create: create };
})();
