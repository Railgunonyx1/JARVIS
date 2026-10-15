# JARVIS Orbit — UI Specification

**Status:** Matches implemented behavior (G13).  
**Product rule:** JARVIS Orbit is a real, recognizable Chromium browser that
happens to have JARVIS built in. The browser must remain fully usable when
JARVIS is offline.

## 1. Architecture boundary (non-negotiable)

Chromium owns the browser chrome and the web; JARVIS owns the agent layer.
The MV3 extension is the only JARVIS UI surface; it never replaces native
chrome.

```
Chromium (native chrome — tabs, omnibox, profile, extensions, menus)
    │  hosts the MV3 extension
    ▼
Extension surfaces (the agent layer)
├── Sidebar      — chat / task composer, status, quick actions, page context
├── New tab      — browser-home search-or-ask + agent actions
├── Service worker — bridge client (127.0.0.1:8170), status loop, chat stream
└── Content      — page context capture (untrusted web content stays data)
    │
    ▼
JARVIS bridge → ToolExecutionService → orbit.* tools → BrowserController → CDP
```

Surfaces from the product design contract fall into three buckets:

| Bucket | Surfaces | Owner |
|--------|----------|-------|
| Native chrome (kept as Chromium ships it) | tab bar/groups, omnibox + dropdown, bookmark bar, extension button + dropdown, profile button + dropdown, three-dot menu, downloads/history/bookmarks pages, private browsing, page context menu | Chromium |
| Agent layer (implemented in the extension) | sidebar, page-context bar, quick actions, new tab, status/agent-state strip, bridge settings | this repo |
| Not yet surfaced (documented contract, needs a consumer event first) | inline approval modal, agents/tasks/memory views, first-run onboarding steps | this repo (scaffolded) |

Deliberate: no reimplementation of omnibox/flyout/profile dropdown. "Keep the
browser recognizable as a normal Chromium browser" (locked decision 2A).

## 2. Design tokens

Single source: `extensions/jbrowser/src/lib/tokens.css`.

- Neutral surfaces; **blue** is the JARVIS accent (`--jb-accent`).
- Dark by default; light flips via `prefers-color-scheme`.
- 8px spacing scale, 6–14px radius scale, shared type scale
  (`--jb-font-ui`, sizes `--jb-text-xs`…`--jb-text-2xl`).
- Semantic status colors: success / warning / danger / info, each with a
  muted background pair used by pills and state strips.

## 3. Sidebar (agent layer core)

`extensions/jbrowser/src/sidebar/`

| Region | Behavior |
|--------|----------|
| Header | logo mark + **JARVIS** title + status pill (`online`/`offline`/`reconnecting` dot), clear + bridge-settings actions |
| Agent-state strip | hidden unless the kernel reports an agent state: `waiting_browser` (amber), `approval` (blue), `error` (red) — each with an action button that re-probes `/status` |
| Page-context bar | current tab title + URL (mono), **Listening** toggle |
| Thread | conversation with roles (`user`/`jarvis`), error styling, empty-state welcome |
| Empty state | quick-action chips — Summarize / Explain / Research / Extract / Remember — that prefill + send |
| Composer | auto-grow textarea; `Ctrl+Enter` (or the ➤ button) sends |
| Settings | optional bearer token for the bridge (`--auth` mode) |

Status wiring: the pill reflects `GET /status` `{ok, kernel}` broadcast as
`STATUS_UPDATE`; agent-layer states ride along on the same payload
(`payload.agent = {state, text}`) — absent, the strip stays hidden and the
UI keeps the plain conversation model, so older bridges never break the UI.

## 4. New tab

`extensions/jbrowser/src/newtab/`

Browser-home feel: top brand row with status, centered greeting, one
search-or-ask field (`Enter` sends through the bridge), agent-action chips,
an **Open JARVIS sidebar** affordance, and a muted footer. The in-page
conversation appears only after the first ask, keeping the idle tab calm.

## 5. Status language

| Visual | Meaning |
|--------|---------|
| Green dot (pill) | `ok:true`, kernel online |
| Red dot | bridge offline — browsing continues, JARVIS paused |
| Amber pulsing dot | reconnecting / waiting for browser |
| Amber strip `waiting_browser` | agent paused on a browser crash; Retry re-probes |
| Blue strip `approval` | agent awaits operator consent for a consequential step |
| Red strip `error` | bridge/kernel error state |

## 6. Component states

Every interactive component carries default / hover / focus-visible (ring) /
disabled styling from tokens. Destructive text (danger) and consent
(approval) use the muted semantic backgrounds so intent reads at a glance
without being alarmist for routine actions.

## 7. Design contract (Figma)

The full product design contract — every surface and state matrix (extension
dropdown, profile dropdown, menus, downloads/history/bookmarks, import
wizard, first run, error/empty/loading states, dark + light) — is tracked as
the canonical UI reference for this feature. Implementation order follows the
buckets above: the agent layer first, native chrome never.
