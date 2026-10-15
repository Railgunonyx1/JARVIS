# J-Browser Foundation Decision — "a new custom browser based on Chrome + Strawberry, with JARVIS replacing Gemini"

**Status:** decision research only — no `jbrowser/` implementation was changed.
**Question we must answer first:** what does "build a new browser" mean, because it changes the project by an order of magnitude.

The requirement, unpacked:
- A **new, separate** browser (not "JARVIS added to the Chrome you already run").
- Feels/behaves like **Chrome + Strawberry** (real tabs, omnibox, bookmarks, history, profiles + an agentic layer).
- **JARVIS is the AI, built in**, replacing Gemini's slot (Chrome's inline Gemini-style assistant).
- **JARVIS has full control** of the browser (drive tabs/windows/pages, run Strawberry-style autonomous agents).
- A **fully functional browser**: all extensions, history, bookmarks, passwords, settings — **importable from Google Chrome**.

---

## 0. The non-negotiable facts that bound this decision

1. **`--load-extension` is gone.** Branded Chrome ≥137 removed the flag (the installed Chrome is 152). A separate browser product therefore cannot be "your existing Chrome + a flag." Something has to be its own build or its own profile.

2. **Electron is disqualified for "all my extensions."** The Electron project states full Chrome-extension compatibility is a *non-goal*: only a subset of APIs is supported (DevTools-first), `chrome.debugger` is **not** supported, `chrome.storage.sync`/`managed` are not, packed `.crx` don't load, and "tabs/popups/actions" aren't known to Electron (they come from third-party bridges like `electron-chrome-extensions`, which still miss `chrome.debugger`). So Electron cannot guarantee your extensions behave the way they do in Chrome.

3. **"Fork Chrome" = fork Chromium, and that is a heavy lift.** Any Chromium-based browser (Brave, and Chromium itself) is a massive C++ codebase. Building it requires tens of GB of toolchain, a many-hour build per machine, and **continuous upstream legacy** (Brave tracks Chromium weekly; the Chromium project mints ~40k commits between releases). This is the single biggest cost and the single biggest long-term risk for a solo project.

4. **Chrome ≈ Mutation of Chromium + Google services.** "Chrome-like" is fully achievable on any Chromium engine. "Identical to Chrome" (sync, DRM/Widevine, Google account, auto-updates, Web Store) is not — and Widevine/DRM is the one thing a stock Chromium/Electron cannot legally include (requires licensing).

5. **CDP full-control is viable** (confirmed via research): `chrome.debugger` works under MV3; plus the existing `jbrowser/` engine already drives Chromium via Playwright+CDP. "JARVIS has full control + Strawberry agents" is therefore an **engine/IPC** problem, not a browser-fork problem.

6. **Chrome data import is feasible, with caveats** (confirmed):
   - Bookmarks + history: writable directly into a target Chromium profile (matches Chrome's checksum manifests); or via the universal `bookmarks.html` import path.
   - Passwords: encrypted and machine-bound — cannot be copied as data. Realistic routes: Chrome's own export-CSV/import, or **Chrome Sync** (sign in → pull into the new profile).
   - Extensions: cannot be silent-installed. Route: reinstall from the store in the new browser (Chromium shares the Chrome store ecosystem; a same-engine reinstall is one click).

7. **Strawberry-style agents** = an autonomous agent runtime driving the browser via CDP, not a browser-subsystem. It should live **outside the engine**, talking to the browser through a control/IPC layer.

---

## 1. Candidates

| Letter | Approach | Chrome-like? | All extensions? | Full JARVIS control + agents? | Import from Chrome? | Build cost | Maintenance cost | Feasible on this machine? |
|--------|----------|--------------|-----------------|-------------------------------|---------------------|-----------|------------------|--------------------------|
| **D** | JARVIS extension layer **inside your existing Chrome** (already built: sidebar · new-tab · `chrome.debugger` full control · bridge) | Yes (it IS Chrome) | Yes (native) | Yes | N/A (already there) | Low | Low | **Yes** |
| **E (recommended)** | **A dedicated Chromium browser build** (e.g. Brave or Chromium) **launched by a JARVIS product launcher** with **its own profile + the JARVIS extension layer + CDP controller + an Import-from-Chrome wizard** — i.e. a *separate, purpose-built browser distro* | Yes (Chromium engine) | Yes (same engine + store) | Yes (via `jbrowser/` + CDP) | Yes (profile import wizard) | **Low–Medium** | Low | **Yes** |
| **C** | Fork **Brave** (open-source Chromium browser) and replace Gemini/Brave AI with JARVIS | Yes | Yes | Yes | Yes | **Very high** (Chromium build) | **Very high** (track upstream) | Marginal–No |
| **B** | Fork **Chromium** upstream directly and build JARVIS-in-chrome | Yes | Yes | Yes | Yes | **Extreme** | **Extreme** | No |
| **A** | Electron custom shell + extension bridge | Approx. (not drop-in) | **No** (partial API) | Partial (`chrome.debugger` absent) | Partial | Medium | Medium | Yes but disqualified by §0.2 |

Reading the table: **A is disqualified** (§0.2). **B and C are architecturally the "most correct," but their build + upstream-maintenance cost is prohibitive for a solo Windows project** and likely not even runnable on a typical dev machine. That isolates the real decision.

---

## 2. The honest decision

The only approaches that actually ship a Chrome-quality, extensions-intact, JARVIS-controlled browser in this project are:

- **D — inside your existing Chrome** (lowest effort, but it is not a *separate* browser), or
- **E — a separate Chromium browser *distro* that we assemble** (same engine Chromium/Brave, own profile, bundled JARVIS layer + controller + import wizard).

**Recommendation: E, built incrementally, reusing D's already-built layer as the JARVIS-in-browser component.**

Why E over a source fork (B/C) is the correct engineering call:

1. **It is genuinely a new, separate browser** — it launches its own Chromium executable into its own "User Data" profile with its own branding, tabs, omnibox, bookmarks, history, settings — not your daily Chrome. That satisfies "new custom browser."
2. **Full Chrome-extension compatibility for free** — we inherit the actual Chromium extension system and store ecosystem; no Electron API gaps, no `chrome.debugger` missing.
3. **Maintenance is an order of magnitude lower** — we don't compile Chromium and we don't carry a fork merge burden. The engine upgrades by swapping in the newer binary or by `git pull` on the unmodified upstream we launch. All our product work lives in **our** layer (extension + bridge + controller + import wizard + agent engine), which is small and testable.
4. **JARVIS stays separate from the engine** — exactly the separation the brief demands:
   ```
   JARVIS layer (extension + bridge + agent runtime)  ⇄  CDP/IPC  ⇄  Chromium (tabs/windows/profiles/extensions)
   ```
5. **Full control + concurrent agents** slot cleanly onto the already-proven `jbrowser/` engine over CDP.
6. **Chrome import** is a first-class wizard: read the installed Chrome profile (bookmarks, history), present a picker, write into the new profile (Chromium checksum-correct bookmarks file + history), guide passwords via Chrome CSV/import and extensions via one-click store reinstall.

**What we give up vs a source fork:** we can't paint custom tabs/omnibox *inside* the Chromium frame by shipping our own C++ chrome; we customize the browser chrome via the extension layer + a themed new-tab/sidebar, and via browser chrome style flags. Visually it is "Chrome with our JARVIS UI and skin," which is precisely the "JARVIS replacing Gemini in a Chrome browser" feel — without running a Chromium build farm.

**If the user needs a true forked binary one day** (e.g. to rebrand the actual window frame), that is a *later, separate* decision (option C on Brave) and should be triggered only after E proves the product and usage warrants the enormous engineering commitment.

---

## 3. Decision matrix (your 16 questions, distilled)

| # | Concern | E (recommended) position |
|---|---------|--------------------------|
| 1 | **Electron vs Chromium fork vs established fork** | Neither Electron nor a source fork: assemble a **distro** of a real Chromium browser (Brave/Chromium) + our JARVIS layer + CDP. |
| 2 | **Actual Chrome-extension compatibility** | Native — we inherit Chromium's real extension system + store. (This is the main reason to reject Electron.) |
| 3 | **CDP & browser-control** | Reuse proven `jbrowser/` (Playwright+CDP) + `chrome.debugger`; covers tabs/windows/nav/DOM/a11y/forms/downloads/history/settings/events/screenshots. |
| 4 | **Multi-agent architecture** | Agent Manager spawns concurrent JARVIS agents; each drives its own tab(s) via CDP with permission gating. Lives in JARVIS layer, not the engine. |
| 5 | **JARVIS ↔ browser IPC** | Existing loopback bridge (`HTTP/SSE on 127.0.0.1`) + the MV3 worker↔bridge↔kernel path; extend for agent/CDP commands. |
| 6 | **Profile/session architecture** | One Chromium "User Data" per user profile; persistent sessions; import wizard populates from Chrome. |
| 7 | **Security/permission model** | Reuse the fail-closed model: control off until opted-in; attach + privileged CDP commands require per-action consent; loopback-only IPC. |
| 8 | **Update strategy** | Ship Chromium engine as a pinned, trendable artifact; product layer updates independently. No fork-merge treadmill. |
| 9 | **Chromium upgrade burden** | Low (swap engine artifact / pull unmodified upstream). Contrast: Brave/Chromium forks rebase weekly → high. |
| 10 | **RAM/CPU/startup** | Roughly Chrome's profile + a lightweight bridge. No off-memory C++ we own. |
| 11 | **Windows packaging** | Package = Chromium portable binary + our layer + launcher + optional NSIS installer. No custom C++ build. |
| 12 | **Chrome data import** | Wizard: bookmarks+history written into profile; passwords via Chrome CSV/import or Chrome Sync; extensions via store reinstall. |
| 13 | **Existing `jbrowser/` reuse** | Direct — it is exactly the browser-control/agent engine E needs; no rewrite. |
| 14 | **Dev complexity** | Product code is JS + Python (extension, bridge, agent runtime, import wizard) — the stack already in this repo. |
| 15 | **Long-term maintainability** | Highest of the viable options: engine is someone else's maintained binary; we maintain a small, testable layer. |
| 16 | **What "full browser control" can mean** | Reason over/control tabs, windows, navigation, page DOM/a11y, forms, downloads, history, bookmarks, permitted settings, extension interactions, concurrent agents, CDP events. All via CDP — no fork needed. |

---

## 4. What this means for the roadmap

**Phase 1 (this) — Decision + spike (no engine rewrite).**
- [x] Architecture decision document.
- [ ] Choose the Chromium runtime (Brave portable vs Ungoogled Chromium vs Chromium) and confirm it launches with its own profile + our extension + CDP.
- [ ] Confirm the already-built MV3 layer (sidebar/new-tab/`chrome.debugger`) works on that runtime with its own profile.

**Phase 2 — Product layer.** Launcher/branding, themed UI + new-tab/sidebar (JARVIS replaces Gemini), bundled bridge backend.

**Phase 3 — Kernel + agents.** Wire `KernelBackend` → JARVIS agent loop / streaming `ModelGateway`; Agent Manager for concurrent Strawberry-style agents; agent CDP actions surface the consent UI.

**Phase 4 — Import from Chrome.** Profile wizard: bookmarks + history (direct write), passwords (Chrome CSV/import or sync), extensions (store reinstall), settings.

**Phase 5+ — Memory / advanced AI.**

A source fork (C) is explicitly decoupled as an optional "later, only if the product earns it" decision.

---

## 5. Tag
`docs/jbrowser/j-browser-foundation-decision.md` — the J-Browser foundation decision. Phase-1 status: decision doc only; `jbrowser/` implementation untouched. Next gate: confirm the selected Chromium runtime in a spike before building the product layer.
