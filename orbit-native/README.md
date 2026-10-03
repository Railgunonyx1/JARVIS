# orbit-native

The Rust foundation for Orbit's move off Electron. Design and full inventory:
[`docs/ORBIT-NATIVE-MIGRATION.md`](../docs/ORBIT-NATIVE-MIGRATION.md).

## What this is

`orbit-core` holds every browser **decision** and no platform code: URL
governance, the site-permission allowlist, the tab lifecycle state machine, the
private-window PIN, the session snapshot format, and the `BrowserController`
trait seam.

The reason to put policy in a pure crate is testability. The Electron build's
`main.js` cannot be tested without launching a browser, so its SSRF filter,
permission defaults and tab sweep were never exercised. Here they run headless:

```
cargo test -p orbit-core
```

49 tests, ~12s, no browser, no display, no network.

## What this is NOT

**The WebView2 host is not implemented.** `crates/orbit-host` does not exist.
The design, the exact COM/API pitfalls, and the phase plan are in the migration
doc; the code is not written. Do not read this crate as a working browser — it is
the policy layer a browser will sit on.

`orbit-browser/` (Electron 44) remains the working browser until the host lands.

## Layout

```
crates/orbit-core/src/
  url.rs          URL parsing, SSRF guard, HTTPS upgrade, scheme allow-list
  permissions.rs  default-deny per-origin allowlist
  tabs.rs         TabRegistry + the Active/Warm/Throttled/Suspended/Restorable state machine
  pin.rs          PBKDF2-HMAC-SHA256 private-window PIN, constant-time compare
  error_log.rs    bounded ring buffer with retry-safe dirty tracking
  controller.rs   the BrowserController seam + EngineCapabilities + FakeController
```

## Notable behaviour changes from the Electron build

These are deliberate, and each has a test:

- `file://`, `javascript:`, `data:` and `vbscript:` are refused by the parser,
  not merely "not navigated to".
- URLs with embedded credentials (`https://trusted.com@evil.example`) are
  refused. `new URL()` accepts them.
- A malformed URL is blocked as malformed rather than treated as "no problem",
  which is how SSRF filters get bypassed.
- The PIN comparison is constant-time. The JS used `===` on hex digests.
- `grant` entries with no permissions left are removed instead of lingering.
- The resident-tab ceiling is actually enforced. `webview-pool.js` claimed
  `maxPoolSize` and never applied it.
- Tab ids are never reused, so a late event for a closed tab cannot land on a
  new one.