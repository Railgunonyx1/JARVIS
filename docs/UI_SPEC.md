# JARVIS MK-X Terminal Specification

**Status:** Locked architecture  
**Canvas:** Windows Terminal + PowerShell 7  
**UI layer:** Rich  
**Rule:** Backend owns state & decisions. Renderer only displays snapshots.

---

## 1. Architecture boundary (non-negotiable)

```
JARVIS Core
    │
Event / State Bus
    │
┌───┴───┬───────┬────────┐
│ Agent │ Tools │ Memory │
└───┬───┴───────┴────────┘
    │
WS / Events
    │
Terminal Renderer (Rich)
    │
Windows Terminal
```

Renderer components:

```
Renderer
├── StatusBar          (collapses by width)
├── Conversation
├── Plan               (stateful snapshot)
├── Activity           (live AgentEvent stream)
├── Input
├── CodeView           (workspace)
├── MemoryView         (workspace)
├── AuditView          (workspace)
├── ConfirmationView   (policy-backed modal)
└── CommandPalette
```

The renderer never decides. The agent never knows how pixels are drawn.

---

## 2. Responsive breakpoints

| Width   | Layout                                      |
|---------|---------------------------------------------|
| ≥ 120   | PLAN + CONVERSATION + ACTIVITY              |
| 90–119  | PLAN + CONVERSATION                         |
| < 70    | CONVERSATION only                           |

Always present: **Status bar** (top) and **Input** (bottom).

Workspaces (`code`, `memory`, `audit`) replace the content area on demand; they are not permanent panels.

---

## 3. Status bar field priority

| Width   | Fields shown                                                |
|---------|-------------------------------------------------------------|
| ≥ 120   | JARVIS · MODE · model · tokens · N TOOL · MEMORY · ONLINE · time |
| 90–119  | JARVIS · MODE · model · tokens · ONLINE · time              |
| < 70    | JARVIS · MODE · tokens · ONLINE                             |

---

## 4. Execution modes (real policies)

| Mode        | Behavior                                              |
|-------------|-------------------------------------------------------|
| AGENT       | Full autonomous execution                             |
| PLAN        | Analyze + build/update plan only; no side effects     |
| CONTROLLED  | Ask before any consequential action                   |
| SMART       | Dynamically choose autonomy from risk + context       |

Enforced by the core policy layer, not by the prompt string.

Prompt always shows: `JARVIS [MODE]>`

---

## 5. Plan model (backend-owned)

```
Plan
├── id
├── goal
├── steps[]
│    ├── id
│    ├── description
│    ├── status          # pending | active | completed | failed | skipped
│    ├── started_at
│    ├── completed_at
│    └── related_event_ids[]
└── revision
```

UI symbols: `✓` completed · `→` active · `○` pending · `✗` failed

The agent may rewrite the plan at any time. The UI only re-renders the current snapshot.

---

## 6. Activity = live structured event stream

```
AgentEvent
├── event_id
├── timestamp
├── type                 # tool | planner | system | memory | security | provider
├── status               # running | completed | failed | pending | cancelled
├── tool
├── arguments
├── result
├── duration_s
├── parent_run_id
├── exit_code
└── full_output          # collapsible
```

Rendered compactly:

```
● repo.search
  authentication
  8 results

✓ filesystem.read
  security/auth.py
  2.1 KB

● shell.execute
  pytest tests/test_auth.py
```

---

## 7. Security confirmation (mandatory)

Never a bare `Allow? [y/N]`. Always structured:

```
┌ SECURITY CONFIRMATION ──────────────────────┐
│ JARVIS wants to execute:                    │
│   package.remove("example")                 │
│ Risk: HIGH                                  │
│ Scope: system package                       │
│ Reversible: NO                              │
│ Allow once?     [y]                         │
│ Allow this run? [r]                         │
│ Deny            [n]                         │
└─────────────────────────────────────────────┘
```

Returns `once` | `run` | `deny` to the security/policy layer.  
UI never bypasses SecurityEngine / PermissionManager / Sandbox.

---

## 8. Workspaces (on-demand)

Command palette (`/palette` or conceptual Ctrl+K):

```
chat | plan | code | activity | memory | audit
```

Suggested bindings (when terminal supports them):

- Ctrl+1 Chat  
- Ctrl+2 Plan  
- Ctrl+3 Code  
- Ctrl+4 Activity  
- Ctrl+5 Memory  
- Ctrl+6 Audit  

### Code
File tree + focused buffer, modification markers, LOC. Conversation remains available; this is a workspace, not a replacement editor.

### Memory
Query + ranked hits (score, title, date, snippet) + optional pipeline visualization.

### Audit
Health sections: SYSTEM, TESTS, PERFORMANCE, SECURITY. Real data only — no invented metrics.

---

## 9. Keyboard map (terminal-safe)

| Key / command     | Action                                      |
|-------------------|---------------------------------------------|
| Up / Down         | History                                     |
| Ctrl+C            | Interrupt agent/tool (never stolen for UI)  |
| Ctrl+L            | Redraw (via /clear + re-render)             |
| /palette          | Command palette                             |
| /mode <name>      | Set execution policy                        |
| /workspace <name> | Switch workspace                            |
| /layout <name>    | Force layout mode                           |
| /status           | Current state                               |
| /exit             | Quit                                        |

If a shortcut conflicts with Windows Terminal, the `/command` form is the fallback.

---

## 10. Input & history

- Interactive (tty): Windows `msvcrt` path when available
- Non-tty / pipes: **must** use `sys.stdin.readline()` — never `msvcrt`
- History: `%USERPROFILE%\.jarvis\history`
  - max 1000 entries
  - no consecutive duplicates
  - ignore empty lines
  - filter obvious secrets (`api_key=`, `token=`, `password=`, `bearer`, …)

---

## 11. Error style

```
✗ Provider unavailable
  Gemini did not respond.
  Trying the configured fallback provider…

✓ Switched to OpenRouter
```

Technical details available on request; default is human-readable.

---

## 12. Implementation modules

```
cli/
  models.py      Plan, AgentEvent, ConfirmationRequest, AppState, Mode
  renderer.py    Pure display — status, plan, activity, workspaces, confirm
  layout.py      Responsive LayoutManager + workspace modes
  input.py       Windows-aware + pipe-safe
  history.py     Secret-filtered history
  theme.py       Professional, low-noise palette
  commands.py    Real commands + palette
  main.py        Entry + REPL
```

---

## 13. Non-goals

- React / Electron / Tauri / Flask / web dashboard
- Fake CPU / RAM / GPU telemetry
- Animated cyberpunk effects
- Agent logic inside the renderer
- Permanent multi-panel clutter on small terminals

---

**The functioning agent is the product.  
The terminal UI exists to make that process clear and controllable.**
