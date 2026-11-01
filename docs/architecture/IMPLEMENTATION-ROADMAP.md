# JARVIS Dynamic Island — Phase 0 Implementation Roadmap

Status: Phase 0 draft, for council review
Branch: `dynamic-island`
Baseline commit: `b1f5051`
Companion documents:
- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/DECISIONS.md`
- `docs/architecture/COMPONENT-BOUNDARIES.md`
Guidance source: `tmp/dynamic-island-council/FULL-REPOSITORY-COUCIL-AUDIT.md`

## 0. How to read this roadmap

This roadmap is ordered by dependency.

The rule is simple: do not jump ahead just because a later feature looks more interesting.

Before any UI code or application runtime rewrite, the council should agree that:
- the product direction is frozen,
- the IPC/lifecycle/state boundaries are defined,
- the existing Rust/GTK conflicts are acknowledged,
- the unresolved decisions are enumerated.

If that has not happened, the correct next step is still documentation and review, not implementation.

## 1. Phase 0 — Architecture freeze

Priority: P0
Type: documentation + decision freeze
Blocking: yes

### Objective

Stop the branch from drifting between incompatible architectures.

### Tasks

- Confirm Qt Quick / QML frontend and Python backend as the preferred direction.
- Confirm KDE Wayland on Bazzite as the first desktop target.
- Confirm explicit interaction activation.
- Confirm minimal Dynamic Island scope.
- Confirm GTK4 is superseded for the planned direction.
- Record Rust as optional and narrow.
- Record that runtime `cfg!(feature = "gtk4")` backend selection is rejected.
- Record that unbounded notification channels are rejected as the final design.
- Record that duplicated state/event types should be reduced.

### Deliverables

- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/DECISIONS.md`
- `docs/architecture/COMPONENT-BOUNDARIES.md`
- `docs/architecture/IMPLEMENTATION-ROADMAP.md`
- A short list of unresolved decisions and conflicts.

### Exit criteria

- The architecture documents exist and are internally consistent.
- The preferred frontend/backend/Rust decisions are explicit.
- The current source conflicts are acknowledged.
- The unresolved items are listed instead of invented away.

### Stop rule

If the council is not satisfied with Phase 0, do not start Phase 1 code.

## 2. Phase 1 — Lifecycle and smallest working island

Priority: P0
Type: implementation
Blocking: for first working milestone

### Objective

Make startup, event handling, and shutdown deterministic, and produce the smallest possible working Dynamic Island.

This phase starts only after Phase 0 is reviewed.

### 1.1 Lifecycle and IPC foundation

Tasks:
- Choose the first IPC mechanism between Python and QML.
- Define the canonical state/event contract.
- Define who owns startup and shutdown.
- Define how UI updates are dispatched to the Qt main thread.
- Define disconnect/unavailable behavior.

Testable requirements:
- Backend can start and stop cleanly.
- Frontend can start and connect.
- A backend state update reaches the frontend.
- A frontend action reaches the backend.
- Clean shutdown does not hang.
- Repeated start/stop cycles are safe.

### 1.2 Smallest working QML island

Tasks:
- Build the minimal QML shell.
- Render a collapsed pill.
- Render an expanded pill.
- Show one status indicator.
- Show one message area.
- Add one interaction button.
- Implement basic show/hide behavior.

Testable requirements:
- Application launches.
- Island appears collapsed.
- Island can expand.
- Island can collapse.
- One interaction button responds.
- UI updates after a backend state change.
- Application shuts down cleanly.
- No excessive idle resource behavior in the first milestone.

### 1.3 Lifecycle tests

Tasks:
- Add automated tests for startup.
- Add automated tests for event delivery.
- Add automated tests for state update rendering.
- Add automated tests for clean shutdown.
- Add automated tests for repeated start/stop.

Acceptance:
- The application can start, process an event, and stop without hanging.
- The application can repeat start/stop without leaving background work running.

### Exit criteria

- Smallest working island exists.
- Lifecycle is deterministic and tested.
- No new feature work is started before these pass.

## 3. Phase 2 — Desktop integration

Priority: P1
Type: implementation
Blocking: for usable desktop behavior

### Objective

Make the frontend behave like a native desktop component.

### Tasks

- Top-center positioning.
- Window stacking and focus behavior.
- Basic multi-monitor behavior.
- Display scaling considerations.
- Show/hide transitions.
- KDE Wayland compatibility checks.
- Startup and clean exit on the target environment.

### Exit criteria

- The island behaves reliably across normal desktop usage for the first milestone.
- Positioning and focus are acceptable on the target environment.
- Basic transitions are acceptable.

### Notes

- Do not assume a specific Wayland anchoring approach before validating the basic window behavior.
- If layer-shell is desired, it should be evaluated after the basic frontend is working.

## 4. Phase 3 — Connect JARVIS capabilities

Priority: P2
Type: integration
Blocking: later

### Objective

Connect the working island to actual JARVIS functionality.

### Tasks

- Python runtime integration with the island.
- AI response state, where applicable.
- Voice input/output, if the team chooses it.
- Processing and error states.
- Gesture interaction only if needed.
- Explicit button-based activation.

### Exit criteria

- The island can initiate and display a real JARVIS interaction.
- Error and processing states are visible and testable.

### Notes

- Voice, gestures, and AI model selection are optional and later if at all.
- This phase should not be started before lifecycle and desktop integration are sound.

## 5. Phase 4 — Optimization and release

Priority: P2
Type: hardening
Blocking: later

### Tasks

- Measure idle CPU and RAM.
- Measure startup latency.
- Profile animation performance.
- Remove unnecessary dependencies.
- Add automated tests and CI.
- Verify packaging and desktop integration.
- Resolve licensing and metadata before release.

### Exit criteria

- Stable, lightweight daily-use behavior for the target environment.
- Release metadata and licensing are consistent.

## 6. Rejected implementation detours

These should not be treated as upcoming phases:

- Building the GTK overlay.
- Rewriting the application backend in Rust.
- Reimplementing the agent kernel in Rust.
- Adding voice/gesture/AI features before the island can start, show state, and shut down cleanly.
- Adding complex animations or full dashboard UI before the minimal island works.

If any of these reappear, they must be justified against the Phase 0 decisions, not assumed.

## 7. Current implementation blockers

These are the concrete blockers before the next working milestone:

- Phase 0 decisions not yet frozen for implementation.
- IPC mechanism not chosen.
- Lifecycle ownership not fully defined for the Qt/Python architecture.
- State/event contract ownership not assigned.
- Current Rust source still contains the rejected runtime `cfg!` backend selection pattern.
- Current Rust workspace still shaped around a GTK prototype.

## 8. Testing requirements by phase

### Phase 0

- Documented consistency checks.
- Conflict and unresolved-item review.

### Phase 1

- Startup tests.
- Event-delivery tests.
- State-update rendering tests.
- Shutdown tests.
- Repeated start/stop tests.

### Phase 2

- Positioning tests.
- Focus behavior tests.
- Basic show/hide tests.
- Target-environment smoke tests on KDE Wayland.

### Phase 3

- Integration tests for real JARVIS capabilities.
- Error/processing state tests.

### Phase 4

- Resource and latency measurements.
- Packaging and metadata verification.

## 9. Recommended immediate work order

1. Review Phase 0 documents.
2. Approve or amend the frozen decisions.
3. Resolve or explicitly keep open the unresolved items.
4. Choose the first IPC mechanism.
5. Define startup/shutdown ownership.
6. Implement the smallest working QML island with lifecycle tests.
7. Only after that, move to desktop integration.

## 10. Milestone definition

The first meaningful milestone is:

A minimal QML Dynamic Island that launches on KDE Wayland, receives a state update from Python, responds to user interaction, and shuts down cleanly.

That milestone is the first proof that the architecture is sound. It is not the end of the project.

## 11. Stop rule

If Phase 0 is not reviewed and approved, do not implement Phase 1.

If Phase 1 lifecycle tests are not passing, do not start Phase 2 desktop integration.

If the smallest working island cannot start, show state, respond to interaction, and shut down cleanly, do not expand scope.
