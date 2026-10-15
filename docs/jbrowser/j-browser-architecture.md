# J-Browser — Chrome-based JARVIS browser (Phase 1-2)

J-Browser is **real Google Chrome** (not a fork, not Electron/WebView2): a normal
browser with all its functionality and all your extensions, plus **JARVIS as a
first-class AI layer** that replaces the Gemini slot, and a Strawberry-style
autonomous agent layer that can **take full control of the browser**.

Decisions that shaped the design (from the product brief):

> "Great browser first, AI browser second." Chromium owns browsing; JARVIS owns
> intelligence. Extension compatibility is P0. J-Browser automation is one
> component under the browser, not the browser itself.

## Target architecture

```
         J-BROWSER  (regular Google Chrome)
                 │
   ┌─────────────┴─────────────┐
   │                           │
Chromium UI            JARVIS MV3 Extension
 (tabs/ext/etc)               │
                 ┌────────────┴────────────┐
                 │                         │
           side_panel sidebar        chrome://newtab override
                 │      (page-aware chat)  │
                 └────────────┬────────────┘
                              │  HTTP/SSE (127.0.0.1:8170)
                       JARVIS Bridge (jbrowser-bridge/)
                              │
                       JARVIS Kernel
                              │
                 ┌────────────┴────────────┐
                 │                         │
          Agent runtime            jbrowser engine
                                          │  (Playwright + CDP)
                                    browser control
```

Three layers, all present by design:

1. **MV3 extension** — the user-facing JARVIS layer (sidebar · new-tab home ·
   page-aware chat · context menus). This is what "replace Gemini with JARVIS"
   means. It is 100% compatible with every existing Chrome extension because it
   *is* an ordinary Chrome extension.
2. **`chrome.debugger`/CDP** — the privileged, consent-gated mechanism for real
   browser control and Strawberry-style autonomous agents (drive tabs, run JS,
   click/type, observe events).
3. **Existing `jbrowser/` Python engine** — the agent/browser-control engine
   under the kernel (`Playwright + CDP → Chromium`). It is re-used, not
   re-authored: `jbrowser/` is the engine beneath the browser, not the browser.

## What this repo contains (Phase 1-2, built & verified)

### `extensions/jbrowser/` — the MV3 extension
- `manifest.json` — side_panel (sidebar), `chrome_url_overrides.newtab`, content
  scripts on `<all_urls>`, `debugger`/`tabs`/`bookmarks`/`history`/`scripting`
  permissions, commands (`Ctrl+Shift+J` toggle, `Ctrl+Shift+Space` ask-about-page).
- `src/background/service-worker.js` — routing hub, session/conversation
  persistence (`chrome.storage.local`), owns a `BridgeClient`, context menus,
  commands, status loop. Gated controller enable persists here.
- `src/bridge/bridge-client.js` — HTTP status + SSE chat client against the
  bridge. Correctly terminates on the `done`/`error` event (not only at EOF).
- `src/content/context.js` — page-context capture (title/url/visible text/
  selection/language) injected on all pages; `selectionchange` → selection events.
- `src/controller/controller.js` — `chrome.debugger` (CDP) controller with an
  **explicit fail-closed security boundary** (see below). Disabled until the user
  opts in; attach requires consent; privileged methods require per-command consent.
- `src/lib/` — `constants.js` (message/storage/bridge contract), `messaging.js`.
- `src/sidebar/` — page-aware JARVIS chat overlay (JARVIS replaces the Gemini slot).
- `src/newtab/` — JARVIS home page override (greeting, omnibox, agent actions).

### `jbrowser-bridge/` — local intelligence bridge (stdlib only)
- `server.py` — `ThreadingHTTPServer` bound to `127.0.0.1:8170`:
  - `GET /status` → `{ok, kernel: online|offline, backend, ...}`
  - `POST /v1/chat` → SSE stream of `start`/`delta`/`done`/`error`
  - `POST /v1/agent` → Phase-3 seam (agent launch), returns `501`
  - `POST /v1/cdp` → Phase-2 seam (CDP delegation to the engine), returns `501`
  - SSE connections close after the terminal event.
- `backend.py` — pluggable `Backend` ABC. `EchoBackend` (default) is a
  deterministic, context-aware stub so the AI layer works end-to-end as a UX
  without a kernel. `KernelBackend` is the seam for driving the real JARVIS
  agent stack.

### `tests/test_jbrowser_bridge.py`
Hermetic (no browser/Playwright) HTTP/SSE tests for the bridge: status, stream
termination, page-context propagation, 400 on bad JSON, 501 on agent/cdp seams.
**7 passed.**

## Verified: `chrome.debugger` is viable under MV3 (2026)

Research confirmed the full-control mechanism the plan was cautious about:

- `chrome.debugger` works in Manifest V3 with the `"debugger"` permission.
  Attach by `tabId`/`targetId`/`extensionId`, `sendCommand(method, params)`,
  `getTargets()`, `onEvent` routed by `tabId`, `onDetach`. Promises are
  supported from MV3 onward.
- **Flat sessions (Chrome 125+)** let you add out-of-process child frames /
  workers as children of one session — important for real page automation.
- Providers we target: `Runtime.evaluate`, `Page.navigate`, `Page.reload`,
  `Input.dispatch*`, `DOM.*`, plus event observation. These cover "inspect tab,
  navigate, interact, inspect DOM/a11y, execute actions, manage tabs/windows,
  observe events, coordinate agents."
- Caveats to design around: opening user DevTools for a tab the extension is
  attached to terminates the debug session (`onDetach`); enterprise
  `ExtensionSettings` policy can block `attach()`.

## Security boundary (fail-closed)

`chrome.debugger` is privileged browser control, so control is DISABLED until
explicitly enabled, and every privileged action needs approval:

1. **Extension default is off.** The `debugger` permission is declared in the
   manifest, but `controller.js` refuses `attach` until
   `settings.controllerEnabled === true` (set via the sidebar ⚙ toggle).
2. **Attach requires operator consent.** `attach(tabId, {consent})` is rejected
   unless the caller first obtained user consent.
3. **Privileged commands need per-instance consent.** `Runtime.evaluate`,
   `Page.navigate`, `Input.*`, `DOM.*`, etc. are classified `PRIVILEGED`; an
   agent-originated privileged command is rejected with `needsConsent` unless
   explicitly approved for that command. Safe/introspection commands are allowed
   once attached.
4. **No persistence of powers.** Attach is per-session; the controller is
   re-gated on reload. `onDetach` cleans up.
5. **Bridge is loopback-only** (`127.0.0.1`) and local.

## Load it

1. Start the bridge (in `jbrowser-bridge/`):
   `..\venv\Scripts\python.exe server.py --backend echo`  (or `--backend kernel`)
2. `chrome://extensions` → enable **Developer mode** → **Load unpacked** →
   select `C:\Users\aayan\Desktop\JARVIS\extensions\jbrowser\`.
3. Pin the JARVIS action; click it (or `Ctrl+Shift+J`) to open the sidebar.
   `Ctrl+Shift+Space` asks about the current page/selection.
4. New tabs open the JARVIS home.

With `--backend echo` the sidebar shows `JARVIS offline` and returns the
context-aware stub reply — a real end-to-end demo. Switching to a real kernel
engine is the next step.

## Next steps (roadmap)

- **Phase 3 — kernel + agent runtime:** wire `KernelBackend.stream_chat` into
  the JARVIS agent loop / streaming `ModelGateway` (extensions/jbrowser →
  bridge → kernel → `jbrowser/` engine). Configure the agent key; turn the
  `/v1/agent` seam into a real autonomous agent session whose privileged CDP
  actions surface the extension's consent UI.
- **Phase 2 — CDP control spike:** exercise `controller.js` against a controlled
  tab: attach (with consent), `Runtime.evaluate`, `Page.navigate`, click/type,
  observe `Page.*` events. Close the loop so an agent can drive the browser.
- **Phase 4+ — memory / advanced AI:** surface JARVIS memory + long-term
  context in the sidebar; page-summary pipeline feeding the kernel.
- Hardening: rate-limit the bridge, token‑budget gating, per‑origin
  page-context stripping, extension Web Store packaging pass.

## Conventions

- No comments unless asked; Python follows repo ruff rules (py311 typing).
- Extension content scripts are classic scripts; extension pages (sidebar/newtab)
  and the service worker are ES modules.
- Bridge stays stdlib-only (no new Python deps).
- The existing `jbrowser/` Playwright engine is unchanged; Phase 2/3 reuse it.
