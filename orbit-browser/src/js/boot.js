/* Extracted from index.html inline script (CSP: no unsafe-inline).
 * MUST run before any other script. */
  /* Error-containment bootstrap — must run before ANY other script.
   * safe(): never lets a handler exception break the calling flow.
   * on():  addEventListener with containment; invoke-time lookup so
   *        load order never matters (chat.js binds before core.js).
   * safeIpc(): contains ipcRenderer.invoke rejections for the renderer. */
  (function () {
    'use strict';
    var _lastToast = {};   // message -> timestamp, rate-limits toast spam
    function _report(err, source) {
      try {
        if (window._errorLogger) window._errorLogger.error(err, source);
        var msg = (err && err.message) || String(err);
        var now = Date.now();
        if (window.showToast && now - (_lastToast[msg] || 0) > 5000) {
          _lastToast[msg] = now;
          window.showToast('err', 'UI error', msg);
        }
      } catch (_) {}
    }
    function safe(fn, label) {
      if (typeof fn !== 'function') return fn;
      return function () {
        try { return fn.apply(this, arguments); }
        catch (err) {
          try { console.error('[ORBIT:safe]', label || fn.name || 'anonymous', err); } catch (_) {}
          _report(err, 'safe:' + (label || fn.name || 'anon'));
        }
      };
    }
    window.safe = safe;
    window.on = function (target, evt, handler, opts) {
      if (!target || typeof target.addEventListener !== 'function') {
        try { console.warn('[ORBIT:on] null target for', evt); } catch (_) {}
        return;
      }
      target.addEventListener(evt, safe(handler, evt), opts);
    };
    window.safeIpc = function (promise, label) {
      return Promise.resolve(promise).catch(function (err) {
        try { console.error('[ORBIT:ipc]', label || 'invoke', err); } catch (_) {}
        _report(err, 'ipc:' + (label || ''));
        return null;
      });
    };

    /* Prototype-level containment: every addEventListener anywhere (core
     * files, optional modules, webviews, future code) gets a safe() handler
     * automatically. Removal stays symmetric via the _orbitWrapped link. */
    try {
      var _ael = EventTarget.prototype.addEventListener;
      var _rel = EventTarget.prototype.removeEventListener;
      EventTarget.prototype.addEventListener = function (type, fn, opts) {
        if (typeof fn === 'function' && !fn._orbitWrapped) {
          var w = safe(fn, type);
          w._orbitOrig = fn;
          fn._orbitWrapped = w;
          return _ael.call(this, type, w, opts);
        }
        return _ael.call(this, type, fn, opts);
      };
      EventTarget.prototype.removeEventListener = function (type, fn, opts) {
        return _rel.call(this, type, (fn && fn._orbitWrapped) || fn, opts);
      };
    } catch (e) { try { console.error('[ORBIT] listener patch failed', e); } catch (_) {} }
  })();
