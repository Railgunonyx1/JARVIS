# JARVIS Dynamic Island — Phase 0 Component Boundaries

Status: Phase 0 draft, for council review
Branch: `dynamic-island`
Baseline commit: `b1f5051`
Companion documents:
- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/DECISIONS.md`
- `docs/architecture/IMPLEMENTATION-ROADMAP.md`
Guidance source: `tmp/dynamic-island-council/FULL-REPOSITORY-COUCIL-AUDIT.md`

## 1. Boundary overview

The Phase 0 architecture divides the Dynamic Island into these main components:

- Python backend
- Qt Quick / QML frontend
- IPC boundary
- event/state contract boundary
- lifecycle and shutdown boundary
- error-handling boundary
- desktop/integration boundary
- optional narrow Rust boundary

Each boundary below states:
- owner
- responsibilities
- inputs
- outputs
- process/thread posture
- in scope for the first working milestone
- out of scope for the first working milestone
- unresolved items
- test expectations

## 2. Python backend

### 2.1 Purpose

The backend is the application's source of truth.

### 2.2 Owner

Python process.

### 2.3 Responsibilities

- Application state and command handling.
- JARVIS capability integration where applicable.
- Preparing content and status for the frontend.
- Lifecycle control for the application side.
- Classifying errors and converting them into frontend-visible status.

### 2.4 Inputs

- IPC commands and user actions from the frontend.
- Internal events from services or capability modules, if any.
- Startup/shutdown signals from the platform or wrapper.

### 2.5 Outputs

- State updates.
- Notification/content payloads.
- Error and status information presented through the IPC boundary.

### 2.6 Process/thread posture

- Owns its own runtime and service initialization.
- Should not assume the frontend is always present.
- Should be able to start, run, and stop independently of presentation details.

### 2.7 In scope for the first working milestone

- Starting and stopping cleanly.
- Publishing at least one initial state update.
- Responding to at least one user interaction forwarded from the frontend.
- Reporting an obvious status change.

### 2.8 Out of scope for the first working milestone

- Full JARVIS agent UI.
- Voice I/O.
- AI model selection.
- Complex background services not needed for the minimal island.

### 2.9 Unresolved

- Exact IPC mechanism.
- Whether the backend is a separate process or embedded worker.
- Which state shape is canonical.

### 2.10 Test expectations

- Can start.
- Can stop.
- Can receive a forwarded action.
- Can publish a state update.
- Does not leave undefined background work after stop.

## 3. Qt Quick / QML frontend

### 3.1 Purpose

The frontend renders the Dynamic Island and forwards user intent.

### 3.2 Owner

Qt Quick / QML process or UI thread.

### 3.3 Responsibilities

- Rendering collapsed and expanded states.
- Showing status and message content.
- Handling user input and interaction buttons.
- Managing show/hide and expand/collapse presentation.
- Forwarding user actions to the backend.
- Updating UI on the Qt main thread.

### 3.4 Inputs

- Backend state and notification payloads.
- User input and interaction events.
- Startup/shutdown/lifecycle signals.

### 3.5 Outputs

- Visual presentation.
- User action requests sent to the backend.
- Lifecycle status back to the backend if needed.

### 3.6 Process/thread posture

- UI work belongs on the Qt main thread.
- Presentation state may be derived from backend state.
- The frontend may keep a small local presentation cache if needed, but it should not become a second application kernel.

### 3.7 In scope for the first working milestone

- Collapsed pill.
- Expanded pill.
- One status indicator.
- One message area.
- One interaction button.
- Basic show/hide behavior.

### 3.8 Out of scope for the first working milestone

- Voice.
- Gestures.
- AI model selection.
- Complex animations.
- Full agent/chat UI.
- Multi-monitor anchoring beyond what is necessary for the first visible milestone.

### 3.9 Unresolved

- Whether the frontend is a separate process or in-process.
- Exact animation policy.
- Exact input routing policy beyond the first button.

### 3.10 Test expectations

- Renders initial state.
- Updates when backend state changes.
- Responds to a user action.
- Does not assume backend is always present.
- Exits cleanly.

## 4. IPC boundary

### 4.1 Purpose

The IPC boundary connects the Python backend and the Qt Quick / QML frontend.

### 4.2 Owner

Shared contract between backend and frontend.

### 4.3 Responsibilities

- Transporting state and notifications.
- Transporting user actions from frontend to backend.
- Defining message ordering and delivery expectations.
- Defining what happens on disconnect.

### 4.4 Inputs

- Backend payloads.
- Frontend action requests.

### 4.5 Outputs

- Delivered messages in the receiving layer.
- Error/disconnect signals when transport fails.

### 4.6 Process/thread posture

- The IPC mechanism must make thread ownership explicit enough that UI updates remain on the Qt main thread.
- Backend-side dispatch must not force unsafe or undocumented thread transitions.

### 4.7 In scope for the first working milestone

- One reliable transport.
- A small message set sufficient for initial state and one interaction.
- Basic disconnect behavior.

### 4.8 Out of scope for the first working milestone

- Generic message-bus architecture.
- Multiplexed subsystems beyond what the island needs.
- Advanced reconnection strategies, unless simple reconnect is deliberately chosen.

### 4.9 Unresolved

- Transport mechanism.
- Message format.
- Retry/reconnect policy.

### 4.10 Test expectations

- A backend state update reaches the frontend.
- A frontend action reaches the backend.
- Disconnect is handled without undefined behavior.

## 5. Event/state contract boundary

### 5.1 Purpose

This boundary defines the meaning of the data exchanged, not the transport.

### 5.2 Owner

Shared contract, owned conceptually by the backend for truth and by the frontend for presentation usage.

### 5.3 Responsibilities

- Define canonical state fields.
- Define notification types.
- Define how errors become visible status.
- Prevent duplicate or drifting type definitions across layers.

### 5.4 Inputs

- Internal application events in the backend.
- User actions in the frontend.

### 5.5 Outputs

- Canonical state representation.
- Canonical notification representation.

### 5.6 Process/thread posture

- This boundary is about semantics, not threads.
- Threading is handled by the IPC and frontend rules.

### 5.7 In scope for the first working milestone

- Initial visible state.
- At least one status/mode concept.
- One user-facing action path.

### 5.8 Out of scope for the first working milestone

- Full event taxonomy for all future JARVIS capabilities.
- Complex history or session reconstruction.

### 5.9 Unresolved

- Canonical field set.
- Canonical notification set.
- Whether some UI-only fields live only in the frontend.

### 5.10 Test expectations

- Backend produces a known state shape.
- Frontend can interpret that shape.
- Both layers agree on meaning.

## 6. Lifecycle and shutdown boundary

### 6.1 Purpose

This boundary defines who starts, who stops, and what survives.

### 6.2 Owner

Shared, but one side should be the primary shutdown driver.

### 6.3 Responsibilities

- Define startup order.
- Define shutdown order.
- Define which owner closes IPC.
- Define what cleanup each side must do.
- Define what must not survive after exit.

### 6.4 Inputs

- User quit action.
- Platform/wrapper shutdown signals.
- Application-level stop requests.

### 6.5 Outputs

- Clean stop signals.
- IPC closure.
- Process exit.

### 6.6 Process/thread posture

- If there are two processes, the shutdown order must be explicit.
- If background work exists, it must be accounted for during shutdown.

### 6.7 In scope for the first working milestone

- Deterministic startup.
- Deterministic shutdown.
- No hanging wait on IPC or event tasks.
- No leftover background work after exit.

### 6.8 Out of scope for the first working milestone

- Complex crash-recovery choreography.

### 6.9 Unresolved

- Primary shutdown driver.
- Whether restart/reconnect is supported.
- Exact cleanup responsibilities.

### 6.10 Test expectations

- Application can quit cleanly from running state.
- Application can quit cleanly from idle state.
- Repeated start/stop cycles are safe.

## 7. Error-handling boundary

### 7.1 Purpose

This boundary defines how failures become visible and recoverable.

### 7.2 Owner

Shared: backend classifies, frontend presents.

### 7.3 Responsibilities

- Classify errors as transient, retryable, or fatal where applicable.
- Convert internal failures into frontend-visible status.
- Present connection loss or backend unavailability in the UI.
- Avoid leaking raw internal detail by default.

### 7.4 Inputs

- Internal failures.
- IPC failures.
- Platform or runtime failures.

### 7.5 Outputs

- Visible status/error states.
- Possible retry or stop decisions.

### 7.6 Process/thread posture

- Error classification lives in the backend unless another owner is justified.
- UI presentation of errors lives in the frontend.

### 7.7 In scope for the first working milestone

- Visible feedback for a simple error or unavailable-backend case.
- Graceful degradation when the backend is not reachable.

### 7.8 Out of scope for the first working milestone

- Full retry/backoff framework for every failure mode.
- Automatic self-healing across all subsystems.

### 7.9 Unresolved

- Which errors are transient vs fatal in the first milestone.
- Whether the frontend should retry connection automatically.

### 7.10 Test expectations

- Backend error produces a frontend-visible status.
- Frontend can show an unavailable-backend state.
- Error path does not hang the application.

## 8. Desktop/integration boundary

### 8.1 Purpose

This boundary covers how the island sits in the desktop environment.

### 8.2 Owner

Frontend plus platform integration concerns.

### 8.3 Responsibilities

- Window presentation and anchoring.
- Input focus behavior.
- Visibility behavior.
- Wayland/X11 considerations where relevant.
- Startup positioning and stacking behavior.

### 8.4 Inputs

- Platform display and compositor behavior.
- User interaction.
- Backend visibility/expand requests.

### 8.5 Outputs

- Placed window/surface.
- Visibility and stacking changes.
- Focus behavior.

### 8.6 Process/thread posture

- Presentation and platform integration belong with the frontend.
- Platform-specific options may need their own care if they affect lifecycle or startup.

### 8.7 In scope for the first working milestone

- Basic window/surface presentation.
- Top-center positioning for the first milestone on KDE Wayland.
- Basic show/hide behavior.
- Acceptable focus behavior.

### 8.8 Out of scope for the first working milestone

- Full layer-shell implementation before the basic window is validated.
- Full multi-monitor intelligence.
- Complex gestures and desktop-wide interaction.

### 8.9 Unresolved

- Exact anchoring approach.
- Whether X11 fallback is needed.
- Compositor-specific limitations.

### 8.10 Test expectations

- Island appears where intended for the first milestone.
- Show/hide works.
- Focus does not behave disruptively.
- Shutdown does not leave visible desktop artifacts.

## 9. Optional narrow Rust boundary

### 9.1 Purpose

Rust may be used only if it solves a concrete problem better than Python/Qt.

### 9.2 Owner

Future native component, if approved.

### 9.3 Responsibilities

- Perform a narrowly defined task.
- Provide a clear IPC or integration contract.
- Not expand into a general application backend.

### 9.4 Inputs

- Whatever is required for the narrow task.

### 9.5 Outputs

- Results or services consumed through a defined boundary.

### 9.6 Process/thread posture

- If used, it must declare its threading and shutdown behavior explicitly.

### 9.7 In scope for the first working milestone

- None required yet.

### 9.8 Out of scope for the first working milestone

- Rewriting the backend.
- Reimplementing the agent kernel.
- Hosting the whole Dynamic Island as a Rust/GTK application.

### 9.9 Unresolved

- Whether any Rust component is needed at all.
- If yes, what the component is and where it lives.

### 9.10 Test expectations

- If a Rust component is added, it must have a justified reason and a testable boundary.
- It must not reintroduce shutdown or threading ambiguity.

## 10. Summary of ownership

| Boundary | Primary owner | Secondary concern |
| --- | --- | --- |
| Application truth, services, JARVIS integration | Python backend | IPC contract |
| Presentation, input, transitions | Qt Quick / QML frontend | Desktop/integration |
| Transport | IPC boundary | Event/state contract |
| Meaning of data | Event/state contract | Backend truth |
| Startup/shutdown | Lifecycle boundary | Both processes |
| Visible failure handling | Error-handling boundary | Both layers |
| Platform anchoring | Desktop/integration boundary | Frontend |
| Optional native work | Narrow Rust boundary, if approved | IPC/lifecycle |

## 11. Test ownership summary

| Behavior | Where it should be verified |
| --- | --- |
| Backend starts and stops | Backend + lifecycle tests |
| Frontend renders and reacts | Frontend + IPC tests |
| State crosses the boundary | IPC + event/state tests |
| Shutdown is clean | Lifecycle + IPC tests |
| Errors are visible | Error-handling tests |
| Desktop behavior is acceptable | Desktop/integration tests |
| Rust component, if any, is justified | Rust component tests + architecture review |

## 12. Open boundary questions

- Is the first milestone one process or two?
- Is IPC synchronous or asynchronous for the first milestone?
- Is UI state purely derived, or is a small local mirror acceptable?
- Is top-center placement done via window manager, compositor, or client code?
- Is Rust needed at all before the first working island?

These are intentional open questions for Phase 0 review, not hidden assumptions.
