# Orbit Native: Electron → Rust + WebView2 migration

Status: plan written after reading all 24,226 lines of `orbit-browser` JavaScript
and all 1,594 lines of `main.js`. Phase 0 is implemented; see "Status" at the end.

---

## 1. What the code actually is (not what the audit counted)

The audit described `orbit-browser` as a monolith. That is true of the *file
count* and false of the *behaviour*. Reading every file produced this:

| Cluster | Files | Lines | Reality |
|---|---|---|---|
| Tab management | `js/tabs.js` 1152, `tab-management.js` 553, `webview-pool.js` 300, `memory-optimizer.js` 618, `advanced-optimizations.js` 764, `vertical-tabs.js` 135, `tab-groups.js` 74 | **3,596** | One real implementation (`tabs.js`) + 6 competing ones. `webview-pool.js` acquires webviews with no global ceiling; `tab-management.js` persists its own state. |
| Performance | `performance.js` 291, `enhanced-performance.js` 448, `performance-monitor.js` 227, `lightweight.js` 580, (memory/advanced above) | **1,546** | `main.js` already says `runSleepCheck` is the single freeze authority. The rest compute state nobody reads. |
| Agents | `agent-loop.js` 390, `multi-agent-planner.js` 422, `needle-agent.js` 275, `js/needle-agent.js` 354, `vision-agent.js` 263 | **1,704** | Quarantined (A-04) since the kernel took over. `main.js` answers `agent:start` with `"disabled"`. `js/needle-agent.js` is a second copy of `needle-agent.js`. |
| Sidebar | `js/sidebar.js` 571, `js/v2-sidebar.js` 571 | **1,142** | Byte-for-byte-equivalent line counts. Two versions of one component. |
| Real behaviour | `main.js` + `preload.js` + `js/tabs.js` + `security.js` + `dsh-native.js` + `js/jarvis.js` | **~4,700** | This is the product. |

**Conclusion: this is not a 24k-line port.** It is ~4,700 lines of behaviour to
preserve and ~15,000 lines of duplication to delete. Any plan that says "rewrite
the browser in Rust" is quoting a number the code does not support, and any plan
that says "rewrite the browser in Rust is cheap because it's only 24k lines" is
quoting a number that hides the hard part: the WebView2 integration.

## 2. Honest WebView2 trade-offs

Adopting the WebView2 proposal. These are the costs, stated plainly, because
they change what the migration buys:

| Capability | Electron today | WebView2 | Note |
|---|---|---|---|
| Chromium version | 152 (pinned `44.5.1`) | **154.0.4258 installed** | Newer, and it updates with Edge. |
| Runtime you ship | Electron + Node (~200 MB) | **none** — uses the OS runtime | The genuine win. |
| Tab rendering | `<webview>` tag in the renderer | Native `ICoreWebView2Controller` per tab | Strictly better: real controllers, not DOM guests. |
| CDP | `webContents.debugger` | `CallDevToolsProtocolMethod` | Equivalent. |
| Downloads | `will-download` | `DownloadStarting` | Equivalent. |
| Permissions | `setPermissionRequestHandler` | `PermissionRequested` | Equivalent. |
| Profiles | one partition per window | `--profile-directory` under one UDF | **Better**: one browser process collection. |
| **Extensions** | `disable-extensions` is on anyway | **No Chrome extension support at all** | Orbit has an "Extension Store" UI that only opens web store pages — so this costs almost nothing *today*, but it forecloses real extensions. |
| **Ad/tracker blocking** | `webRequest.onBeforeRequest` | **No equivalent API.** Must use CDP `Fetch` domain, or lose it. | This is the single biggest functional regression risk. The Shields UI is a headline feature. |
| Per-site cookie pruning | `onHeadersReceived` delete | CDP `Fetch.fulfillRequest` header rewrite | Doable but async and slower. |
| Fingerprint farbling | `executeJavaScript` on dom-ready | Same | Unchanged. |
| Cross-platform | Works | **Windows/macOS only** | Acceptable: Orbit is Windows-first. |

The ad-blocking gap is real and must be solved in Phase 1, not discovered in
Phase 4. CDP `Fetch.enable` intercepts before the network and can both cancel
and rewrite headers, so the policy is expressible — it is an implementation
project, not a capability wall.

## 3. Target architecture

```
                    JARVIS Core  (Python, unchanged, owns decisions)
                            │  authenticated local RPC
                            ▼
┌──────────────────────── orbit-host (Rust) ───────────────────────┐
│  window.rs      native window, tab strip host, frameless chrome    │
│  tabs.rs        TabManager over BrowserController                  │
│  profiles.rs    profile → user-data folder + --profile-directory   │
│  permissions.rs default-deny allowlist (pure, tested)              │
│  network.rs     https upgrade, private-net block, tracker list     │
│  downloads.rs   DownloadStarting state machine                     │
│  jarvis.rs      RPC client + reconnect/backoff                     │
│  cdp.rs         raw DevTools pipe for Fetch/WebSocket lifecycle    │
└───────────────────────────────┬──────────────────────────────────┘
                                │ implements
                    ┌───────────▼────────────┐
                    │  BrowserController     │  ← the seam that makes
                    │  (orbit-core, traits)  │    CEF swappable later
                    └───────────┬────────────┘
                                │ WebView2Backend
                    ┌───────────▼────────────┐
                    │  ICoreWebView2Controller│
                    └───────────┬────────────┘
                                │
                          Chromium 154
```

`orbit-core` holds **every decision** and zero platform code. That is what makes
it testable here: `cargo test` runs headless, so the policy layer can be
verified exhaustively without ever opening a window. `orbit-host` holds only
mechanism.

## 4. Line-by-line disposition

**Port to Rust (`orbit-core`, pure + tested):**
- `main.js` → `url.rs` (isPrivateNetworkHost, isPrivateOrLocalHost, https
  upgrade), `permissions.rs` (PERMISSION_ALLOWLIST + default-deny),
  `lifecycle.rs` (freezeTab/wakeTab/runSleepCheck/measureAllTabMemory policy,
  *not* the CDP calls), `tabs.rs` (TabManager state), `session.rs`
  (sessionSnapshot), `error_log.rs` (logMainError ring buffer).
- `main.js` private PIN (PBKDF2 100k, salt) → `pin.rs` with real timing-safe
  comparison. The JS uses `===` on hex digests, which is a timing side channel.
- `security.js` tracker/ad list + `shouldBlock` → `network.rs`.

**Port to Rust (`orbit-host`, mechanism):**
- createWindow, frameless chrome, downloads, JARVIS WebSocket + backoff,
  offline queue, tab sleeping via CDP `Page.setWebLifecycleState`.

**Port to React/TS:**
- `js/tabs.js`, `js/renderer.js`, `js/core.js`, `js/sidebar.js` (keep ONE,
  delete `v2-sidebar.js`), `js/pages.js`, `js/menus.js`, `js/nav-tools.js`,
  `command-palette.js`, `jarvis-command-bar.js`, `spaces-ui.js`,
  `theme-system.js`, `accessibility.js`, `js/model-button.js`, `js/voice.js`.

**Delete outright — duplicated or dead, no port:**
`webview-pool.js`, `tab-management.js`, `vertical-tabs.js`, `tab-groups.js`,
`memory-optimizer.js`, `advanced-optimizations.js`, `enhanced-performance.js`,
`performance-monitor.js`, `lightweight.js`, `agent-loop.js`,
`multi-agent-planner.js`, `needle-agent.js` (both copies), `vision-agent.js`,
`page-cache.js`, `session-manager.js`, `jarvis-integration.js`,
`js/v2-sidebar.js`, `js/v2.js`, `js/v2-watch.js`, `session-manager.js`.
**~11,000 lines.**

**Keep in JARVIS Core (not the shell at all):**
`security-tester.js` 1106 — this is a security test suite against page
content; it belongs with the kernel's verification engine, not the browser.
`f1.js`, `goodeye.js`, `worldmon.js`, `yt.js`, `worldmap.js` — data panels.

**Undecided / needs a call:** `chrome-import.js` 322. WebView2 cannot be
pointed at an arbitrary Chrome user-data folder, so profile import becomes
*bookmark/history import* only. The bookmarks/history path already exists in
`main.js` and is portable.

## 5. Phasing, with a verification gate per phase

| Phase | Deliverable | Gate |
|---|---|---|
| 0 | `orbit-core`: tab lifecycle, URL policy, permissions, PIN, session | `cargo test` — pure, headless, exhaustive |
| 1 | `orbit-host`: WebView2 env + window + one controller + navigation + CDP `Fetch` blocking | `cargo run --bin orbit-smoke` opens a real window, navigates, exits 0/1 |
| 2 | TabManager over multiple controllers, profiles, suspend/restore | smoke asserts N controllers, restore after suspend |
| 3 | JARVIS RPC client + permission prompts | smoke asserts the RPC handshake and refusal path |
| 4 | React/TS UI on the Rust API | `npm test` + the existing smoke suite |

Each phase ships behind a flag; the Electron build stays runnable until Phase 4
is verified, so there is always a working browser.

## 6. Status

Phase 0 is implemented and tested in `orbit-native/`. See
`orbit-native/README.md` for what passes and what is not built yet.

**Not yet verified:** Phase 1+ does not exist. No WebView2 window has been
opened from this code yet. `cargo test` proves policy, not rendering.