/* Extracted from index.html inline script (CSP: no unsafe-inline).
 * Deferred module loader with error isolation. */
    // Load optional modules with error isolation — one failing module
    // must never prevent the core renderer from working.
    (function() {
      // Critical: load immediately | Deferred: load during idle time.
      // Only modules with live consumers are loaded. enhanced-security.js
      // and enhanced-performance.js define globals nothing references, so
      // they are excluded (kept on disk, never executed).
      const critical = ['dsh-native.js'];
      const deferred = [
        'tab-management.js', 'jarvis-integration.js',
        'security-tester.js', 'tiling-ui.js',
      ];
      function loadMod(m) {
        const s = document.createElement('script');
        s.src = m;
        s.onerror = function() { console.warn('[ORBIT] Module failed:', m); };
        document.body.appendChild(s);
      }
      critical.forEach(loadMod);
      // Self-heal: dsh-native is the bridge client — if its global never
      // materialized (rare boot flake), every bridge feature silently
      // degrades to fallbacks. Re-inject once after the boot settles.
      setTimeout(function() {
        if (!window.dshNative) {
          console.warn('[ORBIT] dsh-native missing after boot — re-injecting');
          loadMod('dsh-native.js');
        }
      }, 4000);
      function loadBatch() {
        if (!deferred.length) return;
        const batch = deferred.splice(0, 3);
        batch.forEach(loadMod);
        if (deferred.length) {
          const fn = function() { setTimeout(loadBatch, 80); };
          window.requestIdleCallback ? requestIdleCallback(fn, {timeout:2000}) : fn();
        }
      }
      window.requestIdleCallback ? requestIdleCallback(loadBatch, {timeout:1000}) : setTimeout(loadBatch, 50);
    })();
