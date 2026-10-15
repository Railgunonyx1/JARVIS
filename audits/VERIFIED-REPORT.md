# VERIFIED REPORT — Orbit Workspace Overhaul Code Review

**Date:** 2026-09-12
**Scope:** `orbit-browser` — workspace architecture overhaul
(`workspace.js`, `goodeye.js`, `f1.js`, `yt.js`, `chat.js`, `renderer.js`,
`main.js`, `f1-nothing.css`, `index.html`)
**Method:** Static review per the code-review skill template + live behavioral
probes against the running Electron app (CDP-driven, real DOM and fetch
instrumentation). Every fix below was re-run against the real surface after
the change.

---

## Review Summary Table

| # | File | Line | Severity | Category | Issue Title |
|---|------|------|----------|----------|-------------|
| 1 | `goodeye.js` / `f1.js` | stop() | 🔴 Critical | Lifecycle | `start()` permanently dead after first `stop()` — workspaces never recover |
| 2 | worktree root | — | 🟠 High | Hygiene | 3 throwaway probe scripts (`behav*.tmp.js`) left in the repo |
| 3 | `main.js` | 1131 | 🟡 Medium | Security/CSP | Merged CSP still allowed external font CDNs no longer used |
| 4 | `workspace.js` | 26 | 🔵 Low | Dead code | `opts.name` accepted but never used |

---

## Detailed Issue Report

### Issue #1 — Workspaces die permanently after first navigation away

| Field | Details |
|-------|---------|
| **File** | `src/js/goodeye.js`, `src/js/f1.js` |
| **Severity** | 🔴 Critical |
| **Category** | State-lifecycle bug (introduced by the overhaul) |

**Problematic code**

```js
function start() {
  if (!canvas || ws) return;   // ws still set after stop()
}
function stop() { if (ws) ws.stop(); }   // ws never cleared
```

**Impact (proven live)** — `stop()` halted polling but left `ws` set, so the
internal-page router's next `start()` early-returned. Result: **zero data
fetches on any revisit** — the workspace showed stale data forever with no
error. An earlier "restarted: true" probe result was a false positive (stale
state object), which is how this survived the overhaul validation pass.

**Fix applied**

```js
function stop() {
  if (ws) { ws.stop(); ws = null; }  // null so the next start() re-arms
}
```

**Re-verification (live, after fix)** — reload, then two full visit cycles
(goodeye → newtab → goodeye → newtab → goodeye): God's Eye polls at full
cadence again (4 fetches in 7s, ISS fix present), F1 re-arms with its session
and 22 cars. **Status: fixed and verified.**

---

### Issue #2 — Probe scripts left in worktree

| Field | Details |
|-------|---------|
| **File** | `behav1.tmp.js`, `behav2.tmp.js`, `behav3.tmp.js` |
| **Severity** | 🟠 High |
| **Category** | Hygiene ("delete unused code") |

**Fix applied** — deleted. Worktree now contains only product changes.
**Status: fixed.**

---

### Issue #3 — CSP allowed external font CDNs that are not used

| Field | Details |
|-------|---------|
| **File** | `main.js` (merged CSP handler) |
| **Severity** | 🟡 Medium |
| **Category** | Security / no-external-CDN rule |

**Problematic** — `style-src … https://fonts.googleapis.com` and
`font-src … https://fonts.gstatic.com` were carried over from the pre-merge
handlers, but grep confirmed no external font usage anywhere
(`src/index.html`, `src/css/*.css`): all fonts are local `@font-face`.

**Fix applied** — tightened to `style-src 'self' 'unsafe-inline'` and
`font-src 'self'`.

**Re-verification (live, after fix)** — `document.fonts.check`: Doto ✓,
Geist Mono ✓ (local fonts load); skin stylesheet applied; no console errors.
**Status: fixed and verified.**

---

### Issue #4 — Unused `opts.name` parameter

| Field | Details |
|-------|---------|
| **File** | `workspace.js` line 26 |
| **Severity** | 🔵 Low |
| **Category** | Dead scaffolding |

Accepted by both call sites, never read. Left in place (documentation value);
trivial to drop later. **Status: noted, not fixed.**

---

## Edge cases additionally probed (passed)

- **`Chat.appendNode` during an active stream** — safely no-ops (no throw),
  cards defer; text fallback persisted.
- **Text fallback in history** — confirmed in `orbit-chat-history`
  (`"…private results…"`) so panel re-renders restore a readable form.
- **Fetch-counted lifecycle** — 0 workspace fetches after `stop()` in a 7s
  window (the 2 observed `:8170/status` calls were dshNative's heartbeat,
  unrelated to workspaces).
- **Retry storms** — under sustained simulated 429s, poll cadence stays
  backoff-driven (TICKS advance on success *and* failure); honest banner
  shown ("OpenF1 rate-limited — retrying in Ns").
- **XSS posture** — result cards, leaderboard rows, and logs build DOM via
  `textContent`; no untrusted `innerHTML`.
- **Console error sweep** — 0 errors across all flows.

---

## Grading Summary

| File | Complexity | Rank | Commit Allowed |
|------|-----------|------|----------------|
| workspace.js | 6 | B | ✅ Yes |
| goodeye.js | 10 | B | ✅ Yes |
| f1.js | 14 | C | ✅ Yes (consider refactor) |
| yt.js | 13 | C | ✅ Yes |
| chat.js | 15 | C | ✅ Yes |
| main.js | 1,417 lines | — | ✅ Yes (< 2,000) |
| renderer.js | 4,490 lines | — | ❌ Exceeds 2,000-line file rule (pre-existing; splitting is the known follow-up) |

*Template note: the code-review skill ships a Python style guide; its rules
were applied in spirit (naming, dead code, hygiene, complexity ranks) to this
JavaScript codebase, with idiomatic JS style retained where the letter of the
rule does not translate.*

---

## Final State

- All 🔴/🟠/🟡 findings fixed and re-verified against the running app.
- The single 🔵 finding is documented above as accepted debt.
- Validation chain: syntax checks on all touched files → full app relaunch →
  CDP-driven behavioral probes (lifecycle, backoff, user paths, CSP, fonts,
  console) — all green.
