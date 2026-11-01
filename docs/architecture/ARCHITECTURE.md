# JARVIS Dynamic Island — Phase 0 Architecture

Status: Phase 0 draft, for council review
Branch: `dynamic-island`
Baseline commit: `b1f5051`
Scope: architecture documentation and planning only
Real repository: not modified here
Guidance source: `tmp/dynamic-island-council/FULL-REPOSITORY-COUCIL-AUDIT.md`

## 1. Purpose

This document records the Phase 0 architecture for the JARVIS Dynamic Island effort on the `dynamic-island` branch.

It does **not** implement the UI. It does **not** rewrite application runtime code. It establishes:
- product direction
- process ownership
- IPC and event flow
- startup and shutdown boundaries
- error handling posture
- frontend/backend responsibilities
- which existing Rust components should be retained, adapted, deprecated, or removed
- testable acceptance criteria for the first working QML Dynamic Island
- unresolved technical decisions that still need approval

This document exists so the next implementation phase starts from agreed boundaries instead of another prototype.

## 2. Product direction

The council audit concluded that the current branch is drifting between incompatible architectures. The strongest near-term product direction is:

| Concern | Decision |
| --- | --- |
| Frontend | Qt Quick / QML |
| Backend | Python |
| Native performance modules | Rust, only when justified |
| Desktop target | KDE Wayland on Bazzite |
| Activation | Explicit button/interaction |
| UI type | Minimal Dynamic Island |
| GTK4 | Superseded for the planned product direction unless deliberately changed |

This is a deliberate pivot away from the current Rust/GTK prototype. The Rust workspace still exists, but it is now treated as a limited experiment and possible source of future native components, not as the application foundation.

## 3. Process ownership

### 3.1 High-level ownership

| Responsibility | Owner |
| --- | --- |
| Application logic, state, services, agent integration | Python |
| Presentation, input, transitions, desktop anchoring | Qt Quick / QML |
| Performance-critical native work | Rust, only if justified later |
| Platform integration | KDE Wayland first |

### 3.2 Runtime model

The application should be split into at least two cooperating processes:

| Process | Role |
| --- | --- |
| Backend process | Python runtime owns application state, services, and JARVIS capability integration. It is the source of truth for app behavior. |
| Frontend process | Qt Quick / QML owns the visible island, input handling, and presentation state. It renders and forwards user intent. |

This separation is chosen so:
- the frontend can be small and focused on presentation,
- the backend can own the application lifecycle,
- shutdown, restart, and recovery can be reasoned about per process.

### 3.3 Ownership rules

- The backend owns application truth.
- The frontend owns presentation state that is derived from the backend.
- The frontend must not become a second application kernel.
- Rust may own a narrow native component only if it is justified by performance, platform access, or reuse.

## 4. IPC and event flow

### 4.1 Communication direction

The first working island should use one clear bidirectional IPC boundary between Python and QML:
- backend to frontend for state and notifications,
- frontend to backend for user actions and queries.

### 4.2 Event flow principles

- One primary event/state transport should be defined early.
- The frontend should not maintain independent copies of application state unless there is a concrete rendering reason.
- Notifications should be bounded and deliberate, not unbounded firehose channels.
- The IPC boundary should be explicit about thread ownership so UI updates happen on the Qt main thread.

### 4.3 Rejected complexity for Phase 0

Do **not** introduce:
- multiple queues for the same event stream,
- duplicated event types in each layer without a clear owner,
- a generic message-bus architecture for a small desktop overlay,
- background wake-word activation.

## 5. Startup and shutdown

### 5.1 Startup

A minimal startup sequence should be:

1. Backend process starts and initializes application services.
2. Frontend launches and connects to the backend IPC.
3. Backend publishes initial visible state.
4. Frontend renders the collapsed island.
5. Application waits for explicit user interaction.

The first milestone is successful if the island can start, show a stable initial state, and wait for interaction without hanging.

### 5.2 Shutdown

Shutdown must be deterministic.

The council audit identified a concrete shutdown concern in the current Rust prototype: the app can wait indefinitely because the notification forwarding task, the core sender, and the UI receiver are not owned by one coherent shutdown owner.

The QML/Python architecture should avoid that by defining:
- who starts shutdown,
- who closes IPC,
- who stops background work,
- which process exits first,
- how repeated start/stop cycles are cleaned up.

### 5.3 Acceptable shutdown behavior

For Phase 1 acceptance, the application must demonstrate:
- clean shutdown from a running state,
- clean shutdown from an idle state,
- no hanging wait on IPC or event tasks,
- no leftover background tasks after exit,
- repeatable start/stop without accumulating state.

## 6. Error handling

### 6.1 Backend errors

The backend should:
- classify errors as transient, retryable, or fatal,
- never expose raw internal details to the frontend unless they are intentionally part of the UI contract,
- convert internal failures into frontend-visible status states.

### 6.2 Frontend errors

The frontend should:
- degrade gracefully when the backend is unavailable,
- make connection loss visible,
- avoid assuming the backend is always present during development.

### 6.3 IPC errors

The IPC layer should define:
- what happens when a message is dropped,
- what happens when the peer disappears,
- how reconnection or restart is handled, if reconnection is supported at all in the first milestone.

For the first milestone, reconnect behavior can be simple. It must still be deliberate.

## 7. Frontend and backend responsibilities

### 7.1 Backend responsibilities

- Application state and command handling.
- JARVIS capability integration, where applicable.
- Notification/content preparation.
- Lifecycle control.
- Error classification and recovery policy.

### 7.2 Frontend responsibilities

- Rendering collapsed/expanded states.
- Input handling.
- Animation and transition styling.
- Desktop anchoring and presentation behavior.
- Translating user actions into backend requests.

### 7.3 Shared responsibilities to assign explicitly

- Which layer defines the canonical state shape.
- Which layer converts internal events into UI-visible notifications.
- Which layer decides visibility, expansion, and mode changes.
- Which layer owns retry/backpressure policy for events.

These should not be left implicit.

## 8. What Rust is for

Rust is allowed in this architecture, but only under constraints.

### 8.1 Acceptable Rust usage

Rust may be used for:
- a performance-critical native component,
- a platform-specific integration that is awkward in Python,
- a small self-contained service if it improves startup, latency, or resource usage materially.

### 8.2 Inappropriate Rust usage for now

Rust should **not** be used yet to:
- reimplement the application backend,
- recreate the agent kernel,
- host the entire Dynamic Island lifecycle as a GTK application,
- justify a third crate workspace without a concrete reason.

### 8.3 Decision rule

If a Rust component is proposed, it must answer:
- what concrete problem it solves,
- why Python/Qt cannot solve that problem adequately,
- what IPC boundary it introduces,
- how it changes startup, shutdown, and testing.

If the answer is weak, the component stays out of scope.

## 9. Existing Rust components: retain, adapt, deprecate, remove

This section is a Phase 0 disposition of the current `dynamic-island` Rust workspace against the Qt/Python direction.

### 9.1 Workspace split

| Current component | Disposition | Reason |
| --- | --- | --- |
| `jarvis-core` | Adapt, then reassess | Good event concepts, but currently too abstract and not aligned with the Qt/Python backend. Retain useful event definitions and lifecycle ideas; do not expand it into a competing application backend. |
| `jarvis-ui` | Adapt or replace | The GTK-specific implementation is not the planned frontend. Keep the idea of a UI trait/lifecycle seam only if it helps the Qt frontend; otherwise replace it with the Qt-appropriate boundary. |
| `jarvis-island` | Adapt | Retain the entrypoint/lifecycle concept, but redesign it around the actual Qt/Python runtime instead of the current Rust-only main. |

### 9.2 Specific types

| Current type/area | Disposition | Reason |
| --- | --- | --- |
| `AppState` concept | Retain concept, consolidate duplication | The idea of visible/expanded/mode/message/error is useful. The current duplication between crates should be reduced. |
| `AppNotification` concept | Retain concept, consolidate duplication | Event-driven notification is reasonable. The exact shape must be owned by one layer. |
| `IslandRunner` trait | Reassess | Do not preserve it automatically. Reassess against the Qt application lifecycle. |
| GTK placeholder runner | Deprecate for product direction | Not the planned frontend. |
| Stub runner | Deprecate as “application runtime” | Useful only as a compile-time test seam, not as a real lifecycle model. |
| Tokio unbounded core channel | Remove as the primary IPC design | Unbounded without backpressure is not a good foundation for a real IPC/event path. |
| `cfg!(feature = "gtk4")` runtime selection | Remove from committed source | Decision record rejects it, but the current source still uses it. |
| `tokio = { features = ["full"] }` | Adapt | Narrow to required features once the runtime choice is settled. |
| `ctrlc` without handler | Adapt or remove | Declared but unused for shutdown; either implement shutdown or remove the dependency. |

### 9.3 Metadata and packaging concerns to fix before release

- `repository` metadata is not a proper repository URL.
- `LICENSE` file is missing while metadata says MIT; the actual licensing policy must be resolved.
- A `Cargo.lock` should be committed for this application workspace.
- Declared but unused dependencies should be removed or justified.

## 10. Conflicts with existing source code

The current committed source does not match the council’s preferred architecture.

### 10.1 Documented decision vs actual code

| Documented preference | Current committed reality |
| --- | --- |
| Compile-time backend selection | `apps/jarvis-island/src/main.rs` currently uses `cfg!(feature = "gtk4")` in a runtime `match` |
| Qt Quick / Python product direction | The branch still structures itself around a Rust/GTK prototype |
| Unified lifecycle ownership | The current Rust entrypoint splits work across Tokio runtime, core, forwarding task, and UI runner without one clear shutdown owner |
| No unbounded notification firehose as the final design | `jarvis-core` currently sends into an unbounded Tokio channel |
| Single canonical state/event model | `jarvis-ui` currently mirrors `jarvis-core` types |

These are Phase 0 conflicts to resolve, not reasons to hide the current state.

## 11. Unresolved technical decisions

These are not invented answers. They are explicitly open.

### 11.1 Frontend/backend boundary

- Exactly which IPC mechanism will connect Python and QML in the first milestone?
- Will the first milestone use a local socket, pipes, D-Bus, or another bridge?
- Will the frontend be a separate process, or an in-process Qt application with a Python worker?

### 11.2 State ownership

- Which layer owns the canonical `AppState` for the QML island?
- Does the frontend keep a local mirror, or render directly from backend state?

### 11.3 Event delivery

- Should backend-to-frontend updates be push-based, pull-based, or hybrid?
- If push-based, how are drops, backlog, and bounded queues handled?
- If Qt Quick is the frontend, how are UI updates guaranteed to run on the Qt main thread?

### 11.4 Lifecycle model

- Who initiates shutdown: frontend, backend, or both?
- What is the shutdown order?
- What happens if one side exits before the other?
- Should the first milestone support restart/reconnect, or is clean exit enough?

### 11.5 Desktop integration

- Will the island be an X11-compatible window, a Wayland layer-shell surface, or both?
- Is top-center positioning a window manager rule, a compositor feature, or a client-side implementation?
- Do we need a minimal non-overlay window first before layer-shell anchoring?

### 11.6 Rust scope

- Is any current Rust crate worth keeping as a future native component?
- If yes, what is the narrow responsibility and IPC contract?
- If no, do we retire the workspace later or merely stop investing in it?

### 11.7 Licensing and packaging

- Is the project truly MIT, or is the intended policy different?
- What is the correct repository URL metadata?
- Which dependencies are truly required for the first working milestone?

## 12. Testable acceptance criteria

### 12.1 Phase 0 acceptance criteria

These are documentation and planning gates, not UI gates.

- The Phase 0 architecture documents exist and are internally consistent.
- The document records the frontend/backend/Rust decisions explicitly.
- The document identifies current source conflicts.
- The document lists unresolved decisions instead of pretending they are solved.
- The document does not depend on the scratch patch being merged as-is.

### 12.2 First working QML Dynamic Island acceptance criteria

These are the smallest testable behaviors the next phase should target.

1. The application launches.
2. The island appears in a collapsed pill state.
3. The backend publishes at least one state update that the frontend renders.
4. The island can expand.
5. The island can collapse.
6. One interaction button is present and responds.
7. The frontend updates its visible state after a backend event.
8. The application shuts down cleanly without hanging.
9. Repeated start/stop cycles do not leave background tasks running.
10. The application behaves acceptably on KDE Wayland for the first milestone.

### 12.3 Explicitly out of scope for the first working island

- Voice input or output.
- Gesture recognition.
- AI model selection.
- Complex animations.
- Full JARVIS chat/agent UI.
- Multi-monitor anchoring that is not required for the first visible milestone.
- Layer-shell implementation unless the team deliberately chooses that before the basic window works.

## 13. Recommended Phase 1 implementation tasks

### 13.1 Must do first

- Freeze Phase 0 decisions in a reviewed document.
- Choose the first IPC mechanism between Python and QML.
- Define the canonical state/event contract.
- Define startup and shutdown ownership.
- Decide explicit thread-ownership rules for UI updates.
- Remove or quarantine designs that assume Rust/GTK is the product.

### 13.2 Then

- Build the smallest possible QML shell.
- Connect it to a minimal Python backend.
- Render collapsed/expanded state.
- Add one interaction button.
- Add basic show/hide behavior.
- Add lifecycle and shutdown tests.

### 13.3 Later

- Top-center positioning and desktop anchoring.
- Multi-monitor behavior.
- Display scaling.
- Transitions.
- KDE Wayland integration details.
- Real JARVIS capability integration.

## 14. Risks and dependencies

### 14.1 Risks

- Continuing to invest in the Rust/GTK path could waste effort if the Qt/Python direction is final.
- Duplicated state and notification types will drift if ownership is not assigned.
- An unbounded notification design can hide shutdown and backpressure problems until later.
- A weak IPC design will make shutdown, reconnection, and testing harder later.
- Leaving unresolved decisions implicit will make Phase 1 implementation slower and more contradictory.

### 14.2 Dependencies

- A Qt/QML development environment for the frontend.
- A Python runtime and IPC choices for the backend.
- Bazzite/KDE Wayland runtime behavior for validation.
- A decision on whether Rust is needed at all in the first working milestone.

## 15. Decision log for this phase

| Decision | Status |
| --- | --- |
| Frontend is Qt Quick / QML | Recorded as preferred direction |
| Backend is Python | Recorded as preferred direction |
| Rust is optional and narrow | Recorded as constraint |
| GTK4 is superseded for the planned direction | Recorded as supersession |
| Runtime `cfg!` backend selection is rejected | Recorded, with current source conflict noted |
| Unbounded notification channel is rejected as the final design | Recorded |
| Single canonical state/event model is required | Recorded |
| Shutdown must be deterministic and tested | Recorded |

## 16. Next review gate

Phase 0 is complete when:
- the architecture documents exist,
- the product direction is explicit,
- the IPC and lifecycle boundaries are defined,
- the unresolved decisions are enumerated,
- the current source conflicts are acknowledged,
- the next implementation tasks are prioritized.

Do not start Phase 1 implementation code until the council is satisfied that Phase 0 actually freezes the architecture.
